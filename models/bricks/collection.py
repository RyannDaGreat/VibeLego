"""
Brick collection -- multiple brick types arranged in a display grid.

Command, specific. Generates various brick configurations and arranges them
in rows by category with 5x PITCH (40mm) spacing. Exports as a single STL.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import Compound, export_stl, Pos
from brick_lib import brick, slope, PITCH
from common import PLATE_HEIGHT

GRID_SPACING = 5 * PITCH  # 40mm between brick centers

# Shared kwargs for LEGO-style bricks (no Clara features)
_LEGO = dict(clutch="TUBE", corner_radius=0, taper_height=0, taper_inset=0,
             stud_taper_height=0, stud_taper_inset=0)


def make_collection():
    """
    Command, specific. Build various brick types and arrange in a grid.

    Layout (rows = categories, columns = sizes):
        Row 0 (LEGO bricks):  1x1, 1x2, 1x4, 2x2, 2x3, 2x4
        Row 1 (LEGO plates):  1x1, 2x4
        Row 2 (LEGO slopes):  2x2
        Row 3 (LATTICE bricks): 2x4, 2x4 tapered
        Row 4 (Cross shapes): + shape, L shape

    Returns:
        Compound: All bricks combined into a single exportable shape.
    """
    parts = []

    # Row 0: Standard LEGO bricks
    bricks = [(1, 1), (1, 2), (1, 4), (2, 2), (2, 3), (2, 4)]
    for col, (sx, sy) in enumerate(bricks):
        b = brick(sx, sy, **_LEGO)
        parts.append(Pos(col * GRID_SPACING, 0, 0) * b)

    # Row 1: LEGO plates
    plates = [(1, 1), (2, 4)]
    for col, (sx, sy) in enumerate(plates):
        p = brick(sx, sy, height=PLATE_HEIGHT, **_LEGO)
        parts.append(Pos(col * GRID_SPACING, -GRID_SPACING, 0) * p)

    # Row 2: LEGO slopes
    slopes_cfg = [(2, 2)]
    for col, (sx, sy) in enumerate(slopes_cfg):
        s = slope(sx, sy, slope_plus_y=1, **_LEGO)
        parts.append(Pos(col * GRID_SPACING, -2 * GRID_SPACING, 0) * s)

    # Row 3: Lattice bricks (Clara-style)
    b1 = brick(2, 4, clutch="LATTICE")
    parts.append(Pos(0, -3 * GRID_SPACING, 0) * b1)
    b2 = brick(2, 4, clutch="LATTICE", corner_radius=2.0,
               taper_height=2.0, taper_inset=0.5, taper_curve="CURVED",
               stud_taper_height=1.5, stud_taper_inset=0.4, stud_taper_curve="CURVED")
    parts.append(Pos(GRID_SPACING, -3 * GRID_SPACING, 0) * b2)

    # Row 4: Cross shapes
    cross_plus = brick(0, 0, clutch="LATTICE", shape_mode="CROSS",
                       plus_x=2, minus_x=2, plus_y=2, minus_y=2)
    parts.append(Pos(0, -4 * GRID_SPACING, 0) * cross_plus)
    cross_l = brick(0, 0, clutch="TUBE", shape_mode="CROSS",
                    plus_x=3, minus_x=0, plus_y=3, minus_y=0,
                    corner_radius=0, taper_height=0, taper_inset=0,
                    stud_taper_height=0, stud_taper_inset=0)
    parts.append(Pos(GRID_SPACING, -4 * GRID_SPACING, 0) * cross_l)

    return Compound(parts)


result = make_collection()

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"Collection ({len(result.solids())} parts) -> {stl_path}")
