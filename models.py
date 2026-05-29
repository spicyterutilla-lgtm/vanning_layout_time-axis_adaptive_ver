import uuid
from dataclasses import dataclass, field
from typing import List, Optional
import datetime

@dataclass
class Item:
    """
    どんな入力フォーマットであっても、システム内部では必ずこのItemクラスとして扱う（共通フォーマット）
    """
    id: str                 # システム内部のユニークID
    original_id: str        # ユーザーのExcelにあったID（行番号や品番）
    name: str               # 品名（IPPC燻蒸Aなど）

    # --- 空間パラメータ ---
    length: float           # L (mm)
    width: float            # W (mm)
    height: float           # H (mm)
    weight: float           # 重量 (kg)

    # --- 時間軸（4D）パラメータ ---
    creation_date: datetime.date             # 納入予定日（コンテナへ積載可能になる日）
    due_date: datetime.date                  # バンニング完了期限（積込みを終える必要がある日）
    expiration_date: Optional[datetime.date] # 木箱などの寿命リミット（最大3週間 = 21日）
    request_code: str = ""                   # 依頼コード
    shipper: str = ""                        # 出荷者名
    consignee: str = ""                      # 受取者名
    destination: str = ""                    # 仕向け地
    part_code: str = ""                      # 部品コード
    vehicle_code: str = ""                   # 車両コード
    unpacked_weight: Optional[float] = None  # 梱包前重量 (kg)
    vessel_loading_date: Optional[datetime.date] = None  # 船積日
    priority: int = 50                       # 業務上の優先度（高いほど先に出す）
    allow_early_ship: bool = True            # 納期前の前倒し出荷を許可するか
    stackable: bool = True                    # 段積み可能か。Falseなら床置きかつ上載せ不可
    floor_only: bool = False                  # 重量物など、必ず床面に置く必要があるか
    rotation_allowed: bool = True             # 水平面で90度回転させて配置できるか
    separation_group: str = ""                # 同じ分離グループの荷物は同一コンテナに載せない

    # --- 3D配置（座標）パラメータ ---
    x: Optional[float] = None       # コンテナ奥からのX座標 (mm)
    y: Optional[float] = None       # コンテナ左からのY座標 (mm)
    z: Optional[float] = None       # コンテナ床面からのZ座標 (mm)
    is_rotated: bool = False        # 水平方向に90度回転しているか (Trueなら L と W が入れ替わる)

    # --- UI/マニュアルオーバーライド用フラグ ---
    is_locked: bool = False       # ユーザーが「このコンテナから動かすな」と手動でピン留めしたか
    force_ship: bool = False      # ユーザーが「赤字でも強制出荷する」と手動でマークしたか
    system_force_ship: bool = False # システムが納期/寿命優先で赤字強制出荷と判定したか
    status_msg: str = ""          # なぜその判断になったかの説明（透過性確保のため）
    selection_reason: str = ""     # Must / Forwardable / Future に分類された理由
    decision_reason: str = ""      # 最適化エンジンが採用/保留/強制出荷した判断根拠

    @property
    def volume_m3(self) -> float:
        """体積（立方メートル）"""
        return (self.length / 1000) * (self.width / 1000) * (self.height / 1000)

    @property
    def is_force_ship(self) -> bool:
        """手動・システムいずれかの理由で強制出荷されるか。"""
        return self.force_ship or self.system_force_ship

@dataclass
class Container:
    id: str
    max_weight: float = 22000.0   # いすゞ制約: 最大積載量 22,000kg

    # いすゞロジスティクス実務上の有効内寸（カタログ値ではなく、作業余裕を引いた制限）(mm)
    length: float = 12000.0
    width: float = 2300.0
    height: float = 2400.0

    vanning_date: Optional[datetime.date] = None # バンニング実施予定日

    items: List[Item] = field(default_factory=list)

    @property
    def max_volume_m3(self) -> float:
        return (self.length / 1000) * (self.width / 1000) * (self.height / 1000)

    @property
    def current_weight(self) -> float:
        return sum(item.weight for item in self.items)

    @property
    def current_volume_m3(self) -> float:
        return sum(item.volume_m3 for item in self.items)

    @property
    def fill_rate_weight(self) -> float:
        """重量の充填率 (%)"""
        return (self.current_weight / self.max_weight) * 100 if self.max_weight > 0 else 0

    @property
    def fill_rate_volume(self) -> float:
        """体積の充填率 (%)"""
        return (self.current_volume_m3 / self.max_volume_m3) * 100 if self.max_volume_m3 > 0 else 0

    def compute_cg(self):
        """重心 (x_cg, y_cg, z_cg) を計算する"""
        if not self.items:
            return self.length / 2, self.width / 2, self.height / 2

        total_w = sum(i.weight for i in self.items)
        if total_w == 0:
            return self.length / 2, self.width / 2, self.height / 2

        sum_x = 0.0
        sum_y = 0.0
        sum_z = 0.0

        for i in self.items:
            # Python内部での回転状態に応じた実効サイズ
            l_eff = i.width if i.is_rotated else i.length
            w_eff = i.length if i.is_rotated else i.width
            h_eff = i.height

            x = i.x if i.x is not None else 0
            y = i.y if i.y is not None else 0
            z = i.z if i.z is not None else 0

            sum_x += i.weight * (x + l_eff / 2)
            sum_y += i.weight * (y + w_eff / 2)
            sum_z += i.weight * (z + h_eff / 2)

        return sum_x / total_w, sum_y / total_w, sum_z / total_w
