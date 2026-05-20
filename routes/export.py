import os
from io import BytesIO
import datetime
import pandas as pd
from flask import request, jsonify, send_file
from services.session import SESSION_DATA
from services.utils import build_container_alert_summary, build_item_brief

def export_rolling_excel():
    rolling = SESSION_DATA.get("last_rolling")
    if not rolling:
        return jsonify({'error': 'エクスポートするローリング結果がありません'}), 400

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    output = BytesIO()
    wb = openpyxl.Workbook()
    summary_ws = wb.active
    summary_ws.title = "Summary"

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    note_fill = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")
    border_thin = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    summary_ws.merge_cells('A1:D1')
    summary_ws['A1'] = f"【30日ローリングシミュレーション】 {rolling['start_date']} 〜 {rolling['end_date']}"
    summary_ws['A1'] = f"【{rolling['days']}日ローリングシミュレーション】 {rolling['start_date']} 〜 {rolling['end_date']}"
    summary_ws['A1'].font = Font(size=14, bold=True)

    summary_rows = [
        ("計画先読み日数", rolling.get("planning_window_days", 0), "日"),
        ("赤字強制出荷判定日数", rolling.get("force_ship_window_days", 0), "日"),
        ("期間日数", rolling["days"], "日"),
        ("総出荷数", rolling["total_shipped"], "件"),
        ("総コンテナ数", rolling["total_containers"], "本"),
        ("週換算コンテナ数", rolling.get("weekly_container_rate", 0), "本/週"),
        ("前倒し補填数", rolling["total_pulls"], "件"),
        ("赤字コンテナ数", rolling["total_alert_containers"], "本"),
        ("赤字率", rolling.get("alert_rate", 0), "%"),
        ("平均体積充填率", rolling["avg_volume_rate"], "%"),
        ("平均重量充填率", rolling["avg_weight_rate"], "%"),
        ("期間後残", rolling["remaining_count"], "件"),
        ("期限到来/超過残", rolling["overdue_count"], "件"),
        ("入力除外", rolling.get("excluded_count", 0), "件"),
    ]

    for row_idx, row in enumerate(summary_rows, 3):
        for col_idx, value in enumerate(row, 1):
            cell = summary_ws.cell(row=row_idx, column=col_idx)
            cell.value = value
            cell.border = border_thin
            if col_idx == 1:
                cell.fill = note_fill
                cell.font = Font(bold=True)

    comparison = rolling.get("comparison")
    if comparison:
        start_row = 16
        summary_ws[f'A{start_row}'] = "前倒しなし / あり 比較"
        summary_ws[f'A{start_row}'].font = Font(bold=True)
        headers = ["KPI", "前倒しなし", "前倒しあり", "差分"]
        for col_idx, header in enumerate(headers, 1):
            cell = summary_ws.cell(row=start_row + 1, column=col_idx)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border_thin

        comparison_rows = [
            ("総コンテナ数", "total_containers", "本"),
            ("総出荷数", "total_shipped", "件"),
            ("赤字コンテナ数", "total_alert_containers", "本"),
            ("期間後残", "remaining_count", "件"),
            ("期限到来/超過残", "overdue_count", "件"),
            ("平均体積充填率", "avg_volume_rate", "pt"),
            ("平均重量充填率", "avg_weight_rate", "pt"),
        ]
        for offset, (label, key, unit) in enumerate(comparison_rows, 2):
            row_idx = start_row + offset
            baseline = comparison["baseline"][key]
            optimized = comparison["optimized"][key]
            delta = comparison["delta"][key]
            values = [label, baseline, optimized, f"{delta:+g} {unit}"]
            for col_idx, value in enumerate(values, 1):
                cell = summary_ws.cell(row=row_idx, column=col_idx)
                cell.value = value
                cell.border = border_thin

    daily_ws = wb.create_sheet(title="Daily")
    daily_headers = [
        "日付", "コンテナ数", "出荷件数", "前倒し補填", "赤字コンテナ",
        "必須出荷", "前倒し候補", "未使用前倒し候補", "前倒し不可",
        "未到着", "保留プール", "期限到来/超過残", "平均体積充填率", "平均重量充填率"
    ]
    for col_idx, header in enumerate(daily_headers, 1):
        cell = daily_ws.cell(row=1, column=col_idx)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = border_thin

    for row_idx, day in enumerate(rolling["daily_results"], 2):
        values = [
            day["date"], day["containers"], day["shipped"], day["pulls"], day["alerts"],
            day["must_ship"], day["forwardable"], day["unused_forwardable"], day["hold"],
            day["future"], day["pool"], day["overdue_remaining"], day["avg_volume_rate"], day["avg_weight_rate"]
        ]
        for col_idx, value in enumerate(values, 1):
            cell = daily_ws.cell(row=row_idx, column=col_idx)
            cell.value = value
            cell.border = border_thin

    risk_ws = wb.create_sheet(title="RemainingRisks")
    risk_headers = [
        "品名", "確認理由", "積載可能日", "納期", "木箱期限", "納期まで(日)",
        "木箱期限まで(日)", "優先度", "分類理由", "判断根拠", "ステータス"
    ]
    for col_idx, header in enumerate(risk_headers, 1):
        cell = risk_ws.cell(row=1, column=col_idx)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = border_thin

    for row_idx, item in enumerate(rolling.get("remaining_risks", []), 2):
        values = [
            item["name"],
            item["reason"],
            item["creation_date"],
            item["due_date"],
            item["expiration_date"],
            item["days_until_due"],
            item["days_until_expiration"],
            item["priority"],
            item["selection_reason"],
            item["decision_reason"],
            item["status_msg"],
        ]
        for col_idx, value in enumerate(values, 1):
            cell = risk_ws.cell(row=row_idx, column=col_idx)
            cell.value = value
            cell.border = border_thin

    trials = rolling.get("strategy_trials", [])
    trial_ws = None
    if trials:
        trial_ws = wb.create_sheet(title="StrategyTrials")
        trial_headers = [
            "計画先読み日数", "赤字強制出荷判定日数", "コンテナ数", "出荷件数", "前倒し補填",
            "赤字コンテナ", "赤字率", "週換算コンテナ数", "期間後残", "期限到来/超過残",
            "平均体積充填率", "平均重量充填率", "採用"
        ]
        for col_idx, header in enumerate(trial_headers, 1):
            cell = trial_ws.cell(row=1, column=col_idx)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
            cell.border = border_thin

        selected_window = rolling.get("planning_window_days")
        selected_force_window = rolling.get("force_ship_window_days")
        for row_idx, trial in enumerate(trials, 2):
            is_selected = (
                trial.get("planning_window_days") == selected_window
                and trial.get("force_ship_window_days") == selected_force_window
            )
            values = [
                trial.get("planning_window_days", 0),
                trial.get("force_ship_window_days", 0),
                trial.get("total_containers", 0),
                trial.get("total_shipped", 0),
                trial.get("total_pulls", 0),
                trial.get("total_alert_containers", 0),
                trial.get("alert_rate", 0),
                trial.get("weekly_container_rate", 0),
                trial.get("remaining_count", 0),
                trial.get("overdue_count", 0),
                trial.get("avg_volume_rate", 0),
                trial.get("avg_weight_rate", 0),
                "採用" if is_selected else "",
            ]
            for col_idx, value in enumerate(values, 1):
                cell = trial_ws.cell(row=row_idx, column=col_idx)
                cell.value = value
                cell.border = border_thin
                if is_selected:
                    cell.fill = note_fill

    export_sheets = [summary_ws, daily_ws, risk_ws]
    if trial_ws:
        export_sheets.append(trial_ws)

    for ws in export_sheets:
        for col in range(1, ws.max_column + 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 18

    wb.save(output)
    output.seek(0)
    return send_file(
        output,
        download_name='rolling_simulation_report.xlsx',
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def export_scenarios_excel():
    scenario_result = SESSION_DATA.get("last_scenarios")
    if not scenario_result:
        return jsonify({'error': 'エクスポートするシナリオ比較結果がありません'}), 400

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    output = BytesIO()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ScenarioComparison"

    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    note_fill = PatternFill(start_color="E0F2FE", end_color="E0F2FE", fill_type="solid")
    border_thin = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

    ws.merge_cells('A1:L1')
    ws['A1'] = f"【シナリオ比較】 基準日 {scenario_result['base_date']}"
    ws['A1'].font = Font(size=14, bold=True)

    recommended = scenario_result.get("recommended", {})
    ws['A3'] = "推奨シナリオ"
    ws['B3'] = f"必須出荷幅 {recommended.get('must_ship_window_days', '-')}日"
    ws['C3'] = f"赤字 {recommended.get('alert_containers', '-')}本"
    ws['D3'] = f"平均体積 {recommended.get('avg_volume_rate', '-')}%"
    for cell in ws[3]:
        cell.border = border_thin
        if cell.column == 1:
            cell.fill = note_fill
            cell.font = Font(bold=True)

    headers = [
        "推奨", "必須出荷幅(日)", "コンテナ数", "赤字コンテナ", "平均体積充填率",
        "平均重量充填率", "必須出荷件数", "前倒し補填", "保留プール",
        "前倒し候補残", "前倒し不可", "未到着"
    ]
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=5, column=col_idx)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = border_thin

    for row_idx, scenario in enumerate(scenario_result.get("scenarios", []), 6):
        values = [
            "採用" if scenario.get("recommended") else "",
            scenario.get("must_ship_window_days"),
            scenario.get("container_count"),
            scenario.get("alert_containers"),
            scenario.get("avg_volume_rate"),
            scenario.get("avg_weight_rate"),
            scenario.get("must_ship_count"),
            scenario.get("total_pulls"),
            scenario.get("pool_count"),
            scenario.get("unused_forwardable_count"),
            scenario.get("hold_count"),
            scenario.get("future_count"),
        ]
        for col_idx, value in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.value = value
            cell.border = border_thin
            if scenario.get("recommended"):
                cell.fill = note_fill

    widths = [10, 16, 12, 14, 16, 16, 14, 12, 12, 14, 12, 12]
    for col_idx, width in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

    wb.save(output)
    output.seek(0)
    return send_file(
        output,
        download_name='scenario_comparison_report.xlsx',
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def export_excel():
    containers = SESSION_DATA.get("last_containers", [])
    if not containers:
        return jsonify({'error': 'エクスポートするデータがありません'}), 400
        
    output = BytesIO()
    
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    
    wb = openpyxl.Workbook()
    wb.remove(wb.active) # デフォルトシートを削除
    
    # スタイルの定義
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    border_thin = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    export_base_date = SESSION_DATA.get("last_base_date", datetime.date.today())
    export_must_ship_window_days = SESSION_DATA.get("last_must_ship_window_days", 7)
    alert_summaries = SESSION_DATA.get("last_alert_summaries", {})

    summary_ws = wb.create_sheet(title="納品順サマリー")
    summary_ws.merge_cells('A1:I1')
    summary_ws['A1'] = "【納品順サマリー】 コンテナ別出荷判断一覧"
    summary_ws['A1'].font = Font(size=14, bold=True)
    summary_headers = [
        "納品順", "計画ID", "最短納期", "木箱期限", "体積充填率", "重量充填率",
        "荷物数", "前倒し補填", "出荷判断"
    ]
    for col_idx, header in enumerate(summary_headers, 1):
        cell = summary_ws.cell(row=3, column=col_idx)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = border_thin

    for row_idx, c in enumerate(containers, 4):
        earliest_due = min([item.due_date for item in c.items]) if c.items else None
        exp_items = [item.expiration_date for item in c.items if item.expiration_date]
        earliest_exp = min(exp_items) if exp_items else None
        pull_count = sum(1 for item in c.items if item.status_msg and "前倒し" in item.status_msg)
        alert_summary = alert_summaries.get(c.id) or build_container_alert_summary(c, export_base_date, export_must_ship_window_days)
        decision_text = (
            f"{alert_summary['title']}：{alert_summary['detail']}"
            if alert_summary.get("title")
            else "体積80%クリア"
        )
        values = [
            row_idx - 3,
            c.id,
            earliest_due.strftime("%Y-%m-%d") if earliest_due else "",
            earliest_exp.strftime("%Y-%m-%d") if earliest_exp else "制限なし",
            f"{round(c.fill_rate_volume, 1)}%",
            f"{round(c.fill_rate_weight, 1)}%",
            len(c.items),
            pull_count,
            decision_text,
        ]
        for col_idx, value in enumerate(values, 1):
            cell = summary_ws.cell(row=row_idx, column=col_idx)
            cell.value = value
            cell.border = border_thin
            if col_idx in {1, 7, 8}:
                cell.alignment = Alignment(horizontal="right")
            if c.fill_rate_volume < VOLUME_TARGET_RATE and col_idx == 9:
                cell.font = Font(color="FF0000", bold=True)
            if col_idx == 9:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    summary_widths = [10, 12, 14, 14, 14, 14, 10, 12, 72]
    for col_idx, width in enumerate(summary_widths, 1):
        summary_ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

    simulation_context = SESSION_DATA.get("simulation_context")
    if simulation_context:
        def pct(value):
            return "" if value is None else f"{value}%"

        context_ws = wb.create_sheet(title="前提サマリー")
        context_ws.merge_cells('A1:D1')
        context_ws['A1'] = "【前提サマリー】 今回のデータの根拠と仮定"
        context_ws['A1'].font = Font(size=14, bold=True)
        context_ws['A2'] = simulation_context.get("summary_note", "")
        context_ws.merge_cells('A2:D2')
        context_ws['A2'].alignment = Alignment(wrap_text=True, vertical="top")

        context_rows = [
            ("データ種別", "開示ケースリスト準拠の検証データ" if simulation_context.get("is_generated") else "読み込みExcelデータ"),
            ("読み込み荷物数", simulation_context.get("loaded_count", "")),
            ("生成時の荷物数", simulation_context.get("generated_rows_setting", "")),
            ("再現用番号", simulation_context.get("seed", "")),
            ("積み方", simulation_context.get("placement_policy", "")),
            ("木箱期限あり", pct(simulation_context.get("wood_deadline_rate"))),
            ("到着状況", f"到着済み {pct(simulation_context.get('arrived_rate'))} / 未到着 {pct(simulation_context.get('future_rate'))}"),
            ("納期範囲", f"{simulation_context.get('due_min', '')} 〜 {simulation_context.get('due_max', '')}"),
            ("平均重量", simulation_context.get("avg_weight", "")),
        ]
        for row_idx, (label, value) in enumerate(context_rows, 4):
            context_ws.cell(row=row_idx, column=1).value = label
            context_ws.cell(row=row_idx, column=2).value = value
            for col_idx in (1, 2):
                cell = context_ws.cell(row=row_idx, column=col_idx)
                cell.border = border_thin
                if col_idx == 1:
                    cell.fill = header_fill
                    cell.font = header_font
                else:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")

        source_start = 18
        source_headers = ["項目", "扱い", "根拠", "備考"]
        for col_idx, header in enumerate(source_headers, 1):
            cell = context_ws.cell(row=source_start, column=col_idx)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
            cell.border = border_thin
        for row_idx, row in enumerate(simulation_context.get("source_rows", []), source_start + 1):
            values = [row.get("item", ""), row.get("status", ""), row.get("basis", ""), row.get("note", "")]
            for col_idx, value in enumerate(values, 1):
                cell = context_ws.cell(row=row_idx, column=col_idx)
                cell.value = value
                cell.border = border_thin
                if row.get("status") in {"仮定", "補完"} and col_idx == 2:
                    cell.font = Font(color="B45309", bold=True)
                if col_idx == 4:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
        for col_idx, width in enumerate([24, 18, 24, 72], 1):
            context_ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

    readiness = build_data_readiness(SESSION_DATA.get("input_profile", {}), SESSION_DATA.get("validation_issues", []))
    readiness_ws = wb.create_sheet(title="実務準備度")
    readiness_ws.merge_cells('A1:E1')
    readiness_ws['A1'] = f"【実務準備度】 {readiness['score']}% / {readiness['risk_level']}"
    readiness_ws['A1'].font = Font(size=14, bold=True)
    readiness_headers = ["項目", "状態", "確認列", "備考", "実データ"]
    for col_idx, header in enumerate(readiness_headers, 1):
        cell = readiness_ws.cell(row=3, column=col_idx)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = border_thin
    for row_idx, row in enumerate(readiness["checks"], 4):
        values = [row["item"], row["status"], row["source"], row["note"], "あり" if row["ready"] else "補完"]
        for col_idx, value in enumerate(values, 1):
            cell = readiness_ws.cell(row=row_idx, column=col_idx)
            cell.value = value
            cell.border = border_thin
            if not row["ready"] and col_idx in {2, 5}:
                cell.font = Font(color="FF0000", bold=True)
            if col_idx == 4:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col_idx, width in enumerate([18, 14, 24, 72, 12], 1):
        readiness_ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width
    
    for c in containers:
        ws = wb.create_sheet(title=str(c.id))
        alert_summary = alert_summaries.get(c.id) or build_container_alert_summary(c, export_base_date, export_must_ship_window_days)
        alert_text = (
            f"{alert_summary['title']}：{alert_summary['detail']}"
            if alert_summary["title"]
            else "体積80%クリア"
        )
        
        # コンテナサマリー部分
        ws.merge_cells('A1:I1')
        ws['A1'] = f"【バンニング指示書】 コンテナ: {c.id}"
        ws['A1'].font = Font(size=14, bold=True)
        
        ws['A3'] = "最大重量(kg)"
        ws['B3'] = c.max_weight
        ws['A4'] = "現在重量(kg)"
        ws['B4'] = c.current_weight
        ws['A5'] = "重量充填率"
        ws['B5'] = f"{round(c.fill_rate_weight, 1)}%"
        ws['A6'] = "体積充填率"
        ws['B6'] = f"{round(c.fill_rate_volume, 1)}%"
        ws['A7'] = "出荷判断"
        ws['B7'] = alert_text
        ws.merge_cells('B7:I7')
        
        for r in range(3, 8):
            ws[f'A{r}'].fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
            ws[f'A{r}'].border = border_thin
            ws[f'B{r}'].border = border_thin
        ws['B7'].alignment = Alignment(wrap_text=True, vertical="top")
        if c.fill_rate_volume < VOLUME_TARGET_RATE:
            ws['B7'].font = Font(color="FF0000", bold=True)
        
        # 荷物リストのヘッダー
        headers = ["積込順", "品名", "重量(kg)", "寸法 L×W×H(mm)", "3D配置 (奥×横×高)", "実務制約", "分類理由", "判断根拠", "特記事項・ステータス"]
        start_row = 10
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col_idx)
            cell.value = h
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
            cell.border = border_thin
            
        # 荷物データの書き込み
        for idx, i in enumerate(c.items, 1):
            row_idx = start_row + idx
            
            # 回転考慮の寸法
            dim_str = f"{i.length} × {i.width} × {i.height}" + (" (回転)" if i.is_rotated else "")
            
            # 3D座標 (Three.jsの表示に合わせて見やすく)
            pos_str = f"X:{i.x} Y:{i.y} Z:{i.z}" if i.x is not None else "未定"
            
            # 現場ステータス
            status = i.status_msg if i.status_msg else "通常"
            if i.is_force_ship and status == "通常":
                status = "🚨 赤字/納期強制出荷"
                
            row_data = [
                idx,
                i.name,
                f"{i.weight:,.1f}",
                dim_str,
                pos_str,
                " / ".join(build_constraint_tags(i)),
                i.selection_reason if i.selection_reason else "通常",
                i.decision_reason or i.selection_reason,
                status
            ]
            
            for col_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.value = val
                cell.border = border_thin
                if col_idx == 1 or col_idx == 3:
                    cell.alignment = Alignment(horizontal="right")
                    
                # 色付けルールの適用
                if col_idx == 9:
                    if "強制出荷" in status:
                        cell.font = Font(color="FF0000", bold=True) # 赤
                    elif "前倒し" in status:
                        cell.font = Font(color="008000", bold=True) # 緑
        
        # 列幅の自動調整
        ws.column_dimensions['A'].width = 8
        ws.column_dimensions['B'].width = 30
        ws.column_dimensions['C'].width = 12
        ws.column_dimensions['D'].width = 25
        ws.column_dimensions['E'].width = 25
        ws.column_dimensions['F'].width = 20
        ws.column_dimensions['G'].width = 20
        ws.column_dimensions['H'].width = 48
        ws.column_dimensions['I'].width = 40

    review_queue = SESSION_DATA.get("last_review_queue", [])
    if review_queue:
        ws = wb.create_sheet(title="ReviewQueue")
        headers = [
            "品名", "確認理由", "積載可能日", "納期", "木箱期限", "納期まで(日)",
            "木箱期限まで(日)", "優先度", "分類理由", "判断根拠", "ステータス"
        ]
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.value = h
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
            cell.border = border_thin

        for row_idx, item in enumerate(review_queue, 2):
            row_data = [
                item["name"],
                item["reason"],
                item["creation_date"],
                item["due_date"],
                item["expiration_date"],
                item["days_until_due"],
                item["days_until_expiration"],
                item["priority"],
                item["selection_reason"],
                item["decision_reason"],
                item["status_msg"],
            ]
            for col_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.value = val
                cell.border = border_thin

        widths = [30, 36, 14, 14, 14, 14, 16, 10, 20, 48, 30]
        for col_idx, width in enumerate(widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = width

    wb.save(output)
    output.seek(0)
    return send_file(
        output, 
        download_name='vanning_instructions.xlsx', 
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )