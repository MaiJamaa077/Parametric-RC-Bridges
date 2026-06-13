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
    
    PROJECT_DIR = r"C:\Users\iharu\Documents\Blue_Rhinos"
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

def _purge_ifc_objects():
    """
    Removes all Blender objects and collections that belong to the current
    IFC session, without calling should_start_fresh_session=True (which would
    wipe the N-panel and all addon state).

    Strategy:
      1. Try bim.unload_project — cleanest path, removes the IfcStore link.
      2. Manually delete every object whose name starts with a known IFC prefix
         or that has an ifc_definition_id, then remove empty collections.
      3. Call bpy.ops.outliner.orphans_purge to free leftover data-blocks.
    """

    # --- Step 1: try the Bonsai unload operator (best case) -----------------
    try:
        bpy.ops.bim.unload_project()
        print("[Bridge Watcher] bim.unload_project succeeded.")
    except Exception as e:
        print(f"[Bridge Watcher] bim.unload_project not available ({e}); "
              "falling back to manual purge.")

    # --- Step 2: remove IFC objects from every scene ------------------------
    # Collect objects to delete (never modify a collection while iterating it)
    to_delete = []
    for obj in bpy.data.objects:
        # Bonsai stamps IFC objects with this custom property
        if obj.get("ifc_definition_id") is not None:
            to_delete.append(obj)
            continue
        # Belt-and-suspenders: names Bonsai assigns follow these prefixes
        if obj.name.startswith(("Ifc", "IfcOpeningElement", "IfcSpace")):
            to_delete.append(obj)

    for obj in to_delete:
        bpy.data.objects.remove(obj, do_unlink=True)

    print(f"[Bridge Watcher] Removed {len(to_delete)} IFC object(s).")

    # --- Step 3: remove IFC collections (they stack too) --------------------
    ifc_coll_prefixes = ("Ifc", "IfcProject", "IfcSite", "IfcBuilding",
                         "OpenBIM", "Bridge")
    colls_to_delete = [
        c for c in bpy.data.collections
        if any(c.name.startswith(p) for p in ifc_coll_prefixes)
    ]
    for coll in colls_to_delete:
        bpy.data.collections.remove(coll)

    print(f"[Bridge Watcher] Removed {len(colls_to_delete)} IFC collection(s).")

    # --- Step 4: purge orphaned meshes / materials / etc. -------------------
    try:
        bpy.ops.outliner.orphans_purge(
            do_local_ids=True, do_linked_ids=True, do_recursive=True
        )
        print("[Bridge Watcher] Orphan data-blocks purged.")
    except Exception as e:
        print(f"[Bridge Watcher] Orphan purge skipped: {e}")


def refresh_bonsai_ifc():
    """
    Purges the current IFC geometry from the scene, then loads the freshly
    generated IFC — without a full session reset so the N-panel stays open.
    """

    print("[Bridge Watcher] Loading updated IFC into Blender/Bonsai...")

    if not os.path.exists(OUTPUT_IFC_PATH):
        print("[Bridge Watcher] Cannot load. IFC not found:")
        print(OUTPUT_IFC_PATH)
        return False

    try:
        # Remove old IFC objects/collections before loading the new file.
        # This prevents geometry stacking while keeping should_start_fresh_session=False
        # so the N-panel and addon state are preserved.
        _purge_ifc_objects()

        bpy.ops.bim.load_project(
            filepath=OUTPUT_IFC_PATH,
            should_start_fresh_session=False,
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