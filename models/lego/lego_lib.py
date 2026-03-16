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


# ── General geometry functions ───────────────────────────────────────────────

def centered_grid(nx, ny, spacing, z=0.0):
    """
    Pure function, general. Compute centered grid positions.

    Returns positions for an nx × ny grid with given spacing, centered
    on the XY origin at the given Z height.

    Args:
        nx (int): Number of positions along X.
        ny (int): Number of positions along Y.
        spacing (float): Distance between adjacent positions (mm).
        z (float): Z coordinate for all positions.

    Returns:
        list[Pos]: Grid positions, row-major order.

    Examples:
        >>> # centered_grid(2, 2, 8.0) -> [Pos(-4,-4,0), Pos(-4,4,0), Pos(4,-4,0), Pos(4,4,0)]
        >>> # centered_grid(1, 1, 8.0, z=5.0) -> [Pos(0, 0, 5.0)]
        >>> # centered_grid(3, 1, 10.0) -> [Pos(-10,0,0), Pos(0,0,0), Pos(10,0,0)]
    """
    return [
        Pos(
            (i - (nx - 1) / 2) * spacing,
            (j - (ny - 1) / 2) * spacing,
            z,
        )
        for i in range(nx)
        for j in range(ny)
    ]


def hollow_box(outer_x, outer_y, outer_z, wall, floor):
    """
    Pure function, general. Create a hollow box (shell with open bottom cavity).

    The box has uniform wall thickness on all four sides and a solid floor
    (ceiling when viewed from inside). The cavity opens downward from Z=0.

    Args:
        outer_x (float): Outer width (X dimension).
        outer_y (float): Outer depth (Y dimension).
        outer_z (float): Outer height (Z dimension).
        wall (float): Wall thickness on all four sides.
        floor (float): Top ceiling thickness.

    Returns:
        Part: Hollow box, centered on XY, bottom at Z=0.

    Examples:
        >>> # hollow_box(15.8, 31.8, 9.6, 1.5, 1.0)
        >>> #   -> 15.8×31.8×9.6mm shell, 1.5mm walls, 1.0mm ceiling
        >>> # hollow_box(10, 10, 5, 2, 1)
        >>> #   -> 10×10×5 box with 6×6×4 cavity
    """
    inner_x = outer_x - 2 * wall
    inner_y = outer_y - 2 * wall
    inner_z = outer_z - floor

    with BuildPart() as body:
        Box(outer_x, outer_y, outer_z,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
        Box(inner_x, inner_y, inner_z,
            align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT)

    return body.part


def cylinders_at(radius, height, positions):
    """
    Pure function, general. Place cylinders at multiple positions.

    Each cylinder is aligned center-center-min (centered on XY, bottom at
    the position's Z coordinate).

    Args:
        radius (float): Cylinder radius.
        height (float): Cylinder height.
        positions (list[Pos]): Where to place each cylinder.

    Returns:
        Part: All cylinders fused into a single Part.

    Examples:
        >>> # cylinders_at(2.4, 1.8, [Pos(0,0,9.6)]) -> one stud
        >>> # cylinders_at(3, 5, centered_grid(2, 2, 8)) -> 4 cylinders in a grid
    """
    with BuildPart() as result:
        with Locations(positions):
            Cylinder(radius, height,
                     align=(Align.CENTER, Align.CENTER, Align.MIN))
    return result.part


def hollow_cylinders_at(outer_radius, inner_radius, height, positions):
    """
    Pure function, general. Place hollow cylinders (tubes) at multiple positions.

    Args:
        outer_radius (float): Outer cylinder radius.
        inner_radius (float): Inner hole radius.
        height (float): Cylinder height.
        positions (list[Pos]): Where to place each tube.

    Returns:
        Part: All tubes fused into a single Part.

    Examples:
        >>> # hollow_cylinders_at(3.155, 2.4, 8.6, [Pos(0,0,0)])
        >>> #   -> one tube with 3.155mm outer, 2.4mm inner radius
    """
    with BuildPart() as result:
        with Locations(positions):
            Cylinder(outer_radius, height,
                     align=(Align.CENTER, Align.CENTER, Align.MIN))
            Cylinder(inner_radius, height,
                     align=(Align.CENTER, Align.CENTER, Align.MIN),
                     mode=Mode.SUBTRACT)
    return result.part


def raised_text_at(text, font_size, height, positions,
                   font_style=FontStyle.BOLD):
    """
    Pure function, general. Create raised (extruded) text at multiple positions.

    Each position gets a copy of the text, extruded upward by `height`.
    Text is centered on XY at each position. The position's Z coordinate
    is the base of the text extrusion.

    Uses build123d's Text class which renders fonts via OCCT directly to
    exact B-Rep curves — no SVG or rasterization intermediate needed.

    Must be added AFTER filleting — text edges are too fine for most
    fillet radii and will cause OCCT kernel failures.

    Args:
        text (str): The text string to render.
        font_size (float): Font size in mm.
        height (float): Extrusion height (raised amount) in mm.
        positions (list[Pos]): Where to place each text instance.
        font_style (FontStyle): Font style. Default BOLD.

    Returns:
        Part: All text geometry fused into a single Part.

    Examples:
        >>> # raised_text_at("ACME", 1.0, 0.1, [Pos(0, 0, 5)])
        >>> #   -> "ACME" in bold, 0.1mm raised, at Z=5
        >>> # raised_text_at("OK", 2.0, 0.5, centered_grid(2, 2, 10, z=3))
        >>> #   -> "OK" at 4 grid positions
    """
    with BuildPart() as result:
        with Locations(positions):
            with BuildSketch(Plane.XY):
                Text(text, font_size=font_size, font_style=font_style,
                     align=(Align.CENTER, Align.CENTER))
            extrude(amount=height)
    return result.part


def fillet_above_z(part, radius, z_threshold=0.0, tolerance=0.01):
    """
    Pure function, general. Fillet all edges except those at or below a
    Z threshold. Useful for parts that sit on a build plate — keeps the
    bottom edges sharp for clean 3D printing bed adhesion.

    Args:
        part (Part): Solid to fillet.
        radius (float): Fillet radius in mm.
        z_threshold (float): Edges with center Z <= this are skipped.
        tolerance (float): Z comparison tolerance.

    Returns:
        Part: Filleted solid.

    Examples:
        >>> # fillet_above_z(box, 0.15) -> fillets everything except Z=0 edges
        >>> # fillet_above_z(box, 0.5, z_threshold=2.0) -> skip edges at Z<=2
    """
    skip = [e for e in part.edges() if e.center().Z <= z_threshold + tolerance]
    fillet_edges = [e for e in part.edges() if e not in skip]
    return part.fillet(radius, fillet_edges)


# ── Clara brick functions (specific) ─────────────────────────────────────────

def lego_brick_body(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, specific. Create the hollow outer shell of a Clara brick.

    Computes outer dimensions from stud count × PITCH - CLEARANCE, then
    delegates to hollow_box().

    Args:
        studs_x (int): Number of studs along X axis.
        studs_y (int): Number of studs along Y axis.
        height (float): Body height in mm. Default BRICK_HEIGHT (9.6mm).

    Returns:
        Part: Hollow brick body centered on XY, bottom at Z=0.

    Examples:
        >>> # lego_brick_body(2, 4) -> 15.8mm x 31.8mm x 9.6mm hollow box
        >>> # lego_brick_body(1, 1, PLATE_HEIGHT) -> 7.8mm x 7.8mm x 3.2mm plate
    """
    outer_x = studs_x * PITCH - 2 * CLEARANCE
    outer_y = studs_y * PITCH - 2 * CLEARANCE
    return hollow_box(outer_x, outer_y, height, WALL_THICKNESS, FLOOR_THICKNESS)


def lego_studs(studs_x, studs_y, z_offset=0.0):
    """
    Pure function, specific. Create studs arranged in a grid on top of a brick.

    Studs are cylinders of STUD_DIAMETER × STUD_HEIGHT at PITCH spacing.
    Text is added separately after filleting via raised_text_at().

    Args:
        studs_x (int): Number of studs along X.
        studs_y (int): Number of studs along Y.
        z_offset (float): Z position of stud bases.

    Returns:
        Part: All studs as a single Part.

    Examples:
        >>> # lego_studs(2, 4, z_offset=9.6) -> 8 studs at Z=9.6
    """
    return cylinders_at(
        STUD_RADIUS, STUD_HEIGHT,
        centered_grid(studs_x, studs_y, PITCH, z=z_offset),
    )


def lego_stud_text(studs_x, studs_y, z_offset=0.0):
    """
    Pure function, specific. Create raised "CLARA" text for all studs.

    Added AFTER filleting to avoid fillet failures on tiny text edges.

    Args:
        studs_x (int): Number of studs along X.
        studs_y (int): Number of studs along Y.
        z_offset (float): Z position of stud bases (text at z_offset + STUD_HEIGHT).

    Returns:
        Part: All text geometry as a single Part.

    Examples:
        >>> # lego_stud_text(2, 4, z_offset=9.6) -> "CLARA" on 8 studs
    """
    return raised_text_at(
        STUD_TEXT, STUD_TEXT_FONT_SIZE, STUD_TEXT_HEIGHT,
        centered_grid(studs_x, studs_y, PITCH, z=z_offset + STUD_HEIGHT),
    )


def lego_bottom_tubes(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, specific. Create anti-stud tubes for the underside of
    bricks that are 2+ studs wide in both dimensions.

    Tubes are hollow cylinders placed between each 2×2 group of studs.

    Args:
        studs_x (int): Number of studs along X.
        studs_y (int): Number of studs along Y.
        height (float): Brick body height (tubes extend from floor to bottom).

    Returns:
        Part or None: Tubes as a single Part, or None if brick is too small.

    Examples:
        >>> # lego_bottom_tubes(2, 4) -> 3 tubes for a 2x4 brick
        >>> # lego_bottom_tubes(1, 2) -> None (1-wide, uses ridge instead)
    """
    if studs_x < 2 or studs_y < 2:
        return None

    tube_count_x = studs_x - 1
    tube_count_y = studs_y - 1
    tube_height = height - FLOOR_THICKNESS

    return hollow_cylinders_at(
        TUBE_OUTER_RADIUS, TUBE_INNER_RADIUS, tube_height,
        centered_grid(tube_count_x, tube_count_y, PITCH),
    )


def lego_bottom_ridge(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, specific. Create a bottom ridge rail for 1-wide bricks.

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
    if min(studs_x, studs_y) != 1 or max(studs_x, studs_y) < 2:
        return None

    ridge_length = (max(studs_x, studs_y) - 1) * PITCH
    ridge_z = height - FLOOR_THICKNESS - RIDGE_HEIGHT

    with BuildPart() as ridge:
        if studs_x == 1:
            Pos(0, 0, ridge_z) * Box(
                RIDGE_WIDTH, ridge_length, RIDGE_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )
        else:
            Pos(0, 0, ridge_z) * Box(
                ridge_length, RIDGE_WIDTH, RIDGE_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

    return ridge.part


def lego_brick(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, specific. Create a complete anatomically correct Clara brick.

    Assembles: hollow body + studs + bottom tubes/ridge + fillets + "CLARA" text.

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
    result = fillet_above_z(brick.part, FILLET_RADIUS)

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
    rows are retained. Bottom tubes/ridges still present.

    The slope descends toward +Y (the "back" of the brick). The flat_rows
    parameter controls how many rows of studs remain on the front.

    Build order (critical — prevents exposed cavity):
        1. Solid outer box → cut slope → solid sloped shell
        2. Interior cavity → cut by same slope plane → trimmed cavity
        3. Subtract trimmed cavity from shell → hollow slope with solid walls
        4. Add internal structure (tubes/ridge) + external (studs)
        5. Fillet → text

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
    outer_x = studs_x * PITCH - 2 * CLEARANCE
    outer_y = studs_y * PITCH - 2 * CLEARANCE
    inner_x = outer_x - 2 * WALL_THICKNESS
    inner_y = outer_y - 2 * WALL_THICKNESS
    inner_z = height - FLOOR_THICKNESS

    # Slope cutting plane: from top at hinge line to lip at far edge.
    # Real bricks have a vertical lip (WALL_THICKNESS tall) at the low end.
    hinge_y = -outer_y / 2 + flat_rows * PITCH
    slope_dy = outer_y / 2 - hinge_y
    slope_dz = height - WALL_THICKNESS  # slope drops to WALL_THICKNESS, not 0
    cut_plane = Plane(
        origin=(0, hinge_y, height),
        x_dir=(1, 0, 0),
        z_dir=(0, slope_dz, slope_dy),
    )

    # Cavity cut plane: offset inward by FLOOR_THICKNESS perpendicular to slope.
    # Without this offset, the cavity ceiling touches the slope surface with
    # zero wall thickness — looking over the lip, you see straight into the
    # interior. The offset ensures FLOOR_THICKNESS of solid material between
    # the slope face and the cavity everywhere.
    slope_normal_mag = math.sqrt(slope_dz**2 + slope_dy**2)
    offset = FLOOR_THICKNESS
    cavity_cut_plane = Plane(
        origin=(0,
                hinge_y - offset * slope_dz / slope_normal_mag,
                height - offset * slope_dy / slope_normal_mag),
        x_dir=(1, 0, 0),
        z_dir=(0, slope_dz, slope_dy),
    )

    # 1. Solid outer box → cut slope
    with BuildPart() as outer:
        Box(outer_x, outer_y, height,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
    sloped_outer = split(outer.part, bisect_by=cut_plane, keep=Keep.BOTTOM)

    # 2. Interior cavity → cut by OFFSET plane (stays inside shell with
    #    FLOOR_THICKNESS clearance from slope surface)
    with BuildPart() as inner:
        Box(inner_x, inner_y, inner_z,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
    sloped_cavity = split(inner.part, bisect_by=cavity_cut_plane, keep=Keep.BOTTOM)

    # 3. Shell = outer - cavity
    shell = sloped_outer - sloped_cavity

    # 4. Add internal features + studs
    flat_xy = [
        ((i - (studs_x - 1) / 2) * PITCH,
         (j - (studs_y - 1) / 2) * PITCH)
        for i in range(studs_x)
        for j in range(flat_rows)
    ]
    stud_positions = [Pos(x, y, height) for x, y in flat_xy]

    with BuildPart() as brick:
        add(shell)

        if stud_positions:
            add(cylinders_at(STUD_RADIUS, STUD_HEIGHT, stud_positions))

        tubes = lego_bottom_tubes(studs_x, studs_y, height)
        if tubes is not None:
            add(tubes)

        ridge = lego_bottom_ridge(studs_x, studs_y, height)
        if ridge is not None:
            add(ridge)

    # 4. Fillet (before text)
    result = fillet_above_z(brick.part, FILLET_RADIUS)

    # 5. Raised text on flat studs only
    text_positions = [Pos(x, y, height + STUD_HEIGHT) for x, y in flat_xy]
    if text_positions:
        with BuildPart() as final:
            add(result)
            add(raised_text_at(
                STUD_TEXT, STUD_TEXT_FONT_SIZE, STUD_TEXT_HEIGHT,
                text_positions,
            ))
        result = final.part

    return result
