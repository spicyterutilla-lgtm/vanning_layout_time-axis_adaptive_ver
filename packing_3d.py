from dataclasses import dataclass
from typing import List, Optional, Tuple
from models import Item, Container

@dataclass
class Space:
    """コンテナ内の「荷物が置ける空きスペース」を表現するクラス"""
    x: float
    y: float
    z: float
    length: float
    width: float
    height: float

class Packer3D:
    """
    3D空間の配置計算エンジン。
    「重なり禁止」「完全収容」「底面接地率100%（大きな箱の上に小さな箱）」を
    空間分割（Guillotine Split）アルゴリズムで保証する。
    """
    def __init__(self, container: Container):
        self.container = container
        # 初期状態はコンテナの全空間が1つの空きスペース
        self.free_spaces: List[Space] = [
            Space(0, 0, 0, container.length, container.width, container.height)
        ]

    def try_pack_item(self, item: Item) -> bool:
        """
        荷物を空きスペースのどこかに配置できるか試し、配置できれば座標を確定する。
        """
        # 1. 荷物の回転パターン（通常と90度回転）を作成
        orientations = [
            (item.length, item.width, False),
            (item.width, item.length, True)
        ]

        # 2. 空間を無駄なく使うため、Z(高さ) -> Y(左) -> X(奥) の順でソートして
        # 最も奥の床に近いスペースから埋めていく
        self.free_spaces.sort(key=lambda s: (s.z, s.x, s.y))

        for space in self.free_spaces:
            for l, w, is_rotated in orientations:
                if l <= space.length and w <= space.width and item.height <= space.height:
                    # このスペースに配置可能！
                    item.x = space.x
                    item.y = space.y
                    item.z = space.z
                    item.is_rotated = is_rotated
                    
                    # 空間を分割して更新する
                    self._split_space(space, l, w, item.height)
                    return True
                    
        return False # どの空きスペースにも入らなかった

    def _split_space(self, space: Space, item_l: float, item_w: float, item_h: float):
        """
        荷物を配置したことで失われた空間を取り除き、残りの空間を3つの新しい空間に分割する。
        （Guillotine Splitアルゴリズム）
        """
        self.free_spaces.remove(space)

        # 1. 箱の「真上」の空間（Top Space）
        # ※この空間は箱の L x W に完全に制限されるため、ここに積まれる荷物は
        # 必然的に「底面接地率100%（はみ出さない）」の制約を満たす。
        if space.height - item_h > 0:
            top_space = Space(
                x=space.x, 
                y=space.y, 
                z=space.z + item_h, 
                length=item_l, 
                width=item_w, 
                height=space.height - item_h
            )
            self.free_spaces.append(top_space)

        # 残りの「右」と「前」の空間をどう分割するか（最大面積が広くなるように分割）
        area_horizontal = space.length * (space.width - item_w)
        area_vertical = (space.length - item_l) * space.width

        if area_horizontal > area_vertical:
            # 水平（右側を広く）カット
            if space.width - item_w > 0:
                right_space = Space(space.x, space.y + item_w, space.z, space.length, space.width - item_w, space.height)
                self.free_spaces.append(right_space)
            if space.length - item_l > 0:
                front_space = Space(space.x + item_l, space.y, space.z, space.length - item_l, item_w, space.height)
                self.free_spaces.append(front_space)
        else:
            # 垂直（手前を広く）カット
            if space.width - item_w > 0:
                right_space = Space(space.x, space.y + item_w, space.z, item_l, space.width - item_w, space.height)
                self.free_spaces.append(right_space)
            if space.length - item_l > 0:
                front_space = Space(space.x + item_l, space.y, space.z, space.length - item_l, space.width, space.height)
                self.free_spaces.append(front_space)
