"""
Parametric LEGO brick builder -- driven by JSON parameter file.

Command, specific. Entry point for Blender panel sliders. Reads dimension
overrides from a JSON file (path in BUILD123D_PARAMS env var), patches
lego_lib module constants, and builds the requested brick type.

Works standalone too -- without BUILD123D_PARAMS, builds a default 2x4 brick.

Worker interface: exposes run(params, stl_path) for build_worker.py.

Usage (standalone):
    BUILD123D_PARAMS=/tmp/params.json BUILD123D_PREVIEW_STL=out.stl uv run parametric.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import lego_lib
import common
import panel_def
from parametric_base import apply_overrides, run as _run, standalone_main

# Derived constants that must be recomputed after overrides
DERIVED_CONSTANTS = {
    "STUD_RADIUS": (common, lambda: common.STUD_DIAMETER / 2),
    "TUBE_OUTER_RADIUS": (lego_lib, lambda: lego_lib.TUBE_OUTER_DIAMETER / 2),
    "TUBE_INNER_RADIUS": (lego_lib, lambda: lego_lib.TUBE_INNER_DIAMETER / 2),
}


def _apply_overrides(params):
    """
    Command, specific. Patch common + lego_lib module constants from params.
    """
    apply_overrides(params, common, lego_lib, panel_def.SECTIONS,
                    derived_constants=DERIVED_CONSTANTS)


def _build(params):
    """
    Pure function, specific. Build a LEGO brick from params dict.

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
    Command, specific. Standard worker interface.

    Args:
        params (dict): All panel parameters (shape + dimension overrides).
        stl_path (str): Path to write the STL file.

    Returns:
        dict: Build info -- faces count, timing.
    """
    return _run(params, stl_path, _build, _apply_overrides)


if __name__ == "__main__":
    standalone_main(run, {"brick_type": "BRICK", "studs_x": 2, "studs_y": 4}, "LEGO")
