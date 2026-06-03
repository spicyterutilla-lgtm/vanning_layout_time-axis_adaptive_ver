import numpy as np
from typing import List
from models import Item, Container
from numba_packing import get_best_space, split_space, prune_free_spaces, probe_can_pack

class Packer3D:
    """
    Numbaベースの3D空間の配置計算エンジン。
    Pythonループを排除し、C言語相当の速度でGuillotine Splitアルゴリズムを実行する。
    """
    def __init__(self, container: Container):
        self.container = container
        self.max_spaces = 10000
        # 空間情報はNumpy配列: [x, y, z, length, width, height, max_supported_weight]
        self.spaces = np.zeros((self.max_spaces, 7), dtype=np.float64)

        self.spaces[0, 0] = 0.0
        self.spaces[0, 1] = 0.0
        self.spaces[0, 2] = 0.0
        self.spaces[0, 3] = container.length
        self.spaces[0, 4] = container.width
        self.spaces[0, 5] = container.height
        self.spaces[0, 6] = -1.0 # None
        self.num_spaces = 1

    def try_pack_item(self, item: Item) -> bool:
        idx, l, w, is_rot = get_best_space(
            self.spaces, self.num_spaces,
            float(item.length), float(item.width), float(item.height),
            float(item.weight), bool(item.floor_only), bool(item.rotation_allowed)
        )

        if idx == -1:
            return False

        item.x = float(self.spaces[idx, 0])
        item.y = float(self.spaces[idx, 1])
        item.z = float(self.spaces[idx, 2])
        item.is_rotated = bool(is_rot)

        self.num_spaces = split_space(
            self.spaces, self.num_spaces, idx,
            l, w, float(item.height), float(item.weight),
            bool(item.stackable), self.max_spaces
        )
        self.num_spaces = prune_free_spaces(self.spaces, self.num_spaces)
        return True

    def can_pack_item_probe(self, item: Item) -> bool:
        return probe_can_pack(
            self.spaces, self.num_spaces,
            float(item.length), float(item.width), float(item.height),
            float(item.weight), bool(item.floor_only), bool(item.rotation_allowed)
        )
