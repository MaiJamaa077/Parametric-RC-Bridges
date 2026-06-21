import bpy
import os
import sys
import json
import time
import subprocess


# ============================================================
# BRIDGE PARAM WATCHER  (fixed)
# Watches src/config.json and regenerates complete_bridge.ifc
# through src/main.py, then reloads it in Blender/Bonsai.
# ============================================================

POLL_SECONDS = 2.0
BUILD_ON_START = False

# ---------------------------------------------------------------------------
# HARDENED PATHS
# Hardcoded to the confirmed project location so path-discovery can never
# silently produce the wrong directory.
# ---------------------------------------------------------------------------
SRC_DIR     = r"C:\Users\iharu\Documents\Blue_Rhinos\src"
PROJECT_DIR = os.path.dirname(SRC_DIR)   # C:\Users\iharu\Documents\Blue_Rhinos
CONFIG_PATH     = os.path.join(SRC_DIR,     "config.json")
MAIN_SCRIPT     = os.path.join(SRC_DIR,     "main.py")
OUTPUT_IFC_PATH = os.path.join(PROJECT_DIR, "ifc_output", "complete_bridge.ifc")


# ---------------------------------------------------------------------------
# PYTHON EXECUTABLE DISCOVERY
# We need the system Python (the one with ifcopenshell), NOT Blender's
# bundled Python.  We search PATH for a python.exe that can import
# ifcopenshell and use the first one that works.
# ---------------------------------------------------------------------------
def _find_system_python():
    """
    Return the path to a Python interpreter that has ifcopenshell.
    Strategy:
      1. Try every python / python3 on PATH.
      2. Fall back to common install locations on Windows.
    """
    import shutil

    candidates = []

    # Entries on PATH
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    # Common Windows install locations
    candidates += [
        r"C:\Python312\python.exe",
        r"C:\Python311\python.exe",
        r"C:\Python310\python.exe",
        r"C:\Python39\python.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Python\Python312\python.exe"),
        os.path.expanduser(r"~\AppData\Local\Programs\Python\Python311\python.exe"),
        os.path.expanduser(r"~\AppData\Local\Programs\Python\Python310\python.exe"),
    ]

    for py in candidates:
        if not py or not os.path.isfile(py):
            continue
        # Quick check: can this interpreter import ifcopenshell?
        probe = subprocess.run(
            [py, "-c", "import ifcopenshell"],
            capture_output=True,
            timeout=8,
        )
        if probe.returncode == 0:
            print(f"[Bridge Watcher] Using Python: {py}")
            return py

    # Last resort: just use 'python' and hope for the best
    print("[Bridge Watcher] WARNING: could not verify ifcopenshell; falling back to 'python'")
    return "python"


PYTHON_EXE = _find_system_python()


state = {
    "last_mtime":    None,
    "is_updating":   False,
    "has_built_once": False,
}


# ---------------------------------------------------------------------------
# SCRIPT RUNNER
# ---------------------------------------------------------------------------
def run_main_pipeline():
    """
    Runs src/main.py with the system Python that has ifcopenshell.
    cwd is set to SRC_DIR so relative imports (main_deck, abutment, etc.)
    resolve correctly — this is the same as running the script from
    a terminal opened in the src folder.
    """
    if not os.path.exists(MAIN_SCRIPT):
        print("[Bridge Watcher] main.py not found:", MAIN_SCRIPT)
        return False

    print("[Bridge Watcher] Running:", PYTHON_EXE, MAIN_SCRIPT)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [PYTHON_EXE, MAIN_SCRIPT],
        cwd=SRC_DIR,          # <-- critical: same as cd into src then python main.py
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        print("[Bridge Watcher] main.py FAILED:")
        print(result.stderr)
        return False

    if not os.path.exists(OUTPUT_IFC_PATH):
        print("[Bridge Watcher] main.py ran but IFC not found at:", OUTPUT_IFC_PATH)
        return False

    print("[Bridge Watcher] IFC regenerated →", OUTPUT_IFC_PATH)
    return True


# ---------------------------------------------------------------------------
# CACHE SYNC
# Writes current config.json values into bpy.app.driver_namespace under
# the same key that bridge_param_editor.py reads on re-registration.
# This must run BEFORE refresh_bonsai_ifc() so that when load_project
# triggers a fresh session and bridge_param_editor re-registers, the
# cache already holds the latest values and the N-panel shows them.
# ---------------------------------------------------------------------------
_CACHE_KEY = "bridge_editor_last_values"

def sync_cache_from_config():
    """
    Reads config.json and pushes every Editable parameter value into
    bpy.app.driver_namespace[_CACHE_KEY] using the same prop_id scheme
    that bridge_param_editor.py uses:
        prop_id = ("p_" + comp_key + "_" + param_key).lower().replace(".", "_")
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        ns = bpy.app.driver_namespace
        if _CACHE_KEY not in ns:
            ns[_CACHE_KEY] = {}
        cache = ns[_CACHE_KEY]

        for comp_key, comp in data.get("components", {}).items():
            for param_key, param in comp.get("parameters", {}).items():
                if param.get("type") != "Editable":
                    continue
                prop_id = ("p_" + comp_key + "_" + param_key).lower().replace(".", "_")
                cache[prop_id] = param.get("example_value")

        print(f"[Bridge Watcher] Cache synced — {len(cache)} values written to driver_namespace.")

    except Exception as e:
        print("[Bridge Watcher] Cache sync failed:", e)


# ---------------------------------------------------------------------------
# BONSAI REFRESH
# ---------------------------------------------------------------------------
def _restore_props_from_cache():
    """
    After Bonsai reloads the IFC the scene is brand new, so all
    PropertyGroup values reset to zero/empty.  This function reads the
    driver_namespace cache (written by sync_cache_from_config) and pushes
    every value back into bridge_params on the new scene.
    Called via a short deferred timer so the scene is fully ready first.
    """
    try:
        ns   = bpy.app.driver_namespace
        cache = ns.get(_CACHE_KEY, {})
        if not cache:
            print("[Bridge Watcher] Cache empty — nothing to restore.")
            return None

        scene = bpy.context.scene
        if not hasattr(scene, "bridge_params"):
            print("[Bridge Watcher] bridge_params not on scene yet — restore skipped.")
            return None

        params = scene.bridge_params
        restored = 0
        for prop_id, value in cache.items():
            if hasattr(params, prop_id):
                try:
                    if isinstance(value, str):
                        setattr(params, prop_id, str(value))
                    else:
                        setattr(params, prop_id, float(value))
                    restored += 1
                except Exception as e:
                    print(f"[Bridge Watcher] Could not restore {prop_id}: {e}")

        print(f"[Bridge Watcher] N-panel restored — {restored} values pushed to PropertyGroup.")
    except Exception as e:
        print("[Bridge Watcher] Restore failed:", e)
    return None  # run once only


def _purge_ifc_objects():
    """
    Removes all IFC-linked objects and collections from the scene without
    calling should_start_fresh_session=True, which would wipe the entire
    Blender session and close the N-Panel.

    Steps:
      1. Try bim.unload_project — cleanest path, removes the IfcStore link.
      2. Manually delete every object stamped with ifc_definition_id or an
         Ifc* name prefix.
      3. Remove leftover IFC collections.
      4. Purge orphaned data-blocks.
    """
    # Step 1 — try Bonsai's own unload operator
    try:
        bpy.ops.bim.unload_project()
        print("[Bridge Watcher] bim.unload_project succeeded.")
    except Exception as e:
        print(f"[Bridge Watcher] bim.unload_project not available ({e}); falling back to manual purge.")

    # Step 2 — remove IFC objects
    to_delete = [
        obj for obj in bpy.data.objects
        if obj.get("ifc_definition_id") is not None
        or obj.name.startswith(("Ifc", "IfcOpeningElement", "IfcSpace"))
    ]
    for obj in to_delete:
        bpy.data.objects.remove(obj, do_unlink=True)
    print(f"[Bridge Watcher] Removed {len(to_delete)} IFC object(s).")

    # Step 3 — remove IFC collections
    ifc_prefixes = ("Ifc", "IfcProject", "IfcSite", "IfcBuilding",
                    "OpenBIM", "Bridge")
    colls = [c for c in bpy.data.collections
             if any(c.name.startswith(p) for p in ifc_prefixes)]
    for c in colls:
        bpy.data.collections.remove(c)
    print(f"[Bridge Watcher] Removed {len(colls)} IFC collection(s).")

    # Step 4 — purge orphaned meshes / materials / curves
    try:
        bpy.ops.outliner.orphans_purge(
            do_local_ids=True, do_linked_ids=True, do_recursive=True
        )
    except Exception as e:
        print(f"[Bridge Watcher] Orphan purge skipped: {e}")


def refresh_bonsai_ifc():
    print("[Bridge Watcher] Reloading IFC in Bonsai…")

    if not os.path.exists(OUTPUT_IFC_PATH):
        print("[Bridge Watcher] Cannot reload — IFC missing:", OUTPUT_IFC_PATH)
        return False

    try:
        # Purge old IFC geometry BEFORE loading — prevents stacking
        _purge_ifc_objects()

        # should_start_fresh_session=False keeps the Blender session alive:
        # — N-Panel stays open
        # — PropertyGroup values are NOT reset
        # — Addon re-register is NOT triggered
        # The manual purge above ensures no geometry stacks up.
        bpy.ops.bim.load_project(
            filepath=OUTPUT_IFC_PATH,
            should_start_fresh_session=False,
            use_relative_path=False,
        )
        print("[Bridge Watcher] Bonsai reload complete. N-Panel preserved.")
        return True

    except Exception as e:
        print("[Bridge Watcher] Bonsai reload failed:", e)
        return False


# ---------------------------------------------------------------------------
# UPDATE PIPELINE
# ---------------------------------------------------------------------------
def update_bridge(reason):
    if state["is_updating"]:
        return False

    state["is_updating"] = True
    try:
        start = time.time()
        print()
        print("=" * 70)
        print(f"[Bridge Watcher] Trigger: {reason}")
        print("=" * 70)

        ok = run_main_pipeline()
        if ok:
            refresh_bonsai_ifc()

        elapsed = time.time() - start
        print(f"[Bridge Watcher] Done in {elapsed:.2f}s")
        print("=" * 70)
        print()

        state["has_built_once"] = True
        return ok

    except Exception as e:
        print("[Bridge Watcher] Unexpected error:", e)
        return False
    finally:
        state["is_updating"] = False


# ---------------------------------------------------------------------------
# CONFIG WATCHER  (Blender timer callback)
# ---------------------------------------------------------------------------
def check_config_file():
    try:
        if not os.path.exists(CONFIG_PATH):
            print("[Bridge Watcher] config.json not found:", CONFIG_PATH)
            return POLL_SECONDS

        current_mtime = os.path.getmtime(CONFIG_PATH)

        if state["last_mtime"] is None:
            state["last_mtime"] = current_mtime
            print("[Bridge Watcher] Watching:", CONFIG_PATH)
            print("[Bridge Watcher] Python  :", PYTHON_EXE)
            print("[Bridge Watcher] IFC out :", OUTPUT_IFC_PATH)
            if BUILD_ON_START:
                update_bridge("initial start")
            return POLL_SECONDS

        if current_mtime != state["last_mtime"]:
            state["last_mtime"] = current_mtime
            update_bridge("config.json changed")

    except Exception as e:
        print("[Bridge Watcher] Timer error:", e)

    return POLL_SECONDS


# ---------------------------------------------------------------------------
# START
# ---------------------------------------------------------------------------
def start_watcher():
    ns = bpy.app.driver_namespace

    # Kill ALL previously registered watcher timers — including any stale
    # instance from a different project folder that may still be running.
    # We track every registered function under a known key and unregister
    # each one before starting fresh.
    for key in list(ns.keys()):
        if key.startswith("bridge_param_watcher"):
            fn = ns.pop(key)
            try:
                if bpy.app.timers.is_registered(fn):
                    bpy.app.timers.unregister(fn)
                    print(f"[Bridge Watcher] Stopped old timer: {key}")
            except Exception:
                pass

    # Reset state so the new instance starts clean
    state["last_mtime"]    = None
    state["is_updating"]   = False
    state["has_built_once"] = False

    ns["bridge_param_watcher_timer"] = check_config_file
    bpy.app.timers.register(check_config_file, first_interval=1.0, persistent=True)

    print("[Bridge Watcher] Started. Polling every", POLL_SECONDS, "seconds.")


start_watcher()