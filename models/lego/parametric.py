"""
Parametric brick builder — driven by JSON parameter file.

Command, specific. Entry point for Blender panel sliders. Reads dimension
overrides from a JSON file (path in BUILD123D_PARAMS env var), patches
lego_lib module constants, and builds the requested brick type.

Works standalone too — without BUILD123D_PARAMS, builds a default 2x4 brick.

Worker interface: exposes run(params, stl_path) for build_worker.py.

Usage (standalone):
    BUILD123D_PARAMS=/tmp/params.json BUILD123D_PREVIEW_STL=out.stl uv run parametric.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from build123d import export_stl
import lego_lib

# ── Overridable constants ───────────────────────────────────────────────────
# Maps JSON key → lego_lib module attribute name.
# Only constants listed here can be overridden from the panel.

OVERRIDABLE_CONSTANTS = [
    "PITCH",
    "STUD_DIAMETER",
    "STUD_HEIGHT",
    "BRICK_HEIGHT",
    "PLATE_HEIGHT",
    "WALL_THICKNESS",
    "FLOOR_THICKNESS",
    "CLEARANCE",
    "TUBE_OUTER_DIAMETER",
    "TUBE_INNER_DIAMETER",
    "RIDGE_WIDTH",
    "RIDGE_HEIGHT",
    "FILLET_RADIUS",
    "STUD_TEXT_FONT_SIZE",
    "STUD_TEXT_HEIGHT",
]

# Derived constants that must be recomputed after overrides
DERIVED_CONSTANTS = {
    "STUD_RADIUS": lambda: lego_lib.STUD_DIAMETER / 2,
    "TUBE_OUTER_RADIUS": lambda: lego_lib.TUBE_OUTER_DIAMETER / 2,
    "TUBE_INNER_RADIUS": lambda: lego_lib.TUBE_INNER_DIAMETER / 2,
}


def _apply_overrides(params):
    """
    Command, specific. Patch lego_lib module constants from a params dict.
    Only keys present in OVERRIDABLE_CONSTANTS are applied; unknown keys
    are ignored. Derived constants (radii) are recomputed after patching.

    Args:
        params (dict): Key-value pairs, e.g. {"PITCH": 8.0, "STUD_DIAMETER": 5.0}.
    """
    for key in OVERRIDABLE_CONSTANTS:
        if key in params:
            setattr(lego_lib, key, float(params[key]))

    for key, compute in DERIVED_CONSTANTS.items():
        setattr(lego_lib, key, compute())


def _build(params):
    """
    Pure function, specific. Build a brick from params dict.

    Args:
        params (dict): Must include "brick_type" (BRICK/PLATE/SLOPE),
            "studs_x", "studs_y". SLOPE also uses "flat_rows".

    Returns:
        Part: The built brick geometry.

    Examples:
        >>> # _build({"brick_type": "BRICK", "studs_x": 2, "studs_y": 4})
    """
    brick_type = params.get("brick_type", "BRICK")
    studs_x = int(params.get("studs_x", 2))
    studs_y = int(params.get("studs_y", 4))
    flat_rows = int(params.get("flat_rows", 1))

    if brick_type == "SLOPE":
        return lego_lib.lego_slope(studs_x, studs_y, flat_rows=flat_rows)
    elif brick_type == "PLATE":
        return lego_lib.lego_brick(studs_x, studs_y, height=lego_lib.PLATE_HEIGHT)
    else:
        return lego_lib.lego_brick(studs_x, studs_y)


def run(params, stl_path):
    """
    Command, specific. Standard worker interface. Apply param overrides,
    build geometry, export STL, return info dict.

    Args:
        params (dict): All panel parameters (shape + dimension overrides).
        stl_path (str): Path to write the STL file.

    Returns:
        dict: Build info — faces count, timing.
    """
    _apply_overrides(params)

    t0 = time.perf_counter()
    result = _build(params)
    t_build = time.perf_counter() - t0

    t1 = time.perf_counter()
    export_stl(result, stl_path)
    t_export = time.perf_counter() - t1

    faces = len(result.faces())
    return {"faces": faces, "build": round(t_build, 3), "export": round(t_export, 3)}


# ── Standalone entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    params_path = os.environ.get("BUILD123D_PARAMS")
    if params_path and os.path.exists(params_path):
        with open(params_path) as f:
            params = json.load(f)
    else:
        params = {"brick_type": "BRICK", "studs_x": 2, "studs_y": 4}

    stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
    info = run(params, stl_path)
    brick_type = params.get("brick_type", "BRICK")
    studs_x = int(params.get("studs_x", 2))
    studs_y = int(params.get("studs_y", 4))
    print(f"{brick_type} {studs_x}x{studs_y} -> {stl_path} ({info['faces']} faces)")
    print(f"  timing: build={info['build']:.2f}s  export={info['export']:.2f}s")
