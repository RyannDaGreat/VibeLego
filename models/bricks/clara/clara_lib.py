"""
Clara brick geometry library -- diagonal lattice clutch system.

Same shell as LEGO bricks, but instead of cylindrical tubes the underside
uses +/-45 degree crisscross struts forming diamond openings. Each diamond's
inscribed circle = STUD_DIAMETER for exact stud fit. The lattice is fully
wall-connected -- no floating internal features.

Architecture: 2D sketch -> extrude, same as LEGO. Shared constants and
fillet_above_z come from common.py.

Coordinate convention: brick sits on XY plane, studs point up (+Z).
Origin at the center-bottom of the brick body (not including studs).
"""

import math
import os
import sys

# Allow importing common.py from parent directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from build123d import (
    Box, Cylinder, Rectangle, Pos, Rot, Plane,
    Align, Mode, FontStyle,
    BuildPart, BuildSketch, add, Locations, GridLocations,
    Text, extrude,
)
from common import (
    PITCH, STUD_DIAMETER, STUD_RADIUS, STUD_HEIGHT,
    BRICK_HEIGHT, WALL_THICKNESS, FLOOR_THICKNESS,
    CLEARANCE, FILLET_RADIUS, ENABLE_FILLET, STUD_TEXT, STUD_TEXT_FONT,
    STUD_TEXT_FONT_SIZE, STUD_TEXT_HEIGHT, fillet_above_z,
)


def clara_brick(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, specific. Create a Clara brick with diagonal lattice clutch.

    Same shell as lego_brick, but instead of cylindrical tubes the underside
    uses +/-45 degree crisscross struts forming diamond openings. Each diamond's
    inscribed circle = STUD_DIAMETER for exact stud fit. The lattice is fully
    wall-connected -- no floating internal features. A Z-plane cross-section
    through the bottom is one contiguous region (walls + struts).

    Strut thickness derived: PITCH / sqrt(2) - STUD_DIAMETER ~ 0.857 mm.
    Struts per direction = studs_x + studs_y (6 for a 2x4).

    Strut positioning: strut center lines are at c-values spaced PITCH apart,
    centered on zero. +45 deg strut at c: line y - x = c, center at (-c/2, c/2).
    -45 deg strut at c: line y + x = c, center at (c/2, c/2). All struts are
    long rectangles clipped to the inner cavity via Mode.INTERSECT.

    Note: fillet threshold is set to cavity_z (not 0) because the thin lattice
    strut intersections create edges too small for OCCT's filleter.

    Args:
        studs_x (int): Studs along X.
        studs_y (int): Studs along Y.
        height (float): Body height. Default BRICK_HEIGHT.

    Returns:
        Part: Complete Clara brick.

    Examples:
        >>> # clara_brick(2, 4) -> 2x4 Clara brick with diamond lattice
        >>> # clara_brick(1, 1) -> 1x1 with X-shaped lattice cross
    """
    outer_x = studs_x * PITCH - 2 * CLEARANCE
    outer_y = studs_y * PITCH - 2 * CLEARANCE
    inner_x = outer_x - 2 * WALL_THICKNESS
    inner_y = outer_y - 2 * WALL_THICKNESS
    cavity_z = height - FLOOR_THICKNESS

    # Strut geometry -- derived from stud-fit constraint
    strut_thickness = PITCH / math.sqrt(2) - STUD_DIAMETER
    n_struts = studs_x + studs_y
    strut_len = (inner_x + inner_y) * 2  # generous, clipped by intersection
    c_start = -(n_struts - 1) / 2 * PITCH
    c_values = [c_start + i * PITCH for i in range(n_struts)]

    with BuildPart() as brick:
        # ── Shell: solid box minus cavity ──
        Box(outer_x, outer_y, height,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
        Box(inner_x, inner_y, cavity_z,
            align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

        # ── Diagonal lattice (2D sketch -> extrude) ──
        # NOTE: Pos * Rot * Rectangle does NOT work in BuildSketch (rotation
        # silently ignored). Must use Locations context manager instead.
        with BuildSketch():
            for c in c_values:
                # +45 deg strut along line y - x = c
                with Locations([Pos(-c / 2, c / 2) * Rot(0, 0, 45)]):
                    Rectangle(strut_len, strut_thickness)
                # -45 deg strut along line y + x = c
                with Locations([Pos(c / 2, c / 2) * Rot(0, 0, -45)]):
                    Rectangle(strut_len, strut_thickness)
            # Clip to cavity bounds (struts fuse with walls)
            Rectangle(inner_x, inner_y, mode=Mode.INTERSECT)
        extrude(amount=cavity_z)

        # ── Studs ──
        with Locations([Pos(0, 0, height)]):
            with GridLocations(PITCH, PITCH, studs_x, studs_y):
                Cylinder(STUD_RADIUS, STUD_HEIGHT,
                         align=(Align.CENTER, Align.CENTER, Align.MIN))

    # Fillet above cavity only -- lattice strut edges are too thin for OCCT filleter
    result = fillet_above_z(brick.part, FILLET_RADIUS, z_threshold=cavity_z) if ENABLE_FILLET else brick.part

    with BuildPart() as final:
        add(result)
        with BuildSketch(Plane.XY.offset(height + STUD_HEIGHT)):
            with GridLocations(PITCH, PITCH, studs_x, studs_y):
                Text(STUD_TEXT, font_size=STUD_TEXT_FONT_SIZE,
                     font=STUD_TEXT_FONT, font_style=FontStyle.BOLD,
                     align=(Align.CENTER, Align.CENTER))
        extrude(amount=STUD_TEXT_HEIGHT)

    return final.part
