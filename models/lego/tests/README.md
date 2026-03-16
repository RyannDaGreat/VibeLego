# Clara Brick Geometry Tests

Mathematical proofs that the diagonal lattice clutch geometry is correct.

## Why these tests exist

The lattice strut placement math must guarantee **exact stud fit** — tangent
contact between stud circles and strut edges, with zero overlap and zero gap.
If the math is wrong, bricks won't connect. These tests verify the geometry
algebraically across all brick sizes.

## Running

```bash
python models/lego/tests/test_clara_lattice.py
```

No build123d dependency needed — pure math only.

## What's tested

| Test | What it verifies |
|------|-----------------|
| `test_strut_thickness_positive` | Strut width > 0 for standard dimensions |
| `test_diamond_inscribed_circle_equals_stud` | Diamond opening inscribed circle = STUD_DIAMETER |
| `test_all_studs_tangent_to_nearest_struts` | Every stud tangent to its 4 nearest struts (1x1 through 4x8) |
| `test_no_strut_stud_overlap` | No strut overlaps any stud (1x1 through 8x8) |
| `test_strut_count` | Struts per direction = studs_x + studs_y |
| `test_struts_reach_walls` | Every strut intersects the cavity (no wasted geometry) |
| `test_symmetry` | C-values symmetric around zero |

## Key formula

```
strut_thickness = PITCH / sqrt(2) - STUD_DIAMETER
```

This ensures each diamond opening's inscribed circle exactly equals the stud
diameter. Proof: the perpendicular spacing between struts = PITCH/sqrt(2).
The diamond opening = spacing - thickness = STUD_DIAMETER. QED.
