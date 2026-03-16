"""
Parametric Clara brick builder -- driven by JSON parameter file.

Command, specific. Entry point for Blender panel sliders. Reads dimension
overrides from JSON, patches clara_lib/common module constants, and builds
Clara bricks.

Separate file from panel_def.py because they run in different processes:
panel_def.py is imported by Blender (no build123d available), while this
file runs in a build_worker.py subprocess under `uv run` (with build123d).

Worker interface: exposes run(params, stl_path) for build_worker.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import clara_lib
import common
import panel_def
from parametric_base import apply_overrides, run as _run, standalone_main

# Derived constants that must be recomputed after overrides
DERIVED_CONSTANTS = {
    "STUD_RADIUS": (common, lambda: common.STUD_DIAMETER / 2),
}


def _apply_overrides(params):
    """
    Command, specific. Patch common + clara_lib module constants from params.
    No LEGO-specific overrides (no tubes/ridges in Clara).
    """
    apply_overrides(params, common, clara_lib, panel_def.SECTIONS,
                    derived_constants=DERIVED_CONSTANTS)


def _build(params):
    """
    Pure function, specific. Build a Clara brick from params dict.

    Args:
        params (dict): Must include "studs_x", "studs_y". Optional:
            "corner_radius", "taper_height", "taper_inset", "taper_curve",
            "stud_taper_height", "stud_taper_inset", "stud_taper_curve".

    Returns:
        Part: The built Clara brick geometry.

    Examples:
        >>> # _build({"studs_x": 2, "studs_y": 4})
        >>> # _build({"studs_x": 2, "studs_y": 4, "corner_radius": 1.5})
        >>> # _build({"studs_x": 2, "studs_y": 4, "taper_curve": "CURVED"})
    """
    studs_x = int(params.get("studs_x", 2))
    studs_y = int(params.get("studs_y", 4))
    enable_corner_radius = params.get("enable_corner_radius", True)
    corner_radius = float(params.get("corner_radius", 0)) if enable_corner_radius else 0

    # Zero out taper params when section is disabled
    enable_wall_taper = params.get("enable_wall_taper", True)
    taper_height = float(params.get("taper_height", 0)) if enable_wall_taper else 0
    taper_inset = float(params.get("taper_inset", 0)) if enable_wall_taper else 0
    taper_curve = str(params.get("taper_curve", "LINEAR"))

    enable_stud_taper = params.get("enable_stud_taper", True)
    stud_taper_height = float(params.get("stud_taper_height", 0)) if enable_stud_taper else 0
    stud_taper_inset = float(params.get("stud_taper_inset", 0)) if enable_stud_taper else 0
    stud_taper_curve = str(params.get("stud_taper_curve", "LINEAR"))

    return clara_lib.clara_brick(studs_x, studs_y,
                                  corner_radius=corner_radius,
                                  taper_height=taper_height,
                                  taper_inset=taper_inset,
                                  taper_curve=taper_curve,
                                  stud_taper_height=stud_taper_height,
                                  stud_taper_inset=stud_taper_inset,
                                  stud_taper_curve=stud_taper_curve)


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
    standalone_main(run, {"studs_x": 2, "studs_y": 4}, "Clara")
