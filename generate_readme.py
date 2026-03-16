"""
Generate README images — renders all brick configs used in README.md.

Command, specific. For each config: builds STL via parametric.run(),
then calls render.sh to produce diagnostic PNGs, and copies the
selected angle to docs/images/.

Usage:
    uv run generate_readme.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(script_dir, "models", "bricks"))

DOCS_DIR = os.path.join(script_dir, "docs", "images")
RENDER_DIR = os.path.join(script_dir, "renders")
RENDER_SCRIPT = os.path.join(script_dir, "render.sh")

# Each entry: (output_name, params_dict, angle)
# angle = name from CAMERA_ANGLES in render_preview.py
README_CONFIGS = [
    ("clara_2x4", {"studs_x": 2, "studs_y": 4}, "iso_fr"),
    ("clara_2x4_bottom", {"studs_x": 2, "studs_y": 4}, "iso_fr_lo"),
    ("lego_2x4", {
        "studs_x": 2, "studs_y": 4, "clutch_type": "TUBE",
        "STUD_TEXT": "LEGO", "STUD_HEIGHT": 1.8,
        "enable_corner_radius": False, "enable_wall_taper": False,
        "enable_stud_taper": False,
    }, "iso_fr"),
    ("lego_2x4_bottom", {
        "studs_x": 2, "studs_y": 4, "clutch_type": "TUBE",
        "STUD_TEXT": "LEGO", "STUD_HEIGHT": 1.8,
        "enable_corner_radius": False, "enable_wall_taper": False,
        "enable_stud_taper": False,
    }, "iso_fr_lo"),
    ("clara_slope", {
        "studs_x": 2, "studs_y": 4,
        "enable_slope": True, "slope_plus_y": 3,
    }, "iso_fr"),
    ("lego_slope", {
        "studs_x": 2, "studs_y": 4, "clutch_type": "TUBE",
        "STUD_TEXT": "LEGO", "STUD_HEIGHT": 1.8,
        "enable_corner_radius": False, "enable_wall_taper": False,
        "enable_stud_taper": False,
        "enable_slope": True, "slope_plus_y": 3,
    }, "iso_fr"),
    ("lego_2x2_plate", {
        "studs_x": 2, "studs_y": 2, "clutch_type": "TUBE",
        "STUD_TEXT": "LEGO", "STUD_HEIGHT": 1.8, "BRICK_HEIGHT": 3.2,
        "enable_corner_radius": False, "enable_wall_taper": False,
        "enable_stud_taper": False,
    }, "iso_fr"),
]


def find_blender():
    """
    Query, specific. Locate Blender executable.

    Returns:
        str: Path to Blender, or None if not found.

    Examples:
        >>> # find_blender() -> "/Applications/Blender.app/Contents/MacOS/Blender"
    """
    mac_path = "/Applications/Blender.app/Contents/MacOS/Blender"
    if os.path.isfile(mac_path):
        return mac_path
    blender = shutil.which("blender")
    return blender


def main():
    """Command, specific. Build and render all README images."""
    blender = find_blender()
    if not blender:
        print("ERROR: Blender not found")
        sys.exit(1)

    os.makedirs(DOCS_DIR, exist_ok=True)
    os.makedirs(RENDER_DIR, exist_ok=True)

    import parametric

    passed = 0
    failed = 0
    stl_path = os.path.join(tempfile.gettempdir(), "_readme_render.stl")
    render_script = os.path.join(script_dir, "render_preview.py")

    for name, params, angle in README_CONFIGS:
        print(f"\n{'='*60}")
        print(f"Building {name}...")

        # Fresh module state
        for mod_name in list(sys.modules):
            if mod_name in ("parametric", "brick_lib", "common", "panel_def",
                            "parametric_base", "panel_common"):
                del sys.modules[mod_name]
        import parametric

        info = parametric.run(params, stl_path)
        print(f"  Built: {info['faces']} faces, {info['build']:.2f}s")

        # Render via Blender headless
        print(f"  Rendering {name}...")
        result = subprocess.run(
            [blender, "--background", "--factory-startup",
             "--python", render_script, "--", stl_path, RENDER_DIR],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  FAIL render {name}: {result.stderr[-500:]}")
            failed += 1
            continue

        # Copy selected angle to docs/images/
        src = os.path.join(RENDER_DIR, f"{angle}.png")
        dst = os.path.join(DOCS_DIR, f"{name}.png")
        if not os.path.isfile(src):
            print(f"  FAIL: {src} not found")
            failed += 1
            continue

        shutil.copy2(src, dst)
        print(f"  Saved: {dst}")
        passed += 1

    print(f"\n{'='*60}")
    print(f"{passed} rendered, {failed} failed, {len(README_CONFIGS)} total")
    print(f"Images in: {DOCS_DIR}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
