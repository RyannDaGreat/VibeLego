"""
Unified parametric brick builder — driven by JSON parameter file.

Command, specific. Entry point for Blender panel sliders. Reads dimension
overrides from a JSON file (path in BUILD123D_PARAMS env var), patches
brick_lib module constants, and builds the requested brick.

Merges lego/parametric.py and clara/parametric.py.

Worker interface: exposes run(params, stl_path) for build_worker.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import brick_lib
import common
import panel_def
from parametric_base import apply_overrides, run as _run, standalone_main

# Derived constants that must be recomputed after overrides
DERIVED_CONSTANTS = {
    "STUD_RADIUS": (common, lambda: common.STUD_DIAMETER / 2),
    "TUBE_OUTER_RADIUS": (brick_lib, lambda: brick_lib.TUBE_OUTER_DIAMETER / 2),
    "TUBE_INNER_RADIUS": (brick_lib, lambda: brick_lib.TUBE_INNER_DIAMETER / 2),
}


def _apply_overrides(params):
    """
    Command, specific. Patch common + brick_lib module constants from params.
    """
    apply_overrides(params, common, brick_lib, panel_def.SECTIONS,
                    derived_constants=DERIVED_CONSTANTS)


def _build(params):
    """
    Pure function, specific. Build a brick from params dict.

    Reads clutch_type, shape_mode, and all shape params from the dict.
    Dispatches to brick_lib.brick() or brick_lib.slope().

    Args:
        params (dict): All panel parameters.

    Returns:
        Part: The built brick geometry.

    Examples:
        >>> # _build({"studs_x": 2, "studs_y": 4})
        >>> # _build({"clutch_type": "TUBE", "studs_x": 2, "studs_y": 4})
    """
    studs_x = int(params.get("studs_x", 2))
    studs_y = int(params.get("studs_y", 4))
    clutch = str(params.get("clutch_type", "LATTICE"))
    shape_mode = str(params.get("shape_mode", "RECTANGLE"))

    # Corner radius
    enable_cr = params.get("enable_corner_radius", True)
    corner_radius = float(params.get("corner_radius", 0)) if enable_cr else 0
    cr_skip_concave = bool(params.get("CR_SKIP_CONCAVE", True))

    # Wall taper
    enable_wt = params.get("enable_wall_taper", True)
    taper_height = float(params.get("taper_height", 0)) if enable_wt else 0
    taper_inset = float(params.get("taper_inset", 0)) if enable_wt else 0
    taper_curve = str(params.get("taper_curve", "LINEAR"))

    # Stud taper
    enable_st = params.get("enable_stud_taper", True)
    stud_taper_height = float(params.get("stud_taper_height", 0)) if enable_st else 0
    stud_taper_inset = float(params.get("stud_taper_inset", 0)) if enable_st else 0
    stud_taper_curve = str(params.get("stud_taper_curve", "LINEAR"))

    # Cross-shape params
    plus_x = int(params.get("studs_plus_x", 0))
    minus_x = int(params.get("studs_minus_x", 0))
    plus_y = int(params.get("studs_plus_y", 0))
    minus_y = int(params.get("studs_minus_y", 0))
    cross_width_x = int(params.get("cross_width_x", 1))
    cross_width_y = int(params.get("cross_width_y", 1))

    shape_kwargs = dict(
        clutch=clutch,
        corner_radius=corner_radius, cr_skip_concave=cr_skip_concave,
        taper_height=taper_height, taper_inset=taper_inset, taper_curve=taper_curve,
        stud_taper_height=stud_taper_height, stud_taper_inset=stud_taper_inset,
        stud_taper_curve=stud_taper_curve,
        shape_mode=shape_mode,
        plus_x=plus_x, minus_x=minus_x, plus_y=plus_y, minus_y=minus_y,
        cross_width_x=cross_width_x, cross_width_y=cross_width_y,
    )

    height = float(params.get("BRICK_HEIGHT", common.BRICK_HEIGHT))

    if params.get("enable_slope", False):
        slope_plus_y = int(params.get("slope_plus_y", 0))
        slope_minus_y = int(params.get("slope_minus_y", 0))
        slope_plus_x = int(params.get("slope_plus_x", 0))
        slope_minus_x = int(params.get("slope_minus_x", 0))
        slope_min_z = float(params.get("slope_min_z", common.WALL_THICKNESS))
        return brick_lib.slope(studs_x, studs_y, height=height,
                               slope_plus_y=slope_plus_y, slope_minus_y=slope_minus_y,
                               slope_plus_x=slope_plus_x, slope_minus_x=slope_minus_x,
                               slope_min_z=slope_min_z,
                               **shape_kwargs)

    return brick_lib.brick(studs_x, studs_y, height=height, **shape_kwargs)


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
    standalone_main(run, {"studs_x": 2, "studs_y": 4}, "Brick")
