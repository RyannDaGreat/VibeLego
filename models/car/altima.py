"""
Nissan Altima 3D Model — build123d parametric sedan.

Command, specific. Creates a 2024 Nissan Altima sedan at ~1:25 scale using
smooth loft with dense pre-interpolated cross-sections, wheel arch cutouts,
and separate wheel cylinders.

Real dimensions: 4900 x 1852 x 1440 mm, wheelbase 2825 mm.
Origin: center of car at ground level. X = length, Y = width, Z = up.

Usage:
    ./render.sh models/car/altima.py
"""

import os
from build123d import (
    BuildPart, BuildSketch, BuildLine,
    Plane, Pos, Rot,
    Cylinder,
    Polyline, make_face,
    loft,
    export_stl, Compound,
)

# ── Master Dimensions (mm at ~1:25) ──────────────────────────────────────────
# Derived from 2024 Nissan Altima official specs.

LENGTH = 196.0          # 4900 / 25
HALF_LENGTH = LENGTH / 2  # 98 — used to center car at origin
MAX_HALF_WIDTH = 37.0   # 1852 / 2 / 25 ≈ 37
HEIGHT = 57.6           # 1440 / 25
WHEELBASE = 113.0       # 2825 / 25
FRONT_OVERHANG = 43.0   # ~22% of length

# Axle X positions (X=0 at car center)
FRONT_AXLE_X = -HALF_LENGTH + FRONT_OVERHANG   # -55
REAR_AXLE_X = FRONT_AXLE_X + WHEELBASE         # 58

# Wheel geometry (17" rims + 215/55R17 tires, OD ~668mm)
WHEEL_RADIUS = 13.4     # 668 / 2 / 25
WHEEL_WIDTH = 8.6        # 215mm / 25
WHEEL_CENTER_Z = WHEEL_RADIUS  # wheels sit on ground (Z=0)

# Wheel arch — must be clearly visible from all angles
ARCH_RADIUS = 17.0       # bigger than wheel for clearance
ARCH_CUT_WIDTH = 24.0    # Y-depth of arch cutout

# ── Body Shape — Key Control Stations ────────────────────────────────────────
# Each: (x, half_width, roof_half_width, bottom_z, beltline_z, roof_z)
#
# Profile is a 6-point closed polygon per section:
#   flat bottom → vertical sides to beltline → angled greenhouse to roof
#
# IMPORTANT: rz must be > beltz at EVERY station to maintain hexagonal
# topology for the loft. Collapsing rz == beltz changes edge count and
# breaks OCCT's loft algorithm.
#
# These key stations are linearly interpolated to NUM_INTERP_STATIONS
# dense stations for a smooth loft — dense pre-interpolation prevents
# the spline overshoot that occurs with sparse, rapidly-changing stations.

KEY_STATIONS = [
    # x       hw    rw    bz    beltz   rz       # description
    (-98,     14,    9,   12,    22,    24),      # front bumper tip
    (-78,     26,   15,    8,    27,    29),      # front fascia
    (-63,     34,   20,    6,    31,    34),      # hood start
    (-55,     37,   22,    5,    32,    35),      # front axle
    (-40,     37,   24,    5,    33,    36),      # mid-hood
    (-26,     37,   26,    5,    33,    38),      # cowl / windshield base
    (-21,     37,   27,    5,    33.5,  42),      # windshield onset
    (-16,     37,   29,    5,    34,    48),      # windshield lower
    (-12,     37,   29.5,  5,    34,    51),      # windshield mid
    ( -8,     37,   30,    5,    34,    54),      # windshield upper
    ( -4,     37,   30,    5,    34,    56),      # windshield-roof transition
    (  0,     37,   30,    5,    34,    57.6),    # roof front edge
    ( 10,     37,   30,    5,    34,    57.6),    # roof peak
    ( 20,     37,   30,    5,    34,    56),      # roof center
    ( 30,     37,   28,    5,    34,    50),      # rear window upper
    ( 35,     37,   26,    5,    34,    46),      # rear window mid
    ( 40,     37,   25,    5,    34,    42),      # rear window / C-pillar
    ( 50,     37,   21,    5,    33,    36),      # trunk start
    ( 58,     37,   20,    5,    32,    35),      # rear axle
    ( 70,     34,   17,    6,    30,    33),      # trunk
    ( 82,     28,   14,    8,    27,    29),      # rear fascia
    ( 94,     20,   11,   10,    24,    26),      # rear bumper
    ( 98,     14,    8,   13,    21,    23),      # rear tip
]

NUM_INTERP_STATIONS = 60  # dense sampling for smooth loft


def _interpolate_stations(key_stations, n):
    """
    Pure function, specific. Linearly interpolate key control stations
    to produce n evenly-spaced cross-sections for smooth lofting.

    Piecewise linear in all 6 dimensions. Guarantees monotonic X values
    and preserves rz > beltz invariant (inherits from key stations).

    Args:
        key_stations (list[tuple]): Sorted key (x, hw, rw, bz, beltz, rz).
        n (int): Number of output stations.

    Returns:
        list[tuple]: n interpolated stations.

    Examples:
        >>> s = _interpolate_stations([(-5, 10, 5, 2, 8, 10), (5, 20, 10, 2, 8, 12)], 3)
        >>> [round(v[0], 1) for v in s]
        [-5.0, 0.0, 5.0]
    """
    xs = [s[0] for s in key_stations]
    x_min, x_max = xs[0], xs[-1]
    result = []
    for i in range(n):
        t = i / (n - 1)
        x = x_min + t * (x_max - x_min)
        for j in range(len(xs) - 1):
            if xs[j] <= x <= xs[j + 1]:
                span = xs[j + 1] - xs[j]
                frac = (x - xs[j]) / span if span > 0 else 0
                s0, s1 = key_stations[j], key_stations[j + 1]
                lerped = tuple(
                    s0[k] + frac * (s1[k] - s0[k]) for k in range(6)
                )
                result.append(lerped)
                break
    return result


STATIONS = _interpolate_stations(KEY_STATIONS, NUM_INTERP_STATIONS)


def _build_body():
    """
    Command, specific. Smooth-loft dense hexagonal cross-sections into sedan body.

    Uses smooth loft with 60 closely spaced pre-interpolated sections.
    Dense linear pre-interpolation ensures small incremental changes between
    adjacent sections, preventing the spline overshoot artifacts that occur
    with sparse stations and large value jumps.
    """
    with BuildPart() as bp:
        for x, hw, rw, bz, beltz, rz in STATIONS:
            with BuildSketch(Plane.YZ.offset(x)):
                with BuildLine():
                    Polyline(
                        (-hw, bz),
                        (-hw, beltz),
                        (-rw, rz),
                        ( rw, rz),
                        ( hw, beltz),
                        ( hw, bz),
                        (-hw, bz),   # close polygon
                    )
                make_face()
        loft()  # smooth loft — works well with dense pre-interpolated stations
    return bp.part


def _build_wheel(x, y, z):
    """
    Pure function, specific. Single wheel cylinder oriented along Y.

    Args:
        x, y, z (float): World position of wheel center.

    Returns:
        Part: Cylinder along Y axis at the given position.

    Examples:
        >>> # _build_wheel(-55, 35, 13.4) → cylinder at front-left
    """
    return Pos(x, y, z) * (Rot(90, 0, 0) * Cylinder(WHEEL_RADIUS, WHEEL_WIDTH))


def build_altima():
    """
    Command, specific. Assemble complete Nissan Altima model.

    Build order:
    1. Smooth-loft body from 60 interpolated cross-sections
    2. Cut wheel arches (cylinders subtracted from body sides)
    3. Create four wheels positioned outside the body
    4. Combine body + wheels into a Compound

    Returns:
        Compound: Complete car model (body + 4 wheels).
    """
    body = _build_body()

    # Cut wheel arches — one cylinder per side per axle
    for axle_x in [FRONT_AXLE_X, REAR_AXLE_X]:
        for sign in [-1, 1]:
            arch = Pos(axle_x, sign * MAX_HALF_WIDTH, WHEEL_CENTER_Z) * (
                Rot(90, 0, 0) * Cylinder(ARCH_RADIUS, ARCH_CUT_WIDTH)
            )
            body = body - arch

    # Wheels — protrude ~2mm outside body edge
    WHEEL_Y_PROTRUSION = 2.0  # mm outside body edge
    wheel_center_y = MAX_HALF_WIDTH + WHEEL_Y_PROTRUSION - WHEEL_WIDTH / 2

    wheels = []
    for axle_x in [FRONT_AXLE_X, REAR_AXLE_X]:
        for sign in [-1, 1]:
            wheels.append(_build_wheel(axle_x, sign * wheel_center_y, WHEEL_CENTER_Z))

    return Compound([body] + wheels)


# ── Main ──────────────────────────────────────────────────────────────────────

result = build_altima()
stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"Altima -> {stl_path}")
