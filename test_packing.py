import numpy as np
from numba_packing import get_best_space, split_space, prune_free_spaces

spaces = np.zeros((100, 7), dtype=np.float64)
spaces[0] = [0, 0, 0, 12000, 2300, 2400, -1]
num_spaces = 1

items = [(1200, 1000, 1000, 100)] * 5

for i, (il, iw, ih, iw_wt) in enumerate(items):
    idx, l, w, rot = get_best_space(spaces, num_spaces, float(il), float(iw), float(ih), float(iw_wt), False)
    if idx == -1:
        print(f"Item {i} could not be placed")
        continue
    sx, sy, sz = spaces[idx, 0], spaces[idx, 1], spaces[idx, 2]
    print(f"Item {i}: rot={rot}, placed at ({sx}, {sy}, {sz}), size ({l}, {w})")
    
    num_spaces = split_space(spaces, num_spaces, idx, l, w, float(ih), float(iw_wt), False, 100)
    num_spaces = prune_free_spaces(spaces, num_spaces)
