import os
import datetime
import pandas as pd
from io import BytesIO
from flask import Flask, request, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename
from data_loader import DataLoader
from vanning_engine import VanningEngine

app = Flask(__name__, static_folder='static')
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 簡易的なオンメモリセッション（プロトタイプ用）
SESSION_DATA = {"items": []}

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/download_template', methods=['GET'])
def download_template():
    import pandas as pd
    import datetime
    import random
    import io
    
    today = datetime.date.today()
    data = []
    
    # よりリアルな規模感の100件のサンプルデータを生成
    for i in range(1, 101):
        item_type = random.choice(["エンジン部品", "トランスミッション", "外装パネル", "木箱", "燻蒸木箱", "サスペンション", "ブレーキキット"])
        name = f"ISZ-{item_type}-{random.randint(1000, 9999)}"
        
        if "エンジン" in item_type or "トランスミッション" in item_type:
            l, w, h = random.randint(800, 1200), random.randint(600, 1000), random.randint(600, 1000)
            weight = random.randint(2000, 5000)
        elif "木箱" in item_type:
            l, w, h = random.randint(1000, 2000), random.randint(1000, 2000), random.randint(1000, 2000)
            weight = random.randint(1000, 3000)
        else:
            l, w, h = random.randint(400, 1500), random.randint(400, 1500), random.randint(400, 1500)
            weight = random.randint(500, 2000)
            
        # 時間軸シミュレーションが映えるように、全体の約50%を「今週納期」にする
        creation_offset = random.randint(-20, 0) # 過去20日以内
        
        if random.random() < 0.5:
            due_offset = random.randint(1, 7)    # 今週納期（確実に出荷対象になる）
        else:
            due_offset = random.randint(8, 35)   # 来週以降（前倒し/保留の候補）
        
        creation_date = today + datetime.timedelta(days=creation_offset)
        due_date = today + datetime.timedelta(days=due_offset)
        
        data.append({
            "品名": name,
            "L": l,
            "W": w,
            "H": h,
            "重量": weight,
            "梱包日": creation_date.strftime("%Y-%m-%d"),
            "納期": due_date.strftime("%Y-%m-%d")
        })
        
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='シミュレーションデータ')
    output.seek(0)
    
    return send_file(
        output,
        download_name='sample_simulation_data.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'ファイルがありません'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'ファイルが選択されていません'}), 400
        
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    loader = DataLoader()
    try:
        items = loader.load_from_excel(filepath)
        SESSION_DATA["items"] = items
        
        # サマリー作成（UI表示用）
        target_count = len(items[:20]) # テストとして最初の20件を今週分とする
        future_count = len(items[20:])
        
        return jsonify({
            'message': 'Success',
            'total_items': len(items),
            'target_count': target_count,
            'future_count': future_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/optimize', methods=['POST'])
def optimize():
    data = request.get_json() or {}
    base_date_str = data.get('base_date')
    if base_date_str:
        current_date = datetime.datetime.strptime(base_date_str, '%Y-%m-%d').date()
    else:
        current_date = datetime.date.today()
        
    items = SESSION_DATA.get("items", [])
    if not items:
        return jsonify({'error': 'データがありません'}), 400
        
    # 実務ベースの分割ロジック：基準日から7日以内を「対象（Must）」、それ以降を「未来（Pull候補）」とする
    target_date_limit = current_date + datetime.timedelta(days=7)
    
    # 既に割り当て済みの荷物のフラグなどをリセット
    for i in items:
        if "前倒し" in str(i.status_msg) or "保留" in str(i.status_msg) or "赤字強制出荷" in str(i.status_msg):
            i.status_msg = ""
            
    target_items = [i for i in items if i.due_date <= target_date_limit]
    future_items = [i for i in items if i.due_date > target_date_limit]
    
    engine = VanningEngine()
    containers, pool, left_future = engine.run_time_axis_packing(target_items, future_items, current_date)
    
    # 指示書ダウンロード用に保持
    SESSION_DATA["last_containers"] = containers
    
    # UI描画用に結果をJSON化
    result_containers = []
    for c in containers:
        is_red_ink = c.fill_rate_weight < 80.0 and c.fill_rate_volume < 80.0
        c_items = []
        for i in c.items:
            c_items.append({
                'id': i.id,
                'name': i.name,
                'status_msg': i.status_msg,
                'is_force_ship': i.force_ship,
                'l': i.length,
                'w': i.width,
                'h': i.height,
                'x': i.x if i.x is not None else 0,
                'y': i.y if i.y is not None else 0,
                'z': i.z if i.z is not None else 0,
                'rotated': i.is_rotated
            })
            
        # 最短納期と最短木箱期限の計算
        earliest_due = min([i.due_date for i in c.items]) if c.items else None
        earliest_exp_items = [i.expiration_date for i in c.items if i.expiration_date]
        earliest_exp = min(earliest_exp_items) if earliest_exp_items else None
        
        pull_count = sum(1 for i in c.items if i.status_msg and "前倒し" in i.status_msg)
            
        result_containers.append({
            'id': c.id,
            'weight_val': c.current_weight,
            'weight_max': c.max_weight,
            'weight_rate': round(c.fill_rate_weight, 1),
            'volume_rate': round(c.fill_rate_volume, 1),
            'earliest_due': earliest_due.strftime('%Y-%m-%d') if earliest_due else 'なし',
            'earliest_exp': earliest_exp.strftime('%Y-%m-%d') if earliest_exp else '制限なし',
            'pull_count': pull_count,
            'is_alert': is_red_ink,
            'items': c_items
        })
        
    # 全体のサマリー集計
    total_pulls = sum(c['pull_count'] for c in result_containers)
    alert_containers = sum(1 for c in result_containers if c['is_alert'])
        
    return jsonify({
        'containers': result_containers,
        'pool_count': len(pool),
        'future_count': len(left_future),
        'total_pulls': total_pulls,
        'alert_containers': alert_containers
    })

@app.route('/api/export', methods=['GET'])
def export_excel():
    containers = SESSION_DATA.get("last_containers", [])
def export_results():
    if not SESSION_DATA.get("last_containers"):
        return jsonify({'error': 'エクスポートするデータがありません'}), 400
        
    output = io.BytesIO()
    
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    
    wb = openpyxl.Workbook()
    wb.remove(wb.active) # デフォルトシートを削除
    
    # スタイルの定義
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    border_thin = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    
    for c in SESSION_DATA["last_containers"]:
        ws = wb.create_sheet(title=str(c.id))
        
        # コンテナサマリー部分
        ws.merge_cells('A1:F1')
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
        
        for r in range(3, 7):
            ws[f'A{r}'].fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
            ws[f'A{r}'].border = border_thin
            ws[f'B{r}'].border = border_thin
        
        # 荷物リストのヘッダー
        headers = ["積込順", "品名", "重量(kg)", "寸法 L×W×H(mm)", "3D配置 (奥×横×高)", "特記事項・ステータス"]
        start_row = 9
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
            if i.force_ship:
                status = "🚨 赤字/納期強制出荷"
                
            row_data = [
                idx,
                i.name,
                f"{i.weight:,.1f}",
                dim_str,
                pos_str,
                status
            ]
            
            for col_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.value = val
                cell.border = border_thin
                if col_idx == 1 or col_idx == 3:
                    cell.alignment = Alignment(horizontal="right")
                    
                # 色付けルールの適用
                if col_idx == 6:
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
        ws.column_dimensions['F'].width = 40

    wb.save(output)
    output.seek(0)
    return send_file(
        output, 
        download_name='vanning_instructions.xlsx', 
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/api/override', methods=['POST'])
def override_item():
    data = request.json
    item_ids = data.get('item_ids', [])
    force_ship = data.get('force_ship')
    
    items = SESSION_DATA.get("items", [])
    found = False
    for item in items:
        if item.id in item_ids:
            item.force_ship = force_ship
            item.status_msg = "手動オーバーライド：現場指示による強制出荷" if force_ship else ""
            found = True
            
    if found:
        return jsonify({'message': 'Success'})
    return jsonify({'error': 'アイテムが見つかりません'}), 404

if __name__ == '__main__':
    print("サーバーを起動しました。ブラウザで http://127.0.0.1:5000 にアクセスしてください。")
    app.run(debug=True, port=5000)
