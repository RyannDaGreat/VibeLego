"""
Blender-side script for live build123d preview.

Command, specific. Launched by run.sh inside Blender. Watches a build123d
source file for changes, re-runs it via subprocess, and updates the mesh
in-place (preserving materials, transforms, and modifiers).

Usage (via run.sh, not directly):
    blender --factory-startup --python blender_watcher.py -- <source.py> <python_path> <stl_path>
"""

import bpy
import os
import sys
import subprocess
import time


# ── Parse arguments ────────────────────────────────────────────────────────────

def parse_custom_args():
    """
    Query, specific. Extract arguments after '--' from sys.argv.

    Returns:
        tuple: (source_path, python_path, stl_path)
    """
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError(
            "No custom arguments found. "
            "Usage: blender --python blender_watcher.py -- <source.py> <python_path> <stl_path>"
        )
    custom = argv[argv.index("--") + 1 :]
    if len(custom) < 3:
        raise RuntimeError(
            f"Expected 3 arguments after '--', got {len(custom)}: {custom}"
        )
    return custom[0], custom[1], custom[2]


SOURCE_FILE, PYTHON_PATH, STL_PATH = parse_custom_args()

POLL_INTERVAL_SECONDS = 0.5
OBJECT_NAME = "build123d_preview"

_last_source_mtime = 0.0
_last_stl_mtime = 0.0


# ── Scene setup ────────────────────────────────────────────────────────────────

def clear_default_scene():
    """
    Command, specific. Remove all default objects (Camera, Cube, Light)
    and purge orphan data for a clean starting point.
    """
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.outliner.orphans_purge(do_recursive=True)


def setup_viewport():
    """
    Command, specific. Configure the 3D viewport for CAD preview:
    orthographic projection, solid shading with studio lighting,
    material colors visible.
    """
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.region_3d.view_perspective = "ORTHO"
                    space.shading.type = "SOLID"
                    space.shading.light = "STUDIO"
                    space.shading.color_type = "MATERIAL"
                    space.overlay.show_floor = True
                    space.overlay.show_axis_x = True
                    space.overlay.show_axis_y = True
                    break


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
        # Frame the object in viewport
        bpy.ops.object.select_all(action="DESELECT")
        temp_obj.select_set(True)
        bpy.context.view_layer.objects.active = temp_obj
        bpy.ops.view3d.view_selected()
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

def run_build(source_path, python_path, stl_path):
    """
    Command, specific. Run a build123d source file via subprocess using
    the system Python (not Blender's Python). The source file is expected
    to export its result to the given STL path.

    Args:
        source_path (str): Path to the .py file to run.
        python_path (str): Path to the Python interpreter (in venv).
        stl_path (str): Path where the script should write the STL.

    Returns:
        bool: True if the build succeeded.
    """
    env = os.environ.copy()
    env["BUILD123D_PREVIEW_STL"] = stl_path

    result = subprocess.run(
        [python_path, source_path],
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


# ── File watcher ───────────────────────────────────────────────────────────────

def poll_source_file():
    """
    Command, specific. Timer callback registered with bpy.app.timers.
    Polls the source .py file for mtime changes. On change, runs the build
    and updates the mesh.

    Returns:
        float: Seconds until next poll (POLL_INTERVAL_SECONDS), or None to stop.
    """
    global _last_source_mtime, _last_stl_mtime

    # Check source file exists
    if not os.path.exists(SOURCE_FILE):
        print(f"[watcher] Source file not found: {SOURCE_FILE}")
        return POLL_INTERVAL_SECONDS

    source_mtime = os.path.getmtime(SOURCE_FILE)

    if source_mtime != _last_source_mtime:
        _last_source_mtime = source_mtime
        print(f"[watcher] Source changed, rebuilding...")

        if run_build(SOURCE_FILE, PYTHON_PATH, STL_PATH):
            # Check if STL was actually produced/updated
            if os.path.exists(STL_PATH):
                stl_mtime = os.path.getmtime(STL_PATH)
                if stl_mtime != _last_stl_mtime:
                    _last_stl_mtime = stl_mtime
                    update_mesh_from_stl(STL_PATH)
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
    print(f"[watcher]   Source: {SOURCE_FILE}")
    print(f"[watcher]   Python: {PYTHON_PATH}")
    print(f"[watcher]   STL:    {STL_PATH}")
    print(f"[watcher]   Poll:   {POLL_INTERVAL_SECONDS}s")

    clear_default_scene()
    setup_viewport()

    # Initial build
    if os.path.exists(SOURCE_FILE):
        global _last_source_mtime, _last_stl_mtime
        _last_source_mtime = os.path.getmtime(SOURCE_FILE)

        print("[watcher] Running initial build...")
        if run_build(SOURCE_FILE, PYTHON_PATH, STL_PATH):
            if os.path.exists(STL_PATH):
                _last_stl_mtime = os.path.getmtime(STL_PATH)
                update_mesh_from_stl(STL_PATH)

    # Start polling
    bpy.app.timers.register(poll_source_file, first_interval=POLL_INTERVAL_SECONDS, persistent=True)
    print("[watcher] File watcher active. Edit your source file to see changes.")


main()
