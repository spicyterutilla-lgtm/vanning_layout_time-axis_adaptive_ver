import os
from flask import Flask, send_from_directory, jsonify, request
from routes.upload import (
    handle_upload, handle_status, download_template
)
from routes.optimize import handle_optimize, handle_override, handle_ga_status, handle_manual_edit_start, handle_manual_edit_revert, handle_baseline
from routes.export import export_excel, export_single_container

app = Flask(__name__, static_folder='static')
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    
    response = send_from_directory('static', 'index.html')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/status', methods=['GET'])
def api_status():
    return handle_status()

@app.route('/api/upload', methods=['POST'])
def api_upload():
    return handle_upload(app)



@app.route('/api/baseline', methods=['POST'])
def api_baseline():
    return handle_baseline()

@app.route('/api/optimize', methods=['POST'])
def api_optimize():
    return handle_optimize()

@app.route('/api/override', methods=['POST'])
def api_override():
    return handle_override()

@app.route('/api/manual_edit', methods=['POST'])
def api_manual_edit():
    from routes.optimize import handle_manual_edit
    return handle_manual_edit()

@app.route('/api/manual_edit_start', methods=['POST'])
def api_manual_edit_start():
    return handle_manual_edit_start()

@app.route('/api/manual_edit_revert', methods=['POST'])
def api_manual_edit_revert():
    return handle_manual_edit_revert()

@app.route('/api/manual_edit_undo', methods=['POST'])
def api_manual_edit_undo():
    from routes.optimize import handle_manual_edit_undo
    return handle_manual_edit_undo()

@app.route('/api/manual_edit_redo', methods=['POST'])
def api_manual_edit_redo():
    from routes.optimize import handle_manual_edit_redo
    return handle_manual_edit_redo()

@app.route('/api/ga_status', methods=['GET'])
def api_ga_status():
    return handle_ga_status()

@app.route('/api/export', methods=['GET'])
def api_export():
    return export_excel()

@app.route('/api/export_container', methods=['GET'])
def api_export_container():
    return export_single_container()

@app.route('/api/download_template', methods=['GET'])
def api_download_template():
    return download_template()

if __name__ == '__main__':
    # host='0.0.0.0' にすることで、同じネットワーク内の他のPCからもアクセス可能になります
    app.run(debug=True, host='0.0.0.0', port=5000)
