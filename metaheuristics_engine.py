import time
import random
import copy
import datetime
from typing import List, Tuple, Optional
from models import Item, Container
from vanning_engine import VanningEngine, VOLUME_TARGET_RATE

class GeneticAlgorithmOptimizer:
    """
    遺伝的アルゴリズム（GA）を用いて、VanningEngineの「順序」を最適化するクラス。
    ベースライン（近似値モードの結果）を受け取り、それをエリートとして保持しながら
    さらに良い解を探索する。
    """
    def __init__(
        self, 
        target_items: List[Item],
        forwardable_items: List[Item],
        current_date: datetime.date,
        vanning_base_date: datetime.date,
        baseline_containers: List[Container],
        baseline_pool: List[Item],
        baseline_unused: List[Item],
        time_limit_seconds: int = 30,
        population_size: int = 20,
        mutation_rate: float = 0.25,
        progress_callback: Optional[callable] = None,
    ):
        self.target_items = target_items
        self.forwardable_items = forwardable_items
        self.current_date = current_date
        self.vanning_base_date = vanning_base_date
        self.time_limit_seconds = time_limit_seconds
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.progress_callback = progress_callback
        
        self.all_items = target_items + forwardable_items
        self.num_targets = len(target_items)
        
        # ベースライン（近似値モードの結果）をエリートとして保持
        self.best_containers = baseline_containers
        self.best_pool = baseline_pool
        self.best_unused = baseline_unused
        self.best_score = self._evaluate_containers(baseline_containers, baseline_pool)
        
        # 統計情報
        self.generations_completed = 0
        self.total_evaluations = 0

    def run(self) -> Tuple[List[Container], List[Item], List[Item]]:
        start_time = time.time()

        temp_engine = VanningEngine(strategy_mode="fast", vanning_base_date=self.vanning_base_date)
        strategies = temp_engine._large_plan_strategies() if self.num_targets >= 300 else temp_engine._packing_strategies()
        sort_key = strategies[0][1]

        target_indices = sorted(range(self.num_targets), key=lambda i: sort_key(self.all_items[i]))
        forward_indices = sorted(range(self.num_targets, len(self.all_items)), key=lambda i: sort_key(self.all_items[i]))
        baseline_order = target_indices + forward_indices

        population = self._build_initial_population(baseline_order)

        while True:
            elapsed = time.time() - start_time
            if elapsed >= self.time_limit_seconds:
                break
                
            self.generations_completed += 1
            scored_population = []
            
            for genome in population:
                # 個体評価中にタイムリミットを超えた場合は即座に打ち切る
                if time.time() - start_time >= self.time_limit_seconds:
                    break
                
                # エリート（第1世代のベースライン）は再計算スキップ
                if self.generations_completed == 1 and genome is population[0]:
                    scored_population.append((self.best_score, genome))
                    continue
                    
                containers, pool, unused, score = self._simulate(genome)
                self.total_evaluations += 1
                scored_population.append((score, genome))
                
                if score > self.best_score:
                    self.best_score = score
                    self.best_containers = containers
                    self.best_pool = pool
                    self.best_unused = unused
                    
            if self.progress_callback:
                self.progress_callback(self.generations_completed, self.best_score)
            
            if not scored_population:
                break
                    
            # スコア降順でソート
            scored_population.sort(key=lambda x: x[0], reverse=True)
            
            # 上位50%を生き残りとして選択
            survivors = [x[1] for x in scored_population[:self.population_size // 2]]
            
            # 交叉と突然変異で次世代を生成
            next_population = survivors.copy()
            while len(next_population) < self.population_size:
                p1 = random.choice(survivors)
                p2 = random.choice(survivors)
                child = self._crossover_ox1(p1, p2)
                
                if random.random() < self.mutation_rate:
                    self._mutate(child)
                next_population.append(child)
                
            population = next_population

        elapsed = time.time() - start_time
        print(f"[GA] {self.generations_completed}世代 / {self.total_evaluations}個体評価 / {elapsed:.1f}秒 / Best: {self.best_score:.1f}")
        return self.best_containers, self.best_pool, self.best_unused

    def _build_initial_population(self, baseline_order: List[int]) -> List[List[int]]:
        population = []
        seen = set()

        def add(genome):
            key = tuple(genome)
            if key not in seen:
                seen.add(key)
                population.append(genome)

        add(baseline_order)
        seed_keys = [
            lambda item: (item.due_date, item.expiration_date or item.due_date, -item.priority, -item.volume_m3),
            lambda item: (-item.volume_m3, -item.weight, item.due_date),
            lambda item: (-(item.length * item.width), -item.volume_m3, item.due_date),
            lambda item: (-item.weight, -item.volume_m3, item.due_date),
            lambda item: (-item.height, -(item.length * item.width), item.due_date),
            lambda item: (self._destination_key(item), item.due_date, -item.volume_m3),
        ]
        for key_func in seed_keys:
            add(self._genome_from_sorted_groups(key_func))
            add(self._genome_from_sorted_groups(key_func, reverse_forwardable=True))

        while len(population) < self.population_size:
            genome = self._create_random_genome()
            before = len(population)
            add(genome)
            if len(population) == before:
                population.append(genome)

        return population[:self.population_size]

    def _destination_key(self, item: Item):
        return getattr(item, "destination", "") or "ZZZ"

    def _genome_from_sorted_groups(self, key_func, reverse_forwardable: bool = False) -> List[int]:
        target_indices = sorted(range(self.num_targets), key=lambda idx: key_func(self.all_items[idx]))
        forwardable_indices = sorted(
            range(self.num_targets, len(self.all_items)),
            key=lambda idx: key_func(self.all_items[idx]),
            reverse=reverse_forwardable,
        )
        return target_indices + forwardable_indices

    def _extract_genome_from_containers(self, containers: List[Container]) -> List[int]:
        """コンテナの配置結果から遺伝子（順序配列）を逆算する"""
        order = []
        placed_ids = set()
        for c in containers:
            for item in c.items:
                for i, orig_item in enumerate(self.all_items):
                    if orig_item.id == item.id and i not in placed_ids:
                        order.append(i)
                        placed_ids.add(i)
                        break
        # 未配置の荷物を末尾に追加
        for i in range(len(self.all_items)):
            if i not in placed_ids:
                order.append(i)
        return order

    def _create_random_genome(self) -> List[int]:
        """ランダムな遺伝子を生成（ターゲットとフォワーダブルを別々にシャッフルして結合）"""
        target_indices = list(range(self.num_targets))
        random.shuffle(target_indices)
        forwardable_indices = list(range(self.num_targets, len(self.all_items)))
        random.shuffle(forwardable_indices)
        combined = target_indices + forwardable_indices
        
        # 10%の位置をランダムにスワップ（多様性確保）
        swap_count = max(1, len(combined) // 10)
        for _ in range(swap_count):
            idx1 = random.randint(0, len(combined) - 1)
            idx2 = random.randint(0, len(combined) - 1)
            combined[idx1], combined[idx2] = combined[idx2], combined[idx1]
        return combined

    def _crossover_ox1(self, p1: List[int], p2: List[int]) -> List[int]:
        """Order Crossover (OX1): 順序付き配列の交叉"""
        size = len(p1)
        if size < 2:
            return p1.copy()
        start, end = sorted(random.sample(range(size), 2))
        child = [-1] * size
        child[start:end] = p1[start:end]
        
        child_set = set(p1[start:end])
        p2_idx = 0
        for i in range(size):
            if child[i] == -1:
                while p2[p2_idx] in child_set:
                    p2_idx += 1
                child[i] = p2[p2_idx]
                child_set.add(p2[p2_idx])
        return child

    def _mutate(self, genome: List[int]):
        """複数箇所のSwap Mutation: ランダムな2〜3点を入れ替える"""
        if len(genome) < 2:
            return
        swap_count = random.randint(1, 3)
        for _ in range(swap_count):
            idx1, idx2 = random.sample(range(len(genome)), 2)
            genome[idx1], genome[idx2] = genome[idx2], genome[idx1]

    def _simulate(self, genome: List[int]):
        """配置の順序通りにVanningEngineに流し込み、結果をシミュレートする"""
        engine = VanningEngine(
            strategy_mode="ga", 
            prioritize_open_containers=True, 
            vanning_base_date=self.vanning_base_date
        )
        
        ordered_target_items = [
            copy.deepcopy(self.all_items[idx])
            for idx in genome
            if idx < self.num_targets
        ]
        ordered_forwardable_items = [
            copy.deepcopy(self.all_items[idx])
            for idx in genome
            if idx >= self.num_targets
        ]

        containers, next_pool, unused_forwardable = engine.run_time_axis_packing(
            ordered_target_items,
            ordered_forwardable_items,
            self.current_date,
            allow_partial_red_pull=True
        )
        score = self._evaluate_containers(containers, next_pool)
        return containers, next_pool, unused_forwardable, score

    def _evaluate_containers(self, containers: List[Container], next_pool: List[Item]) -> float:
        """
        GAの適応度関数（Fitness Function）
        このシステムの制約条件に基づいた多目的評価:
          - 体積充填率 80% 以上が最重要目標
          - コンテナ本数は少ないほど良い（コスト削減）
          - 必須荷物の積み残しは絶対NG
          - 重心が中心に近いほど安全
        """
        if not containers:
            return -100000.0
            
        score = 0.0
        for c in containers:
            vol_rate = c.fill_rate_volume
            
            # 1. 充填率の評価（80%以上は高評価、未満はペナルティ）
            if vol_rate >= VOLUME_TARGET_RATE:
                score += vol_rate * 10
            else:
                score -= (VOLUME_TARGET_RATE - vol_rate) * 50 
                
            # 2. 重心ズレのペナルティ（中心からの距離）
            cg_x, cg_y, cg_z = c.compute_cg()
            center_x = c.length / 2
            center_y = c.width / 2
            deviation_mm = ((cg_x - center_x)**2 + (cg_y - center_y)**2)**0.5
            score -= (deviation_mm / 1000.0) * 10

            # 3. 仕向け地の奥・手前ルール（X軸ブロック化ペナルティ）
            # X座標（奥行き）順に荷物を走査し、仕向け地が分断されている（サンドイッチ状態）なら減点
            items_sorted_by_x = sorted([i for i in c.items if i.x is not None], key=lambda i: i.x)
            seen_destinations = set()
            last_dest = None
            dest_penalty = 0
            
            for item in items_sorted_by_x:
                dest = getattr(item, 'destination', "")
                if not dest:
                    continue
                if dest != last_dest:
                    if dest in seen_destinations:
                        # 一度出現した仕向け地が、別の仕向け地を挟んで再度出現（荷降ろし困難）
                        dest_penalty += 1000
                    seen_destinations.add(dest)
                    last_dest = dest
            score -= dest_penalty
            
        # 4. 必須荷物の積み残しに対する特大ペナルティ
        score -= len(next_pool) * 20000
        
        # 5. コンテナ本数のペナルティ（少ない方が良い）
        score -= len(containers) * 5000
        
        return score
