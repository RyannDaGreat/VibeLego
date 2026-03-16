"""
Blender-side script for live build123d preview.

Command, specific. Launched by run.sh inside Blender. Watches a build123d
source file for changes, re-runs it via `uv run` (no venv needed), and
updates the mesh in-place (preserving materials, transforms, and modifiers).

Usage (via run.sh, not directly):
    blender --factory-startup --python blender_watcher.py -- <source.py> <stl_path>
"""

import bpy
import glob
import json
import os
import shutil
import sys
import subprocess
import tempfile
import time


# ── Parse arguments ────────────────────────────────────────────────────────────

def parse_custom_args():
    """
    Query, specific. Extract arguments after '--' from sys.argv.

    Returns:
        tuple: (source_path, stl_path)
    """
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError(
            "No custom arguments found. "
            "Usage: blender --python blender_watcher.py -- <source.py> <stl_path>"
        )
    custom = argv[argv.index("--") + 1 :]
    if len(custom) < 2:
        raise RuntimeError(
            f"Expected 2 arguments after '--', got {len(custom)}: {custom}"
        )
    return custom[0], custom[1]


SOURCE_FILE, STL_PATH = parse_custom_args()

# Derive repo root and submodule path from this script's location
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD123D_SUBMODULE = os.path.join(REPO_ROOT, "build123d")

# Find uv binary
UV_PATH = shutil.which("uv")
if UV_PATH is None:
    raise RuntimeError("uv not found on PATH. Install via: curl -LsSf https://astral.sh/uv/install.sh | sh")

POLL_INTERVAL_SECONDS = 0.5
OBJECT_NAME = "build123d_preview"
WATCH_DIR = os.path.dirname(os.path.abspath(SOURCE_FILE))
PANEL_STL_PATH = os.path.join(tempfile.gettempdir(), "build123d_panel_preview.stl")

DEBOUNCE_SECONDS = 0.3

_last_dir_mtime = 0.0
_last_stl_mtime = 0.0
_panel_rebuild_pending = False
_panel_def = None          # loaded from WATCH_DIR/panel_def.py if present
_panel_param_keys = []     # [(blender_key, json_key), ...] built at registration
_parametric_script = None  # absolute path to the parametric build script
_worker = None             # persistent Popen process (build_worker.py)
_registered_classes = []   # classes to unregister on panel hot-reload

WORKER_SCRIPT = os.path.join(REPO_ROOT, "build_worker.py")


# ── Scene setup ────────────────────────────────────────────────────────────────

def clear_default_scene():
    """
    Command, specific. Remove all default objects (Camera, Cube, Light)
    and purge orphan data for a clean starting point.
    """
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.outliner.orphans_purge(do_recursive=True)


def _get_3d_space():
    """
    Query, general. Return the first VIEW_3D SpaceView3D in the current screen.

    Returns:
        bpy.types.SpaceView3D or None

    Examples:
        >>> # space = _get_3d_space()
    """
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    return space
    return None


def setup_viewport():
    """
    Command, specific. Configure the 3D viewport for CAD preview:
    orthographic projection, matcap shading with ceramic studio light,
    cavity highlighting for edge definition.
    """
    space = _get_3d_space()
    if space:
        space.region_3d.view_perspective = "ORTHO"
        space.shading.type = "SOLID"
        space.shading.light = "MATCAP"
        space.shading.studio_light = "ceramic_lightbulb.exr"
        space.shading.show_cavity = True
        space.shading.cavity_type = "BOTH"
        space.overlay.show_floor = True
        space.overlay.show_axis_x = True
        space.overlay.show_axis_y = True
        space.show_region_ui = True


# ── Anatomy highlight ────────────────────────────────────────────────────────
# Region definitions and classify_face come from panel_def.py (via panel_common).
# blender_watcher.py only handles the generic Blender machinery: color attributes,
# materials, viewport toggle. The _anatomy_* module globals are set by register_panel().

ANATOMY_COLOR_ATTR_NAME = "anatomy_region"
_anatomy_colors = None        # dict: region -> RGBA, from panel_def.ANATOMY_COLORS
_anatomy_region_items = None  # list of enum tuples, from panel_def.ANATOMY_REGION_ITEMS
_anatomy_region_groups = None  # dict: group_key -> [child_keys], from panel_def
_classify_face_fn = None      # callable(mesh, poly, params) -> str


def _apply_anatomy_colors(obj, params, highlight_region="ALL"):
    """
    Command, specific. Classify all faces of the mesh by anatomical region
    and apply per-face vertex colors. Creates or replaces the color attribute.

    When highlight_region is "ALL", every region gets its own color.
    When a specific region is selected, only that region is colored and
    everything else is light gray — isolating it visually.

    Also sets up a material that displays the color attribute in the viewport.

    Args:
        obj (bpy.types.Object): The mesh object.
        params (dict): Panel params for geometry bounds.
        highlight_region (str): "ALL" or a region key (e.g. "studs", "walls").
    """
    if _classify_face_fn is None or _anatomy_colors is None:
        return

    mesh = obj.data
    dimmed = _anatomy_colors["default"]

    # Remove old color attribute if present
    existing = mesh.color_attributes.get(ANATOMY_COLOR_ATTR_NAME)
    if existing:
        mesh.color_attributes.remove(existing)

    color_attr = mesh.color_attributes.new(
        name=ANATOMY_COLOR_ATTR_NAME,
        type='FLOAT_COLOR',
        domain='CORNER',
    )
    mesh.color_attributes.active = color_attr

    # Resolve group regions (e.g. "walls_all" -> {"walls", "taper"})
    groups = _anatomy_region_groups or {}
    match_set = set(groups[highlight_region]) if highlight_region in groups else None

    # Classify and color each face
    color_data = color_attr.data
    for poly in mesh.polygons:
        region = _classify_face_fn(mesh, poly, params)
        if highlight_region == "ALL":
            color = _anatomy_colors.get(region, dimmed)
        elif match_set is not None:
            color = _anatomy_colors.get(region, dimmed) if region in match_set else dimmed
        else:
            color = _anatomy_colors.get(region, dimmed) if region == highlight_region else dimmed
        for loop_idx in poly.loop_indices:
            color_data[loop_idx].color = color

    # Set up material to display color attribute
    _setup_anatomy_material(obj)


def _clear_anatomy_colors(obj):
    """
    Command, specific. Remove anatomy color attribute and restore the
    default white plastic material.

    Args:
        obj (bpy.types.Object): The mesh object.
    """
    mesh = obj.data
    existing = mesh.color_attributes.get(ANATOMY_COLOR_ATTR_NAME)
    if existing:
        mesh.color_attributes.remove(existing)

    _setup_default_material(obj)


def _setup_material(obj, mat_name, configure_fn):
    """
    Command, specific. Get-or-create a material, clear its nodes, call
    configure_fn to populate the node tree, and assign it to obj's slot 0.

    Args:
        obj (bpy.types.Object): The mesh object.
        mat_name (str): Material name (reused if already exists).
        configure_fn (callable): (nodes, links) -> None. Adds shader nodes.

    Examples:
        >>> # _setup_material(obj, "my_mat", lambda n, l: ...)
    """
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(name=mat_name)

    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    configure_fn(mat.node_tree.nodes, mat.node_tree.links)

    if len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat


def _configure_anatomy_nodes(nodes, links):
    """
    Command, specific. Populate node tree for anatomy color display:
    Color Attribute -> Principled BSDF -> Output.
    """
    attr_node = nodes.new('ShaderNodeAttribute')
    attr_node.attribute_name = ANATOMY_COLOR_ATTR_NAME
    attr_node.location = (-300, 300)

    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 300)
    bsdf.inputs['Roughness'].default_value = 0.4

    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (300, 300)

    links.new(attr_node.outputs['Color'], bsdf.inputs['Base Color'])
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])


def _configure_default_nodes(nodes, links):
    """
    Command, specific. Populate node tree for default white plastic:
    Principled BSDF (white, smooth) -> Output.
    """
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 300)
    bsdf.inputs['Base Color'].default_value = (0.95, 0.95, 0.95, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.3

    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (300, 300)

    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])


def _setup_anatomy_material(obj):
    """Command, specific. Apply anatomy color display material to obj."""
    _setup_material(obj, "anatomy_highlight", _configure_anatomy_nodes)


def _setup_default_material(obj):
    """Command, specific. Apply default white plastic material to obj."""
    _setup_material(obj, "brick_plastic", _configure_default_nodes)


def _on_anatomy_toggle(self, context):
    """
    Command, specific. Callback when anatomy toggle or region selector changes.
    Applies or clears colors on the preview object.
    """
    obj = bpy.data.objects.get(OBJECT_NAME)
    if obj is None:
        return

    props = context.scene.build123d_props
    show = getattr(props, "show_anatomy", False)

    if show:
        region = getattr(props, "anatomy_region", "ALL")
        params = panel_params_to_dict()
        _apply_anatomy_colors(obj, params, highlight_region=region)
        space = _get_3d_space()
        if space:
            space.shading.type = "MATERIAL"
    else:
        _clear_anatomy_colors(obj)
        space = _get_3d_space()
        if space:
            space.shading.type = "SOLID"
            space.shading.light = "MATCAP"
            space.shading.studio_light = "ceramic_lightbulb.exr"


def _reapply_anatomy_if_active():
    """
    Command, specific. If anatomy toggle is on, reapply colors to the
    current mesh. Called after every mesh update to restore colors that
    are lost when geometry is replaced.
    """
    if not hasattr(bpy.types.Scene, "build123d_props"):
        return
    props = bpy.context.scene.build123d_props
    if not getattr(props, "show_anatomy", False):
        return
    obj = bpy.data.objects.get(OBJECT_NAME)
    if obj is None:
        return
    region = getattr(props, "anatomy_region", "ALL")
    params = panel_params_to_dict()
    _apply_anatomy_colors(obj, params, highlight_region=region)


# ── STL import (version-safe) ──────────────────────────────────────────────────

def import_stl(filepath):
    """
    Command, general. Import an STL file using the appropriate Blender
    operator for the current version.

    Blender 4.1+: bpy.ops.wm.stl_import (C++ rewrite)
    Blender <4.1: bpy.ops.import_mesh.stl (legacy Python)

    After calling, the imported object is bpy.context.selected_objects[0].

    Args:
        filepath (str): Absolute path to the .stl file.

    Examples:
        >>> # import_stl("/tmp/box.stl")
        >>> # bpy.context.selected_objects[0].name  # -> "box"
    """
    if hasattr(bpy.ops.wm, "stl_import"):
        bpy.ops.wm.stl_import(filepath=filepath)
    else:
        bpy.ops.import_mesh.stl(filepath=filepath)


# ── Mesh update ────────────────────────────────────────────────────────────────

def update_mesh_from_stl(stl_path):
    """
    Command, specific. Import an STL and update the preview object's mesh
    in-place. On first call, creates the preview object. On subsequent calls,
    replaces only the mesh geometry via clear_geometry() + from_pydata(),
    preserving material slots, transforms, and modifiers.

    Also cleans up temporary import objects and orphan mesh datablocks.

    Args:
        stl_path (str): Path to the STL file to import.
    """
    # Deselect everything
    bpy.ops.object.select_all(action="DESELECT")

    # Import STL — creates a new temporary object
    import_stl(stl_path)

    if not bpy.context.selected_objects:
        print("[watcher] ERROR: STL import produced no objects")
        return

    temp_obj = bpy.context.selected_objects[0]
    temp_mesh = temp_obj.data

    # Extract geometry from imported mesh
    verts = [(v.co.x, v.co.y, v.co.z) for v in temp_mesh.vertices]
    faces = [tuple(p.vertices) for p in temp_mesh.polygons]

    # Get or create the persistent preview object
    target = bpy.data.objects.get(OBJECT_NAME)

    if target is None:
        # First import: rename the temp object and keep it
        temp_obj.name = OBJECT_NAME
        temp_mesh.name = OBJECT_NAME
        print(f"[watcher] Created preview object: {len(verts)} vertices, {len(faces)} faces")
        # Frame the object in viewport (needs context override for startup)
        bpy.ops.object.select_all(action="DESELECT")
        temp_obj.select_set(True)
        bpy.context.view_layer.objects.active = temp_obj
        for area in bpy.context.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "WINDOW":
                        with bpy.context.temp_override(area=area, region=region):
                            bpy.ops.view3d.view_selected()
                        break
                break
        return

    # Subsequent imports: update mesh in-place (preserves materials)
    target_mesh = target.data
    target_mesh.clear_geometry()
    target_mesh.from_pydata(verts, [], faces)
    target_mesh.update(calc_edges=True)

    # Remove the temporary import
    bpy.data.objects.remove(temp_obj, do_unlink=True)
    bpy.data.meshes.remove(temp_mesh, do_unlink=True)

    print(f"[watcher] Updated mesh: {len(verts)} vertices, {len(faces)} faces")


# ── Build subprocess ───────────────────────────────────────────────────────────

def run_build(source_path, stl_path):
    """
    Command, specific. Run a build123d source file via `uv run` subprocess
    (not Blender's Python). The source file is expected to export its result
    to the given STL path. No venv needed — uv manages a cached environment.

    Args:
        source_path (str): Path to the .py file to run.
        stl_path (str): Path where the script should write the STL.

    Returns:
        bool: True if the build succeeded.
    """
    env = os.environ.copy()
    env["BUILD123D_PREVIEW_STL"] = stl_path

    result = subprocess.run(
        [UV_PATH, "run", "--with", BUILD123D_SUBMODULE, source_path],
        env=env,
        capture_output=True,
        text=True,
        cwd=os.path.dirname(source_path),
    )

    if result.stdout.strip():
        print(f"[build] {result.stdout.strip()}")

    if result.returncode != 0:
        print(f"[build] ERROR (exit {result.returncode}):")
        for line in result.stderr.strip().split("\n"):
            print(f"[build]   {line}")
        return False

    return True


# ── Persistent worker ─────────────────────────────────────────────────────

def _spawn_worker():
    """
    Command, specific. Spawn the persistent build worker process. The
    worker imports build123d once and then accepts JSON build requests
    on stdin. Returns the Popen object, or None if spawn failed.

    Returns:
        subprocess.Popen or None
    """
    global _worker

    if _worker is not None:
        _kill_worker()

    proc = subprocess.Popen(
        [UV_PATH, "run", "--with", BUILD123D_SUBMODULE,
         WORKER_SCRIPT, _parametric_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=os.path.dirname(_parametric_script),
    )

    # Wait for ready signal
    ready_line = proc.stdout.readline()
    if not ready_line:
        print("[worker] ERROR: worker exited before ready signal")
        stderr = proc.stderr.read()
        if stderr.strip():
            for line in stderr.strip().split("\n"):
                print(f"[worker]   {line}")
        return None

    ready = json.loads(ready_line)
    print(f"[worker] Spawned (import took {ready.get('import_time', '?')}s)")
    _worker = proc
    return proc


def _kill_worker():
    """
    Command, specific. Kill the persistent worker if it's running.
    """
    global _worker
    if _worker is not None:
        _worker.stdin.close()
        try:
            _worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("[worker] Worker did not exit, sending SIGKILL")
            _worker.kill()
            _worker.wait()
        print("[worker] Killed (will respawn on next slider change)")
        _worker = None


def _get_worker():
    """
    Query, specific. Get the running worker, spawning it if needed.

    Returns:
        subprocess.Popen or None
    """
    global _worker
    if _worker is not None and _worker.poll() is not None:
        print("[worker] Worker died unexpectedly, respawning...")
        _worker = None
    if _worker is None:
        return _spawn_worker()
    return _worker


# ── Panel rebuild (debounced) ──────────────────────────────────────────────

def panel_params_to_dict():
    """
    Query, specific. Read all registered panel properties into a dict using
    the key mapping built at registration time.

    Returns:
        dict: json_key → property value for each registered parameter.
    """
    props = bpy.context.scene.build123d_props
    return {json_key: getattr(props, bpy_key) for bpy_key, json_key in _panel_param_keys}


def _do_panel_rebuild():
    """
    Command, general. Debounce timer callback. Sends params to the
    persistent worker via stdin, reads the response, updates the mesh.

    Returns:
        None: One-shot timer (does not repeat).
    """
    global _panel_rebuild_pending
    _panel_rebuild_pending = False

    worker = _get_worker()
    if worker is None:
        print("[panel] ERROR: no worker available")
        return None

    params = panel_params_to_dict()
    params["stl_path"] = PANEL_STL_PATH

    print(f"[panel] Rebuilding...")
    t_start = time.perf_counter()

    worker.stdin.write(json.dumps(params) + "\n")
    worker.stdin.flush()

    response_line = worker.stdout.readline()
    if not response_line:
        print("[panel] ERROR: worker died during build, respawning...")
        _kill_worker()
        return None

    t_worker = time.perf_counter() - t_start
    response = json.loads(response_line)

    if not response.get("ok"):
        print(f"[panel] ERROR: {response}")
        return None

    if os.path.exists(PANEL_STL_PATH):
        t_mesh_start = time.perf_counter()
        update_mesh_from_stl(PANEL_STL_PATH)
        _reapply_anatomy_if_active()
        t_mesh = time.perf_counter() - t_mesh_start
        build_t = response.get("build", "?")
        export_t = response.get("export", "?")
        print(f"[panel] build={build_t}s  export={export_t}s  mesh={t_mesh:.2f}s  total={t_worker + t_mesh:.2f}s")

    return None


def on_param_change(self, context):
    """
    Command, general. Property update callback. Cancels any pending
    rebuild timer and schedules a new one after DEBOUNCE_SECONDS.
    """
    global _panel_rebuild_pending
    if _panel_rebuild_pending:
        if bpy.app.timers.is_registered(_do_panel_rebuild):
            bpy.app.timers.unregister(_do_panel_rebuild)
    _panel_rebuild_pending = True
    bpy.app.timers.register(_do_panel_rebuild, first_interval=DEBOUNCE_SECONDS)


# ── Dynamic panel builder ────────────────────────────────────────────────
# Reads a panel_def module (pure data: SECTIONS list + PARAMETRIC_SCRIPT)
# and dynamically creates the Blender PropertyGroup + Panel classes.
# No model-specific knowledge lives here.

def _make_bpy_property(param):
    """
    Query, specific. Convert a param dict from panel_def into a
    bpy.props descriptor.

    Args:
        param (dict): Parameter definition with keys: type, label, default,
            and optional min/max/step/precision/description/items.

    Returns:
        bpy.props descriptor (FloatProperty, IntProperty, StringProperty, or EnumProperty).

    Examples:
        >>> # _make_bpy_property({"type": "float", "label": "X", "default": 1.0, "min": 0, "max": 10})
    """
    ptype = param["type"]
    kwargs = {"name": param["label"], "update": on_param_change}

    if "description" in param:
        kwargs["description"] = param["description"]

    if ptype == "float":
        kwargs["default"] = param["default"]
        for k in ("min", "max", "step", "precision"):
            if k in param:
                kwargs[k] = param[k]
        return bpy.props.FloatProperty(**kwargs)

    elif ptype == "int":
        kwargs["default"] = param["default"]
        for k in ("min", "max"):
            if k in param:
                kwargs[k] = param[k]
        return bpy.props.IntProperty(**kwargs)

    elif ptype == "bool":
        kwargs["default"] = param.get("default", False)
        return bpy.props.BoolProperty(**kwargs)

    elif ptype == "string":
        kwargs["default"] = param.get("default", "")
        if "maxlen" in param:
            kwargs["maxlen"] = param["maxlen"]
        return bpy.props.StringProperty(**kwargs)

    elif ptype == "enum":
        kwargs["items"] = param["items"]
        kwargs["default"] = param["default"]
        return bpy.props.EnumProperty(**kwargs)

    raise ValueError(f"Unknown param type: {ptype!r}")


_presets = []  # loaded from panel_def.PRESETS


def _build_panel_classes(sections):
    """
    Command, general. Dynamically create a PropertyGroup and Panel class
    from a list of section definitions (as found in panel_def.SECTIONS).

    Populates the module-level _panel_param_keys list as a side effect.

    Args:
        sections (list[dict]): Section definitions from panel_def module.

    Returns:
        tuple: (PropertyGroupClass, PanelClass) ready for bpy.utils.register_class.
    """
    global _panel_param_keys
    _panel_param_keys = []

    # Build PropertyGroup annotations dynamically
    annotations = {}
    for section in sections:
        for param in section["params"]:
            annotations[param["key"]] = _make_bpy_property(param)
            _panel_param_keys.append((param["key"], param["json_key"]))

    # Build defaults dict for the reset operator
    _defaults = {param["key"]: param["default"]
                 for section in sections for param in section["params"]}

    # Anatomy highlight (display-only, not parametric build params)
    # Registered manually (needs update callback + dynamic enum items),
    # but drawn generically via enable_key section pattern.
    if _anatomy_region_items is not None:
        annotations["show_anatomy"] = bpy.props.BoolProperty(
            name="Show Anatomy Colors",
            description="Color mesh faces by anatomical region (studs, walls, deck, etc.)",
            default=False,
            update=_on_anatomy_toggle,
        )
        annotations["anatomy_region"] = bpy.props.EnumProperty(
            name="Region",
            description="Which region to highlight (All = color everything, or pick one to isolate it)",
            items=_anatomy_region_items,
            default="ALL",
            update=_on_anatomy_toggle,
        )
        _defaults["show_anatomy"] = False
        _defaults["anatomy_region"] = "ALL"

    PropGroup = type(
        "Build123dProperties",
        (bpy.types.PropertyGroup,),
        {"__annotations__": annotations},
    )

    def execute_reset(self, context):
        """Command, general. Reset all panel properties to their defaults."""
        props = context.scene.build123d_props
        for key, value in _defaults.items():
            setattr(props, key, value)
        return {"FINISHED"}

    ResetOp = type(
        "BUILD123D_OT_reset_defaults",
        (bpy.types.Operator,),
        {
            "bl_idname": "build123d.reset_defaults",
            "bl_label": "Reset to Defaults",
            "bl_description": "Reset all parameters to their default values",
            "execute": execute_reset,
        },
    )

    # ── Preset dropdown ──
    # Build json_key -> param_key lookup for applying preset overrides
    _jk_to_key = {}
    for section in sections:
        for param in section["params"]:
            _jk_to_key[param["json_key"]] = param["key"]

    def _apply_preset_by_key(preset_key):
        """Command, general. Apply a preset by key: reset to defaults, then override."""
        props = bpy.context.scene.build123d_props
        for key, value in _defaults.items():
            setattr(props, key, value)
        for preset in _presets:
            if preset["key"] == preset_key:
                for jk, val in preset["params"].items():
                    pk = _jk_to_key.get(jk)
                    if pk and hasattr(props, pk):
                        setattr(props, pk, val)
                break

    def _on_preset_change(self, context):
        """Command, general. Callback when preset dropdown changes."""
        _apply_preset_by_key(self.active_preset)

    if _presets:
        _preset_items = [(p["key"], p["label"], p.get("description", ""))
                         for p in _presets]
        annotations["active_preset"] = bpy.props.EnumProperty(
            name="Preset",
            description="Apply a named preset configuration",
            items=_preset_items,
            default=_presets[0]["key"],
            update=_on_preset_change,
        )

    # Keep PresetOp as no-op for backwards compat (unused but registered)
    PresetOp = type(
        "BUILD123D_OT_apply_preset",
        (bpy.types.Operator,),
        {
            "bl_idname": "build123d.apply_preset",
            "bl_label": "Apply Preset",
            "__annotations__": {
                "preset_key": bpy.props.StringProperty(),
            },
            "execute": lambda self, context: {"FINISHED"},
        },
    )

    # Capture sections for the draw() closure, plus anatomy if available
    _sections = list(sections)
    if _anatomy_region_items is not None:
        _sections.append({
            "label": "Anatomy",
            "icon": "COLOR",
            "enable_key": "show_anatomy",
            "params": [
                {"key": "show_anatomy", "type": "bool", "label": "Show",
                 "default": False},
                {"key": "anatomy_region", "type": "enum", "label": "Region",
                 "default": "ALL"},
            ],
        })

    def draw_panel(self, context):
        """Command, general. Draw preset dropdown (parent panel body)."""
        layout = self.layout
        props = context.scene.build123d_props

        # Preset dropdown + reset
        if _presets:
            row = layout.row(align=True)
            row.prop(props, "active_preset", text="")
            row.operator("build123d.reset_defaults", text="", icon="LOOP_BACK")
        else:
            layout.operator("build123d.reset_defaults", icon="LOOP_BACK")

    PanelClass = type(
        "BUILD123D_PT_Panel",
        (bpy.types.Panel,),
        {
            "bl_label": "build123d",
            "bl_idname": "BUILD123D_PT_panel",
            "bl_space_type": "VIEW_3D",
            "bl_region_type": "UI",
            "bl_category": "build123d",
            "draw": draw_panel,
        },
    )

    # ── Sub-panels (one per section, collapsible) ──
    sub_panel_classes = []
    for idx, section in enumerate(_sections):
        label = section["label"]
        enable_key = section.get("enable_key")
        icon = section.get("icon", "NONE")
        safe_label = label.replace(" ", "_").replace("&", "and")
        idname = f"BUILD123D_PT_section_{safe_label}"

        # Capture loop variables in closure
        def _make_draw(sec, ek):
            def draw_section(self, context):
                props = context.scene.build123d_props
                # Hide body when section is disabled via enable_key
                if ek and not getattr(props, ek):
                    return
                layout = self.layout
                visible_when = sec.get("visible_when", {})
                drawn_in_row = set()
                for param in sec["params"]:
                    key = param["key"]
                    if key == ek:
                        continue
                    if key in visible_when:
                        cond = visible_when[key]
                        if not all(getattr(props, ck) == cv
                                   for ck, cv in cond.items()):
                            continue
                    if key in drawn_in_row:
                        continue
                    in_row = None
                    for row_group in sec.get("rows", []):
                        if key in row_group:
                            in_row = row_group
                            break
                    if in_row:
                        row = layout.row(align=True)
                        for rk in in_row:
                            if rk in visible_when:
                                cond = visible_when[rk]
                                if not all(getattr(props, ck) == cv
                                           for ck, cv in cond.items()):
                                    continue
                            row.prop(props, rk)
                            drawn_in_row.add(rk)
                    else:
                        layout.prop(props, key)
            return draw_section

        def _make_draw_header(ek):
            if not ek:
                return None
            def draw_header(self, context):
                props = context.scene.build123d_props
                self.layout.prop(props, ek, text="")
            return draw_header

        attrs = {
            "bl_label": label,
            "bl_idname": idname,
            "bl_space_type": "VIEW_3D",
            "bl_region_type": "UI",
            "bl_category": "build123d",
            "bl_parent_id": "BUILD123D_PT_panel",
            "bl_options": {"DEFAULT_CLOSED"},
            "draw": _make_draw(section, enable_key),
        }
        header_draw = _make_draw_header(enable_key)
        if header_draw:
            attrs["draw_header"] = header_draw
        if icon != "NONE":
            attrs["bl_options"] = {"DEFAULT_CLOSED"}

        SubPanel = type(f"BUILD123D_PT_section_{safe_label}",
                        (bpy.types.Panel,), attrs)
        sub_panel_classes.append(SubPanel)

    return PropGroup, PanelClass, sub_panel_classes, ResetOp, PresetOp


def _load_panel_def(watch_dir):
    """
    Query, general. Try to import panel_def.py from the given directory.
    Uses importlib to avoid polluting sys.modules with path-dependent names.

    Args:
        watch_dir (str): Directory to look for panel_def.py in.

    Returns:
        module or None: The loaded panel_def module, or None if not found.
    """
    panel_def_path = os.path.join(watch_dir, "panel_def.py")
    if not os.path.exists(panel_def_path):
        return None

    import importlib.util
    spec = importlib.util.spec_from_file_location("panel_def", panel_def_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _unregister_panel():
    """
    Command, general. Unregister all dynamically created panel classes.
    Called before hot-reloading panel_def.py.
    """
    global _registered_classes
    if hasattr(bpy.types.Scene, "build123d_props"):
        del bpy.types.Scene.build123d_props
    # Unregister in reverse order (panel first, then operator, then property group)
    for cls in reversed(_registered_classes):
        bpy.utils.unregister_class(cls)
    _registered_classes = []


def register_panel():
    """
    Command, general. Discover panel_def.py in the watched directory,
    dynamically build and register the PropertyGroup + Panel. If no
    panel_def.py exists, the panel is simply not created (file watcher
    still works). Also loads anatomy data (classify_face, colors, regions)
    from panel_def if available.
    """
    global _panel_def, _parametric_script, _registered_classes
    global _anatomy_colors, _anatomy_region_items, _anatomy_region_groups, _classify_face_fn

    _panel_def = _load_panel_def(WATCH_DIR)
    if _panel_def is None:
        print("[panel] No panel_def.py in watch dir — panel disabled")
        return

    # Load anatomy data from panel_def (optional — panel works without it)
    _classify_face_fn = getattr(_panel_def, "classify_face", None)
    _anatomy_colors = getattr(_panel_def, "ANATOMY_COLORS", None)
    _anatomy_region_items = getattr(_panel_def, "ANATOMY_REGION_ITEMS", None)
    _anatomy_region_groups = getattr(_panel_def, "ANATOMY_REGION_GROUPS", None)
    if _classify_face_fn:
        print("[panel] Anatomy highlight available")

    # Load presets (optional — panel works without them)
    global _presets
    _presets = getattr(_panel_def, "PRESETS", [])
    if _presets:
        print(f"[panel] {len(_presets)} presets available: {', '.join(p['label'] for p in _presets)}")

    _parametric_script = os.path.join(WATCH_DIR, _panel_def.PARAMETRIC_SCRIPT)
    if not os.path.exists(_parametric_script):
        print(f"[panel] WARNING: parametric script not found: {_parametric_script}")

    prop_cls, panel_cls, sub_panels, reset_cls, preset_cls = _build_panel_classes(_panel_def.SECTIONS)
    bpy.utils.register_class(prop_cls)
    bpy.utils.register_class(reset_cls)
    bpy.utils.register_class(preset_cls)
    bpy.utils.register_class(panel_cls)
    for sp in sub_panels:
        bpy.utils.register_class(sp)
    bpy.types.Scene.build123d_props = bpy.props.PointerProperty(type=prop_cls)
    _registered_classes = [prop_cls, reset_cls, preset_cls, panel_cls] + sub_panels
    print(f"[panel] Registered panel with {len(_panel_param_keys)} params from {WATCH_DIR}/panel_def.py")

    # Eagerly spawn worker so first slider change is fast
    _spawn_worker()


def reload_panel():
    """
    Command, general. Hot-reload the panel from panel_def.py. Unregisters
    old classes, reimports the definition, and registers fresh ones. All
    property values reset to defaults.
    """
    print("[panel] Hot-reloading panel_def.py...")
    _unregister_panel()
    register_panel()


# ── File watcher ───────────────────────────────────────────────────────────────

def get_dir_mtime():
    """
    Query, specific. Get the max mtime of all .py files in the
    watched directory. Used to detect changes in the source file or any
    of its local dependencies (e.g., lego_lib.py).

    Returns:
        float: Maximum mtime across all .py files, or 0.0 if none found.

    Examples:
        >>> # get_dir_mtime() -> 1710000000.0
    """
    py_files = glob.glob(os.path.join(WATCH_DIR, "*.py"))
    if not py_files:
        return 0.0
    return max(os.path.getmtime(f) for f in py_files)


def poll_source_file():
    """
    Command, specific. Timer callback registered with bpy.app.timers.
    Polls all .py files in the source directory for mtime changes. On
    any change, re-runs the build and updates the mesh.

    Returns:
        float: Seconds until next poll (POLL_INTERVAL_SECONDS), or None to stop.
    """
    global _last_dir_mtime, _last_stl_mtime

    # Check source file exists
    if not os.path.exists(SOURCE_FILE):
        print(f"[watcher] Source file not found: {SOURCE_FILE}")
        return POLL_INTERVAL_SECONDS

    dir_mtime = get_dir_mtime()

    if dir_mtime != _last_dir_mtime:
        _last_dir_mtime = dir_mtime
        print(f"[watcher] .py file changed in {WATCH_DIR}, rebuilding...")

        # Cancel any pending panel rebuild to avoid race with file-change rebuild
        global _panel_rebuild_pending
        if _panel_rebuild_pending:
            if bpy.app.timers.is_registered(_do_panel_rebuild):
                bpy.app.timers.unregister(_do_panel_rebuild)
            _panel_rebuild_pending = False

        # Kill the persistent worker so it respawns with fresh imports
        if _worker is not None:
            _kill_worker()

        # Hot-reload panel if panel_def.py was the file that changed
        if _registered_classes:
            reload_panel()

        if run_build(SOURCE_FILE, STL_PATH):
            # Check if STL was actually produced/updated
            if os.path.exists(STL_PATH):
                stl_mtime = os.path.getmtime(STL_PATH)
                if stl_mtime != _last_stl_mtime:
                    _last_stl_mtime = stl_mtime
                    update_mesh_from_stl(STL_PATH)
                    _reapply_anatomy_if_active()
            else:
                print(f"[watcher] WARNING: Build succeeded but no STL at {STL_PATH}")

    return POLL_INTERVAL_SECONDS


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    """
    Command, specific. Entry point: clears scene, sets up viewport,
    does initial build, and starts the file watcher timer.
    """
    print(f"[watcher] Starting build123d live preview")
    print(f"[watcher]   Source:    {SOURCE_FILE}")
    print(f"[watcher]   STL:       {STL_PATH}")
    print(f"[watcher]   uv:        {UV_PATH}")
    print(f"[watcher]   build123d: {BUILD123D_SUBMODULE}")
    print(f"[watcher]   Poll:      {POLL_INTERVAL_SECONDS}s")

    clear_default_scene()
    setup_viewport()
    register_panel()

    # Register watcher FIRST — so it runs even if initial build has issues
    bpy.app.timers.register(poll_source_file, first_interval=POLL_INTERVAL_SECONDS, persistent=True)
    print("[watcher] File watcher active. Edit your source file to see changes.")

    # Initial build
    if os.path.exists(SOURCE_FILE):
        global _last_dir_mtime, _last_stl_mtime
        _last_dir_mtime = get_dir_mtime()

        print("[watcher] Running initial build...")
        if run_build(SOURCE_FILE, STL_PATH):
            if os.path.exists(STL_PATH):
                _last_stl_mtime = os.path.getmtime(STL_PATH)
                update_mesh_from_stl(STL_PATH)


main()
