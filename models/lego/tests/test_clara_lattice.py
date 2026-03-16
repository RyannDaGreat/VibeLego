"""
Clara brick lattice geometry tests — pure math verification.

Command, specific. Verifies that the diagonal lattice strut placement
guarantees exact stud fit (tangent contact, zero overlap).

Usage:
    python models/lego/tests/test_clara_lattice.py
"""
import math
import sys

TOLERANCE = 1e-9

# ── Constants (must match lego_lib.py) ────────────────────────────────────────

PITCH = 8.0
STUD_DIAMETER = 4.8
STUD_RADIUS = STUD_DIAMETER / 2
WALL_THICKNESS = 1.5
CLEARANCE = 0.1


def strut_thickness_from(pitch, stud_diameter):
    """
    Pure function, general. Compute lattice strut thickness from pitch
    and stud diameter so that the diamond inscribed circle = stud diameter.

    For ±45° struts with perpendicular spacing pitch/√2, the diamond opening's
    inscribed circle = (perpendicular spacing) − strut_thickness. Setting this
    equal to stud_diameter gives: t = pitch/√2 − stud_diameter.

    Args:
        pitch (float): Stud center-to-center distance (mm).
        stud_diameter (float): Stud outer diameter (mm).

    Returns:
        float: Strut thickness (mm).

    Examples:
        >>> abs(strut_thickness_from(8.0, 4.8) - 0.8569) < 0.001
        True
        >>> strut_thickness_from(10.0, 0.0)  # no studs: struts fill all space
        7.0710678118654755
    """
    return pitch / math.sqrt(2) - stud_diameter


def strut_c_values(studs_x, studs_y, pitch):
    """
    Pure function, general. Compute the c-values for lattice strut center lines.

    Struts are positioned midway between adjacent stud diagonals, plus one
    on each outer side. For both ±45° families, the c-values are identical
    (symmetric grid).

    Args:
        studs_x (int): Number of studs along X.
        studs_y (int): Number of studs along Y.
        pitch (float): Stud pitch (mm).

    Returns:
        list[float]: Sorted list of c-values.

    Examples:
        >>> strut_c_values(2, 4, 8.0)
        [-20.0, -12.0, -4.0, 4.0, 12.0, 20.0]
        >>> strut_c_values(1, 1, 8.0)
        [-4.0, 4.0]
    """
    n = studs_x + studs_y
    c_start = -(n - 1) / 2 * pitch
    return [c_start + i * pitch for i in range(n)]


def stud_to_strut_gap(stud_x, stud_y, strut_c, strut_family, strut_t):
    """
    Pure function, general. Compute gap between a stud circle edge and the
    nearest edge of a strut.

    Positive = clearance. Zero = tangent. Negative = overlap.

    Args:
        stud_x (float): Stud center X (mm).
        stud_y (float): Stud center Y (mm).
        strut_c (float): Strut center-line c-value.
        strut_family (str): "+45" or "-45".
        strut_t (float): Strut thickness (mm).

    Returns:
        float: Gap distance (mm). 0 = tangent, <0 = overlap.

    Examples:
        >>> abs(stud_to_strut_gap(0, 0, 4.0, "+45", 0.857) - 0.0) < 0.01
        True
    """
    if strut_family == "+45":
        perp_dist = abs(stud_y - stud_x - strut_c) / math.sqrt(2)
    elif strut_family == "-45":
        perp_dist = abs(stud_y + stud_x - strut_c) / math.sqrt(2)
    else:
        raise ValueError(f"Unknown strut family: {strut_family}")
    return perp_dist - strut_t / 2 - STUD_RADIUS


def stud_positions(studs_x, studs_y, pitch):
    """
    Pure function, general. Compute stud center positions.

    Args:
        studs_x (int): Studs along X.
        studs_y (int): Studs along Y.
        pitch (float): Stud pitch (mm).

    Returns:
        list[tuple[float, float]]: (x, y) positions.

    Examples:
        >>> stud_positions(1, 1, 8.0)
        [(0.0, 0.0)]
        >>> len(stud_positions(2, 4, 8.0))
        8
    """
    return [
        ((i - (studs_x - 1) / 2) * pitch,
         (j - (studs_y - 1) / 2) * pitch)
        for i in range(studs_x)
        for j in range(studs_y)
    ]


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_strut_thickness_positive():
    """Strut thickness must be positive for standard dimensions."""
    t = strut_thickness_from(PITCH, STUD_DIAMETER)
    assert t > 0, f"Strut thickness {t} <= 0"
    print(f"  strut thickness = {t:.4f} mm > 0")


def test_diamond_inscribed_circle_equals_stud():
    """Diamond opening inscribed circle must equal STUD_DIAMETER."""
    t = strut_thickness_from(PITCH, STUD_DIAMETER)
    perp_spacing = PITCH / math.sqrt(2)
    inscribed_diameter = perp_spacing - t
    error = abs(inscribed_diameter - STUD_DIAMETER)
    assert error < TOLERANCE, f"Inscribed circle {inscribed_diameter} != STUD_DIAMETER {STUD_DIAMETER}"
    print(f"  inscribed circle diameter = {inscribed_diameter:.6f}, stud = {STUD_DIAMETER}")


def test_all_studs_tangent_to_nearest_struts():
    """Every stud must be tangent (zero gap) to its 4 nearest struts."""
    t = strut_thickness_from(PITCH, STUD_DIAMETER)
    sizes = [(1, 1), (1, 2), (1, 4), (2, 2), (2, 4), (4, 4), (4, 8)]
    for sx, sy in sizes:
        studs = stud_positions(sx, sy, PITCH)
        c_vals = strut_c_values(sx, sy, PITCH)
        for stud_x, stud_y in studs:
            # Find 2 nearest +45 struts and 2 nearest -45 struts
            gaps_plus = sorted(
                (stud_to_strut_gap(stud_x, stud_y, c, "+45", t), c)
                for c in c_vals
            )
            gaps_minus = sorted(
                (stud_to_strut_gap(stud_x, stud_y, c, "-45", t), c)
                for c in c_vals
            )
            # Two nearest +45 struts should be tangent
            for gap, c in gaps_plus[:2]:
                assert abs(gap) < TOLERANCE, (
                    f"{sx}x{sy} stud ({stud_x},{stud_y}): +45 strut c={c} gap={gap}"
                )
            # Two nearest -45 struts should be tangent
            for gap, c in gaps_minus[:2]:
                assert abs(gap) < TOLERANCE, (
                    f"{sx}x{sy} stud ({stud_x},{stud_y}): -45 strut c={c} gap={gap}"
                )
        print(f"  {sx}x{sy}: all {len(studs)} studs tangent to nearest struts")


def test_no_strut_stud_overlap():
    """No strut may overlap any stud (gap >= 0 everywhere)."""
    t = strut_thickness_from(PITCH, STUD_DIAMETER)
    sizes = [(1, 1), (2, 4), (4, 8), (8, 8)]
    for sx, sy in sizes:
        studs = stud_positions(sx, sy, PITCH)
        c_vals = strut_c_values(sx, sy, PITCH)
        min_gap = float("inf")
        for stud_x, stud_y in studs:
            for c in c_vals:
                for family in ["+45", "-45"]:
                    gap = stud_to_strut_gap(stud_x, stud_y, c, family, t)
                    min_gap = min(min_gap, gap)
                    assert gap >= -TOLERANCE, (
                        f"{sx}x{sy} stud ({stud_x},{stud_y}): "
                        f"{family} strut c={c} OVERLAP gap={gap}"
                    )
        print(f"  {sx}x{sy}: min gap = {min_gap:.9f} (no overlaps)")


def test_strut_count():
    """Number of struts per direction = studs_x + studs_y."""
    for sx, sy in [(1, 1), (2, 4), (4, 4), (8, 16)]:
        c_vals = strut_c_values(sx, sy, PITCH)
        expected = sx + sy
        assert len(c_vals) == expected, f"{sx}x{sy}: got {len(c_vals)}, want {expected}"
        print(f"  {sx}x{sy}: {len(c_vals)} struts per direction")


def test_struts_reach_walls():
    """Every strut must intersect the cavity rectangle (no wasted struts)."""
    t = strut_thickness_from(PITCH, STUD_DIAMETER)
    sizes = [(2, 4), (1, 2), (4, 4)]
    for sx, sy in sizes:
        inner_x = sx * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
        inner_y = sy * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
        half_x, half_y = inner_x / 2, inner_y / 2
        c_vals = strut_c_values(sx, sy, PITCH)
        for c in c_vals:
            # +45 line y - x = c: check if it crosses the rectangle
            # At x = half_x: y = c + half_x. At x = -half_x: y = c - half_x.
            y_at_right = c + half_x
            y_at_left = c - half_x
            crosses_plus = (
                (-half_y <= y_at_right <= half_y) or
                (-half_y <= y_at_left <= half_y) or
                (y_at_left < -half_y and y_at_right > half_y) or
                (y_at_left > half_y and y_at_right < -half_y)
            )
            # -45 line y + x = c: At x = half_x: y = c - half_x
            y_at_right_m = c - half_x
            y_at_left_m = c + half_x
            crosses_minus = (
                (-half_y <= y_at_right_m <= half_y) or
                (-half_y <= y_at_left_m <= half_y) or
                (y_at_right_m < -half_y and y_at_left_m > half_y) or
                (y_at_right_m > half_y and y_at_left_m < -half_y)
            )
            assert crosses_plus, f"{sx}x{sy}: +45 strut c={c} doesn't cross cavity"
            assert crosses_minus, f"{sx}x{sy}: -45 strut c={c} doesn't cross cavity"
        print(f"  {sx}x{sy}: all {len(c_vals)} struts cross cavity in both directions")


def test_symmetry():
    """C-values must be symmetric around 0."""
    for sx, sy in [(1, 1), (2, 4), (3, 3), (4, 8)]:
        c_vals = strut_c_values(sx, sy, PITCH)
        for c in c_vals:
            assert -c in c_vals, f"{sx}x{sy}: c={c} has no mirror at c={-c}"
        print(f"  {sx}x{sy}: c-values symmetric")


# ── Runner ────────────────────────────────────────────────────────────────────

TESTS = [
    test_strut_thickness_positive,
    test_diamond_inscribed_circle_equals_stud,
    test_strut_count,
    test_all_studs_tangent_to_nearest_struts,
    test_no_strut_stud_overlap,
    test_struts_reach_walls,
    test_symmetry,
]

if __name__ == "__main__":
    passed = 0
    failed = 0
    for test in TESTS:
        name = test.__name__
        print(f"\n{name}:")
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1

    print(f"\n{'=' * 40}")
    print(f"{passed} passed, {failed} failed, {passed + failed} total")
    sys.exit(1 if failed else 0)
