import uuid
import datetime
import copy
from typing import List, Tuple, Dict
from models import Item, Container
from packing_3d import Packer3D

VOLUME_TARGET_RATE = 80.0
WEIGHT_SOFT_LIMIT_RATE = 97.0

class VanningEngine:
    """
    バンニング計算コアエンジン（第3フェーズ：3D配置・時間軸操作対応版）
    """
    def __init__(self, strategy_mode: str = "full"):
        # 各コンテナの3D空間状態を管理するパッカー
        self.packers: Dict[str, Packer3D] = {}
        self.last_packing_strategy = ""
        self.strategy_mode = strategy_mode

    def _nearest_deadline(self, item: Item) -> datetime.date:
        deadlines = [item.due_date]
        if item.expiration_date:
            deadlines.append(item.expiration_date)
        return min(deadlines)

    def _density(self, item: Item) -> float:
        return item.weight / item.volume_m3 if item.volume_m3 > 0 else float('inf')

    def _footprint_m2(self, item: Item) -> float:
        return (item.length / 1000) * (item.width / 1000)

    def _violates_container_rules(self, container: Container, item: Item) -> bool:
        if item.separation_group:
            for existing in container.items:
                if existing.separation_group and existing.separation_group != item.separation_group:
                    return True
        return False

    def _can_pack(self, container: Container, item: Item) -> bool:
        """重量制約と3D座標での当たり判定（完全収容・底面接地率100%）"""
        # 1. 重量チェック
        if container.current_weight + item.weight > container.max_weight:
            return False

        if self._violates_container_rules(container, item):
            return False
            
        # 2. 3D配置判定（パズルの計算）
        if container.id not in self.packers:
            self.packers[container.id] = Packer3D(container)
            
        packer = self.packers[container.id]
        
        # packer.try_pack_item は、空間に空きがあれば座標(x,y,z)を確定させてTrueを返す
        return packer.try_pack_item(item)

    def _can_pack_without_mutation(self, container: Container, item: Item) -> bool:
        """候補評価用。3D空間やItem座標を変更せずに積載可否だけを見る。"""
        if container.current_weight + item.weight > container.max_weight:
            return False
        if self._violates_container_rules(container, item):
            return False

        packer = self.packers.get(container.id)
        probe_packer = copy.deepcopy(packer) if packer else self._build_probe_packer(container)
        if probe_packer is None:
            return False
        probe_item = copy.deepcopy(item)
        return probe_packer.try_pack_item(probe_item)

    def _build_probe_packer(self, container: Container):
        probe_container = copy.deepcopy(container)
        probe_packer = Packer3D(probe_container)
        for item in probe_container.items:
            item.x = item.y = item.z = None
            item.is_rotated = False
            if not probe_packer.try_pack_item(item):
                return None
        return probe_packer

    def explain_unfit_reason(self, container: Container, item: Item) -> str:
        projected_weight_rate = ((container.current_weight + item.weight) / container.max_weight) * 100 if container.max_weight > 0 else 0
        if container.current_weight + item.weight > container.max_weight:
            return "重量上限"
        if projected_weight_rate > WEIGHT_SOFT_LIMIT_RATE and container.fill_rate_volume < VOLUME_TARGET_RATE:
            return "重量ソフト上限"
        if not self._can_pack_without_mutation(container, item):
            return "3D配置"
        return "採用可能"

    def _container_fit_score(self, container: Container, item: Item):
        after_weight_rate = ((container.current_weight + item.weight) / container.max_weight) * 100 if container.max_weight > 0 else 0
        after_volume_rate = ((container.current_volume_m3 + item.volume_m3) / container.max_volume_m3) * 100 if container.max_volume_m3 > 0 else 0
        before_is_alert = container.fill_rate_volume < VOLUME_TARGET_RATE
        after_is_alert = after_volume_rate < VOLUME_TARGET_RATE
        clears_alert = before_is_alert and not after_is_alert
        overweight_near_limit = after_weight_rate >= WEIGHT_SOFT_LIMIT_RATE and after_volume_rate < VOLUME_TARGET_RATE
        weight_soft_penalty = max(0.0, after_weight_rate - WEIGHT_SOFT_LIMIT_RATE)

        return (
            0 if clears_alert else 1 if not after_is_alert else 2,
            max(0.0, VOLUME_TARGET_RATE - after_volume_rate),
            1 if overweight_near_limit else 0,
            weight_soft_penalty,
            -after_volume_rate,
            self._density(item),
            -after_weight_rate,
        )

    def _select_best_container(self, containers: List[Container], item: Item):
        candidates = [
            container
            for container in containers
            if self._can_pack_without_mutation(container, item)
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda container: self._container_fit_score(container, item))

    def _rebuild_packer(self, container: Container) -> bool:
        packer = Packer3D(container)
        for item in container.items:
            item.x = item.y = item.z = None
            item.is_rotated = False
            if not packer.try_pack_item(item):
                return False
        self.packers[container.id] = packer
        return True

    def _can_potentially_reach_volume_target(self, container: Container, forwardable_items: List[Item]) -> bool:
        available_volume_gain = 0.0
        remaining_weight = container.max_weight - container.current_weight
        for item in forwardable_items:
            if item.weight > remaining_weight:
                continue
            if self._violates_container_rules(container, item):
                continue
            available_volume_gain += (item.volume_m3 / container.max_volume_m3) * 100 if container.max_volume_m3 > 0 else 0
        return container.fill_rate_volume + available_volume_gain >= VOLUME_TARGET_RATE

    def _forwardable_metrics(self, container: Container, item: Item, current_date: datetime.date):
        nearest_deadline = self._nearest_deadline(item)
        days_until_deadline = (nearest_deadline - current_date).days

        volume_gap = max(0.0, VOLUME_TARGET_RATE - container.fill_rate_volume)
        weight_gap = max(0.0, VOLUME_TARGET_RATE - container.fill_rate_weight)
        volume_gain = (item.volume_m3 / container.max_volume_m3) * 100 if container.max_volume_m3 > 0 else 0
        weight_gain = (item.weight / container.max_weight) * 100 if container.max_weight > 0 else 0
        after_volume_rate = container.fill_rate_volume + volume_gain
        after_weight_rate = container.fill_rate_weight + weight_gain
        clears_alert = after_volume_rate >= VOLUME_TARGET_RATE
        balance_penalty = abs(volume_gap - volume_gain) + (0.5 * abs(weight_gap - weight_gain))
        density = item.weight / item.volume_m3 if item.volume_m3 > 0 else float('inf')
        density_focus = "体積補填" if volume_gap >= weight_gap else "重量補填"

        return {
            "nearest_deadline": nearest_deadline,
            "days_until_deadline": days_until_deadline,
            "volume_gap": volume_gap,
            "weight_gap": weight_gap,
            "volume_gain": volume_gain,
            "weight_gain": weight_gain,
            "after_volume_rate": after_volume_rate,
            "after_weight_rate": after_weight_rate,
            "clears_alert": clears_alert,
            "balance_penalty": balance_penalty,
            "density": density,
            "density_focus": density_focus,
        }

    def _forwardable_key(self, container: Container, item: Item, current_date: datetime.date):
        metrics = self._forwardable_metrics(container, item, current_date)

        # 赤字判定は体積80%基準。重量を増やしすぎず体積を埋められる荷物を優先する。
        density_preference = metrics["density"]
        return (
            not metrics["clears_alert"],
            max(0.0, VOLUME_TARGET_RATE - metrics["after_volume_rate"]),
            density_preference,
            -metrics["volume_gain"],
            metrics["balance_penalty"],
            metrics["days_until_deadline"],
            -item.priority,
            -item.volume_m3
        )

    def _forwardable_note(self, metrics, before_volume, before_weight, after_volume=None, after_weight=None):
        deadline_text = f"期限まで{metrics['days_until_deadline']}日"
        gain_text = f"体積+{metrics['volume_gain']:.1f}pt / 重量+{metrics['weight_gain']:.1f}pt"
        gap_text = f"不足(体積{metrics['volume_gap']:.1f}pt・重量{metrics['weight_gap']:.1f}pt)"
        fit_text = f"隙間適合度{metrics['balance_penalty']:.1f}"
        clear_text = "赤字解消見込み" if metrics["clears_alert"] else "赤字緩和"
        if after_volume is None or after_weight is None:
            return f"{deadline_text} / {clear_text} / {gain_text} / {gap_text} / {fit_text}"
        return (
            f"{deadline_text} / {clear_text} / {gain_text} / {gap_text} / {fit_text} / "
            f"充填率 体積{before_volume:.1f}->{after_volume:.1f}%・重量{before_weight:.1f}->{after_weight:.1f}%"
        )

    def _basic_sort_prefix(self, item: Item):
        return (
            not item.force_ship,
            -item.weight,
        )

    def _sort_key_volume_first(self, item: Item):
        nearest_deadline = self._nearest_deadline(item)
        return (
            *self._basic_sort_prefix(item),
            self._density(item),
            -item.volume_m3,
            -self._footprint_m2(item),
            nearest_deadline,
            -item.priority,
        )

    def _sort_key_deadline_first(self, item: Item):
        nearest_deadline = self._nearest_deadline(item)
        return (
            *self._basic_sort_prefix(item),
            nearest_deadline,
            -item.priority,
            self._density(item),
            -item.volume_m3,
            -self._footprint_m2(item),
        )

    def _sort_key_bulky_first(self, item: Item):
        nearest_deadline = self._nearest_deadline(item)
        return (
            *self._basic_sort_prefix(item),
            -item.volume_m3,
            -self._footprint_m2(item),
            self._density(item),
            nearest_deadline,
            -item.priority,
        )

    def _sort_key_weight_spread(self, item: Item):
        nearest_deadline = self._nearest_deadline(item)
        return (
            *self._basic_sort_prefix(item),
            -item.weight,
            self._density(item),
            -item.volume_m3,
            nearest_deadline,
            -item.priority,
        )

    def _sort_key_footprint_first(self, item: Item):
        nearest_deadline = self._nearest_deadline(item)
        return (
            *self._basic_sort_prefix(item),
            -self._footprint_m2(item),
            -item.volume_m3,
            self._density(item),
            nearest_deadline,
            -item.priority,
        )

    def _sort_key_tall_and_wide_first(self, item: Item):
        nearest_deadline = self._nearest_deadline(item)
        return (
            *self._basic_sort_prefix(item),
            -item.height,
            -self._footprint_m2(item),
            self._density(item),
            nearest_deadline,
            -item.volume_m3,
        )

    def _sort_key_deadline_footprint(self, item: Item):
        nearest_deadline = self._nearest_deadline(item)
        return (
            *self._basic_sort_prefix(item),
            nearest_deadline,
            -self._footprint_m2(item),
            -item.volume_m3,
            self._density(item),
            -item.priority,
        )

    def _packing_strategies(self):
        strategies = [
            ("volume_first", self._sort_key_volume_first),
            ("deadline_first", self._sort_key_deadline_first),
            ("bulky_first", self._sort_key_bulky_first),
            ("weight_spread", self._sort_key_weight_spread),
            ("footprint_first", self._sort_key_footprint_first),
            ("tall_and_wide_first", self._sort_key_tall_and_wide_first),
            ("deadline_footprint", self._sort_key_deadline_footprint),
        ]
        if self.strategy_mode == "fast":
            return [
                ("volume_first", self._sort_key_volume_first),
                ("deadline_first", self._sort_key_deadline_first),
                ("bulky_first", self._sort_key_bulky_first),
                ("footprint_first", self._sort_key_footprint_first),
            ]
        return strategies

    def _packing_result_score(self, containers: List[Container], unpacked_items: List[Item]):
        if not containers:
            return (len(unpacked_items), 0, 0, 0, 0, 0, 0)

        alert_count = sum(1 for c in containers if c.fill_rate_volume < VOLUME_TARGET_RATE)
        soft_weight_count = sum(1 for c in containers if c.fill_rate_weight >= WEIGHT_SOFT_LIMIT_RATE)
        volume_deficit = sum(max(0.0, VOLUME_TARGET_RATE - c.fill_rate_volume) for c in containers)
        avg_volume = sum(c.fill_rate_volume for c in containers) / len(containers)
        max_weight_rate = max(c.fill_rate_weight for c in containers)

        return (
            len(unpacked_items),
            alert_count,
            len(containers),
            soft_weight_count,
            round(volume_deficit, 4),
            -round(avg_volume, 4),
            round(max_weight_rate, 4),
        )

    def _would_create_new_volume_alert(self, container: Container, item: Item) -> bool:
        if container.fill_rate_volume < VOLUME_TARGET_RATE:
            return False
        after_volume_rate = ((container.current_volume_m3 - item.volume_m3) / container.max_volume_m3) * 100
        return after_volume_rate < VOLUME_TARGET_RATE

    def _rebalance_soft_weight(self, containers: List[Container]):
        moved = True
        while moved:
            moved = False
            heavy_sources = sorted(
                [c for c in containers if c.fill_rate_weight >= WEIGHT_SOFT_LIMIT_RATE],
                key=lambda c: c.fill_rate_weight,
                reverse=True,
            )

            for source in heavy_sources:
                source_rate = source.fill_rate_weight
                movable_items = sorted(
                    source.items,
                    key=lambda item: (item.weight, self._density(item), item.volume_m3),
                    reverse=True,
                )

                for item in movable_items:
                    if self._would_create_new_volume_alert(source, item):
                        continue

                    # 修正: 削除前の元のリスト順序を完全に保存しておく
                    original_items = source.items[:]

                    target_options = []
                    for target in containers:
                        if target is source:
                            continue
                        if self._violates_container_rules(target, item):
                            continue

                        after_weight_rate = ((target.current_weight + item.weight) / target.max_weight) * 100
                        if after_weight_rate >= source_rate or after_weight_rate > 100.0:
                            continue
                        if not self._can_pack_without_mutation(target, item):
                            continue

                        after_volume_rate = ((target.current_volume_m3 + item.volume_m3) / target.max_volume_m3) * 100
                        target_options.append((
                            after_weight_rate >= WEIGHT_SOFT_LIMIT_RATE,
                            after_weight_rate,
                            max(0.0, VOLUME_TARGET_RATE - after_volume_rate),
                            target.id,
                            target,
                        ))

                    if not target_options:
                        continue

                    _, _, _, _, target = min(target_options)
                    source.items.remove(item)
                    item.x = item.y = item.z = None
                    item.is_rotated = False

                    if not self._rebuild_packer(source):
                        # 修正: appendではなく、元の順序のリストで完全復元する
                        source.items = original_items
                        self._rebuild_packer(source)
                        continue

                    if self._can_pack(target, item):
                        target.items.append(item)
                        moved = True
                        break

                    source.items = original_items
                    self._rebuild_packer(source)
                    self._rebuild_packer(target)

                if moved:
                    break

        containers[:] = [container for container in containers if container.items]

    def _run_basic_packing_once(self, items: List[Item], sort_key=None) -> Tuple[List[Container], List[Item]]:
        """基本パッキングロジック（単一期間）"""
        containers: List[Container] = []
        unpacked_items: List[Item] = []
        self.packers = {}
        
        # 体積80%が赤字判定なので、重量は制約として扱い、床面を使う大物・低密度の荷物を先に置く。
        def default_sort_key(item: Item):
            nearest_deadline = self._nearest_deadline(item)
            density = self._density(item)
            return (
                not item.force_ship,
                -item.weight,
                density,
                -item.volume_m3,
                -self._footprint_m2(item),
                nearest_deadline,
                -item.priority
            )

        sort_key = sort_key or default_sort_key
        sorted_items = sorted(items, key=sort_key)
        
        for item in sorted_items:
            placed = False
            best_container = self._select_best_container(containers, item)
            best_score = self._container_fit_score(best_container, item) if best_container else None
            if best_container and self._can_pack(best_container, item):
                best_container.items.append(item)
                if not item.decision_reason:
                    item.decision_reason = (
                        "既存コンテナ候補を比較し、赤字解消・充填率改善・実務制約適合の条件が最も良い配置を選択"
                        if best_score and best_score[0] == 0
                        else "既存コンテナ候補を比較し、実務制約を満たす中で最も充填率が良い配置を選択"
                    )
                placed = True
            
            if not placed:
                new_container = Container(id=f"C-{len(containers) + 1:03d}")
                if self._can_pack(new_container, item):
                    new_container.items.append(item)
                    if not item.decision_reason:
                        if containers:
                            item.decision_reason = "既存コンテナには3D配置・重量・実務制約のいずれかで入らないため新規コンテナを開始"
                        else:
                            item.decision_reason = "当日対象の先頭荷物として新規コンテナを開始"
                    containers.append(new_container)
                else:
                    if not item.decision_reason:
                        item.decision_reason = "コンテナ有効内寸・重量・実務制約のいずれかにより積載不可"
                    unpacked_items.append(item)
                    
        self._rebalance_soft_weight(containers)
        return containers, unpacked_items

    def run_basic_packing(self, items: List[Item]) -> Tuple[List[Container], List[Item]]:
        strategies = self._packing_strategies()
        if len(items) <= 1:
            self.last_packing_strategy = strategies[0][0]
            return self._run_basic_packing_once(items, strategies[0][1])

        best_name = strategies[0][0]
        best_sort_key = strategies[0][1]
        best_score = None

        for name, sort_key in strategies:
            trial_engine = VanningEngine(strategy_mode=self.strategy_mode)
            trial_items = copy.deepcopy(items)
            trial_containers, trial_unpacked = trial_engine._run_basic_packing_once(trial_items, sort_key)
            trial_score = self._packing_result_score(trial_containers, trial_unpacked)
            if best_score is None or trial_score < best_score:
                best_name = name
                best_sort_key = sort_key
                best_score = trial_score

        self.last_packing_strategy = best_name
        return self._run_basic_packing_once(items, best_sort_key)

    def run_time_axis_packing(self, target_items: List[Item], forwardable_items: List[Item], current_date: datetime.date, force_ship_window_days: int = 7, allow_partial_red_pull: bool = False) -> Tuple[List[Container], List[Item], List[Item]]:
        """
        時間軸（前倒し・繰り越し）を考慮したバンニング実行。
        戻り値: (確定コンテナリスト, 次回への保留プール, 使わなかった前倒し候補)
        """
        # 1. まず対象の荷物だけで普通に詰める
        containers, unpacked = self.run_basic_packing(target_items)
        
        final_containers = []
        next_pool = unpacked.copy() # 基本ロジックで溢れたものは無条件でプールへ
        remaining_forwardable = forwardable_items.copy()

        # 2. 各コンテナの充填率を評価し、時間軸操作（Pull/Push）を試みる
        for container in containers:
            is_red_ink = container.fill_rate_volume < VOLUME_TARGET_RATE
            
            if is_red_ink:
                # --- 🟢 PULL (前倒し) の試み ---
                # すでに現場にある前倒し候補から入りそうなものを探し、体積充填率80%を目指す
                pulled_items = []
                if self._can_potentially_reach_volume_target(container, remaining_forwardable):
                    candidates = sorted(
                        remaining_forwardable,
                        key=lambda item: self._forwardable_key(container, item, current_date)
                    )
                    for f_item in candidates:
                        before_volume = container.fill_rate_volume
                        before_weight = container.fill_rate_weight
                        metrics = self._forwardable_metrics(container, f_item, current_date)
                        if self._can_pack(container, f_item):
                            container.items.append(f_item)
                            pulled_items.append(f_item)
                            remaining_forwardable.remove(f_item)
                            f_item.status_msg = f"前倒し補填（元納期: {f_item.due_date.strftime('%m/%d')}）"
                            f_item.decision_reason = self._forwardable_note(
                                metrics,
                                before_volume,
                                before_weight,
                                container.fill_rate_volume,
                                container.fill_rate_weight
                            )
                            # 体積80%を超えたら前倒し完了
                            if container.fill_rate_volume >= VOLUME_TARGET_RATE:
                                break
                        elif not f_item.decision_reason:
                            f_item.decision_reason = self._forwardable_note(metrics, before_volume, before_weight) + " / 3D配置または実務制約によりこのコンテナでは未採用"
                else:
                    for f_item in remaining_forwardable:
                        if not f_item.decision_reason:
                            f_item.decision_reason = "残り前倒し候補を全て使っても体積80%到達見込みがないため未採用"

                if pulled_items and container.fill_rate_volume < VOLUME_TARGET_RATE:
                    for item in pulled_items:
                        container.items.remove(item)
                        item.status_msg = ""
                        item.decision_reason = "前倒ししても体積80%に届かないため、将来便向けに温存"
                        item.x = item.y = item.z = None
                        item.is_rotated = False
                    remaining_forwardable.extend(pulled_items)
                    self._rebuild_packer(container)

            # Pull後もまだ赤字かチェック
            is_still_red_ink = container.fill_rate_volume < VOLUME_TARGET_RATE

            if is_still_red_ink:
                # --- 🟡 PUSH (繰り越し/保留) の試み ---
                # コンテナ内の全荷物が「来週(7日後)まで待てるか」判定する
                can_wait = True
                force_limit_date = current_date + datetime.timedelta(days=force_ship_window_days)
                
                for item in container.items:
                    # 納期アウト、木箱寿命アウト、または手動で「強制出荷(force_ship)」フラグが立っているなら待てない
                    if item.force_ship or item.due_date <= force_limit_date or (item.expiration_date and item.expiration_date <= force_limit_date):
                        can_wait = False
                        break
                
                if can_wait:
                    # 待てるなら、このコンテナは出荷せず中身を全てプールへ戻す（コンテナ破棄）
                    for item in container.items:
                        item.status_msg = "充填率不足のため保留プールへ繰り越し"
                        item.decision_reason = "体積充填率80%未満だが全荷物が翌週以降まで待機可能なため、今回の確定出荷から外す"
                        # 繰り越すため確定していた3D座標をリセット
                        item.x = item.y = item.z = None
                        next_pool.append(item)
                    continue # final_containers には追加しない
                else:
                    # 待てないなら、赤字覚悟で強制出荷
                    if allow_partial_red_pull and remaining_forwardable:
                        candidates = sorted(
                            remaining_forwardable,
                            key=lambda item: self._forwardable_key(container, item, current_date)
                        )
                        for f_item in candidates:
                            projected_weight_rate = ((container.current_weight + f_item.weight) / container.max_weight) * 100 if container.max_weight > 0 else 0
                            if projected_weight_rate > WEIGHT_SOFT_LIMIT_RATE:
                                continue

                            before_volume = container.fill_rate_volume
                            before_weight = container.fill_rate_weight
                            metrics = self._forwardable_metrics(container, f_item, current_date)
                            if self._can_pack(container, f_item):
                                container.items.append(f_item)
                                remaining_forwardable.remove(f_item)
                                f_item.status_msg = f"前倒し補填（元納期: {f_item.due_date.strftime('%m/%d')}）"
                                f_item.decision_reason = (
                                    self._forwardable_note(
                                        metrics,
                                        before_volume,
                                        before_weight,
                                        container.fill_rate_volume,
                                        container.fill_rate_weight
                                    )
                                    + " / 強制出荷する赤字コンテナの空きを活用"
                                )
                                if container.fill_rate_volume >= VOLUME_TARGET_RATE:
                                    break

                    for item in container.items:
                        if item.force_ship:
                            item.status_msg = "手動オーバーライド：現場指示による強制出荷"
                            item.decision_reason = "現場の手動指定を最優先"
                        else:
                            item.system_force_ship = True
                            if "前倒し" in item.status_msg:
                                item.status_msg = f"{item.status_msg} / 赤字強制出荷"
                            else:
                                item.status_msg = "納期/寿命優先のため赤字強制出荷"
                            if not item.decision_reason:
                                item.decision_reason = "体積充填率80%未満でも納期または木箱期限が近く、翌週まで待機できないため確定"

            # 正常、Pullで回復、または強制出荷のコンテナを確定リストへ
            final_containers.append(container)

        self._rebalance_soft_weight(final_containers)

        for item in remaining_forwardable:
            if not item.decision_reason:
                item.decision_reason = "期限・優先度・隙間適合度の評価後、今回の赤字補填では未採用"

        return final_containers, next_pool, remaining_forwardable

if __name__ == "__main__":
    from data_loader import DataLoader
    
    loader = DataLoader()
    try:
        items = loader.load_from_excel("(抜粋)ケースリスト.xlsx", sheet_name=0)
        
        # テストのため、データを「必須出荷分(前半分)」と「前倒し候補(後半分)」に分割
        target_items = items[:20]
        forwardable_items = items[20:]
        current_date = datetime.date.today()
        
        engine = VanningEngine()
        containers, pool, unused_forwardable = engine.run_time_axis_packing(target_items, forwardable_items, current_date)
        
        print("\n=== バンニング計算結果（第2フェーズ：時間軸操作） ===")
        print(f" [確定コンテナ数]: {len(containers)} 本")
        print(f" [保留プール送り]: {len(pool)} 個の荷物")
        print(f" [未使用の前倒し候補]: {len(unused_forwardable)} 個\n")
        
        for c in containers:
            is_alert = c.fill_rate_volume < VOLUME_TARGET_RATE
            alert_str = "[ALERT: 体積80%未満]" if is_alert else "[OK: 体積80%クリア]"
            
            print(f"  [コンテナ {c.id}] {alert_str}")
            print(f"    - 総重量: {c.current_weight:,.1f} kg (充填率: {c.fill_rate_weight:.1f}%)")
            
            print(f"    - 総体積: {c.current_volume_m3:,.1f} m3 (充填率: {c.fill_rate_volume:.1f}%)")
            
            # 各コンテナ内で「時間軸操作」が行われた荷物をハイライト
            special_items = [i for i in c.items if i.status_msg]
            if special_items:
                print(f"    - 時間軸操作ログ:")
                for i in special_items:
                    print(f"      * {i.name}: {i.status_msg}")
                    
            # 3D座標のサンプル表示
            print(f"    - 3D配置座標サンプル (最初の2件):")
            for i in c.items[:2]:
                rot_str = "(回転)" if i.is_rotated else ""
                print(f"      * {i.name}: X={i.x:.1f}, Y={i.y:.1f}, Z={i.z:.1f} {rot_str}")
            print("")
                
    except Exception as e:
        print(f"実行エラー: {e}")
