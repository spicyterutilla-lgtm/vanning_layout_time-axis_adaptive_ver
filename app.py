import os
from flask import Flask, send_from_directory, jsonify, request
from routes.upload import handle_upload, handle_status, download_template
from routes.optimize import handle_optimize, handle_override
from routes.rolling import handle_rolling
from routes.scenarios import handle_scenarios
from routes.export import export_excel, export_rolling_excel, export_scenarios_excel

app = Flask(__name__, static_folder='static')
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/status', methods=['GET'])
def api_status():
    return handle_status()

@app.route('/api/upload', methods=['POST'])
def api_upload():
    return handle_upload(app)

@app.route('/api/optimize', methods=['POST'])
def api_optimize():
    return handle_optimize()

@app.route('/api/override', methods=['POST'])
def api_override():
    return handle_override()

@app.route('/api/rolling', methods=['POST'])
def api_rolling():
    return handle_rolling()

@app.route('/api/scenarios', methods=['POST'])
def api_scenarios():
    return handle_scenarios()

@app.route('/api/export', methods=['GET'])
def api_export():
    return export_excel()

@app.route('/api/export_rolling', methods=['GET'])
def api_export_rolling():
    return export_rolling_excel()

@app.route('/api/export_scenarios', methods=['GET'])
def api_export_scenarios():
    return export_scenarios_excel()

@app.route('/api/download_template', methods=['GET'])
def api_download_template():
    # app.py側に残っていたdownload_templateをroutes/upload.pyに含めるのが正ですが
    # extract_export.py等の兼ね合いもあるため、まずはシンプルにルーティング
    return download_template()

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
