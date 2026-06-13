bl_info = {
    "name": "Bridge Parameter Editor",
    "author": "Claude / AI",
    "version": (1, 3, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar (N) > Bridge",
    "description": "Edit the 'Editable' parameters of config.json and auto-save every change",
    "category": "3D View",
}

import bpy
import json
import os
import tempfile
import shutil

# ---------------------------------------------------------------------------
# PATH DISCOVERY
# ---------------------------------------------------------------------------
def find_project_paths():
    candidates = []
    blend_dir = os.path.normpath(bpy.path.abspath("//"))
    candidates.append(blend_dir)
    candidates.append(os.path.dirname(blend_dir))

    if "__file__" in globals():
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(script_dir)
        candidates.append(os.path.dirname(script_dir))

    unique_candidates = []
    for path in candidates:
        if path and path not in unique_candidates:
            unique_candidates.append(path)

    for candidate in unique_candidates:
        candidate = os.path.normpath(candidate)
        if (os.path.basename(candidate).lower() == "src"
                and os.path.exists(os.path.join(candidate, "main.py"))
                and os.path.exists(os.path.join(candidate, "config.json"))):
            return os.path.dirname(candidate), candidate

        possible_src = os.path.join(candidate, "src")
        if (os.path.exists(os.path.join(possible_src, "main.py"))
                and os.path.exists(os.path.join(possible_src, "config.json"))):
            return candidate, possible_src

    raise RuntimeError("Could not find src/main.py and src/config.json.")


try:
    PROJECT_DIR, SRC_DIR = find_project_paths()
except RuntimeError:
    PROJECT_DIR = r"C:\Users\iharu\Documents\Blue_Rhinos"
    SRC_DIR     = os.path.join(PROJECT_DIR, "src")

CONFIG_PATH = os.path.join(SRC_DIR, "config.json")

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------
_param_registry = {}   # prop_id -> {component, key, is_string, label, unit}
_ui_groups      = []   # [(component_key, component_label, [prop_ids])]
_dynamic_class  = None
_loading        = False   # True while we are pushing JSON values into props
                          # (prevents the update callback from writing back)


# ---------------------------------------------------------------------------
# JSON helpers  — atomic write so the watcher never reads a half-written file
# ---------------------------------------------------------------------------
def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path, data):
    """
    Write JSON to a temp file in the same directory, then rename over the
    target.  On Windows, rename is not atomic but it is much safer than
    truncating-in-place: the watcher will never read a half-written file.
    """
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # On Windows, os.replace handles the case where the destination exists
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _format_number(v):
    fv = float(v)
    return int(fv) if fv.is_integer() else round(fv, 6)


# ---------------------------------------------------------------------------
# Per-property update callback
# ---------------------------------------------------------------------------
def _make_update(prop_id):
    def _update(self, context):
        global _loading
        if _loading:
            return

        info = _param_registry.get(prop_id)
        if info is None:
            return

        if not os.path.isfile(CONFIG_PATH):
            print(f"[Bridge Editor] config.json not found: {CONFIG_PATH}")
            return

        try:
            data = _read_json(CONFIG_PATH)

            value = getattr(self, prop_id)
            if not info["is_string"]:
                value = _format_number(value)

            data["components"][info["component"]]["parameters"][info["key"]]["example_value"] = value

            _write_json_atomic(CONFIG_PATH, data)

            # ----------------------------------------------------------------
            # Persist the in-memory "last known good" value into the
            # driver_namespace cache so it survives even a full module reload
            # triggered by Bonsai — not just unregister/register cycles.
            # ----------------------------------------------------------------
            _get_last_values()[prop_id] = value

        except Exception as e:
            print(f"[Bridge Editor] Error while saving '{prop_id}': {e}")
            import traceback
            traceback.print_exc()

    return _update


# ---------------------------------------------------------------------------
# In-memory cache: survives re-registration AND full module reloads
# ---------------------------------------------------------------------------
# bpy.app.driver_namespace is a plain dict owned by Blender itself, not by
# any Python module.  It is never reset when an addon is unregistered or when
# Bonsai triggers importlib.reload() on our module — so the user's last-typed
# values survive every kind of reload that Bonsai can throw at us.

_CACHE_KEY = "bridge_editor_last_values"

def _get_last_values():
    """Return the persistent cache dict, creating it on first access."""
    ns = bpy.app.driver_namespace
    if _CACHE_KEY not in ns:
        ns[_CACHE_KEY] = {}
    return ns[_CACHE_KEY]


# ---------------------------------------------------------------------------
# Dynamic PropertyGroup
# ---------------------------------------------------------------------------
def _clear_dynamic_group():
    global _dynamic_class
    if _dynamic_class is not None:
        if hasattr(bpy.types.Scene, "bridge_params"):
            del bpy.types.Scene.bridge_params
        try:
            bpy.utils.unregister_class(_dynamic_class)
        except RuntimeError:
            pass
        _dynamic_class = None
    _param_registry.clear()
    _ui_groups.clear()


def _build_dynamic_group(data):
    global _dynamic_class
    _clear_dynamic_group()
    annotations = {}

    for comp_key, comp in data.get("components", {}).items():
        prop_ids = []
        for key, p in comp.get("parameters", {}).items():
            if p.get("type") != "Editable":
                continue

            prop_id   = ("p_" + comp_key + "_" + key).lower().replace(".", "_")
            value     = p.get("example_value")
            is_string = isinstance(value, str)
            label     = p.get("parameter", key)
            unit      = p.get("unit", "")
            display_name = f"{label} [{unit}]" if unit else label

            _param_registry[prop_id] = {
                "component": comp_key,
                "key":       key,
                "is_string": is_string,
                "label":     label,
                "unit":      unit,
            }

            # Use the cached value if available (survives Bonsai reloads),
            # otherwise fall back to the JSON file value.
            cached = _get_last_values().get(prop_id)
            default = cached if cached is not None else value

            if is_string:
                annotations[prop_id] = bpy.props.StringProperty(
                    name=display_name,
                    description=f"{label} ({key})",
                    default=str(default),
                    update=_make_update(prop_id),
                )
            else:
                annotations[prop_id] = bpy.props.FloatProperty(
                    name=display_name,
                    description=f"{label} ({key})",
                    default=float(default),
                    precision=3,
                    step=10,
                    update=_make_update(prop_id),
                )

            prop_ids.append(prop_id)

        if prop_ids:
            comp_label = comp_key.replace("_", " ").title()
            _ui_groups.append((comp_key, comp_label, prop_ids))

    cls = type(
        "BRIDGE_PG_params",
        (bpy.types.PropertyGroup,),
        {"__annotations__": annotations},
    )
    bpy.utils.register_class(cls)
    bpy.types.Scene.bridge_params = bpy.props.PointerProperty(type=cls)
    _dynamic_class = cls


def _load_values_into_props(context, data):
    """
    Push values from `data` (or from _last_values cache) into the live
    PropertyGroup.  Skips the update callback via the _loading guard.
    """
    global _loading
    _loading = True
    try:
        params = context.scene.bridge_params
        for prop_id, info in _param_registry.items():
            # Prefer the driver_namespace cache so that a Bonsai-triggered
            # module reload never rolls back a value the user just changed.
            cached = _get_last_values().get(prop_id)
            if cached is not None:
                file_value = cached
            else:
                file_value = (
                    data["components"][info["component"]]
                        ["parameters"][info["key"]]
                        ["example_value"]
                )

            if info["is_string"]:
                setattr(params, prop_id, str(file_value))
            else:
                setattr(params, prop_id, float(file_value))
    finally:
        _loading = False


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------
class BRIDGE_OT_reload_values(bpy.types.Operator):
    bl_idname  = "bridge.reload_values"
    bl_label   = "Reload values"
    bl_description = (
        "Discard in-memory overrides and re-read all values from config.json"
    )

    def execute(self, context):
        if not os.path.isfile(CONFIG_PATH):
            self.report({'ERROR'}, "config.json not found")
            return {'CANCELLED'}
        try:
            data = _read_json(CONFIG_PATH)
            # Clear the cache so we truly get the on-disk state
            _get_last_values().clear()
            # Always rebuild — not just when the class is missing.
            # This is the only way new/removed parameters in config.json
            # are picked up, since the PropertyGroup annotations are frozen
            # at class-creation time.
            _build_dynamic_group(data)
            _load_values_into_props(context, data)
            self.report({'INFO'}, "Values reloaded from config.json")
        except Exception as e:
            self.report({'ERROR'}, "Invalid JSON: " + str(e))
            return {'CANCELLED'}
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
class BRIDGE_PT_panel(bpy.types.Panel):
    bl_label      = "Bridge Parameter Editor"
    bl_idname     = "BRIDGE_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category   = "Bridge"

    def draw(self, context):
        layout = self.layout
        scene  = context.scene

        row = layout.row(align=True)
        row.operator("bridge.reload_values", icon='FILE_REFRESH', text="Reload from JSON")

        if _dynamic_class is None or not hasattr(scene, "bridge_params"):
            layout.label(text="Failed to load config.json", icon='ERROR')
            return

        params = scene.bridge_params
        layout.label(text="Changes auto-saved & trigger watcher", icon='FILE_REFRESH')

        for comp_key, comp_label, prop_ids in _ui_groups:
            box = layout.box()
            box.label(text=comp_label, icon='MOD_BUILD')
            col = box.column(align=True)
            for prop_id in prop_ids:
                col.prop(params, prop_id)


# ---------------------------------------------------------------------------
# Register / Unregister
# ---------------------------------------------------------------------------
classes = (
    BRIDGE_OT_reload_values,
    BRIDGE_PT_panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)

    if os.path.isfile(CONFIG_PATH):
        try:
            data = _read_json(CONFIG_PATH)
            _build_dynamic_group(data)
            # _get_last_values() already has any previously-set values baked into
            # the default= of each prop, so no explicit load call is needed.
        except Exception as e:
            print(f"[Bridge Editor] Error loading JSON on register: {e}")
    else:
        print(f"[Bridge Editor] config.json not found at: {CONFIG_PATH}")


def unregister():
    _clear_dynamic_group()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()