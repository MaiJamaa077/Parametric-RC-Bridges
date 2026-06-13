"""
Bridge Parameter Editor — Standalone Desktop App
=================================================
Launches the Flask BIM dashboard (app.py) in a background thread,
then opens a native desktop window via pywebview pointing at it.

No browser required. No Blender required.
The full UI — 3 × 2D views + live 3D viewport + parameter inputs — runs
inside this window, served by the local Flask instance.

Usage:
    python bridge_param_editor_standalone.py

Dependencies:
    pip install flask pywebview
"""

import sys
import os
import time
import threading
import socket

# ---------------------------------------------------------------------------
# Ensure this script can find app.py regardless of working directory
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


# ---------------------------------------------------------------------------
# Dependency checks — clear error messages before anything else runs
# ---------------------------------------------------------------------------
def _check_deps():
    missing = []
    try:
        import flask  # noqa: F401
    except ImportError:
        missing.append("flask  →  pip install flask")
    try:
        import webview  # noqa: F401
    except ImportError:
        missing.append("pywebview  →  pip install pywebview")
    if missing:
        print("\n[Bridge Editor] Missing dependencies:\n")
        for m in missing:
            print(f"  {m}")
        print()
        sys.exit(1)

_check_deps()

import webview  # noqa: E402  (after dep check)
from app import app as flask_app, find_free_port  # noqa: E402


# ---------------------------------------------------------------------------
# Flask thread
# ---------------------------------------------------------------------------
_flask_port: int = 0
_flask_ready = threading.Event()


def _run_flask(port: int) -> None:
    """Run Flask in a daemon thread. Werkzeug output is already suppressed in app.py."""
    flask_app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


def _wait_for_flask(port: int, timeout: float = 8.0) -> bool:
    """Poll until Flask is accepting connections or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def start_flask() -> int:
    """Find a free port, start Flask, wait until it is ready, return the port."""
    port = find_free_port()

    t = threading.Thread(target=_run_flask, args=(port,), daemon=True, name="FlaskBridge")
    t.start()

    ok = _wait_for_flask(port)
    if not ok:
        print(f"[Bridge Editor] Flask did not start on port {port} within timeout.")
        sys.exit(1)

    return port


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main() -> None:
    print("[Blue Rhinos] Starting BIM Dashboard…")

    port = start_flask()
    url  = f"http://127.0.0.1:{port}"
    print(f"[Blue Rhinos] Flask ready at {url}")

    # pywebview window — native OS chrome, resizable, BIM-tool proportions
    window = webview.create_window(
        title      = "Blue Rhinos — Parametric Bridge BIM",
        url        = url,
        width      = 1440,
        height     = 860,
        min_size   = (900, 600),
        resizable  = True,
        # Keep the native OS title bar (close/min/max) — no frameless tricks
        # that vary badly across platforms.
        frameless  = False,
        # Expose no JS API (Flask handles all data I/O)
        js_api     = None,
    )

    # Start webview — blocks until the window is closed by the user
    # gui=None lets pywebview pick the best backend for the current OS:
    #   Windows → EdgeChromium / MSHTML
    #   macOS   → WKWebView
    #   Linux   → GTK WebKit2
    webview.start(debug=False)

    print("[Blue Rhinos] Window closed. Exiting.")
    # Flask thread is a daemon — it exits automatically when the main thread ends.


if __name__ == "__main__":
    main()
