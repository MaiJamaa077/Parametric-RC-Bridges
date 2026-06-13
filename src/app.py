import os
import json
import socket
import logging
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# Suppress Werkzeug request logs so the standalone desktop window
# doesn't show a terminal behind it with server noise.
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
# Path resolution — always relative to this file, inside the /src folder
# ---------------------------------------------------------------------------
SRC_DIR     = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SRC_DIR, "config.json")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    """Serves the interactive BIM dashboard webpage."""
    return send_from_directory(SRC_DIR, 'index.html')


@app.route('/api/get-config', methods=['GET'])
def get_config():
    """Returns the full config.json to populate the diagram inputs on load."""
    try:
        if not os.path.exists(CONFIG_PATH):
            return jsonify({"error": f"config.json not found at {CONFIG_PATH}"}), 404
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/save-config', methods=['POST'])
def save_config():
    """Receives edited values from the dashboard and writes them to config.json."""
    try:
        incoming_values = request.get_json()

        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            current_config = json.load(f)

        for component_key, params in incoming_values.items():
            if component_key in current_config.get("components", {}):
                for param_key, new_value in params.items():
                    if param_key in current_config["components"][component_key]["parameters"]:
                        current_config["components"][component_key]["parameters"][param_key]["example_value"] = new_value

        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(current_config, f, indent=2)

        return jsonify({"status": "success", "message": "Parameters written to disk."}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Port helper — used by the standalone shell to avoid hardcoded port 5000
# ---------------------------------------------------------------------------
def find_free_port():
    """Bind to port 0 and let the OS assign a free one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Direct launch (browser mode, not standalone)
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    port = 5000
    print(f"[Blue Rhinos] BIM Dashboard → http://127.0.0.1:{port}")
    app.run(debug=True, port=port, use_reloader=False)
