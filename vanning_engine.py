import uuid
import datetime
import copy
from typing import List, Tuple, Dict, Optional
from models import Item, Container
from packing_3d import Packer3D

VOLUME_TARGET_RATE = 80.0
WEIGHT_SOFT_LIMIT_RATE = 97.0
LARGE_PLAN_ITEM_THRESHOLD = 300
LOCAL_SEARCH_MAX_PASSES = 15
LOCAL_RESCUE_TRIAL_LIMIT = 120
LOCAL_BUNDLE_TRIAL_LIMIT = 80
LOCAL_PAIR_REPACK_TRIAL_LIMIT = 500
LARGE_PLAN_STRATEGY_LIMIT = 4

class VanningEngine:
    """
    バンニング計算コアエンジン（第3フェーズ：3D配置・時間軸操作対応版）
    """
    def __init__(self, strategy_mode: str = "full", prioritize_open_containers: bool = True, vanning_base_date: Optional[datetime.date] = None):
        # 各コンテナの3D空間状態を管理するパッカー
        self.packers: Dict[str, Packer3D] = {}
        self.last_packing_strategy = ""
        self.strategy_mode = strategy_mode
        self.prioritize_open_containers = prioritize_open_containers
        self.vanning_base_date = vanning_base_date
        self.strategy_trials = []
        self.deep_strategy_trials = []
        self.alert_pool_strategy = ""
        self.layout_improvement_stats = {
            "consolidated_containers": 0,
            "rescued_alert_containers": 0,
            "bundled_rescue_containers": 0,
            "pair_repacked_alert_containers": 0,
            "pooled_repack_alert_containers": 0,
        }

    def _nearest_deadline(self, item: Item) -> datetime.date:
        deadlines = [item.due_date]
        if item.expiration_date:
            deadlines.append(item.expiration_date)
        return min(deadlines)

    def _density(self, item: Item) -> float:
        return item.weight / item.volume_m3 if item.volume_m3 > 0 else float('inf')

    def _footprint_m2(self, item: Item) -> float:
        return (item.length / 1000) * (item.width / 1000)

    def _can_pack(self, container: Container, item: Item) -> bool:
        """重量制約と3D座標での当たり判定（完全収容・底面接地率100%）"""
        # 0. 時間制約（バンニング日より後に納入される荷物は積載不可）
        if container.vanning_date and item.creation_date > container.vanning_date:
            return False

        # 1. 重量チェック
        if container.current_weight + item.weight > container.max_weight:
            return False

        # 2. 理論体積チェック（残りの空間体積が荷物の体積より小さいなら絶対に入らない）
        if (container.max_volume_m3 - container.current_volume_m3) < item.volume_m3:
            return False

        # 3. 3D配置判定（パズルの計算）
        if container.id not in self.packers:
            self.packers[container.id] = Packer3D(container)

        packer = self.packers[container.id]

        # packer.try_pack_item は、空間に空きがあれば座標(x,y,z)を確定させてTrueを返す
        return packer.try_pack_item(item)

    def _can_pack_without_mutation(self, container: Container, item: Item) -> bool:
        """候補評価用。3D空間やItem座標を変更せずに積載可否だけを見る。"""
        if container.vanning_date and item.creation_date > container.vanning_date:
            return False
        if container.current_weight + item.weight > container.max_weight:
            return False
        if (container.max_volume_m3 - container.current_volume_m3) < item.volume_m3:
            return False

        packer = self.packers.get(container.id)
        if packer:
            return packer.can_pack_item_probe(item)
        else:
            # まだpackerがない場合はビルドして試す（通常は空のはずなので問題なし）
            probe_packer = self._build_probe_packer(container)
            if probe_packer is None:
                return False
            return probe_packer.can_pack_item_probe(item)

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

        status_priority = (
            (0 if clears_alert else 1 if before_is_alert else 2)
            if self.prioritize_open_containers
            else (0 if clears_alert else 1 if not after_is_alert else 2)
        )
        # 仕向け地グルーピング: 同じ仕向け地の荷物が既に入っているコンテナを優先
        has_matching_dest = False
        if getattr(item, 'destination', None) and container.items:
            has_matching_dest = any(getattr(i, 'destination', None) == item.destination for i in container.items)

        return (
            # Open-container priority improves large single-vessel plans; medium plans
            # may also evaluate the established packing preference as an alternative.
            status_priority,
            not has_matching_dest,  # 同じ仕向け地のコンテナを優先
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
            item.destination, # 配送先でグループ化（奥から詰めるための疑似LIFO/FIFO）
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

    def _sort_key_large_plan(self, item: Item):
        nearest_deadline = self._nearest_deadline(item)
        return (
            not item.force_ship,
            -self._footprint_m2(item),
            -item.volume_m3,
            self._density(item),
            -item.weight,
            nearest_deadline,
            -item.priority,
        )

    def _sort_key_volume_geometry(self, item: Item):
        nearest_deadline = self._nearest_deadline(item)
        return (
            not item.force_ship,
            -item.volume_m3,
            -self._footprint_m2(item),
            -item.weight,
            self._density(item),
            nearest_deadline,
            -item.priority,
        )

    def _sort_key_height_geometry(self, item: Item):
        nearest_deadline = self._nearest_deadline(item)
        return (
            not item.force_ship,
            -self._footprint_m2(item),
            -item.height,
            -item.volume_m3,
            -item.weight,
            nearest_deadline,
            -item.priority,
        )

    def _large_plan_strategies(self):
        return [
            ("floor_area_first", self._sort_key_large_plan),
            ("volume_geometry_first", self._sort_key_volume_geometry),
            ("height_geometry_first", self._sort_key_height_geometry),
            ("weight_volume_first", self._sort_key_bulky_first),
        ][:LARGE_PLAN_STRATEGY_LIMIT]

    def _packing_strategies(self):
        if self.strategy_mode == "ga":
            return [("ga_order", lambda i: 0)]
            
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
            return (len(unpacked_items), 0, 0, 0, 0, 0, 0, 0)

        alert_count = sum(1 for c in containers if c.fill_rate_volume < VOLUME_TARGET_RATE)
        soft_weight_count = sum(1 for c in containers if c.fill_rate_weight >= WEIGHT_SOFT_LIMIT_RATE)
        volume_deficit = sum(max(0.0, VOLUME_TARGET_RATE - c.fill_rate_volume) for c in containers)
        avg_volume = sum(c.fill_rate_volume for c in containers) / len(containers)
        max_weight_rate = max(c.fill_rate_weight for c in containers)
        
        import math
        cg_penalty = 0.0
        for c in containers:
            cg_x, cg_y, _ = c.compute_cg()
            if cg_x is not None and cg_y is not None:
                cg_dist = math.sqrt((cg_x - c.length/2)**2 + (cg_y - c.width/2)**2)
                if cg_dist > 300.0:
                    cg_penalty += (cg_dist - 300.0)

        return (
            len(unpacked_items),
            alert_count,
            round(cg_penalty, 2), # 重心違反ペナルティ（小さいほど良い）
            len(containers),
            soft_weight_count,
            round(volume_deficit, 4),
            -round(avg_volume, 4),
            round(max_weight_rate, 4),
        )

    def _build_local_trial(self, containers: List[Container]):
        """Create a fully repacked copy for a candidate local-search move."""
        trial_engine = VanningEngine(
            strategy_mode=self.strategy_mode,
            prioritize_open_containers=True,
        )
        trial_containers = copy.deepcopy(containers)
        for container in trial_containers:
            if not trial_engine._rebuild_packer(container):
                return None, None
        return trial_engine, trial_containers

    def _reset_placement(self, item: Item):
        item.x = item.y = item.z = None
        item.is_rotated = False

    def _accept_local_candidate(self, containers: List[Container], trial_engine, candidate_containers: List[Container]):
        containers[:] = candidate_containers
        self.packers = trial_engine.packers

    def _build_transfer_trial(self, containers: List[Container], source_id: str, target_id: str):
        """Clone only the two containers changed by an item transfer."""
        trial_engine = VanningEngine(
            strategy_mode=self.strategy_mode,
            prioritize_open_containers=True,
        )
        source = copy.deepcopy(next(container for container in containers if container.id == source_id))
        target = copy.deepcopy(next(container for container in containers if container.id == target_id))
        if not trial_engine._rebuild_packer(source) or not trial_engine._rebuild_packer(target):
            return None, None, None, None
        trial_containers = [
            source if container.id == source_id else target if container.id == target_id else container
            for container in containers
        ]
        return trial_engine, trial_containers, source, target

    def _accept_transfer_candidate(self, containers: List[Container], trial_engine, candidate_containers: List[Container], removed_source_id=None):
        merged_packers = dict(self.packers)
        merged_packers.update(trial_engine.packers)
        if removed_source_id:
            merged_packers.pop(removed_source_id, None)
        containers[:] = candidate_containers
        self.packers = merged_packers

    def _try_consolidate_low_fill_container(self, containers: List[Container]) -> bool:
        """Remove an underfilled container when every item can be reassigned safely."""
        baseline_score = self._packing_result_score(containers, [])
        low_fill_sources = sorted(
            [container for container in containers if container.fill_rate_volume < VOLUME_TARGET_RATE],
            key=lambda container: (container.fill_rate_volume, len(container.items), container.id),
        )

        for original_source in low_fill_sources:
            trial_engine, trial_containers = self._build_local_trial(containers)
            if not trial_engine:
                continue

            source = next(container for container in trial_containers if container.id == original_source.id)
            destinations = [container for container in trial_containers if container.id != source.id]
            movable_items = sorted(list(source.items), key=self._sort_key_large_plan)

            completed = True
            for item in movable_items:
                source.items.remove(item)
                self._reset_placement(item)
                target = trial_engine._select_best_container(destinations, item)
                if target is None or not trial_engine._can_pack(target, item):
                    completed = False
                    break
                target.items.append(item)
                if not item.status_msg:
                    item.decision_reason = "低充填コンテナの統合により、既存コンテナへ再配置"

            if not completed:
                continue

            trial_engine.packers.pop(source.id, None)
            candidate_score = self._packing_result_score(destinations, [])
            if candidate_score < baseline_score:
                self._accept_local_candidate(containers, trial_engine, destinations)
                self.layout_improvement_stats["consolidated_containers"] += 1
                return True

        return False

    def _rescue_transfer_options(self, containers: List[Container]):
        options = []
        low_fill_targets = sorted(
            [container for container in containers if container.fill_rate_volume < VOLUME_TARGET_RATE],
            key=lambda container: (-container.fill_rate_volume, container.id),
        )
        for target in low_fill_targets:
            for source in containers:
                if source is target:
                    continue
                for item in source.items:
                    after_target_rate = (
                        (target.current_volume_m3 + item.volume_m3) / target.max_volume_m3
                    ) * 100
                    if after_target_rate < VOLUME_TARGET_RATE:
                        continue
                    if target.current_weight + item.weight > target.max_weight:
                        continue

                    source_item_count = len(source.items) - 1
                    after_source_rate = (
                        ((source.current_volume_m3 - item.volume_m3) / source.max_volume_m3) * 100
                        if source_item_count
                        else 0
                    )
                    before_alerts = int(target.fill_rate_volume < VOLUME_TARGET_RATE) + int(
                        source.fill_rate_volume < VOLUME_TARGET_RATE
                    )
                    after_alerts = int(after_target_rate < VOLUME_TARGET_RATE)
                    if source_item_count:
                        after_alerts += int(after_source_rate < VOLUME_TARGET_RATE)
                    if after_alerts >= before_alerts:
                        continue

                    options.append((
                        after_alerts,
                        max(0.0, after_target_rate - VOLUME_TARGET_RATE),
                        0 if not source_item_count else 1,
                        -target.fill_rate_volume,
                        source.id,
                        target.id,
                        item.id,
                    ))
        return sorted(options)

    def _try_rescue_low_fill_container(self, containers: List[Container], rescue_limit: int = LOCAL_RESCUE_TRIAL_LIMIT) -> bool:
        """Move one item only when it strictly reduces the alert-container score."""
        baseline_score = self._packing_result_score(containers, [])
        for _, _, _, _, source_id, target_id, item_id in self._rescue_transfer_options(containers)[:rescue_limit]:
            trial_engine, trial_containers, source, target = self._build_transfer_trial(
                containers,
                source_id,
                target_id,
            )
            if not trial_engine:
                continue

            item = next(item for item in source.items if item.id == item_id)
            source.items.remove(item)
            self._reset_placement(item)

            removed_source_id = None
            if source.items:
                if not trial_engine._rebuild_packer(source):
                    continue
            else:
                trial_containers.remove(source)
                trial_engine.packers.pop(source.id, None)
                removed_source_id = source.id

            if not trial_engine._can_pack(target, item):
                continue
            target.items.append(item)
            if not item.status_msg:
                item.decision_reason = "低充填コンテナを80%以上にするため、既存コンテナ間で再配置"

            candidate_score = self._packing_result_score(trial_containers, [])
            if candidate_score < baseline_score:
                self._accept_transfer_candidate(
                    containers,
                    trial_engine,
                    trial_containers,
                    removed_source_id=removed_source_id,
                )
                self.layout_improvement_stats["rescued_alert_containers"] += 1
                return True
        return False

    def _bundle_transfer_options(self, containers: List[Container]):
        options = []
        low_fill_targets = sorted(
            [container for container in containers if container.fill_rate_volume < VOLUME_TARGET_RATE],
            key=lambda container: (-container.fill_rate_volume, container.id),
        )
        for target in low_fill_targets:
            for source in containers:
                if source is target or len(source.items) < 2:
                    continue
                for first_index, first in enumerate(source.items[:-1]):
                    for second in source.items[first_index + 1:]:
                        added_volume = first.volume_m3 + second.volume_m3
                        after_target_rate = (
                            (target.current_volume_m3 + added_volume) / target.max_volume_m3
                        ) * 100
                        if after_target_rate < VOLUME_TARGET_RATE:
                            continue
                        if target.current_weight + first.weight + second.weight > target.max_weight:
                            continue

                        source_item_count = len(source.items) - 2
                        after_source_rate = (
                            ((source.current_volume_m3 - added_volume) / source.max_volume_m3) * 100
                            if source_item_count
                            else 0
                        )
                        before_alerts = int(target.fill_rate_volume < VOLUME_TARGET_RATE) + int(
                            source.fill_rate_volume < VOLUME_TARGET_RATE
                        )
                        after_alerts = int(after_target_rate < VOLUME_TARGET_RATE)
                        if source_item_count:
                            after_alerts += int(after_source_rate < VOLUME_TARGET_RATE)
                        if after_alerts >= before_alerts:
                            continue

                        options.append((
                            after_alerts,
                            max(0.0, after_target_rate - VOLUME_TARGET_RATE),
                            0 if not source_item_count else 1,
                            -target.fill_rate_volume,
                            source.id,
                            target.id,
                            first.id,
                            second.id,
                        ))
        return sorted(options)

    def _try_rescue_low_fill_bundle(self, containers: List[Container]) -> bool:
        """Move two items together when a single-item rescue cannot reach 80%."""
        baseline_score = self._packing_result_score(containers, [])
        options = self._bundle_transfer_options(containers)[:LOCAL_BUNDLE_TRIAL_LIMIT]
        for _, _, _, _, source_id, target_id, first_id, second_id in options:
            trial_engine, trial_containers, source, target = self._build_transfer_trial(
                containers,
                source_id,
                target_id,
            )
            if not trial_engine:
                continue

            moved_items = [
                next(item for item in source.items if item.id == item_id)
                for item_id in (first_id, second_id)
            ]
            for item in moved_items:
                source.items.remove(item)

            removed_source_id = None
            if source.items:
                if not trial_engine._rebuild_packer(source):
                    continue
            else:
                trial_containers.remove(source)
                trial_engine.packers.pop(source.id, None)
                removed_source_id = source.id

            completed = True
            for item in sorted(moved_items, key=self._sort_key_large_plan):
                self._reset_placement(item)
                if not trial_engine._can_pack(target, item):
                    completed = False
                    break
                target.items.append(item)
                if not item.status_msg:
                    item.decision_reason = "低充填コンテナを80%以上にするため、荷物をまとめて再配置"
            if not completed:
                continue

            candidate_score = self._packing_result_score(trial_containers, [])
            if candidate_score < baseline_score:
                self._accept_transfer_candidate(
                    containers,
                    trial_engine,
                    trial_containers,
                    removed_source_id=removed_source_id,
                )
                self.layout_improvement_stats["bundled_rescue_containers"] += 1
                return True
        return False

    def _try_repack_low_fill_pair(self, containers: List[Container]) -> bool:
        """Repack two alert containers from scratch when rearrangement rescues one."""
        baseline_alerts = sum(
            container.fill_rate_volume < VOLUME_TARGET_RATE for container in containers
        )
        alert_containers = [
            container for container in containers
            if container.fill_rate_volume < VOLUME_TARGET_RATE
        ]
        pair_candidates = []
        for first_index, first in enumerate(alert_containers[:-1]):
            for second in alert_containers[first_index + 1:]:
                pair_candidates.append((
                    -(first.fill_rate_volume + second.fill_rate_volume),
                    first.id,
                    second.id,
                ))

        strategies = [self._sort_key_bulky_first, self._sort_key_large_plan]
        for _, first_id, second_id in sorted(pair_candidates)[:LOCAL_PAIR_REPACK_TRIAL_LIMIT]:
            original_pair = [
                next(container for container in containers if container.id == first_id),
                next(container for container in containers if container.id == second_id),
            ]
            items = original_pair[0].items + original_pair[1].items

            for sort_key in strategies:
                trial_engine = VanningEngine(
                    strategy_mode=self.strategy_mode,
                    prioritize_open_containers=True,
                )
                repacked, unpacked = trial_engine._run_basic_packing_once(
                    copy.deepcopy(items),
                    sort_key,
                    apply_local_search=False,
                )
                if unpacked or len(repacked) > 2:
                    continue

                candidate_containers = [
                    container
                    for container in containers
                    if container.id not in (first_id, second_id)
                ] + repacked
                candidate_alerts = sum(
                    container.fill_rate_volume < VOLUME_TARGET_RATE
                    for container in candidate_containers
                )
                if candidate_alerts >= baseline_alerts:
                    continue

                remapped_packers = dict(self.packers)
                remapped_packers.pop(first_id, None)
                remapped_packers.pop(second_id, None)
                original_ids = [first_id, second_id]
                for index, container in enumerate(repacked):
                    trial_id = container.id
                    container.id = original_ids[index]
                    packer = trial_engine.packers[trial_id]
                    packer.container = container
                    remapped_packers[container.id] = packer
                    for item in container.items:
                        if not item.status_msg:
                            item.decision_reason = "低充填コンテナ2本を組み直し、体積80%未満の本数を削減"

                containers[:] = [
                    container
                    for container in containers
                    if container.id not in (first_id, second_id)
                ] + repacked
                self.packers = remapped_packers
                self.layout_improvement_stats["pair_repacked_alert_containers"] += (
                    baseline_alerts - candidate_alerts
                )
                return True

        return False

    def _try_repack_alert_pool(self, containers: List[Container]) -> bool:
        """Rebuild all alert containers using the best bounded geometry-first trial."""
        alert_containers = [
            container for container in containers
            if container.fill_rate_volume < VOLUME_TARGET_RATE
        ]
        if len(alert_containers) < 2:
            return False

        baseline_score = self._packing_result_score(containers, [])
        original_ids = [container.id for container in alert_containers]
        alert_items = sum((container.items for container in alert_containers), [])

        best_trial = None
        pool_strategies = [
            ("floor_area_first", self._sort_key_large_plan),
            ("volume_geometry_first", self._sort_key_volume_geometry),
            ("height_geometry_first", self._sort_key_height_geometry),
            ("weight_volume_first", self._sort_key_bulky_first),
        ]
        for name, sort_key in pool_strategies:
            trial_engine = VanningEngine(
                strategy_mode=self.strategy_mode,
                prioritize_open_containers=True,
            )
            repacked, unpacked = trial_engine._run_basic_packing_once(
                copy.deepcopy(alert_items),
                sort_key,
                apply_local_search=False,
            )
            if unpacked or len(repacked) > len(alert_containers):
                continue
            trial_score = self._packing_result_score(repacked, [])
            if best_trial is None or trial_score < best_trial[0]:
                best_trial = (trial_score, name, trial_engine, repacked)

        if best_trial is None:
            return False

        _, selected_name, trial_engine, repacked = best_trial
        trial_engine._improve_low_fill_layout(repacked, allow_pool_repack=False)
        candidate_containers = [
            container
            for container in containers
            if container.id not in original_ids
        ] + repacked
        candidate_score = self._packing_result_score(candidate_containers, [])
        if candidate_score >= baseline_score:
            return False

        self.alert_pool_strategy = selected_name
        remapped_packers = {
            container_id: packer
            for container_id, packer in self.packers.items()
            if container_id not in original_ids
        }
        for index, container in enumerate(repacked):
            trial_id = container.id
            container.id = original_ids[index]
            packer = trial_engine.packers[trial_id]
            packer.container = container
            remapped_packers[container.id] = packer
            for item in container.items:
                if not item.status_msg:
                    item.decision_reason = "低充填コンテナ群をまとめて組み直し、体積80%未満を削減"

        containers[:] = [
            container
            for container in containers
            if container.id not in original_ids
        ] + repacked
        self.packers = remapped_packers
        self.layout_improvement_stats["pooled_repack_alert_containers"] += (
            baseline_score[1] - candidate_score[1]
        )
        return True

    def _improve_low_fill_layout(self, containers: List[Container], allow_pool_repack: bool = True):
        """Apply bounded local search without changing physical or weight constraints."""
        num_containers = len(containers)
        # 動的に回数を制限（コンテナが多い場合は大幅に減らす）
        max_passes = LOCAL_SEARCH_MAX_PASSES
        rescue_limit = LOCAL_RESCUE_TRIAL_LIMIT
        if num_containers >= 10:
            max_passes = max(1, LOCAL_SEARCH_MAX_PASSES // 3)
            rescue_limit = max(10, LOCAL_RESCUE_TRIAL_LIMIT // 4)
        if num_containers >= 20:
            max_passes = max(1, LOCAL_SEARCH_MAX_PASSES // 5)
            rescue_limit = max(5, LOCAL_RESCUE_TRIAL_LIMIT // 10)
        if num_containers >= 40:
            max_passes = 1
            rescue_limit = 2

        for _ in range(max_passes):
            if self._try_consolidate_low_fill_container(containers):
                continue
            if self._try_rescue_low_fill_container(containers, rescue_limit=rescue_limit):
                continue
            if self._try_repack_low_fill_pair(containers):
                continue
            if self._try_rescue_low_fill_bundle(containers):
                continue
            break
        if allow_pool_repack and self._try_repack_alert_pool(containers):
            self._improve_low_fill_layout(containers, allow_pool_repack=False)

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

    def _run_basic_packing_once(self, items: List[Item], sort_key=None, apply_local_search: bool = True) -> Tuple[List[Container], List[Item]]:
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
                if self.vanning_base_date:
                    import datetime
                    offset_days = -7 + (len(containers) % 6)
                    base_date = self.vanning_base_date + datetime.timedelta(days=offset_days)
                    max_vanning_date = self.vanning_base_date - datetime.timedelta(days=2)
                    target_date = max(base_date, item.creation_date)
                    new_container.vanning_date = min(target_date, max_vanning_date)

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
        if apply_local_search:
            self._improve_low_fill_layout(containers)
        return containers, unpacked_items

    def run_basic_packing(self, items: List[Item]) -> Tuple[List[Container], List[Item]]:
        if self.strategy_mode == "ga":
            strategies = [("ga_order", lambda i: 0)]
        else:
            strategies = (
                self._large_plan_strategies()
                if len(items) >= LARGE_PLAN_ITEM_THRESHOLD
                else self._packing_strategies()
            )

        if len(items) <= 1 or self.strategy_mode == "ga":
            self.last_packing_strategy = strategies[0][0]
            return self._run_basic_packing_once(items, strategies[0][1])

        best_name = strategies[0][0]
        best_sort_key = strategies[0][1]
        best_score = None

        for name, sort_key in strategies:
            trial_engine = VanningEngine(
                strategy_mode=self.strategy_mode,
                # Use the 80%-rescue preference to choose the ordering; the
                # alternative policy changes the final initial placement only.
                prioritize_open_containers=True,
            )
            trial_items = copy.deepcopy(items)
            trial_containers, trial_unpacked = trial_engine._run_basic_packing_once(
                trial_items,
                sort_key,
                apply_local_search=False,
            )
            trial_score = self._packing_result_score(trial_containers, trial_unpacked)
            self.strategy_trials.append({
                "name": name,
                "container_count": len(trial_containers),
                "alert_containers": sum(
                    1 for container in trial_containers
                    if container.fill_rate_volume < VOLUME_TARGET_RATE
                ),
                "avg_volume_rate": round(
                    sum(container.fill_rate_volume for container in trial_containers) / len(trial_containers),
                    1,
                ) if trial_containers else 0,
            })
            if best_score is None or trial_score < best_score:
                best_name = name
                best_sort_key = sort_key
                best_score = trial_score

        if len(items) >= LARGE_PLAN_ITEM_THRESHOLD:
            deep_strategies = [(best_name, best_sort_key)]
            incumbent_name = "weight_volume_first"
            incumbent_key = self._sort_key_bulky_first
            if best_name != incumbent_name:
                deep_strategies.append((incumbent_name, incumbent_key))

            selected_result = None
            for name, sort_key in deep_strategies:
                deep_engine = VanningEngine(
                    strategy_mode=self.strategy_mode,
                    prioritize_open_containers=self.prioritize_open_containers,
                )
                deep_containers, deep_unpacked = deep_engine._run_basic_packing_once(
                    copy.deepcopy(items),
                    sort_key,
                    apply_local_search=True,
                )
                deep_score = self._packing_result_score(deep_containers, deep_unpacked)
                self.deep_strategy_trials.append({
                    "name": name,
                    "container_count": len(deep_containers),
                    "alert_containers": sum(
                        1 for container in deep_containers
                        if container.fill_rate_volume < VOLUME_TARGET_RATE
                    ),
                    "avg_volume_rate": round(
                        sum(container.fill_rate_volume for container in deep_containers) / len(deep_containers),
                        1,
                    ) if deep_containers else 0,
                })
                if selected_result is None or deep_score < selected_result[0]:
                    selected_result = (
                        deep_score,
                        name,
                        deep_engine,
                        deep_containers,
                        deep_unpacked,
                    )

            _, selected_name, selected_engine, selected_containers, selected_unpacked = selected_result
            self.last_packing_strategy = selected_name
            self.packers = selected_engine.packers
            self.layout_improvement_stats = selected_engine.layout_improvement_stats
            self.alert_pool_strategy = selected_engine.alert_pool_strategy
            return selected_containers, selected_unpacked

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
        pulled_any = False

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
                    )[:100] # 高速化のため上位100件に制限
                    for f_item in candidates:
                        before_volume = container.fill_rate_volume
                        before_weight = container.fill_rate_weight
                        metrics = self._forwardable_metrics(container, f_item, current_date)
                        if self._can_pack(container, f_item):
                            container.items.append(f_item)
                            pulled_items.append(f_item)
                            pulled_any = True
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
                        )[:100] # 高速化のため上位100件に制限
                        for f_item in candidates:
                            projected_weight_rate = ((container.current_weight + f_item.weight) / container.max_weight) * 100 if container.max_weight > 0 else 0
                            if projected_weight_rate > WEIGHT_SOFT_LIMIT_RATE:
                                continue

                            before_volume = container.fill_rate_volume
                            before_weight = container.fill_rate_weight
                            metrics = self._forwardable_metrics(container, f_item, current_date)
                            if self._can_pack(container, f_item):
                                container.items.append(f_item)
                                pulled_any = True
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
        if pulled_any:
            self._improve_low_fill_layout(final_containers)

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
