from flask import request, jsonify
from services.session import SESSION_DATA, build_valid_items
from services.utils import parse_base_date, read_bounded_int
from services.rolling import run_adaptive_rolling_simulation

def handle_rolling():
    data = request.get_json(silent=True) or {}
    base_date_str = data.get('base_date')
    days = read_bounded_int(data, 'days', 30, 1, 90)
    current_date, date_error = parse_base_date(base_date_str)
    if date_error:
        return jsonify({'error': date_error}), 400

    valid_items, _ = build_valid_items()
    if not valid_items:
        return jsonify({'error': '積載可能な有効データがありません'}), 400

    result = run_adaptive_rolling_simulation(valid_items, current_date, days=days, allow_pull=True)
    SESSION_DATA["last_rolling"] = result
    
    return jsonify(result)
