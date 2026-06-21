import os
import json
import socket
import logging
import subprocess
import sys
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# Suppress Werkzeug request logs
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# ---------------------------------------------------------------------------
# Hardened path resolution
# Always resolves relative to this file's location (src/)
# ---------------------------------------------------------------------------
SRC_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SRC_DIR)
CONFIG_PATH = os.path.join(SRC_DIR,     "config.json")
MAIN_SCRIPT = os.path.join(SRC_DIR,     "main.py")
IFC_OUTPUT  = os.path.join(PROJECT_DIR, "ifc_output", "complete_bridge.ifc")


# ---------------------------------------------------------------------------
# IFC pipeline runner
# Uses the same Python interpreter that is running app.py — guaranteed to
# have ifcopenshell since the user confirmed "python main.py" works from
# a normal terminal with this interpreter.
# ---------------------------------------------------------------------------
def run_ifc_pipeline():
    """
    Calls main.py with the exact same Python executable that is running
    this Flask server, with SRC_DIR as the working directory so that the
    relative imports (main_deck, abutment, etc.) resolve correctly.
    Returns (success: bool, message: str).
    """
    if not os.path.exists(MAIN_SCRIPT):
        return False, f"main.py not found at {MAIN_SCRIPT}"

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, MAIN_SCRIPT],   # sys.executable = the Python running app.py
        cwd=SRC_DIR,                      # so main_deck / abutment imports resolve
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        return False, f"main.py exited with error:\n{detail}"

    if not os.path.exists(IFC_OUTPUT):
        return False, f"main.py ran but IFC not found at {IFC_OUTPUT}"

    return True, f"IFC regenerated → {IFC_OUTPUT}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return send_from_directory(SRC_DIR, 'index.html')


@app.route('/api/get-config', methods=['GET'])
def get_config():
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
    """
    1. Writes updated parameter values to config.json.
    2. Immediately runs main.py to regenerate complete_bridge.ifc.
    Both steps happen before the response is returned so the client
    knows whether the IFC was actually produced.
    """
    try:
        incoming_values = request.get_json()

        # --- Step 1: update config.json ---
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            current_config = json.load(f)

        for component_key, params in incoming_values.items():
            if component_key in current_config.get("components", {}):
                for param_key, new_value in params.items():
                    if param_key in current_config["components"][component_key]["parameters"]:
                        current_config["components"][component_key]["parameters"][param_key]["example_value"] = new_value

        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(current_config, f, indent=2)

        # --- Step 2: regenerate IFC ---
        ok, message = run_ifc_pipeline()
        if not ok:
            # Config was saved successfully even if IFC failed
            return jsonify({
                "status":  "partial",
                "message": f"config.json saved but IFC generation failed: {message}"
            }), 500

        return jsonify({
            "status":  "success",
            "message": f"config.json saved and IFC regenerated.\n{message}"
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/build-ifc', methods=['POST'])
def build_ifc():
    """
    Standalone endpoint to trigger IFC regeneration without changing
    any config values — useful for a 'Rebuild IFC' button.
    """
    ok, message = run_ifc_pipeline()
    if ok:
        return jsonify({"status": "success", "message": message}), 200
    return jsonify({"status": "error", "message": message}), 500


# ---------------------------------------------------------------------------
# Port helper
# ---------------------------------------------------------------------------
def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Direct launch (browser / dev mode)
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    port = 5000
    print(f"[Blue Rhinos] BIM Dashboard → http://127.0.0.1:{port}")
    print(f"[Blue Rhinos] SRC_DIR  : {SRC_DIR}")
    print(f"[Blue Rhinos] IFC out  : {IFC_OUTPUT}")
    app.run(debug=True, port=port, use_reloader=False)