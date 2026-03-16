"""
Unified brick geometry library — all clutch systems in one module.

Merges lego_lib.py (tube clutch) and clara_lib.py (lattice clutch) into a
single brick() + slope() interface with clutch type as a parameter. Clara-only
features (corner_radius, taper, stud_taper) are now available with any clutch.

Architecture: shell → clutch internals → studs → fillet → text.
Cross-shape bricks (L/T/+) and 4-directional slopes are supported.

Coordinate convention: brick sits on XY plane, studs point up (+Z).
Origin at the center-bottom of the brick body (not including studs).
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import (
    Box, Circle, Cylinder, Rectangle, RectangleRounded, Pos, Rot, Plane,
    Align, Keep, Mode, FontStyle,
    BuildPart, BuildSketch, add, Locations, GridLocations,
    Text, extrude, loft, split, fillet as bd_fillet,
)
from common import (
    PITCH, STUD_DIAMETER, STUD_RADIUS, STUD_HEIGHT,
    BRICK_HEIGHT, WALL_THICKNESS, FLOOR_THICKNESS,
    CLEARANCE, FILLET_RADIUS, ENABLE_FILLET, EDGE_STYLE, FILLET_BOTTOM,
    SKIP_CONCAVE, CR_SKIP_CONCAVE, ENABLE_STUDS, ENABLE_TEXT,
    STUD_TEXT, STUD_TEXT_FONT, STUD_TEXT_FONT_SIZE, STUD_TEXT_HEIGHT,
    STUD_TEXT_ROTATION,
    bevel_above_z,
)

# ── LEGO tube constants (mm) ────────────────────────────────────────────────

TUBE_OUTER_DIAMETER = 6.31
TUBE_INNER_DIAMETER = 4.8
RIDGE_WIDTH = 0.8
RIDGE_HEIGHT = 0.8

TUBE_OUTER_RADIUS = TUBE_OUTER_DIAMETER / 2
TUBE_INNER_RADIUS = TUBE_INNER_DIAMETER / 2


# ── Taper helpers ────────────────────────────────────────────────────────────

_CURVED_TAPER_STEPS = 8


def _taper_profile(t, curve="LINEAR"):
    """
    Pure function, general. Taper inset fraction at normalized position t.

    LINEAR: straight line. CURVED: quarter-circle f(t) = 1 - sqrt(1 - t**2).
    Tangent to vertical at t=0, tangent to horizontal at t=1. Concave up.

    Args:
        t (float): Position along taper, 0 = start, 1 = end.
        curve (str): "LINEAR" or "CURVED".

    Returns:
        float: Fraction of total inset at position t, in [0, 1].

    Examples:
        >>> _taper_profile(0.0, "LINEAR")
        0.0
        >>> _taper_profile(0.5, "LINEAR")
        0.5
        >>> _taper_profile(1.0, "CURVED")
        1.0
        >>> round(_taper_profile(0.5, "CURVED"), 4)
        0.134
    """
    if curve == "CURVED":
        return 1.0 - math.sqrt(1.0 - t * t)
    return t


def _clamp_cr(cr, w, h):
    """
    Pure function, general. Clamp corner radius to fit within w x h rectangle.

    Args:
        cr (float): Desired corner radius.
        w (float): Rectangle width.
        h (float): Rectangle height.

    Returns:
        float: Clamped radius >= 0.

    Examples:
        >>> _clamp_cr(2.0, 10.0, 8.0)
        2.0
        >>> _clamp_cr(6.0, 10.0, 8.0)
        3.99
        >>> _clamp_cr(-1.0, 10.0, 8.0)
        0
    """
    if cr <= 0:
        return 0
    return max(min(cr, w / 2 - 0.01, h / 2 - 0.01), 0)


def _rounded_rect(w, h, r):
    """
    Command, general. Add a (optionally rounded) rectangle to the current
    BuildSketch. Uses RectangleRounded when r > 0, plain Rectangle otherwise.

    Args:
        w (float): Width (X).
        h (float): Height (Y).
        r (float): Corner radius. 0 = sharp corners.

    Examples:
        >>> # with BuildSketch(): _rounded_rect(10, 5, 1.5)
    """
    if r > 0:
        RectangleRounded(w, h, r)
    else:
        Rectangle(w, h)


# ── Stud builder ─────────────────────────────────────────────────────────────

def _build_stud(radius, total_height, taper_height=0, taper_inset=0,
                taper_curve="LINEAR"):
    """
    Pure function, specific. Build a single stud, optionally tapered at the top.

    Origin at center-bottom. Without taper, returns a simple cylinder. With
    taper, lofts circle profiles from full radius down to (radius - taper_inset)
    over the taper zone.

    Args:
        radius (float): Stud radius at base.
        total_height (float): Full stud height.
        taper_height (float): Height of tapered zone at top. 0 = no taper.
        taper_inset (float): Radius reduction at top. 0 = no taper.
        taper_curve (str): "LINEAR" or "CURVED".

    Returns:
        Part: Stud geometry, origin at center-bottom.

    Examples:
        >>> # _build_stud(2.4, 1.8)  -> simple cylinder
        >>> # _build_stud(2.4, 1.8, 0.5, 0.2, "CURVED")  -> tapered stud
    """
    has_taper = taper_height > 0 and taper_inset > 0
    if not has_taper:
        with BuildPart() as stud:
            Cylinder(radius, total_height,
                     align=(Align.CENTER, Align.CENTER, Align.MIN))
        return stud.part

    th = min(taper_height, total_height)
    taper_start_z = total_height - th
    top_radius = max(radius - taper_inset, 0.01)

    with BuildPart() as stud:
        with BuildSketch(Plane.XY):
            Circle(radius)
        if taper_start_z > 0.01:
            with BuildSketch(Plane.XY.offset(taper_start_z)):
                Circle(radius)
        if taper_curve == "CURVED":
            for i in range(1, _CURVED_TAPER_STEPS):
                t = i / _CURVED_TAPER_STEPS
                z = taper_start_z + th * t
                r = radius - taper_inset * _taper_profile(t, "CURVED")
                with BuildSketch(Plane.XY.offset(z)):
                    Circle(max(r, 0.01))
        with BuildSketch(Plane.XY.offset(total_height)):
            Circle(top_radius)
        loft(ruled=True)
    return stud.part


# ── Clutch builders ──────────────────────────────────────────────────────────

def _build_lattice(studs_x, studs_y, inner_x, inner_y, cavity_z):
    """
    Pure function, specific. Build diagonal lattice struts as a standalone Part.

    +/-45 deg crisscross struts forming diamond openings. Each diamond's
    inscribed circle = STUD_DIAMETER for exact stud fit.

    Args:
        studs_x (int): Studs along X.
        studs_y (int): Studs along Y.
        inner_x (float): Inner cavity width.
        inner_y (float): Inner cavity height.
        cavity_z (float): Cavity height (extrusion depth).

    Returns:
        Part: Lattice geometry, origin at (0, 0, 0).

    Examples:
        >>> # _build_lattice(2, 4, 12.8, 28.8, 8.6)
    """
    strut_thickness = PITCH / math.sqrt(2) - STUD_DIAMETER
    n_struts = studs_x + studs_y
    strut_len = (inner_x + inner_y) * 2
    c_start = -(n_struts - 1) / 2 * PITCH
    c_values = [c_start + i * PITCH for i in range(n_struts)]

    with BuildPart() as lattice:
        with BuildSketch():
            for c in c_values:
                with Locations([Pos(-c / 2, c / 2) * Rot(0, 0, 45)]):
                    Rectangle(strut_len, strut_thickness)
                with Locations([Pos(c / 2, c / 2) * Rot(0, 0, -45)]):
                    Rectangle(strut_len, strut_thickness)
            Rectangle(inner_x, inner_y, mode=Mode.INTERSECT)
        extrude(amount=cavity_z)
    return lattice.part


def _build_tubes(studs_x, studs_y, cavity_z):
    """
    Pure function, specific. Build LEGO-style anti-stud tubes as a standalone Part.

    Tubes are placed at the center of each 2x2 stud group — the (N-1)x(M-1) grid.
    Requires studs_x >= 2 and studs_y >= 2.

    Args:
        studs_x (int): Studs along X.
        studs_y (int): Studs along Y.
        cavity_z (float): Cavity height (extrusion depth).

    Returns:
        Part or None: Tube geometry, or None if brick is too small for tubes.

    Examples:
        >>> # _build_tubes(2, 4, 8.6)  -> 3 tubes
        >>> # _build_tubes(1, 4, 8.6)  -> None (1-wide)
    """
    if studs_x < 2 or studs_y < 2:
        return None
    with BuildPart() as tb:
        with BuildSketch():
            with GridLocations(PITCH, PITCH, studs_x - 1, studs_y - 1):
                Circle(TUBE_OUTER_RADIUS)
                Circle(TUBE_INNER_RADIUS, mode=Mode.SUBTRACT)
        extrude(amount=cavity_z)
    return tb.part


def _build_ridge(studs_x, studs_y, cavity_z):
    """
    Pure function, specific. Build bottom ridge rail for 1-wide bricks.

    Only created when min(studs_x, studs_y) == 1 and max >= 2.

    Args:
        studs_x (int): Studs along X.
        studs_y (int): Studs along Y.
        cavity_z (float): Cavity height.

    Returns:
        Part or None: Ridge geometry, or None if not applicable.

    Examples:
        >>> # _build_ridge(1, 4, 8.6)  -> ridge along Y
        >>> # _build_ridge(2, 4, 8.6)  -> None (not 1-wide)
    """
    if min(studs_x, studs_y) != 1 or max(studs_x, studs_y) < 2:
        return None
    ridge_len = (max(studs_x, studs_y) - 1) * PITCH
    rx, ry = (RIDGE_WIDTH, ridge_len) if studs_x == 1 else (ridge_len, RIDGE_WIDTH)
    with BuildPart() as rp:
        Pos(0, 0, cavity_z - RIDGE_HEIGHT) * Box(rx, ry, RIDGE_HEIGHT,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
    return rp.part


# ── Shell builders ───────────────────────────────────────────────────────────

def _build_outer_shell(outer_x, outer_y, height, corner_radius=0,
                       taper_height=0, taper_inset=0, taper_curve="LINEAR"):
    """
    Pure function, specific. Build the outer shell solid (no cavity yet).

    Three-branch construction: taper → loft, corner_radius → rounded extrude,
    else → Box (fastest).

    Args:
        outer_x (float): Outer width.
        outer_y (float): Outer depth.
        height (float): Body height.
        corner_radius (float): 2D corner rounding (mm). 0 = sharp.
        taper_height (float): Wall taper height (mm). 0 = no taper.
        taper_inset (float): Wall taper inset (mm). 0 = no taper.
        taper_curve (str): "LINEAR" or "CURVED".

    Returns:
        Part: Outer shell solid.

    Examples:
        >>> # _build_outer_shell(15.6, 31.6, 9.6)  -> sharp box
        >>> # _build_outer_shell(15.6, 31.6, 9.6, corner_radius=2.0)  -> rounded
    """
    cr = _clamp_cr(corner_radius, outer_x, outer_y)
    has_taper = taper_height > 0 and taper_inset > 0
    top_x = outer_x - 2 * taper_inset if has_taper else outer_x
    top_y = outer_y - 2 * taper_inset if has_taper else outer_y
    top_cr = _clamp_cr(cr, top_x, top_y)

    with BuildPart() as shell:
        if has_taper:
            taper_start_z = height - taper_height
            with BuildSketch(Plane.XY):
                _rounded_rect(outer_x, outer_y, cr)
            with BuildSketch(Plane.XY.offset(taper_start_z)):
                _rounded_rect(outer_x, outer_y, cr)
            if taper_curve == "CURVED":
                for i in range(1, _CURVED_TAPER_STEPS):
                    t = i / _CURVED_TAPER_STEPS
                    z = taper_start_z + taper_height * t
                    inset = taper_inset * _taper_profile(t, "CURVED")
                    w = outer_x - 2 * inset
                    h_dim = outer_y - 2 * inset
                    r = _clamp_cr(cr, w, h_dim)
                    with BuildSketch(Plane.XY.offset(z)):
                        _rounded_rect(w, h_dim, r)
            with BuildSketch(Plane.XY.offset(height)):
                _rounded_rect(top_x, top_y, top_cr)
            loft(ruled=True)
        elif cr > 0:
            with BuildSketch():
                _rounded_rect(outer_x, outer_y, cr)
            extrude(amount=height)
        else:
            Box(outer_x, outer_y, height,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
    return shell.part


# ── Cross-shape helpers ──────────────────────────────────────────────────────

def _cross_stud_positions(plus_x, minus_x, plus_y, minus_y, width_x, width_y):
    """
    Pure function, general. Return list of (x, y) world positions for studs
    within a cross-shaped footprint.

    The cross is the union of:
      - Horizontal bar: X from -minus_x to (width_x - 1 + plus_x), Y from 0 to width_y - 1
      - Vertical bar: X from 0 to width_x - 1, Y from -minus_y to (width_y - 1 + plus_y)

    Grid positions are integer (i, j) indices. The center block spans
    (0..width_x-1) x (0..width_y-1). Positions are converted to world coords
    by centering on the footprint bounding box and scaling by PITCH.

    Args:
        plus_x (int): Arm length in +X direction (studs beyond center block).
        minus_x (int): Arm length in -X direction.
        plus_y (int): Arm length in +Y direction.
        minus_y (int): Arm length in -Y direction.
        width_x (int): Width of Y-axis arms in X (>= 1).
        width_y (int): Width of X-axis arms in Y (>= 1).

    Returns:
        list[tuple[float, float]]: (x, y) world positions.

    Examples:
        >>> len(_cross_stud_positions(0, 0, 0, 0, 1, 1))
        1
        >>> len(_cross_stud_positions(1, 1, 1, 1, 1, 1))
        5
    """
    positions = set()
    # Horizontal bar
    for i in range(-minus_x, width_x + plus_x):
        for j in range(width_y):
            positions.add((i, j))
    # Vertical bar
    for i in range(width_x):
        for j in range(-minus_y, width_y + plus_y):
            positions.add((i, j))

    # Compute bounding box to center the footprint
    all_i = [p[0] for p in positions]
    all_j = [p[1] for p in positions]
    center_i = (min(all_i) + max(all_i)) / 2
    center_j = (min(all_j) + max(all_j)) / 2

    return [((i - center_i) * PITCH, (j - center_j) * PITCH)
            for i, j in positions]


def _cross_tube_positions(plus_x, minus_x, plus_y, minus_y, width_x, width_y):
    """
    Pure function, general. Return list of (x, y) world positions for tubes
    within a cross-shaped footprint.

    Tube positions are at the center of each 2x2 stud group. A tube at grid
    (i, j) requires all four surrounding stud positions (i, j), (i+1, j),
    (i, j+1), (i+1, j+1) to exist in the footprint.

    Args:
        plus_x (int): Arm length in +X direction.
        minus_x (int): Arm length in -X direction.
        plus_y (int): Arm length in +Y direction.
        minus_y (int): Arm length in -Y direction.
        width_x (int): Width of Y-axis arms in X (>= 1).
        width_y (int): Width of X-axis arms in Y (>= 1).

    Returns:
        list[tuple[float, float]]: (x, y) world positions for tubes.

    Examples:
        >>> len(_cross_tube_positions(0, 0, 0, 0, 1, 1))
        0
        >>> len(_cross_tube_positions(1, 1, 1, 1, 1, 1))
        0
        >>> len(_cross_tube_positions(0, 0, 0, 0, 2, 2))
        1
    """
    # Build set of all stud grid positions
    stud_set = set()
    for i in range(-minus_x, width_x + plus_x):
        for j in range(width_y):
            stud_set.add((i, j))
    for i in range(width_x):
        for j in range(-minus_y, width_y + plus_y):
            stud_set.add((i, j))

    # Tube at (i+0.5, j+0.5) requires 4 surrounding studs
    tube_grid = []
    all_i = [p[0] for p in stud_set]
    all_j = [p[1] for p in stud_set]
    for i in range(min(all_i), max(all_i)):
        for j in range(min(all_j), max(all_j)):
            if all(pos in stud_set for pos in
                   [(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)]):
                tube_grid.append((i + 0.5, j + 0.5))

    # Center on footprint bounding box
    center_i = (min(all_i) + max(all_i)) / 2
    center_j = (min(all_j) + max(all_j)) / 2

    return [((i - center_i) * PITCH, (j - center_j) * PITCH)
            for i, j in tube_grid]


def _cross_footprint_dims(plus_x, minus_x, plus_y, minus_y, width_x, width_y):
    """
    Pure function, general. Compute the bounding box dimensions and bar
    dimensions of a cross-shaped footprint.

    Returns:
        dict: Keys: total_x, total_y (bounding box in studs),
              h_bar_x, h_bar_y, v_bar_x, v_bar_y (bar dimensions in studs).

    Examples:
        >>> d = _cross_footprint_dims(1, 1, 1, 1, 1, 1)
        >>> d['total_x'], d['total_y']
        (3, 3)
    """
    total_x = minus_x + width_x + plus_x
    total_y = minus_y + width_y + plus_y
    return {
        "total_x": total_x,
        "total_y": total_y,
        "h_bar_x": total_x,
        "h_bar_y": width_y,
        "v_bar_x": width_x,
        "v_bar_y": total_y,
    }


def _cross_concave_vertices(sketch, v_w, h_h):
    """
    Pure function, specific. Identify concave (reentrant) vertices in a cross sketch.

    Concave vertices are at the inner corners where arms meet — they sit at the
    junction box coordinates (±v_w/2, ±h_h/2) where v_w is the vertical bar width
    and h_h is the horizontal bar height.

    Args:
        sketch (BuildSketch): The cross-shaped sketch.
        v_w (float): Vertical bar width (determines X of junction corners).
        h_h (float): Horizontal bar height (determines Y of junction corners).

    Returns:
        tuple[list[Vertex], list[Vertex]]: (convex_vertices, concave_vertices).

    Examples:
        >>> # convex, concave = _cross_concave_vertices(sk, 7.8, 7.8)
        >>> # len(concave)  -> 4 for a + shape
    """
    jx = v_w / 2
    jy = h_h / 2
    convex = []
    concave = []
    for v in sketch.vertices():
        at_jx = abs(abs(v.X) - jx) < 0.01
        at_jy = abs(abs(v.Y) - jy) < 0.01
        if at_jx and at_jy:
            concave.append(v)
        else:
            convex.append(v)
    return convex, concave


def _build_cross_shell(plus_x, minus_x, plus_y, minus_y, width_x, width_y,
                       height, corner_radius=0, cr_skip_concave=True,
                       taper_height=0, taper_inset=0, taper_curve="LINEAR"):
    """
    Pure function, specific. Build the outer shell for a cross-shaped brick.

    Union of two rectangular bars (horizontal and vertical), extruded to height.
    When corner_radius > 0, convex corners are filleted in 2D before extrusion.
    Concave (reentrant) corners are filleted only if cr_skip_concave is False.
    Taper is NOT supported for cross shapes.

    Args:
        plus_x, minus_x, plus_y, minus_y (int): Arm lengths.
        width_x, width_y (int): Arm widths in studs.
        height (float): Body height.
        corner_radius (float): 2D corner rounding radius. 0 = sharp.
        cr_skip_concave (bool): Skip concave (reentrant) corners. Default True.
        taper_height (float): Ignored for cross shapes.
        taper_inset (float): Ignored for cross shapes.
        taper_curve (str): Ignored for cross shapes.

    Returns:
        Part: Outer shell solid (no cavity).

    Examples:
        >>> # _build_cross_shell(1, 1, 1, 1, 1, 1, 9.6)  -> + shape
        >>> # _build_cross_shell(1, 1, 1, 1, 1, 1, 9.6, corner_radius=2.0)
    """
    dims = _cross_footprint_dims(plus_x, minus_x, plus_y, minus_y,
                                 width_x, width_y)
    h_w = dims["h_bar_x"] * PITCH - 2 * CLEARANCE
    h_h = dims["h_bar_y"] * PITCH - 2 * CLEARANCE
    v_w = dims["v_bar_x"] * PITCH - 2 * CLEARANCE
    v_h = dims["v_bar_y"] * PITCH - 2 * CLEARANCE

    # Offsets of each bar center from BBox center
    h_offset_y = (minus_y - plus_y) / 2 * PITCH
    v_offset_x = (minus_x - plus_x) / 2 * PITCH

    cr = _clamp_cr(corner_radius, min(h_w, v_w), min(h_h, v_h)) if corner_radius > 0 else 0

    if cr > 0:
        # 2D sketch approach: union of two rectangles, fillet selected vertices
        with BuildPart() as shell:
            with BuildSketch() as sk:
                with Locations([Pos(0, h_offset_y)]):
                    Rectangle(h_w, h_h)
                with Locations([Pos(v_offset_x, 0)]):
                    Rectangle(v_w, v_h, mode=Mode.ADD)

                convex, concave = _cross_concave_vertices(sk, v_w, h_h)
                # Always fillet convex corners
                if convex:
                    bd_fillet(convex, radius=cr)
                # Fillet concave only if cr_skip_concave is False
                if concave and not cr_skip_concave:
                    bd_fillet(concave, radius=cr)
            extrude(amount=height)
        return shell.part

    # No corner radius: fast Box union
    with BuildPart() as shell:
        Pos(0, h_offset_y, 0) * Box(h_w, h_h, height,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
        Pos(v_offset_x, 0, 0) * Box(v_w, v_h, height,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
    return shell.part


def _build_cross_cavity(plus_x, minus_x, plus_y, minus_y, width_x, width_y,
                        cavity_z):
    """
    Pure function, specific. Build the cavity for a cross-shaped brick.

    Same cross shape as outer shell but inset by WALL_THICKNESS on each side.
    Each bar is independently inset (sharp inner corners at the junction).

    Args:
        plus_x, minus_x, plus_y, minus_y (int): Arm lengths.
        width_x, width_y (int): Arm widths in studs.
        cavity_z (float): Cavity height.

    Returns:
        Part: Cavity solid to be subtracted from the shell.

    Examples:
        >>> # _build_cross_cavity(1, 1, 1, 1, 1, 1, 8.6)
    """
    dims = _cross_footprint_dims(plus_x, minus_x, plus_y, minus_y,
                                 width_x, width_y)
    wt = WALL_THICKNESS
    h_w = dims["h_bar_x"] * PITCH - 2 * CLEARANCE - 2 * wt
    h_h = dims["h_bar_y"] * PITCH - 2 * CLEARANCE - 2 * wt
    v_w = dims["v_bar_x"] * PITCH - 2 * CLEARANCE - 2 * wt
    v_h = dims["v_bar_y"] * PITCH - 2 * CLEARANCE - 2 * wt

    h_offset_y = (minus_y - plus_y) / 2 * PITCH
    v_offset_x = (minus_x - plus_x) / 2 * PITCH

    # Only add bars with positive dimensions
    parts = []
    with BuildPart() as cav:
        if h_w > 0 and h_h > 0:
            Pos(0, h_offset_y, 0) * Box(h_w, h_h, cavity_z,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
        if v_w > 0 and v_h > 0:
            Pos(v_offset_x, 0, 0) * Box(v_w, v_h, cavity_z,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
    return cav.part


# ── Slope plane helpers ──────────────────────────────────────────────────────

def _slope_planes(direction, outer_x, outer_y, height, flat_rows, slope_min_z):
    """
    Pure function, general. Compute cut plane and cavity cut plane for a slope
    in the given direction.

    Args:
        direction (str): "+Y", "-Y", "+X", "-X".
        outer_x (float): Outer shell width.
        outer_y (float): Outer shell depth.
        height (float): Brick height.
        flat_rows (int): Number of flat stud rows before slope begins.
        slope_min_z (float): Z height where slope terminates (bottom).

    Returns:
        tuple[Plane, Plane]: (cut_plane, cavity_cut_plane).

    Examples:
        >>> # _slope_planes("+Y", 15.6, 31.6, 9.6, 1, 1.5)
    """
    half_x = outer_x / 2
    half_y = outer_y / 2

    if direction == "+Y":
        hinge = -half_y + flat_rows * PITCH
        span = half_y - hinge
        dz = height - slope_min_z
        normal = (0, dz, span)
        origin = (0, hinge, height)
        x_dir = (1, 0, 0)
    elif direction == "-Y":
        hinge = half_y - flat_rows * PITCH
        span = hinge - (-half_y)
        dz = height - slope_min_z
        normal = (0, -dz, span)
        origin = (0, hinge, height)
        x_dir = (-1, 0, 0)
    elif direction == "+X":
        hinge = -half_x + flat_rows * PITCH
        span = half_x - hinge
        dz = height - slope_min_z
        normal = (dz, 0, span)
        origin = (hinge, 0, height)
        x_dir = (0, 1, 0)
    elif direction == "-X":
        hinge = half_x - flat_rows * PITCH
        span = hinge - (-half_x)
        dz = height - slope_min_z
        normal = (-dz, 0, span)
        origin = (hinge, 0, height)
        x_dir = (0, -1, 0)
    else:
        raise ValueError(f"Unknown slope direction: {direction}")

    cut_plane = Plane(origin=origin, x_dir=x_dir, z_dir=normal)

    # Cavity cut plane: offset FLOOR_THICKNESS inward along slope normal
    nx, ny, nz = normal
    normal_mag = math.sqrt(nx**2 + ny**2 + nz**2)
    ox, oy, oz = origin
    cavity_origin = (
        ox - FLOOR_THICKNESS * nx / normal_mag,
        oy - FLOOR_THICKNESS * ny / normal_mag,
        oz - FLOOR_THICKNESS * nz / normal_mag,
    )
    cavity_cut_plane = Plane(origin=cavity_origin, x_dir=x_dir, z_dir=normal)

    return cut_plane, cavity_cut_plane


# ── Main geometry functions ──────────────────────────────────────────────────

def brick(studs_x, studs_y, height=BRICK_HEIGHT,
          clutch="LATTICE",
          corner_radius=0, cr_skip_concave=True,
          taper_height=0, taper_inset=0, taper_curve="LINEAR",
          stud_taper_height=0, stud_taper_inset=0, stud_taper_curve="LINEAR",
          shape_mode="RECTANGLE",
          plus_x=0, minus_x=0, plus_y=0, minus_y=0,
          cross_width_x=1, cross_width_y=1):
    """
    Pure function, specific. Create a brick with configurable clutch and shape.

    Shell → clutch internals → studs → fillet → text.

    Args:
        studs_x (int): Studs along X (RECTANGLE mode only).
        studs_y (int): Studs along Y (RECTANGLE mode only).
        height (float): Body height.
        clutch (str): "TUBE", "LATTICE", or "NONE".
        corner_radius (float): 2D corner rounding (mm). 0 = sharp.
        cr_skip_concave (bool): Skip concave corners on cross shapes. Default True.
        taper_height (float): Wall taper height (mm). 0 = no taper.
        taper_inset (float): Wall taper inset (mm). 0 = no taper.
        taper_curve (str): "LINEAR" or "CURVED".
        stud_taper_height (float): Stud taper height (mm). 0 = no taper.
        stud_taper_inset (float): Stud taper inset (mm). 0 = no taper.
        stud_taper_curve (str): "LINEAR" or "CURVED".
        shape_mode (str): "RECTANGLE" or "CROSS".
        plus_x, minus_x, plus_y, minus_y (int): Cross arm lengths (CROSS only).
        cross_width_x, cross_width_y (int): Cross arm widths (CROSS only).

    Returns:
        Part: Complete brick.

    Examples:
        >>> # brick(2, 4) -> 2x4 lattice brick
        >>> # brick(2, 4, clutch="TUBE") -> 2x4 LEGO-style brick
        >>> # brick(2, 4, corner_radius=2.0) -> rounded corners
        >>> # brick(0, 0, shape_mode="CROSS", plus_x=3, plus_y=3) -> L-shape
    """
    is_cross = shape_mode == "CROSS"

    if is_cross:
        return _brick_cross(height, clutch, plus_x, minus_x, plus_y, minus_y,
                            cross_width_x, cross_width_y, corner_radius,
                            cr_skip_concave,
                            stud_taper_height, stud_taper_inset, stud_taper_curve)

    # ── RECTANGLE mode ──
    outer_x = studs_x * PITCH - 2 * CLEARANCE
    outer_y = studs_y * PITCH - 2 * CLEARANCE
    inner_x = outer_x - 2 * WALL_THICKNESS
    inner_y = outer_y - 2 * WALL_THICKNESS
    cavity_z = height - FLOOR_THICKNESS

    # Fillet Z threshold: LATTICE edges too thin for OCCT → fillet above cavity only
    fillet_z = cavity_z if clutch == "LATTICE" else 0.0

    with BuildPart() as bp:
        # Outer shell
        add(_build_outer_shell(outer_x, outer_y, height,
                               corner_radius, taper_height, taper_inset, taper_curve))
        # Cavity
        Box(inner_x, inner_y, cavity_z,
            align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

        # Clutch internals
        if clutch == "TUBE":
            tubes = _build_tubes(studs_x, studs_y, cavity_z)
            if tubes:
                add(tubes)
            ridge = _build_ridge(studs_x, studs_y, cavity_z)
            if ridge:
                add(ridge)
        elif clutch == "LATTICE":
            add(_build_lattice(studs_x, studs_y, inner_x, inner_y, cavity_z))

        # Studs
        if ENABLE_STUDS:
            has_stud_taper = stud_taper_height > 0 and stud_taper_inset > 0
            if has_stud_taper:
                stud = _build_stud(STUD_RADIUS, STUD_HEIGHT,
                                   stud_taper_height, stud_taper_inset, stud_taper_curve)
                with Locations([Pos(0, 0, height)]):
                    with GridLocations(PITCH, PITCH, studs_x, studs_y):
                        add(stud)
            else:
                with Locations([Pos(0, 0, height)]):
                    with GridLocations(PITCH, PITCH, studs_x, studs_y):
                        Cylinder(STUD_RADIUS, STUD_HEIGHT,
                                 align=(Align.CENTER, Align.CENTER, Align.MIN))

    result = bp.part
    if ENABLE_FILLET:
        result = bevel_above_z(result, FILLET_RADIUS, z_threshold=fillet_z,
                               style=EDGE_STYLE, include_bottom=FILLET_BOTTOM,
                               skip_concave=SKIP_CONCAVE)

    if not ENABLE_TEXT or not ENABLE_STUDS:
        return result

    with BuildPart() as final:
        add(result)
        with BuildSketch(Plane.XY.offset(height + STUD_HEIGHT)):
            with GridLocations(PITCH, PITCH, studs_x, studs_y):
                Text(STUD_TEXT, font_size=STUD_TEXT_FONT_SIZE,
                     font=STUD_TEXT_FONT, font_style=FontStyle.BOLD,
                     rotation=STUD_TEXT_ROTATION,
                     align=(Align.CENTER, Align.CENTER))
        extrude(amount=STUD_TEXT_HEIGHT)
    return final.part


def _brick_cross(height, clutch, plus_x, minus_x, plus_y, minus_y,
                 width_x, width_y, corner_radius=0, cr_skip_concave=True,
                 stud_taper_height=0, stud_taper_inset=0, stud_taper_curve="LINEAR"):
    """
    Pure function, specific. Build a cross-shaped brick.

    Args:
        height (float): Body height.
        clutch (str): "TUBE", "LATTICE", or "NONE".
        plus_x, minus_x, plus_y, minus_y (int): Arm lengths.
        width_x, width_y (int): Arm widths.
        corner_radius (float): 2D corner rounding radius.
        cr_skip_concave (bool): Skip concave corners in corner radius. Default True.
        stud_taper_height, stud_taper_inset (float): Stud taper params.
        stud_taper_curve (str): Stud taper curve type.

    Returns:
        Part: Complete cross-shaped brick.

    Examples:
        >>> # _brick_cross(9.6, "LATTICE", 3, 0, 3, 0, 1, 1)  -> L-shape
    """
    dims = _cross_footprint_dims(plus_x, minus_x, plus_y, minus_y,
                                 width_x, width_y)
    cavity_z = height - FLOOR_THICKNESS
    fillet_z = cavity_z if clutch == "LATTICE" else 0.0

    outer_shell = _build_cross_shell(plus_x, minus_x, plus_y, minus_y,
                                     width_x, width_y, height,
                                     corner_radius=corner_radius,
                                     cr_skip_concave=cr_skip_concave)
    cavity = _build_cross_cavity(plus_x, minus_x, plus_y, minus_y,
                                 width_x, width_y, cavity_z)

    stud_positions = _cross_stud_positions(plus_x, minus_x, plus_y, minus_y,
                                           width_x, width_y)

    with BuildPart() as bp:
        add(outer_shell)
        add(cavity, mode=Mode.SUBTRACT)

        # Clutch internals
        if clutch == "TUBE":
            tube_positions = _cross_tube_positions(plus_x, minus_x, plus_y, minus_y,
                                                   width_x, width_y)
            if tube_positions:
                with BuildPart() as tb:
                    with BuildSketch():
                        with Locations([Pos(x, y) for x, y in tube_positions]):
                            Circle(TUBE_OUTER_RADIUS)
                            Circle(TUBE_INNER_RADIUS, mode=Mode.SUBTRACT)
                    extrude(amount=cavity_z)
                add(tb.part)
        elif clutch == "LATTICE":
            # Build lattice using equivalent studs_x/studs_y from total dims
            # Lattice clipped to cross-shaped cavity
            sx, sy = dims["total_x"], dims["total_y"]
            inner_x = sx * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
            inner_y = sy * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
            if inner_x > 0 and inner_y > 0:
                lattice = _build_lattice(sx, sy, inner_x, inner_y, cavity_z)
                clipped = lattice & cavity
                add(clipped)

        # Studs
        if ENABLE_STUDS:
            has_stud_taper = stud_taper_height > 0 and stud_taper_inset > 0
            if has_stud_taper:
                stud = _build_stud(STUD_RADIUS, STUD_HEIGHT,
                                   stud_taper_height, stud_taper_inset, stud_taper_curve)
                with Locations([Pos(x, y, height) for x, y in stud_positions]):
                    add(stud)
            else:
                with Locations([Pos(x, y, height) for x, y in stud_positions]):
                    Cylinder(STUD_RADIUS, STUD_HEIGHT,
                             align=(Align.CENTER, Align.CENTER, Align.MIN))

    result = bp.part
    if ENABLE_FILLET:
        try:
            result = bevel_above_z(result, FILLET_RADIUS, z_threshold=fillet_z,
                                   style=EDGE_STYLE, include_bottom=FILLET_BOTTOM,
                                   skip_concave=SKIP_CONCAVE)
        except ValueError:
            pass  # Cross shapes may have edges too small for OCCT filleter

    if not ENABLE_TEXT or not ENABLE_STUDS:
        return result

    with BuildPart() as final:
        add(result)
        with BuildSketch(Plane.XY.offset(height + STUD_HEIGHT)):
            with Locations([Pos(x, y) for x, y in stud_positions]):
                Text(STUD_TEXT, font_size=STUD_TEXT_FONT_SIZE,
                     font=STUD_TEXT_FONT, font_style=FontStyle.BOLD,
                     rotation=STUD_TEXT_ROTATION,
                     align=(Align.CENTER, Align.CENTER))
        extrude(amount=STUD_TEXT_HEIGHT)
    return final.part


def slope(studs_x, studs_y, height=BRICK_HEIGHT,
          clutch="LATTICE",
          corner_radius=0, cr_skip_concave=True,
          taper_height=0, taper_inset=0, taper_curve="LINEAR",
          stud_taper_height=0, stud_taper_inset=0, stud_taper_curve="LINEAR",
          slope_plus_y=0, slope_minus_y=0, slope_plus_x=0, slope_minus_x=0,
          slope_min_z=WALL_THICKNESS,
          shape_mode="RECTANGLE",
          plus_x=0, minus_x=0, plus_y=0, minus_y=0,
          cross_width_x=1, cross_width_y=1):
    """
    Pure function, specific. Create a slope brick with configurable clutch,
    shape, and 4-directional slopes.

    Build order (critical — prevents exposed cavity):
        1. Outer shell → split by ALL slope planes
        2. Cavity → split by ALL offset slope planes
        3. Shell = sloped_outer - sloped_cavity
        4. Clutch internals → clip to sloped_cavity via &
        5. Studs on flat portion only
        6. Fillet → text

    Args:
        studs_x, studs_y (int): Studs (RECTANGLE mode).
        height (float): Body height.
        clutch (str): "TUBE", "LATTICE", or "NONE".
        corner_radius, taper_height, taper_inset, taper_curve: Shell shape params.
        stud_taper_height, stud_taper_inset, stud_taper_curve: Stud taper params.
        slope_plus_y (int): Sloped rows in +Y direction. 0 = no slope.
        slope_minus_y (int): Sloped rows in -Y direction.
        slope_plus_x (int): Sloped rows in +X direction.
        slope_minus_x (int): Sloped rows in -X direction.
        slope_min_z (float): Z height where slopes terminate.
        shape_mode (str): "RECTANGLE" or "CROSS".
        plus_x, minus_x, plus_y, minus_y (int): Cross arm lengths (CROSS only).
        cross_width_x, cross_width_y (int): Cross arm widths (CROSS only).

    Returns:
        Part: Complete slope brick.

    Examples:
        >>> # slope(2, 4, slope_plus_y=3) -> 2x4 slope, 3 sloped rows in +Y
        >>> # slope(2, 4, slope_plus_y=3, slope_minus_x=3) -> corner roof
    """
    is_cross = shape_mode == "CROSS"

    # Determine total rows per axis for sloped→flat conversion
    if is_cross:
        dims = _cross_footprint_dims(plus_x, minus_x, plus_y, minus_y,
                                     cross_width_x, cross_width_y)
        rows_x, rows_y = dims["total_x"], dims["total_y"]
    else:
        rows_x, rows_y = studs_x, studs_y

    # Collect active slopes, converting sloped_rows → flat_rows
    active_slopes = []
    if slope_plus_y > 0:
        active_slopes.append(("+Y", rows_y - slope_plus_y))
    if slope_minus_y > 0:
        active_slopes.append(("-Y", rows_y - slope_minus_y))
    if slope_plus_x > 0:
        active_slopes.append(("+X", rows_x - slope_plus_x))
    if slope_minus_x > 0:
        active_slopes.append(("-X", rows_x - slope_minus_x))

    if not active_slopes:
        # No slopes active — just build a regular brick
        return brick(studs_x, studs_y, height, clutch,
                     corner_radius, cr_skip_concave,
                     taper_height, taper_inset, taper_curve,
                     stud_taper_height, stud_taper_inset, stud_taper_curve,
                     shape_mode, plus_x, minus_x, plus_y, minus_y,
                     cross_width_x, cross_width_y)

    if is_cross:
        return _slope_cross(height, clutch, active_slopes, slope_min_z,
                            plus_x, minus_x, plus_y, minus_y,
                            cross_width_x, cross_width_y,
                            corner_radius=corner_radius,
                            cr_skip_concave=cr_skip_concave,
                            stud_taper_height=stud_taper_height,
                            stud_taper_inset=stud_taper_inset,
                            stud_taper_curve=stud_taper_curve)

    # ── RECTANGLE slope ──
    outer_x = studs_x * PITCH - 2 * CLEARANCE
    outer_y = studs_y * PITCH - 2 * CLEARANCE
    inner_x = outer_x - 2 * WALL_THICKNESS
    inner_y = outer_y - 2 * WALL_THICKNESS
    cavity_z = height - FLOOR_THICKNESS
    fillet_z = cavity_z if clutch == "LATTICE" else 0.0

    # Compute all slope planes
    cut_planes = []
    cavity_cut_planes = []
    for direction, flat_rows in active_slopes:
        cp, ccp = _slope_planes(direction, outer_x, outer_y, height,
                                flat_rows, slope_min_z)
        cut_planes.append(cp)
        cavity_cut_planes.append(ccp)

    # Build and cut outer shell
    outer = _build_outer_shell(outer_x, outer_y, height,
                               corner_radius, taper_height, taper_inset, taper_curve)
    sloped_outer = outer
    for cp in cut_planes:
        sloped_outer = split(sloped_outer, bisect_by=cp, keep=Keep.BOTTOM)

    # Build and cut cavity
    cavity = Box(inner_x, inner_y, cavity_z,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    sloped_cavity = cavity
    for ccp in cavity_cut_planes:
        sloped_cavity = split(sloped_cavity, bisect_by=ccp, keep=Keep.BOTTOM)

    shell = sloped_outer - sloped_cavity

    # Clutch internals clipped to sloped cavity
    clipped_clutch = None
    if clutch == "TUBE":
        tubes = _build_tubes(studs_x, studs_y, cavity_z)
        if tubes:
            clipped_clutch = tubes & sloped_cavity
    elif clutch == "LATTICE":
        lattice = _build_lattice(studs_x, studs_y, inner_x, inner_y, cavity_z)
        clipped_clutch = lattice & sloped_cavity

    # Determine flat stud positions
    flat_xy = _flat_stud_positions_rect(studs_x, studs_y, outer_x, outer_y,
                                        height, active_slopes, slope_min_z)

    # Assemble
    with BuildPart() as bp:
        add(shell)
        if clipped_clutch:
            add(clipped_clutch)
        if clutch == "TUBE":
            ridge = _build_ridge(studs_x, studs_y, cavity_z)
            if ridge:
                add(ridge)

        # Studs on flat portion
        if ENABLE_STUDS:
            has_stud_taper = stud_taper_height > 0 and stud_taper_inset > 0
            if flat_xy:
                if has_stud_taper:
                    stud = _build_stud(STUD_RADIUS, STUD_HEIGHT,
                                       stud_taper_height, stud_taper_inset,
                                       stud_taper_curve)
                    with Locations([Pos(x, y, height) for x, y in flat_xy]):
                        add(stud)
                else:
                    with Locations([Pos(x, y, height) for x, y in flat_xy]):
                        Cylinder(STUD_RADIUS, STUD_HEIGHT,
                                 align=(Align.CENTER, Align.CENTER, Align.MIN))

    result = bp.part
    if ENABLE_FILLET:
        try:
            result = bevel_above_z(result, FILLET_RADIUS, z_threshold=fillet_z,
                                   style=EDGE_STYLE, include_bottom=FILLET_BOTTOM,
                                   skip_concave=SKIP_CONCAVE)
        except ValueError:
            pass  # Fillet failure on slopes is a known OCCT limitation

    if not ENABLE_TEXT or not ENABLE_STUDS or not flat_xy:
        return result

    with BuildPart() as final:
        add(result)
        with BuildSketch(Plane.XY.offset(height + STUD_HEIGHT)):
            with Locations([Pos(x, y) for x, y in flat_xy]):
                Text(STUD_TEXT, font_size=STUD_TEXT_FONT_SIZE,
                     font=STUD_TEXT_FONT, font_style=FontStyle.BOLD,
                     rotation=STUD_TEXT_ROTATION,
                     align=(Align.CENTER, Align.CENTER))
        extrude(amount=STUD_TEXT_HEIGHT)
    return final.part


def _flat_stud_positions_rect(studs_x, studs_y, outer_x, outer_y,
                              height, active_slopes, slope_min_z):
    """
    Pure function, specific. Compute which stud positions are on the flat deck
    for a rectangular slope brick with multiple active slopes.

    A stud is flat if it's on the non-sloped side of every active slope's hinge.

    Args:
        studs_x, studs_y (int): Stud counts.
        outer_x, outer_y (float): Outer dimensions.
        height (float): Brick height.
        active_slopes (list[tuple]): List of (direction, flat_rows) tuples.
        slope_min_z (float): Where slopes terminate.

    Returns:
        list[tuple[float, float]]: (x, y) positions for flat studs.

    Examples:
        >>> # _flat_stud_positions_rect(2, 4, 15.6, 31.6, 9.6, [("+Y", 1)], 1.5)
    """
    half_x = outer_x / 2
    half_y = outer_y / 2

    # Generate all stud positions
    all_xy = [((i - (studs_x - 1) / 2) * PITCH,
               (j - (studs_y - 1) / 2) * PITCH)
              for i in range(studs_x) for j in range(studs_y)]

    flat = []
    for x, y in all_xy:
        is_flat = True
        for direction, flat_rows in active_slopes:
            if direction == "+Y":
                hinge_y = -half_y + flat_rows * PITCH
                if y > hinge_y - PITCH / 2 + 0.01:
                    is_flat = False
            elif direction == "-Y":
                hinge_y = half_y - flat_rows * PITCH
                if y < hinge_y + PITCH / 2 - 0.01:
                    is_flat = False
            elif direction == "+X":
                hinge_x = -half_x + flat_rows * PITCH
                if x > hinge_x - PITCH / 2 + 0.01:
                    is_flat = False
            elif direction == "-X":
                hinge_x = half_x - flat_rows * PITCH
                if x < hinge_x + PITCH / 2 - 0.01:
                    is_flat = False
        if is_flat:
            flat.append((x, y))
    return flat


def _slope_cross(height, clutch, active_slopes, slope_min_z,
                 plus_x, minus_x, plus_y, minus_y,
                 width_x, width_y,
                 corner_radius=0, cr_skip_concave=True,
                 stud_taper_height=0, stud_taper_inset=0, stud_taper_curve="LINEAR"):
    """
    Pure function, specific. Build a cross-shaped slope brick.

    Args:
        height (float): Body height.
        clutch (str): Clutch type.
        active_slopes (list[tuple]): List of (direction, flat_rows) tuples.
        slope_min_z (float): Where slopes terminate.
        plus_x, minus_x, plus_y, minus_y (int): Arm lengths.
        width_x, width_y (int): Arm widths.
        corner_radius (float): 2D corner rounding radius.
        cr_skip_concave (bool): Skip concave corners in corner radius.
        stud_taper_height, stud_taper_inset (float): Stud taper params.
        stud_taper_curve (str): Stud taper curve type.

    Returns:
        Part: Complete cross-shaped slope brick.

    Examples:
        >>> # _slope_cross(9.6, "LATTICE", [("+Y", 1)], 1.5, 3, 0, 3, 0, 1, 1)
    """
    dims = _cross_footprint_dims(plus_x, minus_x, plus_y, minus_y,
                                 width_x, width_y)
    cavity_z = height - FLOOR_THICKNESS
    fillet_z = cavity_z if clutch == "LATTICE" else 0.0

    # Use bounding box dimensions for slope planes
    bbox_x = dims["total_x"] * PITCH - 2 * CLEARANCE
    bbox_y = dims["total_y"] * PITCH - 2 * CLEARANCE

    # Compute slope planes using bounding box
    cut_planes = []
    cavity_cut_planes = []
    for direction, flat_rows in active_slopes:
        cp, ccp = _slope_planes(direction, bbox_x, bbox_y, height,
                                flat_rows, slope_min_z)
        cut_planes.append(cp)
        cavity_cut_planes.append(ccp)

    # Build and cut outer shell
    outer = _build_cross_shell(plus_x, minus_x, plus_y, minus_y,
                               width_x, width_y, height,
                               corner_radius=corner_radius,
                               cr_skip_concave=cr_skip_concave)
    sloped_outer = outer
    for cp in cut_planes:
        sloped_outer = split(sloped_outer, bisect_by=cp, keep=Keep.BOTTOM)

    # Build and cut cavity
    cavity = _build_cross_cavity(plus_x, minus_x, plus_y, minus_y,
                                 width_x, width_y, cavity_z)
    sloped_cavity = cavity
    for ccp in cavity_cut_planes:
        sloped_cavity = split(sloped_cavity, bisect_by=ccp, keep=Keep.BOTTOM)

    shell = sloped_outer - sloped_cavity

    # Clutch internals clipped to sloped cavity
    clipped_clutch = None
    if clutch == "TUBE":
        tube_positions = _cross_tube_positions(plus_x, minus_x, plus_y, minus_y,
                                               width_x, width_y)
        if tube_positions:
            with BuildPart() as tb:
                with BuildSketch():
                    with Locations([Pos(x, y) for x, y in tube_positions]):
                        Circle(TUBE_OUTER_RADIUS)
                        Circle(TUBE_INNER_RADIUS, mode=Mode.SUBTRACT)
                extrude(amount=cavity_z)
            clipped_clutch = tb.part & sloped_cavity
    elif clutch == "LATTICE":
        sx, sy = dims["total_x"], dims["total_y"]
        inner_x = sx * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
        inner_y = sy * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
        if inner_x > 0 and inner_y > 0:
            lattice = _build_lattice(sx, sy, inner_x, inner_y, cavity_z)
            clipped_lattice = lattice & cavity  # clip to cross-shaped cavity first
            clipped_clutch = clipped_lattice & sloped_cavity  # then clip to slope

    # Determine flat stud positions
    all_stud_xy = _cross_stud_positions(plus_x, minus_x, plus_y, minus_y,
                                        width_x, width_y)
    # Filter to flat positions only
    flat_xy = _filter_flat_studs_cross(all_stud_xy, bbox_x, bbox_y, height,
                                       active_slopes, slope_min_z)

    with BuildPart() as bp:
        add(shell)
        if clipped_clutch:
            add(clipped_clutch)

        if ENABLE_STUDS:
            has_stud_taper = stud_taper_height > 0 and stud_taper_inset > 0
            if flat_xy:
                if has_stud_taper:
                    stud = _build_stud(STUD_RADIUS, STUD_HEIGHT,
                                       stud_taper_height, stud_taper_inset,
                                       stud_taper_curve)
                    with Locations([Pos(x, y, height) for x, y in flat_xy]):
                        add(stud)
                else:
                    with Locations([Pos(x, y, height) for x, y in flat_xy]):
                        Cylinder(STUD_RADIUS, STUD_HEIGHT,
                                 align=(Align.CENTER, Align.CENTER, Align.MIN))

    result = bp.part
    if ENABLE_FILLET:
        try:
            result = bevel_above_z(result, FILLET_RADIUS, z_threshold=fillet_z,
                                   style=EDGE_STYLE, include_bottom=FILLET_BOTTOM,
                                   skip_concave=SKIP_CONCAVE)
        except ValueError:
            pass

    if not ENABLE_TEXT or not ENABLE_STUDS or not flat_xy:
        return result

    with BuildPart() as final:
        add(result)
        with BuildSketch(Plane.XY.offset(height + STUD_HEIGHT)):
            with Locations([Pos(x, y) for x, y in flat_xy]):
                Text(STUD_TEXT, font_size=STUD_TEXT_FONT_SIZE,
                     font=STUD_TEXT_FONT, font_style=FontStyle.BOLD,
                     rotation=STUD_TEXT_ROTATION,
                     align=(Align.CENTER, Align.CENTER))
        extrude(amount=STUD_TEXT_HEIGHT)
    return final.part


def _filter_flat_studs_cross(stud_positions, bbox_x, bbox_y, height,
                             active_slopes, slope_min_z):
    """
    Pure function, specific. Filter stud positions to only those on the flat
    deck of a sloped cross-shaped brick.

    Uses the same hinge-based logic as _flat_stud_positions_rect.

    Args:
        stud_positions (list[tuple]): All (x, y) stud positions.
        bbox_x, bbox_y (float): Bounding box outer dimensions.
        height (float): Brick height.
        active_slopes (list[tuple]): List of (direction, flat_rows) tuples.
        slope_min_z (float): Where slopes terminate.

    Returns:
        list[tuple[float, float]]: Flat stud positions.

    Examples:
        >>> # _filter_flat_studs_cross([(0,0)], 15.6, 31.6, 9.6, [("+Y", 1)], 1.5)
    """
    half_x = bbox_x / 2
    half_y = bbox_y / 2

    flat = []
    for x, y in stud_positions:
        is_flat = True
        for direction, flat_rows in active_slopes:
            if direction == "+Y":
                hinge_y = -half_y + flat_rows * PITCH
                if y > hinge_y - PITCH / 2 + 0.01:
                    is_flat = False
            elif direction == "-Y":
                hinge_y = half_y - flat_rows * PITCH
                if y < hinge_y + PITCH / 2 - 0.01:
                    is_flat = False
            elif direction == "+X":
                hinge_x = -half_x + flat_rows * PITCH
                if x > hinge_x - PITCH / 2 + 0.01:
                    is_flat = False
            elif direction == "-X":
                hinge_x = half_x - flat_rows * PITCH
                if x < hinge_x + PITCH / 2 - 0.01:
                    is_flat = False
        if is_flat:
            flat.append((x, y))
    return flat
