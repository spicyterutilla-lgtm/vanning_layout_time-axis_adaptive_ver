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
    creation_date: datetime.date             # 梱包完了日（倉庫に入った日）
    due_date: datetime.date                  # 納期（絶対に出荷しなければならない日）
    expiration_date: Optional[datetime.date] # 木箱などの寿命リミット（最大3週間 = 21日）
    
    # --- 3D配置（座標）パラメータ ---
    x: Optional[float] = None       # コンテナ奥からのX座標 (mm)
    y: Optional[float] = None       # コンテナ左からのY座標 (mm)
    z: Optional[float] = None       # コンテナ床面からのZ座標 (mm)
    is_rotated: bool = False        # 水平方向に90度回転しているか (Trueなら L と W が入れ替わる)
    
    # --- UI/マニュアルオーバーライド用フラグ ---
    is_locked: bool = False       # ユーザーが「このコンテナから動かすな」と手動でピン留めしたか
    force_ship: bool = False      # システムまたはユーザーが「赤字でも強制出荷する」とマークしたか
    status_msg: str = ""          # なぜその判断になったかの説明（透過性確保のため）

    @property
    def volume_m3(self) -> float:
        """体積（立方メートル）"""
        return (self.length / 1000) * (self.width / 1000) * (self.height / 1000)

@dataclass
class Container:
    id: str
    max_weight: float = 22000.0   # いすゞ制約: 最大積載量 22,000kg
    
    # 40ft HCコンテナの標準的な内寸 (mm) - 後でより正確な値に調整可能
    length: float = 12032.0
    width: float = 2352.0
    height: float = 2698.0
    
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
