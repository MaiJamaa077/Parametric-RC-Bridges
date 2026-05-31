"""
BLUE RHINOS - BONSAI SCRIPTING PANEL WRAPPER

"""
import bpy
import sys
import os
import json

# ─────────────────────────────────────────────────────────────────────────────
# 1. PATH RESOLUTION
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = r"C:\Users\iharu\Documents\Blue_Rhinos"
SRC_DIR      = os.path.join(PROJECT_ROOT, "src")
CONFIG_PATH  = os.path.join(SRC_DIR, "config.json")
IFC_OUTPUT   = os.path.join(PROJECT_ROOT, "ifc_output", "complete_bridge.ifc")

# ─────────────────────────────────────────────────────────────────────────────
# 2. RAB-ING STANDARDS & COMPONENT CHECKLIST
# ─────────────────────────────────────────────────────────────────────────────
REQUIRED_COMPONENTS = {
    "foundation": "Foundation",
    "blinding":   "Blinding layer",
    "abutment":   "Abutments",
    "wing":       "Wingwalls",
    "deck":       "Deck slab",
    "rebar":      "Rebar",
}
RAB_CLEARANCE_MIN    = 4.70  # m
RAB_WALL_THICKNESS   = 1.0   # m (±5% tolerance)


def _log(msg, level="INFO"):
    tag = {"INFO": "✔", "HEAD": "═", "FAIL": "✘", "WARN": "⚠"}.get(level, "·")
    print(f"[BONSAI_COCKPIT] {tag} {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# 3. SETUP PATHS
# ─────────────────────────────────────────────────────────────────────────────

def setup_project_paths():
    """Appends root and src to sys.path so Blender can find the generation modules."""
    for path in (PROJECT_ROOT, SRC_DIR):
        if path not in sys.path:
            sys.path.append(path)
    _log(f"Paths registered: {PROJECT_ROOT}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. SCENE CLEANUP
# ─────────────────────────────────────────────────────────────────────────────

def clear_old_bridge():
    """Deletes existing bridge/IFC objects to ensure a clean staging area."""
    keywords = ("ifc", "bridge", "abutment", "wingwall", "deck",
                "foundation", "sauberkeit", "rebar")
    bpy.ops.object.select_all(action='DESELECT')
    deleted = 0
    for obj in bpy.data.objects:
        if any(kw in obj.name.lower() for kw in keywords):
            obj.select_set(True)
            deleted += 1
    if deleted:
        bpy.ops.object.delete()
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    _log(f"Scene cleaned: {deleted} old object(s) removed.")


# ─────────────────────────────────────────────────────────────────────────────
# 5. BRIDGE GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def generate_bridge_via_engine():
    """
    Calls build_bridge() from src/main.py — the real Master Assembly sequence.
    Order: base scaffold → Deck → Foundation → Abutments → Wingwalls.
   
    """
    import main as bridge_main

    _log("Executing Master Assembly sequence...", "HEAD")
    bridge_main.build_bridge()
    _log(f"Engine: IFC saved to {IFC_OUTPUT}")

    # Return config so later steps can read geometric parameters
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────────────────────
# 6. IFC IMPORT VIA BONSAI
# ─────────────────────────────────────────────────────────────────────────────

def import_to_bonsai():
    """Uses the Bonsai operator to load the model into the 3D viewport."""
    if not os.path.exists(IFC_OUTPUT):
        _log(f"IFC file not found at {IFC_OUTPUT} — skipping import.", "FAIL")
        return

    try:
        # Bonsai ≥ 0.0.231
        bpy.ops.bim.load_project(filepath=IFC_OUTPUT)
        _log("Bonsai: Model imported via bim.load_project.")
    except AttributeError:
        try:
            # Older BlenderBIM fallback
            bpy.ops.import_ifc.bim(filepath=IFC_OUTPUT)
            _log("Bonsai: Model imported via import_ifc.bim (legacy).")
        except Exception as e:
            _log(f"Bonsai import failed: {e}", "FAIL")


# ─────────────────────────────────────────────────────────────────────────────
# 7. CAMERA & SCENE STAGING
# ─────────────────────────────────────────────────────────────────────────────

def setup_technical_view():
    """Stages a 3/4 isometric camera and enables material preview shading."""
    import mathutils

    cam_name = "Cockpit_Technical_View"
    if cam_name not in bpy.data.objects:

        # Create camera
        cam_data = bpy.data.cameras.new(cam_name)
        cam_obj  = bpy.data.objects.new(cam_name, cam_data)
        cam_obj.location = (18, -18, 12)
        cam_obj.rotation_euler = mathutils.Euler((1.1, 0, 0.785), 'XYZ')
        bpy.context.scene.collection.objects.link(cam_obj)

    bpy.context.scene.camera = bpy.data.objects[cam_name]

    # Viewport shading — iterate all screens/areas safely
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'MATERIAL'
                break

    _log("Technical View: Camera set and Material shading active.")


# ─────────────────────────────────────────────────────────────────────────────
# 8. VISUAL QUALITY GATE
# ─────────────────────────────────────────────────────────────────────────────

def run_visual_quality_gate(config):
    """Verifies RAB-ING compliance and all 6 mandatory components are present."""
    _log("--- VISUAL QUALITY GATE (PHASE 3.3) ---", "HEAD")

    # Check 1: Component presence
    found = []
    for kw, label in REQUIRED_COMPONENTS.items():
        exists = any(kw in obj.name.lower() for obj in bpy.data.objects)
        status = "✔" if exists else "✘"
        print(f"  [ {status} ] {label}")
        if exists:
            found.append(label)

    # Check 2: Clearance height from config
    try:
        clearance = config["components"]["abutment"]["parameters"]["Abut_h"]["example_value"]
    except KeyError:
        # Fallback: try a flat key
        clearance = None

    if clearance is not None:
        status_c = "✔" if clearance >= RAB_CLEARANCE_MIN else "✘"
        print(f"  [ {status_c} ] Abutment height (clearance proxy): {clearance} m  (config value)")
    else:
        print(f"  [ · ] Vertical clearance: key not found in config — check manually")

    # Check 3: Wall thickness
    try:
        wall_t = config["components"]["abutment"]["parameters"]["Abut_t"]["example_value"]
    except KeyError:
        wall_t = None

    if wall_t is not None:
        in_tolerance = abs(wall_t - RAB_WALL_THICKNESS) <= RAB_WALL_THICKNESS * 0.05
        status_w = "✔" if in_tolerance else "✘"
        print(f"  [ {status_w} ] Abutment thickness (Abut_t): {wall_t} m  (RAB-ING target 1.0 m ±5%)")
    else:
        print(f"  [ · ] Wall thickness: key not found in config — check manually")

    _log(f"Quality Gate: {len(found)}/6 components detected.")
    return len(found) == 6


# ─────────────────────────────────────────────────────────────────────────────
# 9. MASTER ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_integration_pipeline():
    """The master 'One-Click' method for the Scripting Panel."""
    setup_project_paths()
    clear_old_bridge()
    config = generate_bridge_via_engine()
    import_to_bonsai()
    setup_technical_view()
    run_visual_quality_gate(config)
    _log("Pipeline complete. Press NUMPAD-0 to enter camera view.")


if __name__ == "__main__":
    run_integration_pipeline()
