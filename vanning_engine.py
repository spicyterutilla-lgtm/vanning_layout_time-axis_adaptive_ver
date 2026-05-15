import uuid
import datetime
from typing import List, Tuple, Dict
from models import Item, Container
from packing_3d import Packer3D

class VanningEngine:
    """
    バンニング計算コアエンジン（第3フェーズ：3D配置・時間軸操作対応版）
    """
    def __init__(self):
        # 各コンテナの3D空間状態を管理するパッカー
        self.packers: Dict[str, Packer3D] = {}

    def _can_pack(self, container: Container, item: Item) -> bool:
        """重量制約と3D座標での当たり判定（完全収容・底面接地率100%）"""
        # 1. 重量チェック
        if container.current_weight + item.weight > container.max_weight:
            return False
            
        # 2. 3D配置判定（パズルの計算）
        if container.id not in self.packers:
            self.packers[container.id] = Packer3D(container)
            
        packer = self.packers[container.id]
        
        # packer.try_pack_item は、空間に空きがあれば座標(x,y,z)を確定させてTrueを返す
        return packer.try_pack_item(item)

    def run_basic_packing(self, items: List[Item]) -> Tuple[List[Container], List[Item]]:
        """基本パッキングロジック（単一期間）"""
        containers: List[Container] = []
        unpacked_items: List[Item] = []
        
        # ユーザー要望反映：
        # 「重量優先だとコンテナがスカスカになる」問題への対応として、
        # 「比重（1m3あたりの重量）」が軽い（＝フワフワした）荷物から優先して詰める。
        # 比重が同じ場合は、空間の断片化を防ぐため「体積が大きいもの」から詰める。
        sorted_items = sorted(items, key=lambda x: (x.weight / x.volume_m3 if x.volume_m3 > 0 else float('inf'), -x.volume_m3))
        
        for item in sorted_items:
            placed = False
            for container in containers:
                if self._can_pack(container, item):
                    container.items.append(item)
                    placed = True
                    break
            
            if not placed:
                new_container = Container(id=f"C-{len(containers) + 1:03d}")
                if self._can_pack(new_container, item):
                    new_container.items.append(item)
                    containers.append(new_container)
                else:
                    unpacked_items.append(item)
                    
        return containers, unpacked_items

    def run_time_axis_packing(self, target_items: List[Item], future_items: List[Item], current_date: datetime.date) -> Tuple[List[Container], List[Item], List[Item]]:
        """
        時間軸（前倒し・繰り越し）を考慮したバンニング実行。
        戻り値: (確定コンテナリスト, 次回への保留プール, 使わなかった未来の荷物)
        """
        # 1. まず対象の荷物だけで普通に詰める
        containers, unpacked = self.run_basic_packing(target_items)
        
        final_containers = []
        next_pool = unpacked.copy() # 基本ロジックで溢れたものは無条件でプールへ
        remaining_future = future_items.copy()

        # 2. 各コンテナの充填率を評価し、時間軸操作（Pull/Push）を試みる
        for container in containers:
            is_red_ink = container.fill_rate_weight < 80.0 and container.fill_rate_volume < 80.0
            
            if is_red_ink:
                # --- 🟢 PULL (前倒し) の試み ---
                # 未来の荷物から入りそうなものを探し、充填率80%を目指す
                pulled_items = []
                for f_item in list(remaining_future):
                    if self._can_pack(container, f_item):
                        container.items.append(f_item)
                        pulled_items.append(f_item)
                        remaining_future.remove(f_item)
                        f_item.status_msg = f"前倒し補填（元納期: {f_item.due_date.strftime('%m/%d')}）"
                        # 80%を超えたら前倒し完了
                        if container.fill_rate_weight >= 80.0 or container.fill_rate_volume >= 80.0:
                            break

            # Pull後もまだ赤字かチェック
            is_still_red_ink = container.fill_rate_weight < 80.0 and container.fill_rate_volume < 80.0

            if is_still_red_ink:
                # --- 🟡 PUSH (繰り越し/保留) の試み ---
                # コンテナ内の全荷物が「来週(7日後)まで待てるか」判定する
                can_wait = True
                next_week = current_date + datetime.timedelta(days=7)
                
                for item in container.items:
                    # 納期アウト、木箱寿命アウト、または手動で「強制出荷(force_ship)」フラグが立っているなら待てない
                    if item.force_ship or item.due_date < next_week or (item.expiration_date and item.expiration_date < next_week):
                        can_wait = False
                        break
                
                if can_wait:
                    # 待てるなら、このコンテナは出荷せず中身を全てプールへ戻す（コンテナ破棄）
                    for item in container.items:
                        item.status_msg = "充填率不足のため保留プールへ繰り越し"
                        # 繰り越すため確定していた3D座標をリセット
                        item.x = item.y = item.z = None
                        next_pool.append(item)
                    continue # final_containers には追加しない
                else:
                    # 待てないなら、赤字覚悟で強制出荷
                    for item in container.items:
                        item.force_ship = True
                        item.status_msg = "納期/寿命優先のため赤字強制出荷"

            # 正常、Pullで回復、または強制出荷のコンテナを確定リストへ
            final_containers.append(container)

        return final_containers, next_pool, remaining_future

if __name__ == "__main__":
    from data_loader import DataLoader
    
    loader = DataLoader()
    try:
        items = loader.load_from_excel("(抜粋)ケースリスト.xlsx", sheet_name=0)
        
        # テストのため、データを「今週分(前半分)」と「未来分(後半分)」に分割
        target_items = items[:20]
        future_items = items[20:]
        current_date = datetime.date.today()
        
        engine = VanningEngine()
        containers, pool, left_future = engine.run_time_axis_packing(target_items, future_items, current_date)
        
        print("\n=== バンニング計算結果（第2フェーズ：時間軸操作） ===")
        print(f" [確定コンテナ数]: {len(containers)} 本")
        print(f" [保留プール送り]: {len(pool)} 個の荷物")
        print(f" [未来の残り荷物]: {len(left_future)} 個\n")
        
        for c in containers:
            is_alert = c.fill_rate_weight < 80.0 and c.fill_rate_volume < 80.0
            alert_str = "[ALERT: 強制出荷]" if is_alert else "[OK: 80%クリア]"
            
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
