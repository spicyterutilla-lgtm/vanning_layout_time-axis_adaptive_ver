import copy
from flask import request, jsonify
from services.session import SESSION_DATA, build_valid_items, reset_runtime_state
from services.validation import classify_items_for_day, validate_container_geometry
from services.utils import (
    read_bounded_int, parse_base_date, order_containers_for_output,
    build_efficiency_summary
)
from vanning_engine import VanningEngine, LARGE_PLAN_ITEM_THRESHOLD

def handle_optimize():
    data = request.get_json(silent=True) or {}
    base_date_str = data.get('base_date')
    must_ship_window_days = read_bounded_int(data, 'must_ship_window_days', 7, 0, 30)
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
    alternative_items = (
        (copy.deepcopy(target_items), copy.deepcopy(forwardable_items))
        if 0 < len(target_items) < LARGE_PLAN_ITEM_THRESHOLD
        else None
    )

    engine = VanningEngine()
    containers, pool, unused_forwardable = engine.run_time_axis_packing(
        target_items,
        forwardable_items,
        current_date,
        allow_partial_red_pull=True
    )
    if alternative_items and any(c.fill_rate_volume < 80.0 for c in containers):
        alternative_engine = VanningEngine(prioritize_open_containers=False)
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
    
    response_containers = []
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
            c_dict["items"].append({
                "id": item.id,
                "name": item.name,
                "l": item.length,
                "w": item.width,
                "h": item.height,
                "x": item.x,
                "y": item.y,
                "z": item.z,
                "rotated": item.is_rotated,
                "is_force_ship": item.force_ship,
                "is_manual_force_ship": item.force_ship and not getattr(item, 'system_force_ship', False),
                "status_msg": item.status_msg
            })
        response_containers.append(c_dict)

    return jsonify({
        "containers": response_containers,
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
        }
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
