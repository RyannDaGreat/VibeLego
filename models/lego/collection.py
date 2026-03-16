"""
Clara brick collection — all brick types arranged in a display grid.

Command, specific. Generates every brick type and arranges them in rows
by category (bricks, plates, slopes) with 5×PITCH (40mm) spacing.
Exports as a single combined STL.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import Compound, export_stl, Location, Pos
from lego_lib import lego_brick, lego_slope, PITCH, PLATE_HEIGHT, BRICK_HEIGHT

GRID_SPACING = 5 * PITCH  # 40mm between brick centers


def make_collection():
    """
    Command, specific. Build all Clara brick types and arrange in a grid.

    Layout (rows = categories, columns = sizes):
        Row 0 (bricks):  1x1, 1x2, 1x4, 2x2, 2x3, 2x4
        Row 1 (plates):  1x1, 2x4
        Row 2 (slopes):  2x2

    Returns:
        Compound: All bricks combined into a single exportable shape.
    """
    parts = []

    # Row 0: Standard bricks
    bricks = [
        (1, 1), (1, 2), (1, 4),
        (2, 2), (2, 3), (2, 4),
    ]
    for col, (sx, sy) in enumerate(bricks):
        brick = lego_brick(sx, sy)
        parts.append(Pos(col * GRID_SPACING, 0, 0) * brick)

    # Row 1: Plates
    plates = [
        (1, 1), (2, 4),
    ]
    for col, (sx, sy) in enumerate(plates):
        plate = lego_brick(sx, sy, height=PLATE_HEIGHT)
        parts.append(Pos(col * GRID_SPACING, -GRID_SPACING, 0) * plate)

    # Row 2: Slopes
    slopes = [
        (2, 2),
    ]
    for col, (sx, sy) in enumerate(slopes):
        slope = lego_slope(sx, sy)
        parts.append(Pos(col * GRID_SPACING, -2 * GRID_SPACING, 0) * slope)

    return Compound(parts)


result = make_collection()

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"Collection ({len(result.solids())} parts) -> {stl_path}")
