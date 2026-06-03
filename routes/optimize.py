import copy
import time
import datetime
from flask import request, jsonify
from services.session import SESSION_DATA, build_valid_items, reset_runtime_state
from services.validation import classify_items_for_day, validate_container_geometry
from services.utils import (
    read_bounded_int, parse_base_date, order_containers_for_output,
    build_efficiency_summary, build_review_queue, build_container_alert_summary
)
from vanning_engine import VanningEngine, LARGE_PLAN_ITEM_THRESHOLD
from metaheuristics_engine import GeneticAlgorithmOptimizer
import math

def handle_baseline():
    data = request.get_json(silent=True) or {}
    base_date_str = data.get('base_date')
    must_ship_window_days = 21
    
    current_date, date_error = parse_base_date(base_date_str)
    if date_error:
        return jsonify({'error': date_error}), 400

    items = SESSION_DATA.get("items", [])
    valid_items, invalid_item_ids = build_valid_items()
    if not valid_items:
        return jsonify({'error': '積載可能な有効データがありません。'}), 400

    day_groups = classify_items_for_day(valid_items, current_date, must_ship_window_days)
    target_items = day_groups["must_ship"]
    
    total_volume_m3 = 0
    for item in target_items:
        w = 0 if item.width is None or math.isnan(item.width) else item.width
        l = 0 if item.length is None or math.isnan(item.length) else item.length
        h = 0 if item.height is None or math.isnan(item.height) else item.height
        vol = (w * l * h) / 1_000_000_000
        total_volume_m3 += vol

    if math.isnan(total_volume_m3):
        total_volume_m3 = 0

    theoretical_min = int(total_volume_m3 / 60.0) if total_volume_m3 > 0 else 0
    theoretical_min = max(1, theoretical_min) if total_volume_m3 > 0 else 0
    greedy_estimate = int(total_volume_m3 / 40.0) if total_volume_m3 > 0 else 0
    greedy_estimate = max(1, greedy_estimate) if total_volume_m3 > 0 else 0

    return jsonify({
        'target_items_count': len(target_items),
        'total_volume_m3': round(total_volume_m3, 1),
        'theoretical_min': theoretical_min,
        'greedy_estimate': greedy_estimate
    })

def handle_optimize():
    start_time = time.time()
    data = request.get_json(silent=True) or {}
    base_date_str = data.get('base_date')
    optimization_mode = data.get('optimization_mode', 'fast')
    # 情報受領日（計算基準日）から船積日までの21日間を積込対象ウィンドウとして固定
    must_ship_window_days = 21
    
    current_date, date_error = parse_base_date(base_date_str)
    if date_error:
        return jsonify({'error': date_error}), 400

    items = SESSION_DATA.get("items", [])
    if not items:
        return jsonify({'error': 'データがありません'}), 400

    valid_items, invalid_item_ids = build_valid_items()
    if not valid_items:
        return jsonify({'error': '積載可能な有効データがありません。入力データのエラーを確認してください。'}), 400

    reset_runtime_state(items)
    day_groups = classify_items_for_day(valid_items, current_date, must_ship_window_days)
    target_items = day_groups["must_ship"]
    forwardable_items = day_groups["forwardable"]

    if not target_items and not forwardable_items:
        return jsonify({'error': '現在の基準日では積載対象となる荷物が0件です。基準日を変更するか、別のデータをアップロードしてください。'}), 400

    alternative_items = (
        (copy.deepcopy(target_items), copy.deepcopy(forwardable_items))
        if 0 < len(target_items) < LARGE_PLAN_ITEM_THRESHOLD
        else None
    )

    vessel_loading_date = current_date + datetime.timedelta(days=21)
    engine = VanningEngine(vanning_base_date=vessel_loading_date)

    # ── 常に近似値モード（高速）を先に実行 ──
    containers, pool, unused_forwardable = engine.run_time_axis_packing(
        target_items,
        forwardable_items,
        current_date,
        allow_partial_red_pull=True
    )
    if alternative_items and any(c.fill_rate_volume < 80.0 for c in containers):
        alternative_engine = VanningEngine(prioritize_open_containers=False, vanning_base_date=vessel_loading_date)
        alternative_containers, alternative_pool, alternative_unused = alternative_engine.run_time_axis_packing(
            alternative_items[0],
            alternative_items[1],
            current_date,
            allow_partial_red_pull=True
        )
        if alternative_engine._packing_result_score(alternative_containers, alternative_pool) < engine._packing_result_score(containers, pool):
            engine = alternative_engine
            containers = alternative_containers
            pool = alternative_pool
            unused_forwardable = alternative_unused

    # ── 深層モード: 近似値モードの結果をエリートとしてGAに渡す ──
    if optimization_mode == "deep":
        try:
            SESSION_DATA["ga_status"] = {"generation": 0, "best_score": 0}

            def ga_progress_callback(gen, score):
                SESSION_DATA["ga_status"]["generation"] = gen
                SESSION_DATA["ga_status"]["best_score"] = score

            ga = GeneticAlgorithmOptimizer(
                target_items=copy.deepcopy(target_items),
                forwardable_items=copy.deepcopy(forwardable_items),
                current_date=current_date,
                vanning_base_date=vessel_loading_date,
                baseline_containers=containers,
                baseline_pool=pool,
                baseline_unused=unused_forwardable,
                time_limit_seconds=60,      # 高レベル探索のため制限時間を延長 (30 -> 60)
                population_size=100,        # Numbaによる高速化の恩恵を活かし個体数を大幅増 (20 -> 100)
                progress_callback=ga_progress_callback
            )
            containers, pool, unused_forwardable = ga.run()
            SESSION_DATA["ga_status"]["finished"] = True
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Deep Optimization Failed: {str(e)}'}), 500

    containers = order_containers_for_output(containers)
    for idx, c in enumerate(containers, 1):
        c.display_order = idx
        c.id = f"C-{idx:03d}"

    SESSION_DATA["last_containers"] = containers
    SESSION_DATA["last_base_date"] = current_date
    SESSION_DATA["last_must_ship_window_days"] = must_ship_window_days

    alert_containers = sum(1 for c in containers if c.fill_rate_volume < 80.0)
    efficiency_summary = build_efficiency_summary(containers)
    geometry_results = [validate_container_geometry(container) for container in containers]
    geometry_warning_count = sum(result["warning_count"] for result in geometry_results)
    optimization_summary = {
        **efficiency_summary,
        "selected_strategy": engine.last_packing_strategy,
        "strategy_trials": engine.strategy_trials,
        "strategy_trial_count": len(engine.strategy_trials),
        "deep_strategy_trials": engine.deep_strategy_trials,
        "deep_strategy_trial_count": len(engine.deep_strategy_trials),
        "alert_pool_strategy": engine.alert_pool_strategy,
        "geometry_valid": geometry_warning_count == 0,
        "geometry_warning_count": geometry_warning_count,
    }
    SESSION_DATA["last_optimization_summary"] = optimization_summary

    alert_summaries = {}
    for c in containers:
        alert_summaries[c.id] = build_container_alert_summary(c, current_date, must_ship_window_days)
    SESSION_DATA["last_alert_summaries"] = alert_summaries

    review_queue = build_review_queue(
        pool_items=pool,
        unused_forwardable=unused_forwardable,
        hold_items=day_groups.get("hold", []),
        future_items=day_groups.get("future", []),
        current_date=current_date,
        limit=50
    )
    SESSION_DATA["last_review_queue"] = review_queue

    response_containers = []
    packed_item_ids = set()
    for c in containers:
        c_dict = {
            "id": c.id,
            "display_order": c.display_order,
            "volume_rate": c.fill_rate_volume,
            "weight_val": c.current_weight,
            "weight_max": c.max_weight,
            "is_alert": c.fill_rate_volume < 80.0,
            "cg_x": c.compute_cg()[0],
            "cg_y": c.compute_cg()[1],
            "cg_z": c.compute_cg()[2],
            "items": []
        }
        for item in c.items:
            packed_item_ids.add(item.id)
            c_dict["items"].append({
                "id": item.id,
                "name": item.name,
                "destination": item.destination,
                "l": item.length,
                "w": item.width,
                "h": item.height,
                "x": item.x,
                "y": item.y,
                "z": item.z,
                "rotated": item.is_rotated,
                "is_force_ship": item.force_ship,
                "is_manual_force_ship": item.force_ship and not getattr(item, 'system_force_ship', False),
                "status_msg": item.status_msg,
                "weight": item.weight,
                "volume_m3": item.volume_m3,
                "due_date": item.due_date.strftime('%m/%d') if getattr(item, 'due_date', None) else ""
            })
        response_containers.append(c_dict)

    updated_items_map = {item.id: item for item in pool + unused_forwardable}
    response_unused = []
    for item in valid_items:
        if item.id not in packed_item_ids:
            current_item = updated_items_map.get(item.id, item)
            response_unused.append({
                "id": current_item.id,
                "name": current_item.name,
                "destination": current_item.destination,
                "l": current_item.length,
                "w": current_item.width,
                "h": current_item.height,
                "weight": current_item.weight,
                "volume_m3": current_item.volume_m3,
                "is_force_ship": current_item.force_ship,
                "status_msg": current_item.status_msg,
                "due_date": current_item.due_date.strftime('%m/%d') if getattr(current_item, 'due_date', None) else ""
            })

    return jsonify({
        "containers": response_containers,
        "unused_items": response_unused,
        "planning_conditions": {
            "base_date": current_date.isoformat(),
        },
        "alert_containers": alert_containers,
        "optimization_summary": optimization_summary,
        "layout_improvements": {
            **engine.layout_improvement_stats,
            "improved_alert_containers": (
                engine.layout_improvement_stats["consolidated_containers"]
                + engine.layout_improvement_stats["rescued_alert_containers"]
                + engine.layout_improvement_stats["bundled_rescue_containers"]
                + engine.layout_improvement_stats["pair_repacked_alert_containers"]
                + engine.layout_improvement_stats["pooled_repack_alert_containers"]
            ),
        },
        "total_pulls": sum(
            1 for c in containers for i in c.items if i.status_msg and "前倒し" in i.status_msg
        ),
        "inventory_stats": {
            "total_valid_items": len(valid_items),
            "must_ship_count": len(target_items),
            "forwardable_count": len(forwardable_items),
            "future_count": len(day_groups["future"])
        },
        "execution_time_seconds": round(time.time() - start_time, 2)
    })

def handle_override():
    data = request.get_json(silent=True) or {}
    item_ids = data.get('item_ids', [])
    force_ship = bool(data.get('force_ship', False))

    if not item_ids:
        return jsonify({'error': 'アイテムIDが指定されていません'}), 400

    items = SESSION_DATA.get("items", [])
    updated = 0
    for item in items:
        if item.id in item_ids:
            item.force_ship = force_ship
            updated += 1

    if updated == 0:
        return jsonify({'error': '指定されたアイテムが見つかりません'}), 404

    return jsonify({'message': f'{updated}件のアイテムを更新しました'})

def handle_ga_status():
    status = SESSION_DATA.get("ga_status", {})
    return jsonify(status)

def handle_manual_edit():
    data = request.get_json(silent=True) or {}
    container_id = data.get('container_id')
    action = data.get('action') # "remove" or "add"
    item_id = data.get('item_id')

    if not container_id or not action or not item_id:
        return jsonify({'error': '必要なパラメータが不足しています'}), 400

    containers = SESSION_DATA.get("last_containers", [])
    valid_items, _ = build_valid_items()
    
    target_c = next((c for c in containers if c.id == container_id), None)
    if not target_c:
        return jsonify({'error': 'コンテナが見つかりません'}), 404

    target_item = next((i for i in valid_items if i.id == item_id), None)
    if not target_item:
        return jsonify({'error': 'アイテムが見つかりません'}), 404

    if "undo_stacks" not in SESSION_DATA:
        SESSION_DATA["undo_stacks"] = {}
    if "redo_stacks" not in SESSION_DATA:
        SESSION_DATA["redo_stacks"] = {}
    
    if container_id not in SESSION_DATA["undo_stacks"]:
        SESSION_DATA["undo_stacks"][container_id] = []
    
    # 変更前の状態をUndoスタックに積む
    SESSION_DATA["undo_stacks"][container_id].append(copy.deepcopy(target_c))
    if container_id in SESSION_DATA.get("redo_stacks", {}):
        SESSION_DATA["redo_stacks"][container_id] = []

    from vanning_engine import VanningEngine
    engine = VanningEngine(strategy_mode="fast")

    if action == "remove":
        target_c.items = [i for i in target_c.items if i.id != item_id]
    elif action == "add":
        if any(i.id == item_id for i in target_c.items):
            SESSION_DATA["undo_stacks"][container_id].pop()
            return jsonify({'error': 'すでに積載されています'}), 400
        target_item_copy = copy.deepcopy(target_item)
        target_item_copy.status_msg = "手動追加"
        target_c.items.append(target_item_copy)
    elif action == "reorder":
        items_order = data.get("items_order", [])
        if not items_order:
            SESSION_DATA["undo_stacks"][container_id].pop()
            return jsonify({'error': '順序データがありません'}), 400
        
        # 新しい順序に従ってアイテムを並び替え
        item_map = {i.id: i for i in target_c.items}
        new_items = []
        for iid in items_order:
            if iid in item_map:
                new_items.append(item_map[iid])
        
        # もしフロントエンドから送られてきたID以外にも要素があれば後ろに付ける
        for i in target_c.items:
            if i.id not in items_order:
                new_items.append(i)
        
        target_c.items = new_items
    else:
        SESSION_DATA["undo_stacks"][container_id].pop()
        return jsonify({'error': '不正なアクションです'}), 400

    # 3D再パッキング (軽量)
    is_overloaded = False
    if not engine._rebuild_packer(target_c):
        # 物理的に入らなくなった場合、変更をロールバックする
        if action == "reorder":
            # Undoスタックから直前の状態を取り出して復元
            prev_c = SESSION_DATA["undo_stacks"][container_id].pop()
            # 参照を維持するため属性をコピー
            target_c.items = prev_c.items
            engine._rebuild_packer(target_c)
            return jsonify({'error': '順番を変えた結果、一部の荷物が入りきらなくなりました。元の順番に戻します。', 'rollback': True}), 400
        else:
            is_overloaded = True
    
    if target_c.current_weight > target_c.max_weight:
        is_overloaded = True
        
    c_dict = {
        "id": target_c.id,
        "display_order": target_c.display_order,
        "volume_rate": target_c.fill_rate_volume,
        "weight_val": target_c.current_weight,
        "weight_max": target_c.max_weight,
        "is_alert": target_c.fill_rate_volume < 80.0,
        "is_overloaded": is_overloaded,
        "cg_x": target_c.compute_cg()[0],
        "cg_y": target_c.compute_cg()[1],
        "cg_z": target_c.compute_cg()[2],
        "items": []
    }
    for item in target_c.items:
        c_dict["items"].append({
            "id": item.id,
            "name": item.name,
            "destination": item.destination,
            "l": item.length,
            "w": item.width,
            "h": item.height,
            "x": item.x,
            "y": item.y,
            "z": item.z,
            "rotated": item.is_rotated,
            "is_force_ship": item.force_ship,
            "status_msg": item.status_msg,
            "weight": item.weight,
            "volume_m3": item.volume_m3,
            "due_date": item.due_date.strftime('%m/%d') if getattr(item, 'due_date', None) else ""
        })

    return jsonify({
        "container": c_dict,
        "can_undo": len(SESSION_DATA.get("undo_stacks", {}).get(container_id, [])) > 0,
        "can_redo": len(SESSION_DATA.get("redo_stacks", {}).get(container_id, [])) > 0
    })

def handle_manual_edit_start():
    data = request.get_json(silent=True) or {}
    container_id = data.get('container_id')
    if not container_id:
        return jsonify({'error': 'コンテナIDが指定されていません'}), 400

    containers = SESSION_DATA.get("last_containers", [])
    target_c = next((c for c in containers if c.id == container_id), None)
    if not target_c:
        return jsonify({'error': 'コンテナが見つかりません'}), 404

    if "backup_containers" not in SESSION_DATA:
        SESSION_DATA["backup_containers"] = {}
    if "undo_stacks" not in SESSION_DATA:
        SESSION_DATA["undo_stacks"] = {}
    if "redo_stacks" not in SESSION_DATA:
        SESSION_DATA["redo_stacks"] = {}
    
    # 編集開始時にディープコピーをバックアップとして保存
    SESSION_DATA["backup_containers"][container_id] = copy.deepcopy(target_c)
    SESSION_DATA["undo_stacks"][container_id] = []
    SESSION_DATA["redo_stacks"][container_id] = []
    
    return jsonify({"message": "編集セッションを開始しました"})

def handle_manual_edit_revert():
    data = request.get_json(silent=True) or {}
    container_id = data.get('container_id')
    if not container_id:
        return jsonify({'error': 'コンテナIDが指定されていません'}), 400

    backup = SESSION_DATA.get("backup_containers", {}).get(container_id)
    if not backup:
        return jsonify({'error': 'バックアップが見つかりません'}), 404

    containers = SESSION_DATA.get("last_containers", [])
    for i, c in enumerate(containers):
        if c.id == container_id:
            containers[i] = copy.deepcopy(backup)
            break
            
    if "undo_stacks" in SESSION_DATA and container_id in SESSION_DATA["undo_stacks"]:
        SESSION_DATA["undo_stacks"][container_id] = []
    if "redo_stacks" in SESSION_DATA and container_id in SESSION_DATA["redo_stacks"]:
        SESSION_DATA["redo_stacks"][container_id] = []

    # 復元時に返却するコンテナ情報を構築
    target_c = containers[i]
    c_dict = {
        "id": target_c.id,
        "display_order": target_c.display_order,
        "volume_rate": target_c.fill_rate_volume,
        "weight_val": target_c.current_weight,
        "weight_max": target_c.max_weight,
        "is_alert": target_c.fill_rate_volume < 80.0,
        "is_overloaded": target_c.current_weight > target_c.max_weight, # 簡易判定
        "cg_x": target_c.compute_cg()[0],
        "cg_y": target_c.compute_cg()[1],
        "cg_z": target_c.compute_cg()[2],
        "items": []
    }
    for item in target_c.items:
        c_dict["items"].append({
            "id": item.id,
            "name": item.name,
            "destination": item.destination,
            "l": item.length,
            "w": item.width,
            "h": item.height,
            "x": item.x,
            "y": item.y,
            "z": item.z,
            "rotated": item.is_rotated,
            "is_force_ship": item.force_ship,
            "status_msg": item.status_msg,
            "weight": item.weight,
            "volume_m3": item.volume_m3,
            "due_date": item.due_date.strftime('%m/%d') if getattr(item, 'due_date', None) else ""
        })

    valid_items, _ = build_valid_items()
    packed_item_ids = {item.id for item in target_c.items}
    # 実際には全コンテナのpacked_item_idsを取るべき
    all_packed_ids = set()
    for cont in containers:
        for it in cont.items:
            all_packed_ids.add(it.id)

    response_unused = []
    for item in valid_items:
        if item.id not in all_packed_ids:
            response_unused.append({
                "id": item.id,
                "name": item.name,
                "destination": item.destination,
                "l": item.length,
                "w": item.width,
                "h": item.height,
                "weight": item.weight,
                "volume_m3": item.volume_m3,
                "is_force_ship": item.force_ship,
                "status_msg": item.status_msg,
                "due_date": item.due_date.strftime('%m/%d') if getattr(item, 'due_date', None) else ""
            })

    return jsonify({
        "container": c_dict, 
        "unused_items": response_unused,
        "can_undo": len(SESSION_DATA.get("undo_stacks", {}).get(container_id, [])) > 0,
        "can_redo": len(SESSION_DATA.get("redo_stacks", {}).get(container_id, [])) > 0
    })

def _restore_stack_state(container_id, source_stack, target_stack):
    if container_id not in SESSION_DATA.get(source_stack, {}) or not SESSION_DATA[source_stack][container_id]:
        return jsonify({'error': '状態がありません'}), 400

    containers = SESSION_DATA.get("last_containers", [])
    target_c = next((c for c in containers if c.id == container_id), None)
    if not target_c:
        return jsonify({'error': 'コンテナが見つかりません'}), 404

    if target_stack not in SESSION_DATA:
        SESSION_DATA[target_stack] = {}
    if container_id not in SESSION_DATA[target_stack]:
        SESSION_DATA[target_stack][container_id] = []

    # 現在の状態を対象のスタック（redo等）に保存
    SESSION_DATA[target_stack][container_id].append(copy.deepcopy(target_c))

    # 元のスタック（undo等）から取り出して復元
    prev_state = SESSION_DATA[source_stack][container_id].pop()
    for i, c in enumerate(containers):
        if c.id == container_id:
            containers[i] = prev_state
            target_c = containers[i]
            break

    c_dict = {
        "id": target_c.id,
        "display_order": target_c.display_order,
        "volume_rate": target_c.fill_rate_volume,
        "weight_val": target_c.current_weight,
        "weight_max": target_c.max_weight,
        "is_alert": target_c.fill_rate_volume < 80.0,
        "is_overloaded": target_c.current_weight > target_c.max_weight,
        "cg_x": target_c.compute_cg()[0],
        "cg_y": target_c.compute_cg()[1],
        "cg_z": target_c.compute_cg()[2],
        "items": []
    }
    for item in target_c.items:
        c_dict["items"].append({
            "id": item.id,
            "name": item.name,
            "destination": item.destination,
            "l": item.length,
            "w": item.width,
            "h": item.height,
            "x": item.x,
            "y": item.y,
            "z": item.z,
            "rotated": item.is_rotated,
            "is_force_ship": item.force_ship,
            "status_msg": item.status_msg,
            "weight": item.weight,
            "volume_m3": item.volume_m3,
            "due_date": item.due_date.strftime('%m/%d') if getattr(item, 'due_date', None) else ""
        })

    valid_items, _ = build_valid_items()
    all_packed_ids = set()
    for cont in containers:
        for it in cont.items:
            all_packed_ids.add(it.id)

    response_unused = []
    for item in valid_items:
        if item.id not in all_packed_ids:
            response_unused.append({
                "id": item.id,
                "name": item.name,
                "destination": item.destination,
                "l": item.length,
                "w": item.width,
                "h": item.height,
                "weight": item.weight,
                "volume_m3": item.volume_m3,
                "is_force_ship": item.force_ship,
                "status_msg": item.status_msg,
                "due_date": item.due_date.strftime('%m/%d') if getattr(item, 'due_date', None) else ""
            })

    return jsonify({
        "container": c_dict, 
        "unused_items": response_unused,
        "can_undo": len(SESSION_DATA.get("undo_stacks", {}).get(container_id, [])) > 0,
        "can_redo": len(SESSION_DATA.get("redo_stacks", {}).get(container_id, [])) > 0
    })

def handle_manual_edit_undo():
    data = request.get_json(silent=True) or {}
    container_id = data.get('container_id')
    return _restore_stack_state(container_id, "undo_stacks", "redo_stacks")

def handle_manual_edit_redo():
    data = request.get_json(silent=True) or {}
    container_id = data.get('container_id')
    return _restore_stack_state(container_id, "redo_stacks", "undo_stacks")
