"""Test: per-arm lattice build with 2D clipping, then union."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "models", "bricks"))

from build123d import (
    Box, Rectangle, Pos, Rot, Align, Mode,
    BuildPart, BuildSketch, extrude, Locations,
)
import brick_lib
from common import PITCH, CLEARANCE, WALL_THICKNESS, FLOOR_THICKNESS, BRICK_HEIGHT
import math

plus_x, minus_x, plus_y, minus_y = 3, 0, 3, 0
width_x, width_y = 1, 1
height = BRICK_HEIGHT
cavity_z = height - FLOOR_THICKNESS

dims = brick_lib._cross_footprint_dims(plus_x, minus_x, plus_y, minus_y, width_x, width_y)
sx, sy = dims["total_x"], dims["total_y"]
inner_x = sx * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
inner_y = sy * PITCH - 2 * CLEARANCE - 2 * WALL_THICKNESS
wt = WALL_THICKNESS

h_w = dims["h_bar_x"] * PITCH - 2 * CLEARANCE - 2 * wt
h_h = dims["h_bar_y"] * PITCH - 2 * CLEARANCE - 2 * wt
v_w = dims["v_bar_x"] * PITCH - 2 * CLEARANCE - 2 * wt
v_h = dims["v_bar_y"] * PITCH - 2 * CLEARANCE - 2 * wt
h_offset_y = (minus_y - plus_y) / 2 * PITCH
v_offset_x = (minus_x - plus_x) / 2 * PITCH

# Build strut parameters
strut_thickness = PITCH / math.sqrt(2) - brick_lib.STUD_DIAMETER
n_struts = sx + sy
strut_len = (inner_x + inner_y) * 2
c_start = -(n_struts - 1) / 2 * PITCH
c_values = [c_start + i * PITCH for i in range(n_struts)]

def _strut_sketch():
    """Add lattice strut rectangles to current BuildSketch context."""
    for c in c_values:
        with Locations([Pos(-c / 2, c / 2) * Rot(0, 0, 45)]):
            Rectangle(strut_len, strut_thickness)
        with Locations([Pos(c / 2, c / 2) * Rot(0, 0, -45)]):
            Rectangle(strut_len, strut_thickness)

# Approach: build per-arm lattice, clip each in 2D, then union
with BuildPart() as h_lat:
    with BuildSketch():
        _strut_sketch()
        with Locations([Pos(0, h_offset_y)]):
            Rectangle(h_w, h_h, mode=Mode.INTERSECT)
    extrude(amount=cavity_z)

with BuildPart() as v_lat:
    with BuildSketch():
        _strut_sketch()
        with Locations([Pos(v_offset_x, 0)]):
            Rectangle(v_w, v_h, mode=Mode.INTERSECT)
    extrude(amount=cavity_z)

lattice = h_lat.part + v_lat.part
print(f"Per-arm lattice volume: {lattice.volume:.1f}")

# Check empty quadrant
with BuildPart() as eq:
    Pos(-9.6, -9.6, 0) * Box(24, 24, cavity_z,
                              align=(Align.MIN, Align.MIN, Align.MIN))
empty_quad = eq.part
leaked = lattice & empty_quad
print(f"Empty quadrant volume: {leaked.volume:.1f}")

# Also test: degenerate rectangle (plus_x=0, minus_x=0, width_x=2, width_y=4)
# Should produce same lattice as _build_lattice(2, 4, ...)
dims_rect = brick_lib._cross_footprint_dims(0, 0, 0, 0, 2, 4)
rect_inner_x = 2 * PITCH - 2 * CLEARANCE - 2 * wt
rect_inner_y = 4 * PITCH - 2 * CLEARANCE - 2 * wt

# Original rectangle lattice
rect_lattice = brick_lib._build_lattice(2, 4, rect_inner_x, rect_inner_y, cavity_z)
print(f"\nOriginal rect lattice volume: {rect_lattice.volume:.1f}")

# Per-arm for degenerate rectangle
rh_w = dims_rect["h_bar_x"] * PITCH - 2 * CLEARANCE - 2 * wt
rh_h = dims_rect["h_bar_y"] * PITCH - 2 * CLEARANCE - 2 * wt
rv_w = dims_rect["v_bar_x"] * PITCH - 2 * CLEARANCE - 2 * wt
rv_h = dims_rect["v_bar_y"] * PITCH - 2 * CLEARANCE - 2 * wt
rh_offset_y = 0.0
rv_offset_x = 0.0

r_strut_thickness = PITCH / math.sqrt(2) - brick_lib.STUD_DIAMETER
r_n = 2 + 4  # studs_x + studs_y
r_strut_len = (rect_inner_x + rect_inner_y) * 2
r_c_start = -(r_n - 1) / 2 * PITCH
r_c_values = [r_c_start + i * PITCH for i in range(r_n)]

def _rect_struts():
    for c in r_c_values:
        with Locations([Pos(-c / 2, c / 2) * Rot(0, 0, 45)]):
            Rectangle(r_strut_len, r_strut_thickness)
        with Locations([Pos(c / 2, c / 2) * Rot(0, 0, -45)]):
            Rectangle(r_strut_len, r_strut_thickness)

with BuildPart() as rh:
    with BuildSketch():
        _rect_struts()
        Rectangle(rh_w, rh_h, mode=Mode.INTERSECT)
    extrude(amount=cavity_z)

with BuildPart() as rv:
    with BuildSketch():
        _rect_struts()
        Rectangle(rv_w, rv_h, mode=Mode.INTERSECT)
    extrude(amount=cavity_z)

rect_via_cross = rh.part + rv.part
print(f"Rect via cross lattice volume: {rect_via_cross.volume:.1f}")
print(f"Volume match: {abs(rect_lattice.volume - rect_via_cross.volume) < 1.0}")
