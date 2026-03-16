"""
Clara brick geometry library — pure functions for generating anatomically
correct brick geometry using build123d.

Architecture: 2D sketch → extrude. Cross-section profiles (walls, tubes)
are defined in 2D and extruded once, so internal features can't exceed
boundaries. A ceiling box seals the top separately (different thickness
from walls). Studs, fillets, and raised text are added in separate passes.

Coordinate convention: brick sits on XY plane, studs point up (+Z).
Origin at the center-bottom of the brick body (not including studs).
"""

from build123d import (
    Box, Circle, Cylinder, Rectangle, Pos, Plane,
    Align, Kind, Mode, Keep, FontStyle,
    BuildPart, BuildSketch, add, Locations, GridLocations,
    Text, extrude, offset, split,
)
import math

# ── Dimension Constants (mm) ─────────────────────────────────────────────────
# Sources: LDraw (1 LDU = 0.4mm), OpenSCAD lego.scad, Bartneck measurements
# Base unit: 1 LDU = 0.4mm. Stud pitch = 20 LDU = 8.0mm.

PITCH = 8.0             # stud center-to-center (20 LDU)
STUD_DIAMETER = 4.8     # stud outer diameter (12 LDU)
STUD_HEIGHT = 1.8       # stud protrusion above brick top
BRICK_HEIGHT = 9.6      # standard brick body (24 LDU, without stud)
PLATE_HEIGHT = 3.2      # plate body (8 LDU, 1/3 of brick)
WALL_THICKNESS = 1.5    # outer wall thickness
FLOOR_THICKNESS = 1.0   # top ceiling thickness
CLEARANCE = 0.1         # per-side fit clearance

TUBE_OUTER_DIAMETER = 6.31  # anti-stud tube outer
TUBE_INNER_DIAMETER = 4.8   # tube inner (~stud diameter)
RIDGE_WIDTH = 0.8       # bottom ridge for 1-wide bricks
RIDGE_HEIGHT = 0.8      # ridge depth below ceiling

FILLET_RADIUS = 0.15    # edge rounding
STUD_TEXT = "CLARA"
STUD_TEXT_FONT_SIZE = 1.0
STUD_TEXT_HEIGHT = 0.1  # raised text height

STUD_RADIUS = STUD_DIAMETER / 2
TUBE_OUTER_RADIUS = TUBE_OUTER_DIAMETER / 2
TUBE_INNER_RADIUS = TUBE_INNER_DIAMETER / 2


# ── General helper ───────────────────────────────────────────────────────────

def fillet_above_z(part, radius, z_threshold=0.0, tolerance=0.01):
    """
    Pure function, general. Fillet all edges above a Z threshold.

    Keeps bottom edges sharp (build plate adhesion / clean base).

    Args:
        part (Part): Solid to fillet.
        radius (float): Fillet radius (mm).
        z_threshold (float): Edges at or below this Z are skipped.
        tolerance (float): Z comparison tolerance.

    Returns:
        Part: Filleted solid.

    Examples:
        >>> # fillet_above_z(box, 0.15) -> fillets everything except Z=0
        >>> # fillet_above_z(box, 0.5, z_threshold=2.0) -> skip Z<=2
    """
    edges = [e for e in part.edges() if e.center().Z > z_threshold + tolerance]
    return part.fillet(radius, edges)


# ── Clara bricks ─────────────────────────────────────────────────────────────

def lego_brick(studs_x, studs_y, height=BRICK_HEIGHT):
    """
    Pure function, specific. Create a complete Clara brick.

    Cross-section sketch (walls + tubes) → extrude → ceiling → ridge →
    studs → fillet → text.

    Args:
        studs_x (int): Studs along X (e.g., 2 for a 2x4).
        studs_y (int): Studs along Y (e.g., 4 for a 2x4).
        height (float): Body height. BRICK_HEIGHT (9.6) or PLATE_HEIGHT (3.2).

    Returns:
        Part: Complete brick.

    Examples:
        >>> # lego_brick(2, 4) -> classic 2x4 brick
        >>> # lego_brick(1, 1) -> 1x1 brick
        >>> # lego_brick(2, 2, PLATE_HEIGHT) -> 2x2 plate
    """
    outer_x = studs_x * PITCH - 2 * CLEARANCE
    outer_y = studs_y * PITCH - 2 * CLEARANCE
    cavity_z = height - FLOOR_THICKNESS

    with BuildPart() as brick:
        # ── Cross-section (walls + tubes) → extrude ──
        with BuildSketch():
            perimeter = Rectangle(outer_x, outer_y)
            offset(perimeter, amount=-WALL_THICKNESS,
                   kind=Kind.INTERSECTION, mode=Mode.SUBTRACT)
            if studs_x >= 2 and studs_y >= 2:
                with GridLocations(PITCH, PITCH, studs_x - 1, studs_y - 1):
                    Circle(TUBE_OUTER_RADIUS)
                    Circle(TUBE_INNER_RADIUS, mode=Mode.SUBTRACT)
        extrude(amount=cavity_z)

        # ── Ceiling ──
        Pos(0, 0, cavity_z) * Box(outer_x, outer_y, FLOOR_THICKNESS,
            align=(Align.CENTER, Align.CENTER, Align.MIN))

        # ── Ridge (1-wide bricks: thin rail grips studs from below) ──
        if min(studs_x, studs_y) == 1 and max(studs_x, studs_y) >= 2:
            ridge_len = (max(studs_x, studs_y) - 1) * PITCH
            rx, ry = (RIDGE_WIDTH, ridge_len) if studs_x == 1 else (ridge_len, RIDGE_WIDTH)
            Pos(0, 0, cavity_z - RIDGE_HEIGHT) * Box(rx, ry, RIDGE_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN))

        # ── Studs ──
        with Locations([Pos(0, 0, height)]):
            with GridLocations(PITCH, PITCH, studs_x, studs_y):
                Cylinder(STUD_RADIUS, STUD_HEIGHT,
                         align=(Align.CENTER, Align.CENTER, Align.MIN))

    # Fillet, then text (text edges too fine for OCCT filleter)
    result = fillet_above_z(brick.part, FILLET_RADIUS)

    with BuildPart() as final:
        add(result)
        with Locations([Pos(0, 0, height + STUD_HEIGHT)]):
            with GridLocations(PITCH, PITCH, studs_x, studs_y):
                with BuildSketch(Plane.XY):
                    Text(STUD_TEXT, font_size=STUD_TEXT_FONT_SIZE,
                         font_style=FontStyle.BOLD,
                         align=(Align.CENTER, Align.CENTER))
                extrude(amount=STUD_TEXT_HEIGHT)

    return final.part


def lego_slope(studs_x, studs_y, height=BRICK_HEIGHT, flat_rows=1):
    """
    Pure function, specific. Create a slope/wedge brick.

    Slope descends toward +Y. Only flat_rows of studs retained.

    Build order (critical — prevents exposed cavity):
        1. Solid outer box → cut slope
        2. Interior cavity → cut by OFFSET slope plane (ensures
           FLOOR_THICKNESS of material between slope face and cavity)
        3. Shell = outer - cavity
        4. Tubes: sketch → extrude → clip to cavity via boolean &
        5. Add studs, ridge → fillet → text

    The cavity cut plane is offset inward along the slope normal by
    FLOOR_THICKNESS. Without this, the cavity ceiling touches the slope
    surface, exposing the interior through the slope face.

    Args:
        studs_x (int): Studs along X.
        studs_y (int): Studs along Y (>= 2).
        height (float): Body height. Default BRICK_HEIGHT.
        flat_rows (int): Stud rows on the flat top. Default 1.

    Returns:
        Part: Slope brick.

    Examples:
        >>> # lego_slope(2, 2) -> 2x2 slope, 1 flat row
        >>> # lego_slope(2, 4, flat_rows=2) -> 2x4 slope, 2 flat rows
    """
    outer_x = studs_x * PITCH - 2 * CLEARANCE
    outer_y = studs_y * PITCH - 2 * CLEARANCE
    inner_x = outer_x - 2 * WALL_THICKNESS
    inner_y = outer_y - 2 * WALL_THICKNESS
    cavity_z = height - FLOOR_THICKNESS

    # ── Slope planes ──
    # Hinge: where the flat top meets the slope.
    # Slope descends from height at hinge_y to WALL_THICKNESS at +Y edge.
    hinge_y = -outer_y / 2 + flat_rows * PITCH
    slope_dy = outer_y / 2 - hinge_y
    slope_dz = height - WALL_THICKNESS
    normal = (0, slope_dz, slope_dy)

    cut_plane = Plane(
        origin=(0, hinge_y, height), x_dir=(1, 0, 0), z_dir=normal)

    # Cavity cut plane: offset FLOOR_THICKNESS inward along slope normal.
    normal_mag = math.sqrt(slope_dz**2 + slope_dy**2)
    cavity_cut_plane = Plane(
        origin=(0,
                hinge_y - FLOOR_THICKNESS * slope_dz / normal_mag,
                height - FLOOR_THICKNESS * slope_dy / normal_mag),
        x_dir=(1, 0, 0), z_dir=normal)

    # ── Sloped shell ──
    outer = Box(outer_x, outer_y, height,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
    sloped_outer = split(outer, bisect_by=cut_plane, keep=Keep.BOTTOM)

    cavity = Box(inner_x, inner_y, cavity_z,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    sloped_cavity = split(cavity, bisect_by=cavity_cut_plane, keep=Keep.BOTTOM)

    shell = sloped_outer - sloped_cavity

    # ── Tubes: sketch → extrude → clip to cavity ──
    clipped_tubes = None
    if studs_x >= 2 and studs_y >= 2:
        with BuildPart() as tb:
            with BuildSketch():
                with GridLocations(PITCH, PITCH, studs_x - 1, studs_y - 1):
                    Circle(TUBE_OUTER_RADIUS)
                    Circle(TUBE_INNER_RADIUS, mode=Mode.SUBTRACT)
            extrude(amount=cavity_z)
        clipped_tubes = tb.part & sloped_cavity

    # ── Flat stud positions (front rows only, centered in full grid) ──
    flat_xy = [((i - (studs_x - 1) / 2) * PITCH,
                (j - (studs_y - 1) / 2) * PITCH)
               for i in range(studs_x) for j in range(flat_rows)]

    # ── Assemble ──
    with BuildPart() as brick:
        add(shell)

        if clipped_tubes:
            add(clipped_tubes)

        # Ridge (1-wide bricks)
        if min(studs_x, studs_y) == 1 and max(studs_x, studs_y) >= 2:
            ridge_len = (max(studs_x, studs_y) - 1) * PITCH
            rx, ry = (RIDGE_WIDTH, ridge_len) if studs_x == 1 else (ridge_len, RIDGE_WIDTH)
            Pos(0, 0, cavity_z - RIDGE_HEIGHT) * Box(rx, ry, RIDGE_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN))

        # Studs on flat portion
        if flat_xy:
            with Locations([Pos(x, y, height) for x, y in flat_xy]):
                Cylinder(STUD_RADIUS, STUD_HEIGHT,
                         align=(Align.CENTER, Align.CENTER, Align.MIN))

    # Fillet, then text on flat studs
    result = fillet_above_z(brick.part, FILLET_RADIUS)

    if flat_xy:
        with BuildPart() as final:
            add(result)
            with Locations([Pos(x, y, height + STUD_HEIGHT) for x, y in flat_xy]):
                with BuildSketch(Plane.XY):
                    Text(STUD_TEXT, font_size=STUD_TEXT_FONT_SIZE,
                         font_style=FontStyle.BOLD,
                         align=(Align.CENTER, Align.CENTER))
                extrude(amount=STUD_TEXT_HEIGHT)
        result = final.part

    return result
