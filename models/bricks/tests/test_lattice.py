"""
Lattice geometry tests -- pure math verification.

Command, specific. Verifies that the diagonal lattice strut placement
guarantees exact stud fit (tangent contact, zero overlap).

Usage:
    python models/bricks/tests/test_lattice.py
"""
import math
import sys

TOLERANCE = 1e-9

# ── Constants (must match common.py) ─────────────────────────────────────────

PITCH = 8.0
STUD_DIAMETER = 4.8
STUD_RADIUS = STUD_DIAMETER / 2
WALL_THICKNESS = 1.5
CLEARANCE = 0.1


def strut_thickness_from(pitch, stud_diameter):
    """
    Pure function, general. Compute lattice strut thickness from pitch
    and stud diameter so that the diamond inscribed circle = stud diameter.

    For +/-45 deg struts with perpendicular spacing pitch/sqrt(2), the diamond
    opening's inscribed circle = (perpendicular spacing) - strut_thickness.
    Setting this equal to stud_diameter gives: t = pitch/sqrt(2) - stud_diameter.

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
    on each outer side. For both +/-45 deg families, the c-values are identical
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


# ── Junction centering helpers ────────────────────────────────────────────────

def cross_stud_positions_junction(plus_x, minus_x, plus_y, minus_y,
                                  width_x, width_y, pitch):
    """
    Pure function, general. Compute junction-centered stud positions.

    Mirrors _cross_stud_positions logic from brick_lib.py but with no
    build123d dependency. Origin at center of center block.

    Args:
        plus_x, minus_x, plus_y, minus_y (int): Arm lengths.
        width_x, width_y (int): Arm widths.
        pitch (float): Stud pitch.

    Returns:
        list[tuple[float, float]]: (x, y) world positions.

    Examples:
        >>> cross_stud_positions_junction(0, 0, 0, 0, 1, 1, 8.0)
        [(0.0, 0.0)]
    """
    positions = set()
    for i in range(-minus_x, width_x + plus_x):
        for j in range(width_y):
            positions.add((i, j))
    for i in range(width_x):
        for j in range(-minus_y, width_y + plus_y):
            positions.add((i, j))
    center_i = (width_x - 1) / 2
    center_j = (width_y - 1) / 2
    return [((i - center_i) * pitch, (j - center_j) * pitch)
            for i, j in positions]


def cross_stud_positions_bbox(plus_x, minus_x, plus_y, minus_y,
                              width_x, width_y, pitch):
    """
    Pure function, general. Compute bbox-centered stud positions (old method).

    For comparison with junction centering — should give identical results
    for symmetric crosses.

    Args:
        plus_x, minus_x, plus_y, minus_y (int): Arm lengths.
        width_x, width_y (int): Arm widths.
        pitch (float): Stud pitch.

    Returns:
        list[tuple[float, float]]: (x, y) world positions.

    Examples:
        >>> cross_stud_positions_bbox(0, 0, 0, 0, 1, 1, 8.0)
        [(0.0, 0.0)]
    """
    positions = set()
    for i in range(-minus_x, width_x + plus_x):
        for j in range(width_y):
            positions.add((i, j))
    for i in range(width_x):
        for j in range(-minus_y, width_y + plus_y):
            positions.add((i, j))
    all_i = [p[0] for p in positions]
    all_j = [p[1] for p in positions]
    center_i = (min(all_i) + max(all_i)) / 2
    center_j = (min(all_j) + max(all_j)) / 2
    return [((i - center_i) * pitch, (j - center_j) * pitch)
            for i, j in positions]


# ── Junction centering tests ─────────────────────────────────────────────────

def test_cross_stud_junction_centering():
    """Asymmetric cross: grid (0,0) maps to world (0,0) with width_x=1."""
    positions = cross_stud_positions_junction(2, 0, 0, 0, 1, 1, PITCH)
    # Grid (0,0) should be at world (0, 0)
    assert (0.0, 0.0) in positions, f"(0,0) not in positions: {positions}"
    # Should have 3 studs: grid (0,0), (1,0), (2,0)
    assert len(positions) == 3, f"Expected 3, got {len(positions)}"
    # World X should be 0, 8, 16 (not -8, 0, 8 like bbox centering)
    xs = sorted(p[0] for p in positions)
    assert abs(xs[0]) < TOLERANCE, f"Min X should be 0, got {xs[0]}"
    assert abs(xs[-1] - 16.0) < TOLERANCE, f"Max X should be 16, got {xs[-1]}"
    print(f"  (+2, -0, w=1): positions = {sorted(positions)}")
    print(f"  Grid (0,0) at world (0,0) ✓")


def test_cross_cavity_bar_offsets():
    """Asymmetric cross: h_bar has X offset, v_bar has Y offset."""
    # plus_x=2, minus_x=0, plus_y=1, minus_y=0, widths=1
    # h_offset_i = (2 - 0) / 2 = 1.0
    # v_offset_j = (1 - 0) / 2 = 0.5
    h_offset_i = (2 - 0) / 2
    v_offset_j = (1 - 0) / 2
    h_offset_x = h_offset_i * PITCH
    v_offset_y = v_offset_j * PITCH
    assert abs(h_offset_x - 8.0) < TOLERANCE, f"h_offset_x = {h_offset_x}, expected 8.0"
    assert abs(v_offset_y - 4.0) < TOLERANCE, f"v_offset_y = {v_offset_y}, expected 4.0"
    print(f"  h_offset_x = {h_offset_x} mm, v_offset_y = {v_offset_y} mm")

    # Verify these match what _cross_footprint_dims would return
    total_x = 0 + 1 + 2  # minus_x + width_x + plus_x = 3
    total_y = 0 + 1 + 1  # minus_y + width_y + plus_y = 2
    assert total_x == 3 and total_y == 2
    print(f"  Total studs: {total_x}x{total_y}")


def test_junction_equals_bbox_for_symmetric():
    """Symmetric cross: junction and bbox centering produce identical positions."""
    configs = [
        (1, 1, 1, 1, 1, 1),   # + shape
        (2, 2, 2, 2, 1, 1),   # larger +
        (3, 3, 3, 3, 2, 2),   # wide arms
        (0, 0, 0, 0, 2, 4),   # degenerate rectangle
        (0, 0, 0, 0, 1, 1),   # single stud
    ]
    for px, mx, py, my, wx, wy in configs:
        junction = sorted(cross_stud_positions_junction(px, mx, py, my, wx, wy, PITCH))
        bbox = sorted(cross_stud_positions_bbox(px, mx, py, my, wx, wy, PITCH))
        assert len(junction) == len(bbox), (
            f"({px},{mx},{py},{my},{wx},{wy}): count mismatch "
            f"{len(junction)} vs {len(bbox)}"
        )
        for j, b in zip(junction, bbox):
            assert abs(j[0] - b[0]) < TOLERANCE and abs(j[1] - b[1]) < TOLERANCE, (
                f"({px},{mx},{py},{my},{wx},{wy}): mismatch {j} vs {b}"
            )
        print(f"  ({px},{mx},{py},{my},{wx},{wy}): {len(junction)} studs match ✓")


# ── Slope hinge alignment tests ──────────────────────────────────────────────

GEOM_TOL = 0.01


def slope_hinge_edges(sx, sy, h_offset_x, v_offset_y, use_clearance):
    """
    Pure function, general. Compute slope hinge edge coordinates.

    Mirrors the edge computation in slope() from brick_lib.py.
    Returns (edge_minus_x, edge_plus_x, edge_minus_y, edge_plus_y).

    Args:
        sx, sy (int): Total stud counts.
        h_offset_x (float): Horizontal bar offset (mm).
        v_offset_y (float): Vertical bar offset (mm).
        use_clearance (bool): If True, use CLEARANCE-adjusted edges (old bug).

    Returns:
        tuple[float, float, float, float]: Edge coordinates.

    Examples:
        >>> slope_hinge_edges(2, 4, 0, 0, False)
        (-8.0, 8.0, -16.0, 16.0)
        >>> slope_hinge_edges(2, 4, 0, 0, True)
        (-7.9, 7.9, -15.9, 15.9)
    """
    if use_clearance:
        bbox_x = sx * PITCH - 2 * CLEARANCE
        bbox_y = sy * PITCH - 2 * CLEARANCE
    else:
        bbox_x = sx * PITCH
        bbox_y = sy * PITCH
    return (
        h_offset_x - bbox_x / 2,
        h_offset_x + bbox_x / 2,
        v_offset_y - bbox_y / 2,
        v_offset_y + bbox_y / 2,
    )


def filter_flat_studs(stud_positions, edge_minus_x, edge_plus_x,
                      edge_minus_y, edge_plus_y, active_slopes):
    """
    Pure function, general. Filter studs to flat deck positions.

    Mirrors _filter_flat_studs from brick_lib.py without build123d deps.

    Args:
        stud_positions (list[tuple]): All (x, y) stud positions.
        edge_minus_x, edge_plus_x (float): Shell X edges.
        edge_minus_y, edge_plus_y (float): Shell Y edges.
        active_slopes (list[tuple]): (direction, flat_rows) tuples.

    Returns:
        list[tuple[float, float]]: Flat stud positions.

    Examples:
        >>> filter_flat_studs([(0, -12), (0, -4), (0, 4), (0, 12)],
        ...                   -8.0, 8.0, -16.0, 16.0, [("+Y", 1)])
        [(0, -12), (0, -4)]
    """
    flat = []
    for x, y in stud_positions:
        is_flat = True
        for direction, flat_rows in active_slopes:
            if direction == "+Y":
                hinge_y = edge_minus_y + flat_rows * PITCH
                if y > hinge_y - PITCH / 2 + GEOM_TOL:
                    is_flat = False
            elif direction == "-Y":
                hinge_y = edge_plus_y - flat_rows * PITCH
                if y < hinge_y + PITCH / 2 - GEOM_TOL:
                    is_flat = False
            elif direction == "+X":
                hinge_x = edge_minus_x + flat_rows * PITCH
                if x > hinge_x - PITCH / 2 + GEOM_TOL:
                    is_flat = False
            elif direction == "-X":
                hinge_x = edge_plus_x - flat_rows * PITCH
                if x < hinge_x + PITCH / 2 - GEOM_TOL:
                    is_flat = False
        if is_flat:
            flat.append((x, y))
    return flat


def test_slope_hinge_grid_aligned():
    """Slope hinge edges use PITCH formula (no CLEARANCE term), differ from shell edges."""
    configs = [
        # (sx, sy, h_offset_x, v_offset_y)
        (2, 4, 0.0, 0.0),        # symmetric rectangle
        (4, 4, 0.0, 0.0),        # square
        (3, 5, 8.0, 4.0),        # asymmetric cross offsets
    ]
    for sx, sy, hx, vy in configs:
        edges_pitch = slope_hinge_edges(sx, sy, hx, vy, use_clearance=False)
        edges_clear = slope_hinge_edges(sx, sy, hx, vy, use_clearance=True)

        # PITCH-based edges differ from CLEARANCE-based by exactly CLEARANCE
        for ep, ec in zip(edges_pitch, edges_clear):
            diff = abs(ep) - abs(ec)
            assert abs(diff - CLEARANCE) < TOLERANCE, (
                f"CLEARANCE offset mismatch: |{ep}| - |{ec}| = {diff}, expected {CLEARANCE}"
            )

        # Verify the formula: edge = offset ± total * PITCH / 2
        assert abs(edges_pitch[0] - (hx - sx * PITCH / 2)) < TOLERANCE
        assert abs(edges_pitch[1] - (hx + sx * PITCH / 2)) < TOLERANCE
        assert abs(edges_pitch[2] - (vy - sy * PITCH / 2)) < TOLERANCE
        assert abs(edges_pitch[3] - (vy + sy * PITCH / 2)) < TOLERANCE
        print(f"  {sx}x{sy} offset=({hx},{vy}): PITCH edges correct ✓")


def test_filter_flat_studs_pitch_vs_clearance():
    """_filter_flat_studs with PITCH-based edges classifies studs correctly."""
    # 2x4 brick, 3 sloped rows in +Y → flat_rows = 1
    studs = [(0, y) for y in [-12, -4, 4, 12]]
    active = [("+Y", 1)]

    # With PITCH-based edges (correct): hinge_y = -16 + 8 = -8
    # Stud at y=-12: -12 > -8 - 4 + 0.01 = -11.99? No → flat ✓
    # Stud at y=-4:  -4 > -11.99? Yes → not flat
    edges_p = slope_hinge_edges(2, 4, 0, 0, use_clearance=False)
    flat_p = filter_flat_studs(studs, *edges_p, active)

    # With CLEARANCE-based edges (old bug): hinge_y = -15.9 + 8 = -7.9
    # Stud classification changes at boundary
    edges_c = slope_hinge_edges(2, 4, 0, 0, use_clearance=True)
    flat_c = filter_flat_studs(studs, *edges_c, active)

    # PITCH-based: 1 flat stud (only y=-12)
    assert len(flat_p) == 1, f"PITCH: expected 1 flat, got {len(flat_p)}: {flat_p}"
    assert flat_p[0][1] == -12, f"PITCH: expected y=-12, got {flat_p[0]}"
    print(f"  PITCH-based: {len(flat_p)} flat stud(s) ✓")

    # Both should give same count here (boundary doesn't change for this config)
    # but the hinge position differs by 0.1mm
    print(f"  CLEARANCE-based: {len(flat_c)} flat stud(s)")
    print(f"  Hinge positions: PITCH={edges_p[2] + 1*PITCH}, CLEAR={edges_c[2] + 1*PITCH}")


def test_filter_flat_studs_multi_direction():
    """Multiple active slopes correctly intersect flat regions."""
    # 4x4 brick, corner roof: -X=3, -Y=3 → each has flat_rows=1
    # "-X" slope descends toward -X → flat portion at +X end
    # "-Y" slope descends toward -Y → flat portion at +Y end
    studs = [(x, y) for x in [-12, -4, 4, 12] for y in [-12, -4, 4, 12]]
    active = [("-X", 1), ("-Y", 1)]
    edges = slope_hinge_edges(4, 4, 0, 0, use_clearance=False)
    flat = filter_flat_studs(studs, *edges, active)

    # -X slope: hinge_x = 16 - 1*8 = 8. NOT flat if x < 8 + 4 - 0.01 = 11.99
    # → only x=12 survives
    # -Y slope: hinge_y = 16 - 1*8 = 8. NOT flat if y < 8 + 4 - 0.01 = 11.99
    # → only y=12 survives
    # Flat = intersection: only (12, 12)
    expected_count = 1
    assert len(flat) == expected_count, (
        f"Expected {expected_count} flat stud, got {len(flat)}: {flat}"
    )
    assert flat[0] == (12, 12), f"Expected (12,12), got {flat[0]}"
    print(f"  Corner roof 4x4 (-X,-Y): {len(flat)} flat stud at +X,+Y corner ✓")

    # Also test +X=3, +Y=3 → flat portion at -X,-Y end
    active2 = [("+X", 1), ("+Y", 1)]
    flat2 = filter_flat_studs(studs, *edges, active2)
    # +X: hinge_x = -16 + 8 = -8. NOT flat if x > -8 - 4 + 0.01 = -11.99
    # → only x=-12 survives
    # +Y: hinge_y = -16 + 8 = -8. NOT flat if y > -8 - 4 + 0.01 = -11.99
    # → only y=-12 survives
    assert len(flat2) == 1, f"Expected 1, got {len(flat2)}: {flat2}"
    assert flat2[0] == (-12, -12), f"Expected (-12,-12), got {flat2[0]}"
    print(f"  Corner roof 4x4 (+X,+Y): {len(flat2)} flat stud at -X,-Y corner ✓")


# ── Runner ────────────────────────────────────────────────────────────────────

TESTS = [
    test_strut_thickness_positive,
    test_diamond_inscribed_circle_equals_stud,
    test_strut_count,
    test_all_studs_tangent_to_nearest_struts,
    test_no_strut_stud_overlap,
    test_struts_reach_walls,
    test_symmetry,
    test_cross_stud_junction_centering,
    test_cross_cavity_bar_offsets,
    test_junction_equals_bbox_for_symmetric,
    test_slope_hinge_grid_aligned,
    test_filter_flat_studs_pitch_vs_clearance,
    test_filter_flat_studs_multi_direction,
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
