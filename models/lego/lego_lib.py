"""
Lego brick geometry library — pure functions for generating anatomically
correct Lego brick geometry using build123d.

All dimensions from measured Lego bricks and community CAD specifications
(LDraw, OpenSCAD lego.scad, Christoph Bartneck measurements).

Coordinate convention: brick sits on XY plane, studs point up (+Z).
Origin at the center-bottom of the brick body (not including studs).
"""

from build123d import (
    Box, Cylinder, Location, Pos, Part,
    Align, Axis, Mode,
    BuildPart, add, Locations, GridLocations,
)
import math

# ── Lego Dimension Constants (mm) ─────────────────────────────────────────────
# Sources: LDraw spec (1 LDU = 0.4mm), OpenSCAD lego.scad, Bartneck measurements,
#          OrionRobots specs, cfinke/LEGO.scad, LUGNET FAQ
#
# Base unit: 1 LDU = 0.4mm. Stud pitch = 20 LDU = 8.0mm.
# Brick height = 24 LDU = 9.6mm. Plate = 8 LDU = 3.2mm.

PITCH = 8.0             # stud center-to-center distance (20 LDU)
STUD_DIAMETER = 4.8     # outer diameter of a stud (12 LDU)
STUD_HEIGHT = 1.8       # height of stud above brick top
BRICK_HEIGHT = 9.6      # height of standard brick body (24 LDU, without stud)
PLATE_HEIGHT = 3.2      # height of a plate (8 LDU, 1/3 of brick)
WALL_THICKNESS = 1.5    # outer wall thickness (OrionRobots: 1.5mm, zoeblade: 1.6mm)
FLOOR_THICKNESS = 1.0   # bottom floor/ceiling thickness
CLEARANCE = 0.1         # per-side clearance for brick-to-brick fit

# Anti-stud tubes (for 2+ wide bricks) — grip studs from below
# Stud snaps into annular gap between tube outer wall and brick inner wall
TUBE_OUTER_DIAMETER = 6.31  # outer diameter of bottom tubes (OrionRobots)
TUBE_INNER_DIAMETER = 4.8   # inner diameter (~stud diameter)

# 1-wide bricks use internal spline ribs instead of tubes
RIDGE_WIDTH = 0.8       # width of the bottom ridge/spline rib
RIDGE_HEIGHT = 0.8      # how far the ridge extends down from the ceiling

# Derived
STUD_RADIUS = STUD_DIAMETER / 2
TUBE_OUTER_RADIUS = TUBE_OUTER_DIAMETER / 2
TUBE_INNER_RADIUS = TUBE_INNER_DIAMETER / 2


# ── General geometry functions ─────────────────────────────────────────────────

def lego_brick_body(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, general. Create the solid outer shell of a Lego brick
    with hollow interior.

    The body is a box with walls of WALL_THICKNESS and a floor of
    FLOOR_THICKNESS. Interior is hollow to save material and allow
    stud clutching from below.

    Args:
        studs_x (int): Number of studs along X axis.
        studs_y (int): Number of studs along Y axis.
        height (float): Body height in mm. Default BRICK_HEIGHT (9.6mm).

    Returns:
        Part: Hollow brick body centered on XY, bottom at Z=0.

    Examples:
        >>> # lego_brick_body(2, 4) -> 16mm x 32mm x 9.6mm hollow box
        >>> # lego_brick_body(1, 1, PLATE_HEIGHT) -> 8mm x 8mm x 3.2mm plate
    """
    outer_x = studs_x * PITCH - 2 * CLEARANCE
    outer_y = studs_y * PITCH - 2 * CLEARANCE
    inner_x = outer_x - 2 * WALL_THICKNESS
    inner_y = outer_y - 2 * WALL_THICKNESS
    inner_z = height - FLOOR_THICKNESS

    with BuildPart() as body:
        # Outer shell
        Box(outer_x, outer_y, height, align=(Align.CENTER, Align.CENTER, Align.MIN))
        # Hollow interior (subtract inner cavity)
        Box(
            inner_x, inner_y, inner_z,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT,
        )

    return body.part


def lego_studs(studs_x, studs_y, z_offset=0.0):
    """
    Pure function, general. Create studs arranged in a grid on top of a brick.

    Studs are cylinders of STUD_DIAMETER x STUD_HEIGHT, positioned at
    PITCH spacing, centered on the brick footprint.

    Args:
        studs_x (int): Number of studs along X.
        studs_y (int): Number of studs along Y.
        z_offset (float): Z position of stud bases. Default 0.

    Returns:
        Part: All studs as a single Part.

    Examples:
        >>> # lego_studs(2, 4, z_offset=9.6) -> 8 studs at Z=9.6
    """
    with BuildPart() as studs:
        with Locations(
            [
                Pos(
                    (i - (studs_x - 1) / 2) * PITCH,
                    (j - (studs_y - 1) / 2) * PITCH,
                    z_offset,
                )
                for i in range(studs_x)
                for j in range(studs_y)
            ]
        ):
            Cylinder(
                STUD_RADIUS,
                STUD_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

    return studs.part


def lego_bottom_tubes(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, general. Create anti-stud tubes for the underside of
    bricks that are 2+ studs wide in both dimensions.

    Tubes are hollow cylinders placed between each 2x2 group of studs.
    Their outer diameter grips studs from adjacent bricks.

    Args:
        studs_x (int): Number of studs along X.
        studs_y (int): Number of studs along Y.
        height (float): Brick body height (tubes extend from floor to bottom).

    Returns:
        Part or None: Tubes as a single Part, or None if brick is too small.

    Examples:
        >>> # lego_bottom_tubes(2, 4) -> 4 tubes for a 2x4 brick
        >>> # lego_bottom_tubes(1, 2) -> None (1-wide, uses ridge instead)
    """
    if studs_x < 2 or studs_y < 2:
        return None

    tube_count_x = studs_x - 1
    tube_count_y = studs_y - 1
    tube_height = height - FLOOR_THICKNESS

    with BuildPart() as tubes:
        with Locations(
            [
                Pos(
                    (i - (tube_count_x - 1) / 2) * PITCH,
                    (j - (tube_count_y - 1) / 2) * PITCH,
                    0,
                )
                for i in range(tube_count_x)
                for j in range(tube_count_y)
            ]
        ):
            Cylinder(
                TUBE_OUTER_RADIUS,
                tube_height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
            Cylinder(
                TUBE_INNER_RADIUS,
                tube_height,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
                mode=Mode.SUBTRACT,
            )

    return tubes.part


def lego_bottom_ridge(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, general. Create a bottom ridge rail for 1-wide bricks.

    1-wide bricks (1xN where N >= 2) have a single rail running along
    the length instead of tubes. This rail grips studs from below.

    Args:
        studs_x (int): Number of studs along X.
        studs_y (int): Number of studs along Y.
        height (float): Brick body height.

    Returns:
        Part or None: Ridge rail, or None if not a 1-wide brick.

    Examples:
        >>> # lego_bottom_ridge(1, 4) -> rail along Y axis
        >>> # lego_bottom_ridge(2, 4) -> None (uses tubes instead)
    """
    # Only for 1-wide bricks with 2+ studs in the other dimension
    if min(studs_x, studs_y) != 1 or max(studs_x, studs_y) < 2:
        return None

    ridge_length = (max(studs_x, studs_y) - 1) * PITCH
    ridge_z = height - FLOOR_THICKNESS - RIDGE_HEIGHT

    with BuildPart() as ridge:
        if studs_x == 1:
            # Ridge along Y
            Pos(0, 0, ridge_z) * Box(
                RIDGE_WIDTH, ridge_length, RIDGE_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
        else:
            # Ridge along X
            Pos(0, 0, ridge_z) * Box(
                ridge_length, RIDGE_WIDTH, RIDGE_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

    return ridge.part


# ── Specific brick builders ────────────────────────────────────────────────────

def lego_brick(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, general. Create a complete anatomically correct Lego brick.

    Assembles: hollow body + studs on top + bottom tubes (2+ wide) or
    bottom ridge (1-wide).

    Args:
        studs_x (int): Studs along X (e.g., 2 for a 2x4 brick).
        studs_y (int): Studs along Y (e.g., 4 for a 2x4 brick).
        height (float): Body height. Default BRICK_HEIGHT (9.6mm).
            Use PLATE_HEIGHT (3.2mm) for plates.

    Returns:
        Part: Complete Lego brick.

    Examples:
        >>> # lego_brick(2, 4) -> classic 2x4 brick
        >>> # lego_brick(1, 1) -> 1x1 brick
        >>> # lego_brick(2, 2, PLATE_HEIGHT) -> 2x2 plate
    """
    with BuildPart() as brick:
        add(lego_brick_body(studs_x, studs_y, height))
        add(lego_studs(studs_x, studs_y, z_offset=height))

        tubes = lego_bottom_tubes(studs_x, studs_y, height)
        if tubes is not None:
            add(tubes)

        ridge = lego_bottom_ridge(studs_x, studs_y, height)
        if ridge is not None:
            add(ridge)

    return brick.part
