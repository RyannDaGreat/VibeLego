"""
Unified brick geometry library — all clutch systems in one module.

Merges lego_lib.py (tube clutch) and clara_lib.py (lattice clutch) into a
single brick() + slope() interface with clutch type as a parameter. Clara-only
features (corner_radius, taper, stud_taper) are now available with any clutch.

Architecture: shell → clutch internals → studs → fillet → text.
Cross-shape bricks (L/T/+) and 4-directional slopes are supported.

Coordinate convention: brick sits on XY plane, studs point up (+Z).
Origin at the center of the center block (junction center), bottom of body.
For cross shapes, grid (0,0) always maps to world (0,0) — the bounding
box is NOT centered at origin for asymmetric crosses.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import (
    Box, Circle, Cylinder, Rectangle, RectangleRounded, Pos, Rot, Plane,
    Align, Keep, Mode, FontStyle, Axis,
    BuildPart, BuildSketch, BuildLine, add, Locations, GridLocations,
    Line, Polyline, TangentArc, make_face,
    Text, extrude, loft, revolve, split, fillet as bd_fillet,
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

_CURVED_TAPER_STEPS = 4


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
    taper, revolves a 2D XZ profile around Z — exact geometry for both LINEAR
    (straight slope) and CURVED (quarter-circle via TangentArc) taper modes.

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
        >>> # _build_stud(2.4, 1.8, 0.5, 0.2, "CURVED")  -> exact quarter-circle taper
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

    # Revolve a 2D profile in the XZ plane around Z axis
    with BuildPart() as stud:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                if taper_start_z > 0.01:
                    Polyline([(0, 0), (radius, 0), (radius, taper_start_z)])
                else:
                    Polyline([(0, 0), (radius, 0)])
                taper_start = (radius, max(taper_start_z, 0))
                taper_end = (top_radius, total_height)
                if taper_curve == "CURVED":
                    TangentArc(taper_start, taper_end, tangent=(0, 1))
                else:
                    Line(taper_start, taper_end)
                Polyline([taper_end, (0, total_height), (0, 0)])
            make_face()
        revolve(axis=Axis.Z)
    return stud.part


# ── Clutch builders ──────────────────────────────────────────────────────────

def _build_lattice(studs_x, studs_y, inner_x, inner_y, cavity_z,
                   clip_rects=None, grid_offset=(0.0, 0.0)):
    """
    Pure function, specific. Build diagonal lattice struts as a standalone Part.

    +/-45 deg crisscross struts forming diamond openings. Each diamond's
    inscribed circle = STUD_DIAMETER for exact stud fit.

    grid_offset shifts strut centers so the lattice stays aligned with
    junction-centered studs. For symmetric shapes offset is (0, 0).

    clip_rects overrides the default bounding-box clip. Each rect is
    (center_x, center_y, width, height). For cross shapes, one rect per arm
    avoids OCCT 3D intersection bugs on thin geometry. Each arm is clipped
    independently in 2D and the results are unioned.

    Args:
        studs_x (int): Studs along X (bounding box).
        studs_y (int): Studs along Y (bounding box).
        inner_x (float): Inner cavity width (bounding box).
        inner_y (float): Inner cavity height (bounding box).
        cavity_z (float): Cavity height (extrusion depth).
        clip_rects (list[tuple] | None): Per-arm clip rects [(cx, cy, w, h), ...].
            None = single bounding-box rectangle (default, for simple rectangles).
        grid_offset (tuple[float, float]): (gx, gy) shift for strut centers
            to align with junction-centered stud grid. Default (0, 0).

    Returns:
        Part: Lattice geometry, origin at (0, 0, 0).

    Examples:
        >>> # _build_lattice(2, 4, 12.8, 28.8, 8.6)
        >>> # _build_lattice(3, 1, 20.8, 4.8, 8.6,
        >>> #     grid_offset=(8.0, 0.0))
    """
    strut_thickness = PITCH / math.sqrt(2) - STUD_DIAMETER
    n_struts = studs_x + studs_y
    strut_len = (inner_x + inner_y) * 2
    c_start = -(n_struts - 1) / 2 * PITCH
    c_values = [c_start + i * PITCH for i in range(n_struts)]

    def _add_struts():
        """Command, specific. Add lattice strut rectangles to current sketch."""
        gx, gy = grid_offset
        for c in c_values:
            with Locations([Pos(-c / 2 + gx, c / 2 + gy) * Rot(0, 0, 45)]):
                Rectangle(strut_len, strut_thickness)
            with Locations([Pos(c / 2 + gx, c / 2 + gy) * Rot(0, 0, -45)]):
                Rectangle(strut_len, strut_thickness)

    if clip_rects is None or len(clip_rects) == 1:
        # Single clip region: standard bounding-box clip
        cx, cy, cw, ch = clip_rects[0] if clip_rects else (0, 0, inner_x, inner_y)
        with BuildPart() as lattice:
            with BuildSketch():
                _add_struts()
                with Locations([Pos(cx, cy)]):
                    Rectangle(cw, ch, mode=Mode.INTERSECT)
            extrude(amount=cavity_z)
        return lattice.part

    # Multiple clip regions: build per-arm, union results.
    # Avoids OCCT 3D intersection bugs with thin lattice vs complex cavity.
    parts = []
    for cx, cy, cw, ch in clip_rects:
        if cw <= 0 or ch <= 0:
            continue
        with BuildPart() as arm:
            with BuildSketch():
                _add_struts()
                with Locations([Pos(cx, cy)]):
                    Rectangle(cw, ch, mode=Mode.INTERSECT)
            extrude(amount=cavity_z)
        parts.append(arm.part)

    if not parts:
        # Fallback: empty lattice
        with BuildPart() as lattice:
            Box(0.01, 0.01, 0.01)
        return lattice.part

    result = parts[0]
    for p in parts[1:]:
        result = result + p
    return result


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
        with Locations([Pos(0, 0, cavity_z - RIDGE_HEIGHT)]):
            Box(rx, ry, RIDGE_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
    return rp.part


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
    by centering on the junction (center block center) and scaling by PITCH.
    Grid (0,0) always maps to world (0,0) when width_x == width_y == 1.

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

    # Junction centering: origin at center of center block
    center_i = (width_x - 1) / 2
    center_j = (width_y - 1) / 2

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

    # Junction centering: origin at center of center block
    center_i = (width_x - 1) / 2
    center_j = (width_y - 1) / 2

    return [((i - center_i) * PITCH, (j - center_j) * PITCH)
            for i, j in tube_grid]


def _cross_footprint_dims(plus_x, minus_x, plus_y, minus_y, width_x, width_y):
    """
    Pure function, general. Compute the bounding box dimensions, bar
    dimensions, and junction-centered offsets of a cross-shaped footprint.

    Origin is at the center of the center block (junction), not the
    bounding-box center.  h_offset_i / v_offset_j give the offset of
    each bar's center from the junction in grid units (multiply by PITCH
    for world coords).

    Returns:
        dict: Keys: total_x, total_y (bounding box in studs),
              h_bar_x, h_bar_y, v_bar_x, v_bar_y (bar dimensions in studs),
              h_offset_i, v_offset_j (bar offsets from junction in grid units).

    Examples:
        >>> d = _cross_footprint_dims(1, 1, 1, 1, 1, 1)
        >>> d['total_x'], d['total_y']
        (3, 3)
        >>> d['h_offset_i'], d['v_offset_j']
        (0.0, 0.0)
        >>> d2 = _cross_footprint_dims(2, 0, 0, 0, 1, 1)
        >>> d2['h_offset_i']
        1.0
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
        "h_offset_i": (plus_x - minus_x) / 2,
        "v_offset_j": (plus_y - minus_y) / 2,
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


def _cross_sketch(h_w, h_h, v_w, v_h, h_offset_x, v_offset_y,
                  cr=0, cr_skip_concave=True):
    """
    Pure function, specific. Build a 2D cross footprint sketch (two rectangles).

    Must be called inside a BuildSketch context. Optionally fillets vertices.
    In junction-centered coords, h_bar gets an X offset (asymmetric extension
    along its long axis) and v_bar gets a Y offset.

    Args:
        h_w, h_h (float): Horizontal bar width/height.
        v_w, v_h (float): Vertical bar width/height.
        h_offset_x (float): Horizontal bar X offset from junction.
        v_offset_y (float): Vertical bar Y offset from junction.
        cr (float): Corner radius. 0 = sharp.
        cr_skip_concave (bool): Skip concave corners.

    Examples:
        >>> # Called inside BuildSketch: _cross_sketch(15.6, 7.6, 7.6, 15.6, 0, 0)
    """
    # Degenerate rectangle: single bar, use simple rounded rect
    is_degenerate = (abs(h_w - v_w) < 0.01 and abs(h_h - v_h) < 0.01
                     and abs(h_offset_x) < 0.01 and abs(v_offset_y) < 0.01)
    if is_degenerate:
        _rounded_rect(h_w, h_h, _clamp_cr(cr, h_w, h_h) if cr > 0 else 0)
        return

    with Locations([Pos(h_offset_x, 0)]):
        Rectangle(h_w, h_h)
    with Locations([Pos(0, v_offset_y)]):
        Rectangle(v_w, v_h, mode=Mode.ADD)
    if cr > 0:
        sk = BuildSketch._get_context()
        convex, concave = _cross_concave_vertices(sk, v_w, h_h)
        if convex:
            bd_fillet(convex, radius=cr)
        if concave and not cr_skip_concave:
            bd_fillet(concave, radius=cr)


def _build_cross_shell(plus_x, minus_x, plus_y, minus_y, width_x, width_y,
                       height, corner_radius=0, cr_skip_concave=True,
                       taper_height=0, taper_inset=0, taper_curve="LINEAR"):
    """
    Pure function, specific. Build the outer shell for a cross-shaped brick.

    Union of two rectangular bars (horizontal and vertical), extruded to height.
    When corner_radius > 0, vertices are filleted in 2D.
    When taper is active, builds via multi-section loft (same as rectangle taper).

    Args:
        plus_x, minus_x, plus_y, minus_y (int): Arm lengths.
        width_x, width_y (int): Arm widths in studs.
        height (float): Body height.
        corner_radius (float): 2D corner rounding radius. 0 = sharp.
        cr_skip_concave (bool): Skip concave (reentrant) corners. Default True.
        taper_height (float): Wall taper height from top. 0 = no taper.
        taper_inset (float): Per-side inset at top. 0 = no taper.
        taper_curve (str): "LINEAR" or "CURVED".

    Returns:
        Part: Outer shell solid (no cavity).

    Examples:
        >>> # _build_cross_shell(1, 1, 1, 1, 1, 1, 9.6)  -> + shape
        >>> # _build_cross_shell(1, 1, 1, 1, 1, 1, 9.6, corner_radius=2.0)
        >>> # _build_cross_shell(1, 1, 1, 1, 1, 1, 9.6, taper_height=2.0, taper_inset=0.5)
    """
    dims = _cross_footprint_dims(plus_x, minus_x, plus_y, minus_y,
                                 width_x, width_y)
    h_w = dims["h_bar_x"] * PITCH - 2 * CLEARANCE
    h_h = dims["h_bar_y"] * PITCH - 2 * CLEARANCE
    v_w = dims["v_bar_x"] * PITCH - 2 * CLEARANCE
    v_h = dims["v_bar_y"] * PITCH - 2 * CLEARANCE

    # Junction-centered offsets (single source of truth from dims)
    h_offset_x = dims["h_offset_i"] * PITCH
    v_offset_y = dims["v_offset_j"] * PITCH

    cr = _clamp_cr(corner_radius, min(h_w, v_w), min(h_h, v_h)) if corner_radius > 0 else 0
    has_taper = taper_height > 0 and taper_inset > 0

    if has_taper:
        # Loft approach: same as _build_outer_shell but with cross footprint
        taper_start_z = height - taper_height
        with BuildPart() as shell:
            # Base sketch (Z=0)
            with BuildSketch(Plane.XY):
                _cross_sketch(h_w, h_h, v_w, v_h, h_offset_x, v_offset_y,
                              cr, cr_skip_concave)
            # Sketch at taper start (same size)
            with BuildSketch(Plane.XY.offset(taper_start_z)):
                _cross_sketch(h_w, h_h, v_w, v_h, h_offset_x, v_offset_y,
                              cr, cr_skip_concave)
            # Intermediate sketches for curved taper
            if taper_curve == "CURVED":
                for i in range(1, _CURVED_TAPER_STEPS):
                    t = i / _CURVED_TAPER_STEPS
                    z = taper_start_z + taper_height * t
                    inset = taper_inset * _taper_profile(t, "CURVED")
                    tw = h_w - 2 * inset
                    th = h_h - 2 * inset
                    tvw = v_w - 2 * inset
                    tvh = v_h - 2 * inset
                    tcr = _clamp_cr(cr, min(tw, tvw), min(th, tvh)) if cr > 0 else 0
                    with BuildSketch(Plane.XY.offset(z)):
                        _cross_sketch(tw, th, tvw, tvh, h_offset_x, v_offset_y,
                                      tcr, cr_skip_concave)
            # Top sketch (inset)
            top_hw = h_w - 2 * taper_inset
            top_hh = h_h - 2 * taper_inset
            top_vw = v_w - 2 * taper_inset
            top_vh = v_h - 2 * taper_inset
            top_cr = _clamp_cr(cr, min(top_hw, top_vw), min(top_hh, top_vh)) if cr > 0 else 0
            with BuildSketch(Plane.XY.offset(height)):
                _cross_sketch(top_hw, top_hh, top_vw, top_vh,
                              h_offset_x, v_offset_y, top_cr, cr_skip_concave)
            loft(ruled=True)
        return shell.part

    if cr > 0:
        # 2D sketch + fillet + extrude
        with BuildPart() as shell:
            with BuildSketch():
                _cross_sketch(h_w, h_h, v_w, v_h, h_offset_x, v_offset_y,
                              cr, cr_skip_concave)
            extrude(amount=height)
        return shell.part

    # No corner radius, no taper: fast Box path
    is_degenerate = (abs(h_w - v_w) < 0.01 and abs(h_h - v_h) < 0.01
                     and abs(h_offset_x) < 0.01 and abs(v_offset_y) < 0.01)
    with BuildPart() as shell:
        if is_degenerate:
            Box(h_w, h_h, height,
                align=(Align.CENTER, Align.CENTER, Align.MIN))
        else:
            with Locations([Pos(h_offset_x, 0, 0)]):
                Box(h_w, h_h, height,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
            with Locations([Pos(0, v_offset_y, 0)]):
                Box(v_w, v_h, height,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
    return shell.part


def _cross_cavity_bar_dims(plus_x, minus_x, plus_y, minus_y, width_x, width_y):
    """
    Pure function, specific. Compute inner cavity bar dimensions and offsets
    for a cross-shaped (or degenerate rectangular) footprint.

    Returns the per-arm inner dimensions used for both the cavity solid and
    the lattice clip rectangles — single source of truth.

    Args:
        plus_x, minus_x, plus_y, minus_y (int): Arm lengths.
        width_x, width_y (int): Arm widths in studs.

    Returns:
        list[tuple[float, float, float, float]]: List of (cx, cy, w, h) for
            each cavity bar with positive dimensions. For a pure rectangle,
            returns a single bar. For crosses, returns two bars.

    Examples:
        >>> _cross_cavity_bar_dims(0, 0, 0, 0, 2, 4)
        [(0.0, 0.0, 12.8, 28.8)]
        >>> len(_cross_cavity_bar_dims(1, 1, 1, 1, 1, 1))
        2
    """
    dims = _cross_footprint_dims(plus_x, minus_x, plus_y, minus_y,
                                 width_x, width_y)
    wt = WALL_THICKNESS
    h_w = dims["h_bar_x"] * PITCH - 2 * CLEARANCE - 2 * wt
    h_h = dims["h_bar_y"] * PITCH - 2 * CLEARANCE - 2 * wt
    v_w = dims["v_bar_x"] * PITCH - 2 * CLEARANCE - 2 * wt
    v_h = dims["v_bar_y"] * PITCH - 2 * CLEARANCE - 2 * wt
    # Junction-centered offsets (single source of truth from dims)
    h_offset_x = dims["h_offset_i"] * PITCH
    v_offset_y = dims["v_offset_j"] * PITCH

    bars = []
    if h_w > 0 and h_h > 0:
        bars.append((h_offset_x, 0.0, h_w, h_h))
    if v_w > 0 and v_h > 0:
        bars.append((0.0, v_offset_y, v_w, v_h))
    # Deduplicate: degenerate rectangle has h_bar == v_bar
    if len(bars) == 2 and bars[0] == bars[1]:
        bars = bars[:1]
    return bars


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
    bars = _cross_cavity_bar_dims(plus_x, minus_x, plus_y, minus_y,
                                  width_x, width_y)
    with BuildPart() as cav:
        for cx, cy, w, h in bars:
            with Locations([Pos(cx, cy, 0)]):
                Box(w, h, cavity_z,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
    return cav.part


# ── Slope plane helpers ──────────────────────────────────────────────────────

def _slope_planes(direction, edge_minus_x, edge_plus_x, edge_minus_y,
                  edge_plus_y, height, flat_rows, slope_min_z):
    """
    Pure function, general. Compute cut plane and cavity cut plane for a slope
    in the given direction.

    Uses edge coordinates (not symmetric halves) so the brick need not be
    centered at the origin. For junction-centered bricks, edges are computed
    from bar offset + half-width.

    Args:
        direction (str): "+Y", "-Y", "+X", "-X".
        edge_minus_x (float): Shell left edge (most negative X).
        edge_plus_x (float): Shell right edge (most positive X).
        edge_minus_y (float): Shell front edge (most negative Y).
        edge_plus_y (float): Shell back edge (most positive Y).
        height (float): Brick height.
        flat_rows (int): Number of flat stud rows before slope begins.
        slope_min_z (float): Z height where slope terminates (bottom).

    Returns:
        tuple[Plane, Plane]: (cut_plane, cavity_cut_plane).

    Examples:
        >>> # _slope_planes("+Y", -7.8, 7.8, -15.8, 15.8, 9.6, 1, 1.5)
    """
    if direction == "+Y":
        hinge = edge_minus_y + flat_rows * PITCH
        span = edge_plus_y - hinge
        dz = height - slope_min_z
        normal = (0, dz, span)
        origin = (0, hinge, height)
        x_dir = (1, 0, 0)
    elif direction == "-Y":
        hinge = edge_plus_y - flat_rows * PITCH
        span = hinge - edge_minus_y
        dz = height - slope_min_z
        normal = (0, -dz, span)
        origin = (0, hinge, height)
        x_dir = (-1, 0, 0)
    elif direction == "+X":
        hinge = edge_minus_x + flat_rows * PITCH
        span = edge_plus_x - hinge
        dz = height - slope_min_z
        normal = (dz, 0, span)
        origin = (hinge, 0, height)
        x_dir = (0, 1, 0)
    elif direction == "-X":
        hinge = edge_plus_x - flat_rows * PITCH
        span = hinge - edge_minus_x
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


# ── Shared assembly helpers ──────────────────────────────────────────────────

def _normalize_cross(shape_mode, studs_x, studs_y,
                     plus_x, minus_x, plus_y, minus_y,
                     cross_width_x, cross_width_y):
    """
    Pure function, specific. Normalize RECTANGLE params to degenerate cross params.

    Returns:
        tuple: (plus_x, minus_x, plus_y, minus_y, cross_width_x, cross_width_y).

    Examples:
        >>> _normalize_cross("RECTANGLE", 2, 4, 0, 0, 0, 0, 1, 1)
        (0, 0, 0, 0, 2, 4)
        >>> _normalize_cross("CROSS", 0, 0, 3, 0, 3, 0, 1, 1)
        (3, 0, 3, 0, 1, 1)
    """
    if shape_mode != "CROSS":
        return 0, 0, 0, 0, studs_x, studs_y
    return plus_x, minus_x, plus_y, minus_y, cross_width_x, cross_width_y


def _place_studs(positions, height, stud_taper_height=0, stud_taper_inset=0,
                 stud_taper_curve="LINEAR"):
    """
    Command, specific. Add studs at the given (x, y) positions.
    Must be called inside a BuildPart context.

    Args:
        positions (list[tuple]): (x, y) positions for stud centers.
        height (float): Brick body height (studs placed on top).
        stud_taper_height (float): Stud taper height. 0 = no taper.
        stud_taper_inset (float): Stud taper inset. 0 = no taper.
        stud_taper_curve (str): "LINEAR" or "CURVED".

    Examples:
        >>> # Inside BuildPart: _place_studs([(0, 0), (8, 0)], 9.6)
    """
    if not ENABLE_STUDS or not positions:
        return
    has_taper = stud_taper_height > 0 and stud_taper_inset > 0
    if has_taper:
        stud = _build_stud(STUD_RADIUS, STUD_HEIGHT,
                           stud_taper_height, stud_taper_inset, stud_taper_curve)
        with Locations([Pos(x, y, height) for x, y in positions]):
            add(stud)
    else:
        with Locations([Pos(x, y, height) for x, y in positions]):
            Cylinder(STUD_RADIUS, STUD_HEIGHT,
                     align=(Align.CENTER, Align.CENTER, Align.MIN))


def _try_fillet(result, fillet_z):
    """
    Command, specific. Apply fillet/chamfer to part. Returns original on OCCT
    failure (known limitation for cross shapes with edges too small for filleter).

    Args:
        result (Part): Part to fillet.
        fillet_z (float): Z threshold — only fillet edges above this height.

    Returns:
        Part: Filleted part, or original if OCCT rejects.

    Examples:
        >>> # _try_fillet(part, cavity_z)  -> fillet edges above cavity
    """
    if not ENABLE_FILLET:
        return result
    try:
        return bevel_above_z(result, FILLET_RADIUS, z_threshold=fillet_z,
                             style=EDGE_STYLE, include_bottom=FILLET_BOTTOM,
                             skip_concave=SKIP_CONCAVE)
    except ValueError:
        return result


def _apply_text(result, positions, height):
    """
    Command, specific. Add raised text to stud tops.

    Args:
        result (Part): Brick part to add text onto.
        positions (list[tuple]): (x, y) stud positions.
        height (float): Brick body height.

    Returns:
        Part: Part with text, or original if text disabled or no positions.

    Examples:
        >>> # _apply_text(part, [(0, 0)], 9.6)
    """
    if not ENABLE_TEXT or not ENABLE_STUDS or not positions:
        return result
    with BuildPart() as final:
        add(result)
        with BuildSketch(Plane.XY.offset(height + STUD_HEIGHT)):
            with Locations([Pos(x, y) for x, y in positions]):
                Text(STUD_TEXT, font_size=STUD_TEXT_FONT_SIZE,
                     font=STUD_TEXT_FONT, font_style=FontStyle.BOLD,
                     rotation=STUD_TEXT_ROTATION,
                     align=(Align.CENTER, Align.CENTER))
        extrude(amount=STUD_TEXT_HEIGHT)
    return final.part


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

    Rectangle is a degenerate cross (all arms=0, widths=studs). One code path
    handles both shapes: shell → cavity → clutch → studs → fillet → text.

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
    # Normalize: rectangle is a degenerate cross
    plus_x, minus_x, plus_y, minus_y, cross_width_x, cross_width_y = \
        _normalize_cross(shape_mode, studs_x, studs_y,
                         plus_x, minus_x, plus_y, minus_y,
                         cross_width_x, cross_width_y)

    dims = _cross_footprint_dims(plus_x, minus_x, plus_y, minus_y,
                                 cross_width_x, cross_width_y)
    sx, sy = dims["total_x"], dims["total_y"]
    cavity_z = height - FLOOR_THICKNESS
    fillet_z = cavity_z if clutch == "LATTICE" else 0.0

    # Shell + cavity + positions — one source of truth
    outer_shell = _build_cross_shell(plus_x, minus_x, plus_y, minus_y,
                                     cross_width_x, cross_width_y, height,
                                     corner_radius=corner_radius,
                                     cr_skip_concave=cr_skip_concave,
                                     taper_height=taper_height,
                                     taper_inset=taper_inset,
                                     taper_curve=taper_curve)
    cavity = _build_cross_cavity(plus_x, minus_x, plus_y, minus_y,
                                 cross_width_x, cross_width_y, cavity_z)
    cavity_bars = _cross_cavity_bar_dims(plus_x, minus_x, plus_y, minus_y,
                                         cross_width_x, cross_width_y)
    stud_positions = _cross_stud_positions(plus_x, minus_x, plus_y, minus_y,
                                           cross_width_x, cross_width_y)

    with BuildPart() as bp:
        add(outer_shell)
        add(cavity, mode=Mode.SUBTRACT)

        # Clutch internals
        if clutch == "TUBE":
            tube_positions = _cross_tube_positions(plus_x, minus_x, plus_y, minus_y,
                                                   cross_width_x, cross_width_y)
            if tube_positions:
                with BuildPart() as tb:
                    with BuildSketch():
                        with Locations([Pos(x, y) for x, y in tube_positions]):
                            Circle(TUBE_OUTER_RADIUS)
                            Circle(TUBE_INNER_RADIUS, mode=Mode.SUBTRACT)
                    extrude(amount=cavity_z)
                add(tb.part)
            # Ridge for 1-wide arms (only meaningful for degenerate rectangles)
            ridge = _build_ridge(sx, sy, cavity_z)
            if ridge:
                add(ridge)
        elif clutch == "LATTICE":
            inner_x = sx * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
            inner_y = sy * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
            grid_off = (dims["h_offset_i"] * PITCH,
                        dims["v_offset_j"] * PITCH)
            if inner_x > 0 and inner_y > 0:
                add(_build_lattice(sx, sy, inner_x, inner_y, cavity_z,
                                   clip_rects=cavity_bars,
                                   grid_offset=grid_off))

        # Studs
        _place_studs(stud_positions, height,
                     stud_taper_height, stud_taper_inset, stud_taper_curve)

    result = _try_fillet(bp.part, fillet_z)
    return _apply_text(result, stud_positions, height)


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

    Rectangle is a degenerate cross (same normalization as brick()). One code
    path handles both shapes.

    Build order (critical — prevents exposed cavity):
        1. Outer shell → split by ALL slope planes
        2. Cavity → split by ALL offset slope planes
        3. Shell = sloped_outer - sloped_cavity
        4. Clutch internals → per-arm 2D clip, then 3D slope clip
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
    # Normalize: rectangle is a degenerate cross
    plus_x, minus_x, plus_y, minus_y, cross_width_x, cross_width_y = \
        _normalize_cross(shape_mode, studs_x, studs_y,
                         plus_x, minus_x, plus_y, minus_y,
                         cross_width_x, cross_width_y)

    dims = _cross_footprint_dims(plus_x, minus_x, plus_y, minus_y,
                                 cross_width_x, cross_width_y)
    sx, sy = dims["total_x"], dims["total_y"]

    # Collect active slopes, converting sloped_rows → flat_rows
    active_slopes = []
    if slope_plus_y > 0:
        active_slopes.append(("+Y", sy - slope_plus_y))
    if slope_minus_y > 0:
        active_slopes.append(("-Y", sy - slope_minus_y))
    if slope_plus_x > 0:
        active_slopes.append(("+X", sx - slope_plus_x))
    if slope_minus_x > 0:
        active_slopes.append(("-X", sx - slope_minus_x))

    if not active_slopes:
        return brick(studs_x, studs_y, height, clutch,
                     corner_radius, cr_skip_concave,
                     taper_height, taper_inset, taper_curve,
                     stud_taper_height, stud_taper_inset, stud_taper_curve,
                     shape_mode, plus_x, minus_x, plus_y, minus_y,
                     cross_width_x, cross_width_y)

    cavity_z = height - FLOOR_THICKNESS
    fillet_z = cavity_z if clutch == "LATTICE" else 0.0

    # Junction-centered edge coordinates for slope planes
    h_offset_x = dims["h_offset_i"] * PITCH
    v_offset_y = dims["v_offset_j"] * PITCH
    bbox_x = sx * PITCH - 2 * CLEARANCE
    bbox_y = sy * PITCH - 2 * CLEARANCE
    edge_minus_x = h_offset_x - bbox_x / 2
    edge_plus_x = h_offset_x + bbox_x / 2
    edge_minus_y = v_offset_y - bbox_y / 2
    edge_plus_y = v_offset_y + bbox_y / 2

    # Compute all slope planes
    cut_planes = []
    cavity_cut_planes = []
    for direction, flat_rows in active_slopes:
        cp, ccp = _slope_planes(direction, edge_minus_x, edge_plus_x,
                                edge_minus_y, edge_plus_y, height,
                                flat_rows, slope_min_z)
        cut_planes.append(cp)
        cavity_cut_planes.append(ccp)

    # Build and cut outer shell
    outer = _build_cross_shell(plus_x, minus_x, plus_y, minus_y,
                               cross_width_x, cross_width_y, height,
                               corner_radius=corner_radius,
                               cr_skip_concave=cr_skip_concave,
                               taper_height=taper_height,
                               taper_inset=taper_inset,
                               taper_curve=taper_curve)
    sloped_outer = outer
    for cp in cut_planes:
        sloped_outer = split(sloped_outer, bisect_by=cp, keep=Keep.BOTTOM)

    # Build and cut cavity
    cavity = _build_cross_cavity(plus_x, minus_x, plus_y, minus_y,
                                 cross_width_x, cross_width_y, cavity_z)
    sloped_cavity = cavity
    for ccp in cavity_cut_planes:
        sloped_cavity = split(sloped_cavity, bisect_by=ccp, keep=Keep.BOTTOM)

    shell = sloped_outer - sloped_cavity

    # Clutch internals — per-arm 2D clip, then 3D slope clip
    cavity_bars = _cross_cavity_bar_dims(plus_x, minus_x, plus_y, minus_y,
                                         cross_width_x, cross_width_y)
    grid_off = (h_offset_x, v_offset_y)
    clipped_clutch = None
    if clutch == "TUBE":
        tube_positions = _cross_tube_positions(plus_x, minus_x, plus_y, minus_y,
                                               cross_width_x, cross_width_y)
        if tube_positions:
            with BuildPart() as tb:
                with BuildSketch():
                    with Locations([Pos(x, y) for x, y in tube_positions]):
                        Circle(TUBE_OUTER_RADIUS)
                        Circle(TUBE_INNER_RADIUS, mode=Mode.SUBTRACT)
                extrude(amount=cavity_z)
            clipped_clutch = tb.part & sloped_cavity
    elif clutch == "LATTICE":
        inner_x = sx * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
        inner_y = sy * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
        if inner_x > 0 and inner_y > 0:
            lattice = _build_lattice(sx, sy, inner_x, inner_y, cavity_z,
                                     clip_rects=cavity_bars,
                                     grid_offset=grid_off)
            clipped_clutch = lattice & sloped_cavity

    # Flat stud positions (all positions filtered by slope hinges)
    all_stud_xy = _cross_stud_positions(plus_x, minus_x, plus_y, minus_y,
                                        cross_width_x, cross_width_y)
    flat_xy = _filter_flat_studs(all_stud_xy, edge_minus_x, edge_plus_x,
                                 edge_minus_y, edge_plus_y, active_slopes)

    # Assemble
    with BuildPart() as bp:
        add(shell)
        if clipped_clutch:
            add(clipped_clutch)
        if clutch == "TUBE":
            ridge = _build_ridge(sx, sy, cavity_z)
            if ridge:
                add(ridge & sloped_cavity)

        _place_studs(flat_xy, height,
                     stud_taper_height, stud_taper_inset, stud_taper_curve)

    result = _try_fillet(bp.part, fillet_z)
    return _apply_text(result, flat_xy, height)


def _filter_flat_studs(stud_positions, edge_minus_x, edge_plus_x,
                       edge_minus_y, edge_plus_y, active_slopes):
    """
    Pure function, specific. Filter stud positions to those on the flat deck
    of a sloped brick with multiple active slopes.

    A stud is flat if it's on the non-sloped side of every active slope's hinge.
    Works for both rectangle and cross shapes — stud positions are pre-computed
    by _cross_stud_positions.

    Uses edge coordinates (not symmetric halves) so the brick need not be
    centered at the origin.

    Args:
        stud_positions (list[tuple]): All (x, y) stud positions.
        edge_minus_x (float): Shell left edge.
        edge_plus_x (float): Shell right edge.
        edge_minus_y (float): Shell front edge.
        edge_plus_y (float): Shell back edge.
        active_slopes (list[tuple]): List of (direction, flat_rows) tuples.

    Returns:
        list[tuple[float, float]]: Flat stud positions.

    Examples:
        >>> _filter_flat_studs([(0, -12), (0, -4), (0, 4), (0, 12)],
        ...                    -7.8, 7.8, -15.8, 15.8, [("+Y", 1)])
        [(0, -12), (0, -4)]
    """
    flat = []
    for x, y in stud_positions:
        is_flat = True
        for direction, flat_rows in active_slopes:
            if direction == "+Y":
                hinge_y = edge_minus_y + flat_rows * PITCH
                if y > hinge_y - PITCH / 2 + 0.01:
                    is_flat = False
            elif direction == "-Y":
                hinge_y = edge_plus_y - flat_rows * PITCH
                if y < hinge_y + PITCH / 2 - 0.01:
                    is_flat = False
            elif direction == "+X":
                hinge_x = edge_minus_x + flat_rows * PITCH
                if x > hinge_x - PITCH / 2 + 0.01:
                    is_flat = False
            elif direction == "-X":
                hinge_x = edge_plus_x - flat_rows * PITCH
                if x < hinge_x + PITCH / 2 - 0.01:
                    is_flat = False
        if is_flat:
            flat.append((x, y))
    return flat


