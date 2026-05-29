import numpy as np
from numba import njit

@njit
def get_best_space(
    spaces, num_spaces, 
    item_l, item_w, item_h, item_weight, floor_only, allow_rotation
):
    best_score_0 = 999
    best_score_1 = 999999.0
    best_score_2 = 999999.0
    best_score_3 = 999999.0
    best_score_4 = -1.0
    best_score_5 = 999999.0
    best_score_6 = 999999.0
    best_score_7 = 999999.0
    best_score_8 = 999999.0
    
    best_space_idx = -1
    best_l = 0.0
    best_w = 0.0
    best_is_rotated = False
    
    for i in range(num_spaces):
        sx = spaces[i, 0]
        sy = spaces[i, 1]
        sz = spaces[i, 2]
        sl = spaces[i, 3]
        sw = spaces[i, 4]
        sh = spaces[i, 5]
        s_mw = spaces[i, 6]
        
        if floor_only and sz > 0.001:
            continue
            
        if sz > 0.001 and s_mw >= 0.0 and item_weight > s_mw:
            continue

        rotations_to_try = [(item_l, item_w, False)]
        if allow_rotation and abs(item_l - item_w) > 1e-5:
            rotations_to_try.append((item_w, item_l, True))

        for (l, w, is_rot) in rotations_to_try:
            if l <= sl + 1e-5 and w <= sw + 1e-5 and item_h <= sh + 1e-5:
                leftover_l = sl - l
                leftover_w = sw - w
                leftover_h = sh - item_h
                leftover_vol = (sl * sw * sh) - (l * w * item_h)
                footprint_waste = (sl * sw) - (l * w)
                split_balance = abs(leftover_l - leftover_w)
                
                is_perfect_footprint = footprint_waste < 0.1
                is_perfect_volume = leftover_vol < 0.1
                
                if is_perfect_volume:
                    p_score = 0
                elif is_perfect_footprint:
                    p_score = 1
                else:
                    p_score = 2
                    
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
                                if l_max > best_score_4: better = True
                                elif l_max == best_score_4:
                                    if split_balance < best_score_5: better = True
                                    elif split_balance == best_score_5:
                                        if leftover_h < best_score_6: better = True
                                        elif leftover_h == best_score_6:
                                            if sx < best_score_7: better = True
                                            elif sx == best_score_7:
                                                if sy < best_score_8: better = True
                                                
                if better:
                    best_score_0 = p_score
                    best_score_1 = sz
                    best_score_2 = footprint_waste
                    best_score_3 = leftover_vol
                    best_score_4 = max(leftover_l, leftover_w)
                    best_score_5 = split_balance
                    best_score_6 = leftover_h
                    best_score_7 = sx
                    best_score_8 = sy
                    
                    best_space_idx = i
                    best_l = l
                    best_w = w
                    best_is_rotated = is_rot
                    
    return best_space_idx, best_l, best_w, best_is_rotated


@njit
def split_space(spaces, num_spaces, space_idx, item_l, item_w, item_h, item_weight, stackable, max_spaces):
    sx = spaces[space_idx, 0]
    sy = spaces[space_idx, 1]
    sz = spaces[space_idx, 2]
    sl = spaces[space_idx, 3]
    sw = spaces[space_idx, 4]
    sh = spaces[space_idx, 5]
    s_mw = spaces[space_idx, 6]
    
    spaces[space_idx] = spaces[num_spaces - 1]
    num_spaces -= 1
    
    if stackable and sh - item_h > 0.001:
        if num_spaces < max_spaces:
            spaces[num_spaces, 0] = sx
            spaces[num_spaces, 1] = sy
            spaces[num_spaces, 2] = sz + item_h
            spaces[num_spaces, 3] = item_l
            spaces[num_spaces, 4] = item_w
            spaces[num_spaces, 5] = sh - item_h
            spaces[num_spaces, 6] = item_weight
            num_spaces += 1
            
    area_horizontal = sl * (sw - item_w)
    area_vertical = (sl - item_l) * sw
    
    if area_horizontal > area_vertical:
        if sw - item_w > 0.001 and num_spaces < max_spaces:
            spaces[num_spaces, 0] = sx
            spaces[num_spaces, 1] = sy + item_w
            spaces[num_spaces, 2] = sz
            spaces[num_spaces, 3] = sl
            spaces[num_spaces, 4] = sw - item_w
            spaces[num_spaces, 5] = sh
            spaces[num_spaces, 6] = s_mw
            num_spaces += 1
        if sl - item_l > 0.001 and num_spaces < max_spaces:
            spaces[num_spaces, 0] = sx + item_l
            spaces[num_spaces, 1] = sy
            spaces[num_spaces, 2] = sz
            spaces[num_spaces, 3] = sl - item_l
            spaces[num_spaces, 4] = item_w
            spaces[num_spaces, 5] = sh
            spaces[num_spaces, 6] = s_mw
            num_spaces += 1
    else:
        if sw - item_w > 0.001 and num_spaces < max_spaces:
            spaces[num_spaces, 0] = sx
            spaces[num_spaces, 1] = sy + item_w
            spaces[num_spaces, 2] = sz
            spaces[num_spaces, 3] = item_l
            spaces[num_spaces, 4] = sw - item_w
            spaces[num_spaces, 5] = sh
            spaces[num_spaces, 6] = s_mw
            num_spaces += 1
        if sl - item_l > 0.001 and num_spaces < max_spaces:
            spaces[num_spaces, 0] = sx + item_l
            spaces[num_spaces, 1] = sy
            spaces[num_spaces, 2] = sz
            spaces[num_spaces, 3] = sl - item_l
            spaces[num_spaces, 4] = sw
            spaces[num_spaces, 5] = sh
            spaces[num_spaces, 6] = s_mw
            num_spaces += 1
            
    return num_spaces

@njit
def contains_space(o_x, o_y, o_z, o_l, o_w, o_h, i_x, i_y, i_z, i_l, i_w, i_h):
    return (o_x <= i_x + 0.001 and 
            o_y <= i_y + 0.001 and 
            o_z <= i_z + 0.001 and 
            o_x + o_l + 0.001 >= i_x + i_l and 
            o_y + o_w + 0.001 >= i_y + i_w and 
            o_z + o_h + 0.001 >= i_z + i_h)

@njit
def prune_free_spaces(spaces, num_spaces):
    keep = np.ones(num_spaces, dtype=np.bool_)
    
    for i in range(num_spaces):
        i_x, i_y, i_z, i_l, i_w, i_h = spaces[i, :6]
        
        contained = False
        for j in range(num_spaces):
            if i == j: continue
            o_x, o_y, o_z, o_l, o_w, o_h = spaces[j, :6]
            
            if contains_space(o_x, o_y, o_z, o_l, o_w, o_h, i_x, i_y, i_z, i_l, i_w, i_h):
                same_space = (abs(i_x - o_x) < 0.001 and 
                              abs(i_y - o_y) < 0.001 and 
                              abs(i_z - o_z) < 0.001 and 
                              abs(i_l - o_l) < 0.001 and 
                              abs(i_w - o_w) < 0.001 and 
                              abs(i_h - o_h) < 0.001)
                              
                if not same_space or j < i:
                    contained = True
                    break
        if contained:
            keep[i] = False
            
    new_num = 0
    for i in range(num_spaces):
        if keep[i]:
            spaces[new_num] = spaces[i]
            new_num += 1
            
    return new_num

@njit
def probe_can_pack(spaces, num_spaces, item_l, item_w, item_h, item_weight, floor_only, allow_rotation):
    for i in range(num_spaces):
        sz = spaces[i, 2]
        sl = spaces[i, 3]
        sw = spaces[i, 4]
        sh = spaces[i, 5]
        s_mw = spaces[i, 6]
        
        if floor_only and sz > 0.001:
            continue
            
        if sz > 0.001 and s_mw >= 0.0 and item_weight > s_mw:
            continue

        if item_l <= sl + 1e-5 and item_w <= sw + 1e-5 and item_h <= sh + 1e-5:
            return True
        if allow_rotation and item_w <= sl + 1e-5 and item_l <= sw + 1e-5 and item_h <= sh + 1e-5:
            return True
            
    return False
