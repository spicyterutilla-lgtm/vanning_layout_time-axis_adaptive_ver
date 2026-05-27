import os
import uuid
import pandas as pd
import json
from io import BytesIO
from flask import request, jsonify, send_file
from services.session import SESSION_DATA, clear_last_results, ALLOWED_EXTENSIONS, SIMULATION_ASSUMPTIONS_FILE
from services.validation import validate_items, build_validation_summary, build_data_readiness
from services.simulation import (
    read_generation_parameters, build_simulation_context,
    load_case_master_rows, generate_case_based_simulation_rows,
    build_case_class_summary_rows, build_case_assumptions_rows,
    build_planning_dates
)
from simulation_assumptions import build_generation_parameter_rows, load_simulation_assumptions
from data_loader import DataLoader

def build_upload_path(upload_folder, original_filename):
    _, ext = os.path.splitext(original_filename or "")
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Excelファイル（.xlsx / .xls）のみアップロードできます")
    return os.path.join(upload_folder, f"{uuid.uuid4().hex}{ext}")

def handle_upload(app):
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルがありません'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400

    try:
        filepath = build_upload_path(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    loader = DataLoader()
    try:
        items = loader.load_from_excel(filepath)
        validation_issues, invalid_item_ids = validate_items(items)
        clear_last_results()
        SESSION_DATA["items"] = items
        SESSION_DATA["validation_issues"] = validation_issues
        SESSION_DATA["invalid_item_ids"] = invalid_item_ids
        SESSION_DATA["input_profile"] = loader.input_profile
        generation_parameters = read_generation_parameters(filepath)
        simulation_context = build_simulation_context(items, loader.input_profile, generation_parameters)
        SESSION_DATA["simulation_context"] = simulation_context
        readiness = build_data_readiness(loader.input_profile, validation_issues)
        
        target_count = len(items[:20])
        future_count = len(items[20:])
        
        return jsonify({
            'message': 'Success',
            'total_items': len(items),
            'valid_items': len(items) - len(invalid_item_ids),
            'invalid_items': len(invalid_item_ids),
            'target_count': target_count,
            'future_count': future_count,
            'validation_summary': build_validation_summary(validation_issues),
            'validation_issues': validation_issues[:8],
            'readiness': readiness,
            'simulation_context': simulation_context
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def handle_status():
    items = SESSION_DATA.get("items", [])
    if items:
        validation_issues = SESSION_DATA.get("validation_issues", [])
        return jsonify({
            'has_data': True,
            'total_items': len(items),
            'validation_summary': build_validation_summary(validation_issues),
            'validation_issues': validation_issues[:8],
            'readiness': build_data_readiness(SESSION_DATA.get("input_profile", {}), validation_issues),
            'simulation_context': SESSION_DATA.get("simulation_context")
        })
    return jsonify({'has_data': False})



def assumptions_api():
    project_root = os.path.dirname(os.path.dirname(__file__))
    assumptions_path = os.path.join(project_root, SIMULATION_ASSUMPTIONS_FILE)
    assumptions = load_simulation_assumptions(assumptions_path)

    if request.method == 'POST':
        with open(assumptions_path, "w", encoding="utf-8") as handle:
            json.dump(assumptions, handle, ensure_ascii=False, indent=2)

    return jsonify({
        "class_weights": assumptions.get("class_weights", {}),
        "density_ranges": assumptions.get("density_ranges", {}),
        "arrival_distribution": assumptions.get("arrival_distribution", []),
    })

def download_template():
    row_count = request.args.get("rows", default=800, type=int)
    if not row_count:
        row_count = 800
    row_count = max(50, min(row_count, 3000))
    seed = request.args.get("seed", default=20260516, type=int) or 20260516
    project_root = os.path.dirname(os.path.dirname(__file__))
    assumptions_path = os.path.join(project_root, SIMULATION_ASSUMPTIONS_FILE)
    assumptions = load_simulation_assumptions(assumptions_path)

    case_master = load_case_master_rows()
    planning_dates = build_planning_dates(assumptions)
    simulation_rows = generate_case_based_simulation_rows(
        case_master,
        row_count=row_count,
        assumptions=assumptions,
        seed=seed,
        planning_dates=planning_dates,
    )
    df = pd.DataFrame(simulation_rows)
    case_df = pd.DataFrame(case_master)
    summary_df = pd.DataFrame(build_case_class_summary_rows(case_master))
    parameter_rows = build_generation_parameter_rows(assumptions, row_count=row_count, seed=seed)
    for item, value in planning_dates.items():
        parameter_rows.append({
            "区分": "今回の計画日程",
            "項目": item,
            "値": value.strftime("%Y-%m-%d"),
            "扱い": "先方回答ベース",
            "説明": "船積日からの回答済みリードタイムに基づく日付",
        })
    parameters_df = pd.DataFrame(parameter_rows)
    assumptions_df = pd.DataFrame(build_case_assumptions_rows(row_count=row_count))
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='シミュレーションデータ')
        case_df.to_excel(writer, index=False, sheet_name='ケースマスタ')
        summary_df.to_excel(writer, index=False, sheet_name='ケース階級サマリ')
        parameters_df.to_excel(writer, index=False, sheet_name='生成パラメータ')
        assumptions_df.to_excel(writer, index=False, sheet_name='前提条件')

        for sheet_name in ["シミュレーションデータ", "ケースマスタ", "ケース階級サマリ", "生成パラメータ", "前提条件"]:
            ws = writer.book[sheet_name]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for col in ws.columns:
                max_length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(max_length + 2, 10), 34)

        writer.book["生成パラメータ"].column_dimensions["E"].width = 56
        writer.book["前提条件"].column_dimensions["C"].width = 72
    output.seek(0)

    return send_file(
        output,
        download_name='case_master_based_simulation_data.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
