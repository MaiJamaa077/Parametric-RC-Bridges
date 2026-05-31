import bpy
import os
import time
import subprocess


# ============================================================
# BRIDGE PARAM WATCHER
# Watches src/config.json and regenerates complete_bridge.ifc
# through src/main.py, then reloads it in Blender/Bonsai.
# ============================================================

POLL_SECONDS = 2.0
BUILD_ON_START = False


# ------------------------------------------------------------
# PATH DISCOVERY
# ------------------------------------------------------------

def find_project_paths():
    """
    Finds PROJECT_DIR and SRC_DIR safely.

    Supports:
    - .blend saved in project root
    - .blend saved in project_root/models
    - .blend saved in project_root/src
    - script opened from src/bridge_param_watcher.py
    """

    candidates = []

    # 1. Current .blend folder
    blend_dir = os.path.normpath(bpy.path.abspath("//"))
    candidates.append(blend_dir)
    candidates.append(os.path.dirname(blend_dir))

    # 2. If script is opened from an external file, try its location
    if "__file__" in globals():
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(script_dir)
        candidates.append(os.path.dirname(script_dir))

    # Remove duplicates
    unique_candidates = []
    for path in candidates:
        if path and path not in unique_candidates:
            unique_candidates.append(path)

    for candidate in unique_candidates:
        candidate = os.path.normpath(candidate)

        # Case A: candidate itself is src
        if (
            os.path.basename(candidate).lower() == "src"
            and os.path.exists(os.path.join(candidate, "main.py"))
            and os.path.exists(os.path.join(candidate, "config.json"))
        ):
            src_dir = candidate
            project_dir = os.path.dirname(src_dir)
            return project_dir, src_dir

        # Case B: candidate contains src
        possible_src = os.path.join(candidate, "src")
        if (
            os.path.exists(os.path.join(possible_src, "main.py"))
            and os.path.exists(os.path.join(possible_src, "config.json"))
        ):
            project_dir = candidate
            src_dir = possible_src
            return project_dir, src_dir

    raise RuntimeError(
        "Could not find src/main.py and src/config.json. "
        "Save the .blend file in the project root or models folder, "
        "or open this script directly from the src folder."
    )


try:
    PROJECT_DIR, SRC_DIR = find_project_paths()
except RuntimeError:
    
    PROJECT_DIR = r"C:\Users\iharu\Documents\Gate Project\src"
    SRC_DIR     = os.path.join(PROJECT_DIR, "src")
    print("[Bridge Watcher] Used hardcoded fallback paths.")

CONFIG_PATH = os.path.join(SRC_DIR, "config.json")
MAIN_SCRIPT = os.path.join(SRC_DIR, "main.py")
OUTPUT_IFC_PATH = os.path.join(PROJECT_DIR, "ifc_output", "complete_bridge.ifc")


state = {
    "last_mtime": None,
    "is_updating": False,
    "has_built_once": False
}


# ------------------------------------------------------------
# SCRIPT RUNNER
# ------------------------------------------------------------

def run_main_pipeline():
    """
    Runs src/main.py using the same normal Python command
    that works in VS Code/PowerShell.
    """

    if not os.path.exists(MAIN_SCRIPT):
        print("[Bridge Watcher] main.py not found:", MAIN_SCRIPT)
        return False

    print("[Bridge Watcher] Running bridge generation pipeline:")
    print("[Bridge Watcher] python", MAIN_SCRIPT)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        ["python", MAIN_SCRIPT],
        cwd=SRC_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env
    )

    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        print("[Bridge Watcher] main.py failed:")
        print(result.stderr)
        return False

    if not os.path.exists(OUTPUT_IFC_PATH):
        print("[Bridge Watcher] complete_bridge.ifc was not created:")
        print(OUTPUT_IFC_PATH)
        return False

    print("[Bridge Watcher] IFC regenerated successfully:")
    print(OUTPUT_IFC_PATH)
    return True


# ------------------------------------------------------------
# BONSAI / BLENDER REFRESH
# ------------------------------------------------------------

def refresh_bonsai_ifc():
    """
    Loads the generated IFC into Blender/Bonsai.

    We use load_project directly instead of reload_ifc_file because
    reload_ifc_file can fail if Bonsai still points to an old or missing IFC path.
    """

    print("[Bridge Watcher] Loading updated IFC into Blender/Bonsai...")

    if not os.path.exists(OUTPUT_IFC_PATH):
        print("[Bridge Watcher] Cannot load. IFC not found:")
        print(OUTPUT_IFC_PATH)
        return False

    try:
        bpy.ops.bim.load_project(
            filepath=OUTPUT_IFC_PATH,
            should_start_fresh_session=True,
            use_relative_path=False
        )

        print("[Bridge Watcher] IFC loaded automatically:")
        print(OUTPUT_IFC_PATH)
        return True

    except Exception as load_error:
        print("[Bridge Watcher] Could not load IFC automatically.")
        print("[Bridge Watcher] Load error:", load_error)
        return False


# ------------------------------------------------------------
# UPDATE PIPELINE
# ------------------------------------------------------------

def update_bridge(reason):
    """
    Runs the full update pipeline:
    config.json -> main.py -> complete_bridge.ifc -> Bonsai refresh
    """

    if state["is_updating"]:
        return False

    state["is_updating"] = True

    try:
        start_time = time.time()

        print("")
        print("=" * 70)
        print(f"[Bridge Watcher] Updating bridge because: {reason}")
        print("=" * 70)

        ok = run_main_pipeline()

        if ok:
            refresh_bonsai_ifc()

        elapsed = time.time() - start_time
        print(f"[Bridge Watcher] Update finished in {elapsed:.2f} seconds.")

        if elapsed <= 30:
            print("[Bridge Watcher] Requirement check: update within 30 seconds PASSED.")
        else:
            print("[Bridge Watcher] Requirement check: update exceeded 30 seconds.")

        print("=" * 70)
        print("")

        state["has_built_once"] = True
        return ok

    except Exception as error:
        print("[Bridge Watcher] Update error:", error)
        return False

    finally:
        state["is_updating"] = False


# ------------------------------------------------------------
# CONFIG WATCHER
# ------------------------------------------------------------

def check_config_file():
    """
    Timer function. Blender calls this repeatedly.
    """

    try:
        if not os.path.exists(CONFIG_PATH):
            print("[Bridge Watcher] config.json not found:")
            print(CONFIG_PATH)
            return POLL_SECONDS

        current_mtime = os.path.getmtime(CONFIG_PATH)

        # First timer tick
        if state["last_mtime"] is None:
            state["last_mtime"] = current_mtime

            print("[Bridge Watcher] Started watching config.json")
            print("[Bridge Watcher] Project folder:", PROJECT_DIR)
            print("[Bridge Watcher] Source folder:", SRC_DIR)
            print("[Bridge Watcher] Config path:", CONFIG_PATH)
            print("[Bridge Watcher] Output IFC:", OUTPUT_IFC_PATH)

            if BUILD_ON_START:
                update_bridge("initial watcher start")

            return POLL_SECONDS

        # Later config changes
        if current_mtime != state["last_mtime"]:
            state["last_mtime"] = current_mtime
            update_bridge("config.json changed")

    except Exception as error:
        print("[Bridge Watcher] Timer error:", error)

    return POLL_SECONDS


# ------------------------------------------------------------
# START WATCHER
# ------------------------------------------------------------

def start_watcher():
    old_timer = bpy.app.driver_namespace.get("bridge_param_watcher_timer")

    if old_timer and bpy.app.timers.is_registered(old_timer):
        bpy.app.timers.unregister(old_timer)

    bpy.app.driver_namespace["bridge_param_watcher_timer"] = check_config_file

    bpy.app.timers.register(
        check_config_file,
        first_interval=1.0,
        persistent=True
    )

    print("[Bridge Watcher] Started inside Blender/Bonsai.")
    print("[Bridge Watcher] Waiting for config.json changes.")


start_watcher()