from flask import request, jsonify
from services.session import SESSION_DATA, build_valid_items
from services.utils import parse_base_date, read_bounded_int
from services.rolling import run_single_day_scenario, single_day_scenario_score

def handle_scenarios():
    data = request.get_json(silent=True) or {}
    base_date_str = data.get('base_date')
    user_window = read_bounded_int(data, 'must_ship_window_days', 7, 0, 30)
    current_date, date_error = parse_base_date(base_date_str)
    if date_error:
        return jsonify({'error': date_error}), 400

    valid_items, _ = build_valid_items()
    if not valid_items:
        return jsonify({'error': '積載可能な有効データがありません'}), 400

    candidates = [0, 3, 5, 7, 10, 14]
    if user_window not in candidates:
        candidates.append(user_window)
    candidates.sort()

    scenarios = []
    best_scenario = None
    best_score = None

    for window in candidates:
        scenario = run_single_day_scenario(valid_items, current_date, window)
        score = single_day_scenario_score(scenario)
        if best_score is None or score < best_score:
            best_score = score
            best_scenario = scenario
        scenarios.append(scenario)

    for s in scenarios:
        s["recommended"] = (s["must_ship_window_days"] == best_scenario["must_ship_window_days"])

    result = {
        "base_date": current_date.strftime("%Y-%m-%d"),
        "scenarios": scenarios,
        "recommended": best_scenario
    }
    
    SESSION_DATA["last_scenarios"] = result
    return jsonify(result)
