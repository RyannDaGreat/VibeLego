"""
Clara brick geometry library -- diagonal lattice clutch system.

Same shell as LEGO bricks, but instead of cylindrical tubes the underside
uses +/-45 degree crisscross struts forming diamond openings. Each diamond's
inscribed circle = STUD_DIAMETER for exact stud fit. The lattice is fully
wall-connected -- no floating internal features.

3D printing features: optional corner radius (2D rounding of brick outline)
and wall taper (top of outer walls slopes inward for print tolerance).

Architecture: 2D sketch -> extrude (or loft for taper). Shared constants
and bevel_above_z come from common.py.

Coordinate convention: brick sits on XY plane, studs point up (+Z).
Origin at the center-bottom of the brick body (not including studs).
"""

import math
import os
import sys

# Allow importing common.py from parent directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from build123d import (
    Box, Circle, Cylinder, Rectangle, RectangleRounded, Pos, Rot, Plane,
    Align, Keep, Mode, FontStyle,
    BuildPart, BuildSketch, add, Locations, GridLocations,
    Text, extrude, loft, split,
)
from common import (
    PITCH, STUD_DIAMETER, STUD_RADIUS, STUD_HEIGHT,
    BRICK_HEIGHT, WALL_THICKNESS, FLOOR_THICKNESS,
    CLEARANCE, FILLET_RADIUS, ENABLE_FILLET, EDGE_STYLE, FILLET_BOTTOM, SKIP_CONCAVE, ENABLE_TEXT,
    STUD_TEXT, STUD_TEXT_FONT, STUD_TEXT_FONT_SIZE, STUD_TEXT_HEIGHT, STUD_TEXT_ROTATION,
    bevel_above_z,
)


# Intermediate profiles for smooth taper curves (piecewise-linear loft)
_CURVED_TAPER_STEPS = 8


def _taper_profile(t, curve="LINEAR"):
    """
    Pure function, general. Taper inset fraction at normalized position t.

    LINEAR: straight line. CURVED: quarter-circle f(t) = 1 - sqrt(1 - t**2).
    The quarter-circle is tangent to vertical at t=0 (continues straight wall)
    and tangent to horizontal at t=1 (meets deck). Concave up, no inflection.

    Args:
        t (float): Position along taper, 0 = start (bottom), 1 = end (top).
        curve (str): "LINEAR" or "CURVED".

    Returns:
        float: Fraction of total inset at position t, in [0, 1].

    Examples:
        >>> _taper_profile(0.0, "LINEAR")
        0.0
        >>> _taper_profile(0.5, "LINEAR")
        0.5
        >>> _taper_profile(1.0, "LINEAR")
        1.0
        >>> _taper_profile(0.0, "CURVED")
        0.0
        >>> round(_taper_profile(0.5, "CURVED"), 4)
        0.134
        >>> _taper_profile(1.0, "CURVED")
        1.0
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


def _build_stud(radius, total_height, taper_height=0, taper_inset=0,
                taper_curve="LINEAR"):
    """
    Pure function, specific. Build a single stud, optionally tapered at the top.

    Origin at center-bottom. Without taper, returns a simple cylinder. With
    taper, lofts circle profiles from full radius down to (radius - taper_inset)
    over the taper zone. Same curve options as wall taper.

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
        # Bottom profile (full radius)
        with BuildSketch(Plane.XY):
            Circle(radius)
        # Taper start (same radius — straight cylinder below)
        if taper_start_z > 0.01:
            with BuildSketch(Plane.XY.offset(taper_start_z)):
                Circle(radius)
        # Intermediate profiles for curved taper
        if taper_curve == "CURVED":
            for i in range(1, _CURVED_TAPER_STEPS):
                t = i / _CURVED_TAPER_STEPS
                z = taper_start_z + th * t
                r = radius - taper_inset * _taper_profile(t, "CURVED")
                with BuildSketch(Plane.XY.offset(z)):
                    Circle(max(r, 0.01))
        # Top profile (reduced radius)
        with BuildSketch(Plane.XY.offset(total_height)):
            Circle(top_radius)
        loft(ruled=True)
    return stud.part


def _build_lattice(studs_x, studs_y, inner_x, inner_y, cavity_z):
    """
    Pure function, specific. Build diagonal lattice struts as a standalone Part.

    Used by both clara_brick (added directly) and clara_slope (clipped to
    sloped cavity via boolean intersection before adding).

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


def clara_brick(studs_x, studs_y, height=BRICK_HEIGHT,
                corner_radius=0, taper_height=0, taper_inset=0,
                taper_curve="LINEAR",
                stud_taper_height=0, stud_taper_inset=0,
                stud_taper_curve="LINEAR"):
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
        corner_radius (float): 2D corner rounding of brick outline (mm).
            Like CSS border-radius — visible from top-down. Default 0 (sharp).
        taper_height (float): Height of tapered region below top (mm).
            The top portion of outer walls slopes inward. Default 0 (no taper).
        taper_inset (float): How far walls narrow at the top (mm per side).
            Default 0 (no taper).
        taper_curve (str): "LINEAR" (straight) or "CURVED" (quarter-circle
            profile — tangent to wall at bottom, tangent to deck at top).
        stud_taper_height (float): Height of tapered zone at top of studs (mm).
            Default 0 (no stud taper).
        stud_taper_inset (float): How far stud radius narrows at top (mm).
            Default 0 (no stud taper).
        stud_taper_curve (str): "LINEAR" or "CURVED" for stud taper profile.

    Returns:
        Part: Complete Clara brick.

    Examples:
        >>> # clara_brick(2, 4) -> 2x4 Clara brick with diamond lattice
        >>> # clara_brick(2, 4, corner_radius=1.5) -> rounded corners
        >>> # clara_brick(2, 4, taper_height=2, taper_inset=0.3) -> linear taper
        >>> # clara_brick(2, 4, taper_height=2, taper_inset=0.3, taper_curve="CURVED")
        >>> # clara_brick(2, 4, stud_taper_height=0.5, stud_taper_inset=0.2)
    """
    outer_x = studs_x * PITCH - 2 * CLEARANCE
    outer_y = studs_y * PITCH - 2 * CLEARANCE
    inner_x = outer_x - 2 * WALL_THICKNESS
    inner_y = outer_y - 2 * WALL_THICKNESS
    cavity_z = height - FLOOR_THICKNESS

    cr = _clamp_cr(corner_radius, outer_x, outer_y)

    has_taper = taper_height > 0 and taper_inset > 0
    top_x = outer_x - 2 * taper_inset if has_taper else outer_x
    top_y = outer_y - 2 * taper_inset if has_taper else outer_y
    top_cr = _clamp_cr(cr, top_x, top_y)

    with BuildPart() as brick:
        # ── Outer shell ──
        if has_taper:
            taper_start_z = height - taper_height
            # Bottom + taper start: identical profiles → straight walls below
            with BuildSketch(Plane.XY) as sk:
                _rounded_rect(outer_x, outer_y, cr)
            with BuildSketch(Plane.XY.offset(taper_start_z)) as sk:
                _rounded_rect(outer_x, outer_y, cr)
            # Intermediate profiles for curved taper
            if taper_curve == "CURVED":
                for i in range(1, _CURVED_TAPER_STEPS):
                    t = i / _CURVED_TAPER_STEPS
                    z = taper_start_z + taper_height * t
                    inset = taper_inset * _taper_profile(t, "CURVED")
                    w = outer_x - 2 * inset
                    h_dim = outer_y - 2 * inset
                    r = _clamp_cr(cr, w, h_dim)
                    with BuildSketch(Plane.XY.offset(z)) as sk:
                        _rounded_rect(w, h_dim, r)
            # Top profile (full inset)
            with BuildSketch(Plane.XY.offset(height)) as sk:
                _rounded_rect(top_x, top_y, top_cr)
            loft(ruled=True)
        elif cr > 0:
            # Rounded rect extrude (no taper)
            with BuildSketch() as sk:
                _rounded_rect(outer_x, outer_y, cr)
            extrude(amount=height)
        else:
            # Sharp box (original, fastest)
            Box(outer_x, outer_y, height,
                align=(Align.CENTER, Align.CENTER, Align.MIN))

        # ── Cavity ──
        Box(inner_x, inner_y, cavity_z,
            align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

        # ── Diagonal lattice ──
        add(_build_lattice(studs_x, studs_y, inner_x, inner_y, cavity_z))

        # ── Studs ──
        has_stud_taper = stud_taper_height > 0 and stud_taper_inset > 0
        if has_stud_taper:
            stud = _build_stud(STUD_RADIUS, STUD_HEIGHT,
                               stud_taper_height, stud_taper_inset,
                               stud_taper_curve)
            with Locations([Pos(0, 0, height)]):
                with GridLocations(PITCH, PITCH, studs_x, studs_y):
                    add(stud)
        else:
            with Locations([Pos(0, 0, height)]):
                with GridLocations(PITCH, PITCH, studs_x, studs_y):
                    Cylinder(STUD_RADIUS, STUD_HEIGHT,
                             align=(Align.CENTER, Align.CENTER, Align.MIN))

    # Fillet above cavity only -- lattice strut edges are too thin for OCCT filleter
    result = bevel_above_z(brick.part, FILLET_RADIUS, z_threshold=cavity_z, style=EDGE_STYLE, include_bottom=FILLET_BOTTOM, skip_concave=SKIP_CONCAVE) if ENABLE_FILLET else brick.part

    if not ENABLE_TEXT:
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


def clara_slope(studs_x, studs_y, height=BRICK_HEIGHT, flat_rows=1,
                corner_radius=0, taper_height=0, taper_inset=0,
                taper_curve="LINEAR",
                stud_taper_height=0, stud_taper_inset=0,
                stud_taper_curve="LINEAR"):
    """
    Pure function, specific. Create a Clara slope brick with diagonal lattice.

    Slope descends toward +Y. Only flat_rows of studs retained on the flat
    deck portion. Lattice struts are clipped to the sloped cavity via boolean
    intersection.

    Build order (same proven pattern as lego_slope):
        1. Outer shell (with optional corner_radius/taper) -> split by slope plane
        2. Cavity box -> split by OFFSET slope plane (FLOOR_THICKNESS gap)
        3. Shell = sloped_outer - sloped_cavity
        4. Lattice -> clip to sloped_cavity via &
        5. Studs on flat portion (with optional stud taper)
        6. Fillet -> text

    Args:
        studs_x (int): Studs along X.
        studs_y (int): Studs along Y (>= 2).
        height (float): Body height. Default BRICK_HEIGHT.
        flat_rows (int): Stud rows on the flat top. Default 1.
        corner_radius (float): 2D corner rounding (mm). Default 0.
        taper_height (float): Wall taper height (mm). Default 0.
        taper_inset (float): Wall taper inset (mm). Default 0.
        taper_curve (str): "LINEAR" or "CURVED".
        stud_taper_height (float): Stud taper height (mm). Default 0.
        stud_taper_inset (float): Stud taper inset (mm). Default 0.
        stud_taper_curve (str): "LINEAR" or "CURVED".

    Returns:
        Part: Complete Clara slope brick.

    Examples:
        >>> # clara_slope(2, 2) -> 2x2 slope, 1 flat row
        >>> # clara_slope(2, 4, flat_rows=2) -> 2x4 slope, 2 flat rows
        >>> # clara_slope(2, 4, corner_radius=2.0) -> slope with rounded corners
    """
    outer_x = studs_x * PITCH - 2 * CLEARANCE
    outer_y = studs_y * PITCH - 2 * CLEARANCE
    inner_x = outer_x - 2 * WALL_THICKNESS
    inner_y = outer_y - 2 * WALL_THICKNESS
    cavity_z = height - FLOOR_THICKNESS

    # ── Slope planes (same math as lego_slope, battle-tested) ──
    hinge_y = -outer_y / 2 + flat_rows * PITCH
    slope_dy = outer_y / 2 - hinge_y
    slope_dz = height - WALL_THICKNESS
    normal = (0, slope_dz, slope_dy)

    cut_plane = Plane(
        origin=(0, hinge_y, height), x_dir=(1, 0, 0), z_dir=normal)

    # Cavity cut plane: offset FLOOR_THICKNESS inward along slope normal
    normal_mag = math.sqrt(slope_dz**2 + slope_dy**2)
    cavity_cut_plane = Plane(
        origin=(0,
                hinge_y - FLOOR_THICKNESS * slope_dz / normal_mag,
                height - FLOOR_THICKNESS * slope_dy / normal_mag),
        x_dir=(1, 0, 0), z_dir=normal)

    # ── Sloped outer shell ──
    cr = _clamp_cr(corner_radius, outer_x, outer_y)
    has_taper = taper_height > 0 and taper_inset > 0

    if has_taper or cr > 0:
        # Build full shell (taper/rounded), then split
        with BuildPart() as outer_bp:
            if has_taper:
                taper_start_z = height - taper_height
                with BuildSketch(Plane.XY) as sk:
                    _rounded_rect(outer_x, outer_y, cr)
                with BuildSketch(Plane.XY.offset(taper_start_z)) as sk:
                    _rounded_rect(outer_x, outer_y, cr)
                if taper_curve == "CURVED":
                    top_x = outer_x - 2 * taper_inset
                    top_y = outer_y - 2 * taper_inset
                    for i in range(1, _CURVED_TAPER_STEPS):
                        t = i / _CURVED_TAPER_STEPS
                        z = taper_start_z + taper_height * t
                        inset = taper_inset * _taper_profile(t, "CURVED")
                        w = outer_x - 2 * inset
                        h_dim = outer_y - 2 * inset
                        r = _clamp_cr(cr, w, h_dim)
                        with BuildSketch(Plane.XY.offset(z)) as sk:
                            _rounded_rect(w, h_dim, r)
                top_x = outer_x - 2 * taper_inset
                top_y = outer_y - 2 * taper_inset
                top_cr = _clamp_cr(cr, top_x, top_y)
                with BuildSketch(Plane.XY.offset(height)) as sk:
                    _rounded_rect(top_x, top_y, top_cr)
                loft(ruled=True)
            else:
                with BuildSketch() as sk:
                    _rounded_rect(outer_x, outer_y, cr)
                extrude(amount=height)
        sloped_outer = split(outer_bp.part, bisect_by=cut_plane, keep=Keep.BOTTOM)
    else:
        outer = Box(outer_x, outer_y, height,
                    align=(Align.CENTER, Align.CENTER, Align.MIN))
        sloped_outer = split(outer, bisect_by=cut_plane, keep=Keep.BOTTOM)

    # ── Sloped cavity ──
    cavity = Box(inner_x, inner_y, cavity_z,
                 align=(Align.CENTER, Align.CENTER, Align.MIN))
    sloped_cavity = split(cavity, bisect_by=cavity_cut_plane, keep=Keep.BOTTOM)

    shell = sloped_outer - sloped_cavity

    # ── Lattice: build separately, clip to sloped cavity ──
    lattice = _build_lattice(studs_x, studs_y, inner_x, inner_y, cavity_z)
    clipped_lattice = lattice & sloped_cavity

    # ── Flat stud positions (front rows only) ──
    flat_xy = [((i - (studs_x - 1) / 2) * PITCH,
                (j - (studs_y - 1) / 2) * PITCH)
               for i in range(studs_x) for j in range(flat_rows)]

    # ── Assemble ──
    with BuildPart() as brick:
        add(shell)
        add(clipped_lattice)

        # Studs on flat portion (with optional taper)
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

    # Fillet above cavity (may fail on slopes — known issue)
    result = brick.part
    if ENABLE_FILLET:
        try:
            result = bevel_above_z(result, FILLET_RADIUS, z_threshold=cavity_z,
                                   style=EDGE_STYLE, include_bottom=FILLET_BOTTOM,
                                   skip_concave=SKIP_CONCAVE)
        except ValueError:
            pass  # Fillet failure on slopes is a known OCCT limitation

    if not ENABLE_TEXT or not flat_xy:
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
