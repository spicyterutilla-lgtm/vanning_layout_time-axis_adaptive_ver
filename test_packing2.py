import numpy as np
from numba_packing import get_best_space, split_space, prune_free_spaces

spaces = np.zeros((100, 7), dtype=np.float64)
spaces[0] = [0, 0, 0, 12000, 2300, 2400, -1]
num_spaces = 1

items = [(1200, 1000, 1000, 100)] * 5

def my_get_best_space(spaces, num_spaces, item_l, item_w, item_h, item_weight, floor_only):
    best_score_0 = 999
    best_score_1 = 999999.0
    best_score_2 = 999999.0
    best_score_3 = 999999.0
    best_score_4 = 999999.0 # We will use l_max here
    best_space_idx = -1
    best_l = 0.0
    best_w = 0.0
    best_is_rotated = False

    for i in range(num_spaces):
        sx, sy, sz, sl, sw, sh, s_mw = spaces[i]
        
        for (l, w, is_rot) in [(item_l, item_w, False), (item_w, item_l, True)]:
            if l <= sl + 1e-5 and w <= sw + 1e-5 and item_h <= sh + 1e-5:
                leftover_l = sl - l
                leftover_w = sw - w
                leftover_vol = (sl * sw * sh) - (l * w * item_h)
                footprint_waste = (sl * sw) - (l * w)
                
                is_perfect_footprint = footprint_waste < 0.1
                is_perfect_vol = leftover_vol < 0.1
                if is_perfect_vol: p_score = 0
                elif is_perfect_footprint: p_score = 1
                else: p_score = 2
                
                better = False
                if p_score < best_score_0: better = True
                elif p_score == best_score_0:
                    if sz < best_score_1: better = True
                    elif sz == best_score_1:
                        if footprint_waste < best_score_2: better = True
                        elif footprint_waste == best_score_2:
                            if leftover_vol < best_score_3: better = True
                            elif leftover_vol == best_score_3:
                                l_max = max(leftover_l, leftover_w)
                                if l_max < best_score_4: better = True
                                
                if better:
                    best_score_0 = p_score
                    best_score_1 = sz
                    best_score_2 = footprint_waste
                    best_score_3 = leftover_vol
                    best_score_4 = max(leftover_l, leftover_w)
                    best_space_idx = i
                    best_l = l
                    best_w = w
                    best_is_rotated = is_rot
    return best_space_idx, best_l, best_w, best_is_rotated

for i, (il, iw, ih, iw_wt) in enumerate(items):
    idx, l, w, rot = my_get_best_space(spaces, num_spaces, float(il), float(iw), float(ih), float(iw_wt), False)
    if idx == -1:
        print(f"Item {i} could not be placed")
        continue
    sx, sy, sz = spaces[idx, 0], spaces[idx, 1], spaces[idx, 2]
    print(f"Item {i}: rot={rot}, placed at ({sx}, {sy}, {sz}), size ({l}, {w})")
    
    num_spaces = split_space(spaces, num_spaces, idx, l, w, float(ih), float(iw_wt), False, 100)
    num_spaces = prune_free_spaces(spaces, num_spaces)
