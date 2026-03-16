"""
Headless Blender render — STL to multi-angle PNGs for VLM verification.

Command, specific. Launched by render.sh inside Blender. Imports an STL,
applies a plastic-like material, and renders 4 diagnostic angles using EEVEE.

Usage (via render.sh, not directly):
    blender --background --factory-startup --python render_preview.py -- <stl_path> <output_dir>

Output: 4 PNG files in output_dir:
    front_iso.png   — 45°/30° isometric
    back_iso.png    — 225°/30° isometric (rear view)
    top.png         — near-top-down (89°)
    bottom.png      — near-bottom-up (-89°)
"""

import bpy
import math
import os
import sys


# ── Parse arguments ──────────────────────────────────────────────────────────

def parse_args():
    """
    Query, specific. Extract arguments after '--' from sys.argv.

    Returns:
        tuple: (stl_path, output_dir)
    """
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError(
            "Usage: blender --background --python render_preview.py "
            "-- <stl_path> <output_dir>"
        )
    custom = argv[argv.index("--") + 1:]
    if len(custom) < 2:
        raise RuntimeError(f"Expected 2 arguments after '--', got {len(custom)}")
    return custom[0], custom[1]


STL_PATH, OUTPUT_DIR = parse_args()


# ── Camera angles ────────────────────────────────────────────────────────────
# Each entry: (name, azimuth_deg, elevation_deg)

# 6 cardinal directions + 8 diagonal (45° elevation) = 14 total
CAMERA_ANGLES = [
    # Cardinals (face-on views)
    ("front",   0,   0),      # +X face
    ("back",    180, 0),      # -X face
    ("right",   90,  0),      # +Y face
    ("left",    270, 0),      # -Y face
    ("top",     0,   89),     # top-down
    ("bottom",  0,   -89),    # bottom-up
    # Diagonals (45° elevation, 8 octants)
    ("iso_fr",  45,  30),     # front-right iso
    ("iso_fl",  315, 30),     # front-left iso
    ("iso_br",  135, 30),     # back-right iso
    ("iso_bl",  225, 30),     # back-left iso
    ("iso_fr_lo", 45,  -30),  # front-right low (looking up)
    ("iso_fl_lo", 315, -30),  # front-left low
    ("iso_br_lo", 135, -30),  # back-right low
    ("iso_bl_lo", 225, -30),  # back-left low
]

RENDER_SIZE_PX = 1024
CAMERA_DISTANCE = 80  # mm from origin — covers a 2x4 brick comfortably


# ── Scene setup ──────────────────────────────────────────────────────────────

def clear_scene():
    """
    Command, specific. Remove all default objects for a clean render.
    """
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.outliner.orphans_purge(do_recursive=True)


def import_stl(filepath):
    """
    Command, general. Import STL using appropriate Blender operator.

    Args:
        filepath (str): Absolute path to .stl file.
    """
    if hasattr(bpy.ops.wm, "stl_import"):
        bpy.ops.wm.stl_import(filepath=filepath)
    else:
        bpy.ops.import_mesh.stl(filepath=filepath)


def create_plastic_material():
    """
    Command, specific. Create a white plastic Principled BSDF material.

    Returns:
        bpy.types.Material: The plastic material.
    """
    mat = bpy.data.materials.new(name="Plastic")
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.95, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.3
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    return mat


def setup_lighting():
    """
    Command, specific. Set up sun lights and ambient world for even,
    directional illumination that reveals surface detail.
    """
    # Sun lights — no distance attenuation, consistent across object
    sun_configs = [
        ("Key",  (45, -30), 3.0),    # azimuth, elevation (degrees), strength
        ("Fill", (-60, 20), 1.5),
        ("Rim",  (160, 45), 1.0),
    ]
    for name, (az_deg, el_deg), strength in sun_configs:
        az = math.radians(az_deg)
        el = math.radians(el_deg)
        light_data = bpy.data.lights.new(name=name, type="SUN")
        light_data.energy = strength
        light_obj = bpy.data.objects.new(name, light_data)
        # Sun direction is the object's -Z axis, so we set rotation
        light_obj.rotation_euler = (
            math.pi / 2 - el,  # tilt from vertical
            0,
            az,
        )
        bpy.context.scene.collection.objects.link(light_obj)

    # World ambient for fill — prevents pure black shadows
    world = bpy.data.worlds.new("World")
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.2, 0.2, 0.22, 1.0)
    bg.inputs["Strength"].default_value = 0.8
    bpy.context.scene.world = world


def setup_camera():
    """
    Command, specific. Create the render camera.

    Returns:
        bpy.types.Object: The camera object.
    """
    cam_data = bpy.data.cameras.new(name="RenderCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 60  # covers ~60mm width — enough for a 2x4
    cam_obj = bpy.data.objects.new("RenderCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    return cam_obj


def position_camera(cam_obj, azimuth_deg, elevation_deg, distance):
    """
    Command, general. Position camera at spherical coordinates looking at origin.

    Args:
        cam_obj: Blender camera object.
        azimuth_deg (float): Horizontal angle in degrees (0=+X, 90=+Y).
        elevation_deg (float): Vertical angle in degrees (0=horizon, 90=top).
        distance (float): Distance from origin in mm.

    Examples:
        >>> # position_camera(cam, 45, 30, 80) -> 45° azimuth, 30° elevation
    """
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    x = distance * math.cos(el) * math.cos(az)
    y = distance * math.cos(el) * math.sin(az)
    z = distance * math.sin(el)
    cam_obj.location = (x, y, z)

    # Point at origin using track-to constraint
    for c in cam_obj.constraints:
        cam_obj.constraints.remove(c)
    track = cam_obj.constraints.new(type="TRACK_TO")
    track.target = bpy.data.objects.new("_origin", None)
    bpy.context.scene.collection.objects.link(track.target)
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"


def setup_render_settings():
    """
    Command, specific. Configure EEVEE render settings for diagnostic output.
    """
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = RENDER_SIZE_PX
    scene.render.resolution_y = RENDER_SIZE_PX
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    """
    Command, specific. Import STL, set up scene, render all angles.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    clear_scene()
    import_stl(STL_PATH)

    if not bpy.context.selected_objects:
        print(f"ERROR: No objects imported from {STL_PATH}")
        sys.exit(1)

    model_obj = bpy.context.selected_objects[0]

    # Flat shading — crisp CAD facets, no smooth interpolation
    bpy.ops.object.shade_flat()

    # Apply plastic material
    mat = create_plastic_material()
    model_obj.data.materials.append(mat)

    setup_lighting()
    cam_obj = setup_camera()
    setup_render_settings()

    # Render each angle
    for name, azimuth, elevation in CAMERA_ANGLES:
        position_camera(cam_obj, azimuth, elevation, CAMERA_DISTANCE)
        output_path = os.path.join(OUTPUT_DIR, f"{name}.png")
        bpy.context.scene.render.filepath = output_path
        bpy.ops.render.render(write_still=True)
        print(f"Rendered: {output_path}")

    print(f"Done — {len(CAMERA_ANGLES)} renders in {OUTPUT_DIR}")


main()
