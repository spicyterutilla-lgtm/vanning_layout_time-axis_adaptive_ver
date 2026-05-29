import os
from flask import Flask, send_from_directory, jsonify, request
from routes.upload import (
    handle_upload, handle_status, download_template
)
from routes.optimize import handle_optimize, handle_override, handle_ga_status
from routes.export import export_excel

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

@app.route('/api/ga_status', methods=['GET'])
def api_ga_status():
    return handle_ga_status()

@app.route('/api/export', methods=['GET'])
def api_export():
    return export_excel()

@app.route('/api/download_template', methods=['GET'])
def api_download_template():
    return download_template()

if __name__ == '__main__':
    # host='0.0.0.0' にすることで、同じネットワーク内の他のPCからもアクセス可能になります
    app.run(debug=True, host='0.0.0.0', port=5000)
