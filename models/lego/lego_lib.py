"""
Clara brick geometry library — pure functions for generating anatomically
correct brick geometry using build123d.

All dimensions from measured Lego bricks and community CAD specifications
(LDraw, OpenSCAD lego.scad, Christoph Bartneck measurements).

Coordinate convention: brick sits on XY plane, studs point up (+Z).
Origin at the center-bottom of the brick body (not including studs).
"""

from build123d import (
    Box, Cylinder, Location, Pos, Part, Plane,
    Align, Axis, Mode, Keep, FontStyle,
    BuildPart, BuildSketch, add, Locations, GridLocations,
    Text, extrude, split,
)
import math

# ── Dimension Constants (mm) ─────────────────────────────────────────────────
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

# Fillets — real bricks have subtle edge rounding
FILLET_RADIUS = 0.15    # edge fillet radius (measured ~0.1-0.2mm on real bricks)

# Stud text — raised brand text on every stud top
STUD_TEXT = "CLARA"
STUD_TEXT_FONT_SIZE = 1.0   # gives ~72% width ratio on 4.8mm stud (real Lego: ~77%)
STUD_TEXT_HEIGHT = 0.1      # raised height above stud surface (measured 0.08-0.1mm)

# Derived
STUD_RADIUS = STUD_DIAMETER / 2
TUBE_OUTER_RADIUS = TUBE_OUTER_DIAMETER / 2
TUBE_INNER_RADIUS = TUBE_INNER_DIAMETER / 2


# ── General geometry functions ─────────────────────────────────────────────────

def lego_brick_body(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, general. Create the solid outer shell of a brick
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


def _stud_positions(studs_x, studs_y, z_offset=0.0):
    """
    Pure function, general. Compute stud center positions for a grid.

    Args:
        studs_x (int): Number of studs along X.
        studs_y (int): Number of studs along Y.
        z_offset (float): Z position of stud bases.

    Returns:
        list[Pos]: List of position objects for each stud.

    Examples:
        >>> # _stud_positions(2, 2, 9.6) -> [Pos(-4,  -4, 9.6), ...]
    """
    return [
        Pos(
            (i - (studs_x - 1) / 2) * PITCH,
            (j - (studs_y - 1) / 2) * PITCH,
            z_offset,
        )
        for i in range(studs_x)
        for j in range(studs_y)
    ]


def lego_studs(studs_x, studs_y, z_offset=0.0):
    """
    Pure function, general. Create studs arranged in a grid on top of a brick.

    Studs are cylinders of STUD_DIAMETER x STUD_HEIGHT, positioned at
    PITCH spacing, centered on the brick footprint. Text is added separately
    after filleting via lego_stud_text().

    Args:
        studs_x (int): Number of studs along X.
        studs_y (int): Number of studs along Y.
        z_offset (float): Z position of stud bases. Default 0.

    Returns:
        Part: All studs as a single Part (no text — added later).

    Examples:
        >>> # lego_studs(2, 4, z_offset=9.6) -> 8 studs at Z=9.6
    """
    with BuildPart() as studs:
        with Locations(_stud_positions(studs_x, studs_y, z_offset)):
            Cylinder(
                STUD_RADIUS,
                STUD_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

    return studs.part


def lego_stud_text(studs_x, studs_y, z_offset=0.0):
    """
    Pure function, specific. Create raised "CLARA" text for all studs.

    Added AFTER filleting to avoid fillet failures on tiny text edges.
    Each stud gets 0.1mm raised bold text centered on its top face.

    Args:
        studs_x (int): Number of studs along X.
        studs_y (int): Number of studs along Y.
        z_offset (float): Z position of stud bases (text sits at z_offset + STUD_HEIGHT).

    Returns:
        Part: All text geometry as a single Part.

    Examples:
        >>> # lego_stud_text(2, 4, z_offset=9.6) -> "CLARA" on 8 studs
    """
    text_z = z_offset + STUD_HEIGHT

    with BuildPart() as texts:
        with Locations(_stud_positions(studs_x, studs_y, text_z)):
            with BuildSketch(Plane.XY):
                Text(
                    STUD_TEXT,
                    font_size=STUD_TEXT_FONT_SIZE,
                    font_style=FontStyle.BOLD,
                    align=(Align.CENTER, Align.CENTER),
                )
            extrude(amount=STUD_TEXT_HEIGHT)

    return texts.part


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


def _apply_fillets(result):
    """
    Pure function, specific. Apply fillets to all edges except the bottom
    plane (Z=0) for 3D printability.

    Must be called BEFORE adding stud text — text edges are too small
    for the fillet radius and will cause OCCT failures.

    Args:
        result (Part): Solid to fillet.

    Returns:
        Part: Filleted solid.

    Examples:
        >>> # _apply_fillets(some_brick) -> same brick with 0.15mm fillets
    """
    bottom_edges = [e for e in result.edges() if abs(e.center().Z) < 0.01]
    fillet_edges = [e for e in result.edges() if e not in bottom_edges]
    return result.fillet(FILLET_RADIUS, fillet_edges)


# ── Specific brick builders ────────────────────────────────────────────────────

def lego_brick(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, general. Create a complete anatomically correct brick.

    Assembles: hollow body + studs with "CLARA" text on top + bottom
    tubes (2+ wide) or bottom ridge (1-wide) + fillets.

    Args:
        studs_x (int): Studs along X (e.g., 2 for a 2x4 brick).
        studs_y (int): Studs along Y (e.g., 4 for a 2x4 brick).
        height (float): Body height. Default BRICK_HEIGHT (9.6mm).
            Use PLATE_HEIGHT (3.2mm) for plates.

    Returns:
        Part: Complete brick.

    Examples:
        >>> # lego_brick(2, 4) -> classic 2x4 brick
        >>> # lego_brick(1, 1) -> 1x1 brick
        >>> # lego_brick(2, 2, PLATE_HEIGHT) -> 2x2 plate
    """
    # Build structural geometry (body + studs + tubes/ridges)
    with BuildPart() as brick:
        add(lego_brick_body(studs_x, studs_y, height))
        add(lego_studs(studs_x, studs_y, z_offset=height))

        tubes = lego_bottom_tubes(studs_x, studs_y, height)
        if tubes is not None:
            add(tubes)

        ridge = lego_bottom_ridge(studs_x, studs_y, height)
        if ridge is not None:
            add(ridge)

    # Fillet BEFORE text (text edges are too small for OCCT filleter)
    result = _apply_fillets(brick.part)

    # Add raised text on stud tops
    with BuildPart() as final:
        add(result)
        add(lego_stud_text(studs_x, studs_y, z_offset=height))

    return final.part


def lego_slope(studs_x, studs_y, height=BRICK_HEIGHT, flat_rows=1):
    """
    Pure function, specific. Create a slope/wedge brick.

    The brick body is cut at an angle from the top of the flat portion
    down to the bottom of the far edge. Only studs on the flat (non-sloped)
    rows are retained. Bottom tubes/ridges are still present.

    The slope descends toward +Y (the "back" of the brick). The flat_rows
    parameter controls how many rows of studs remain on the front.

    Args:
        studs_x (int): Studs along X.
        studs_y (int): Studs along Y (must be >= 2).
        height (float): Body height. Default BRICK_HEIGHT.
        flat_rows (int): Number of stud rows on the flat top. Default 1.

    Returns:
        Part: Slope brick with angled top surface.

    Examples:
        >>> # lego_slope(2, 2) -> 2x2 slope, 1 flat row, 1 sloped row
        >>> # lego_slope(2, 4, flat_rows=2) -> 2x4 slope, 2 flat rows
    """
    outer_y = studs_y * PITCH - 2 * CLEARANCE

    # Build full body + studs only on flat rows + bottom structure
    with BuildPart() as brick:
        add(lego_brick_body(studs_x, studs_y, height))

        # Only place studs on flat_rows (front rows, toward -Y)
        # Stud positions: j=0 is the -Y side, j=studs_y-1 is the +Y side
        # We keep j < flat_rows
        # Studs only on flat rows (toward -Y)
        flat_stud_positions = [
            Pos(
                (i - (studs_x - 1) / 2) * PITCH,
                (j - (studs_y - 1) / 2) * PITCH,
                height,
            )
            for i in range(studs_x)
            for j in range(flat_rows)
        ]
        if flat_stud_positions:
            with Locations(flat_stud_positions):
                Cylinder(
                    STUD_RADIUS,
                    STUD_HEIGHT,
                    align=(Align.CENTER, Align.CENTER, Align.MIN),
                )

        tubes = lego_bottom_tubes(studs_x, studs_y, height)
        if tubes is not None:
            add(tubes)

        ridge = lego_bottom_ridge(studs_x, studs_y, height)
        if ridge is not None:
            add(ridge)

    result = brick.part

    # Cut the slope: plane from top at hinge to bottom at far edge
    hinge_y = -outer_y / 2 + flat_rows * PITCH
    slope_dy = outer_y / 2 - hinge_y
    slope_dz = height
    cut_plane = Plane(
        origin=(0, hinge_y, height),
        x_dir=(1, 0, 0),
        z_dir=(0, slope_dz, slope_dy),
    )
    result = split(result, bisect_by=cut_plane, keep=Keep.BOTTOM)

    # Fillet, then add text on flat studs
    result = _apply_fillets(result)

    # Add raised text on the flat studs only
    text_positions = [
        Pos(
            (i - (studs_x - 1) / 2) * PITCH,
            (j - (studs_y - 1) / 2) * PITCH,
            height + STUD_HEIGHT,
        )
        for i in range(studs_x)
        for j in range(flat_rows)
    ]
    if text_positions:
        with BuildPart() as final:
            add(result)
            with Locations(text_positions):
                with BuildSketch(Plane.XY):
                    Text(
                        STUD_TEXT,
                        font_size=STUD_TEXT_FONT_SIZE,
                        font_style=FontStyle.BOLD,
                        align=(Align.CENTER, Align.CENTER),
                    )
                extrude(amount=STUD_TEXT_HEIGHT)
        result = final.part

    return result
