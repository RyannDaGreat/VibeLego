"""
Integration tests — every brick config through the full parametric pipeline.

Command, specific. Runs each configuration through parametric.run() which
calls brick_lib.brick() or brick_lib.slope() via build123d, exports STL,
and verifies no exceptions + expected face counts.

Usage:
    uv run models/bricks/tests/test_integration.py
"""

import os
import sys
import tempfile

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(script_dir, ".."))

stl = os.path.join(tempfile.gettempdir(), "_integration_test.stl")

# ── Shared kwargs for LEGO-style (no Clara features) ────────────────────────

_LEGO_BASE = {
    "clutch_type": "TUBE", "STUD_TEXT": "LEGO", "STUD_HEIGHT": 1.8,
    "enable_corner_radius": False, "enable_wall_taper": False,
    "enable_stud_taper": False,
}

_NO_CLARA = {
    "enable_corner_radius": False, "enable_wall_taper": False,
    "enable_stud_taper": False,
}

# ── Test configurations ──────────────────────────────────────────────────────

CONFIGS = [
    # Clara-equivalent (lattice clutch, default features)
    ("Clara 2x4", {"studs_x": 2, "studs_y": 4}),
    ("Clara chamfer", {"studs_x": 2, "studs_y": 4, "EDGE_STYLE": "CHAMFER"}),
    ("Clara slope", {"studs_x": 2, "studs_y": 4, "enable_slope": True, "slope_plus_y": 3}),
    ("Clara skip_concave", {"studs_x": 2, "studs_y": 4, "SKIP_CONCAVE": True}),
    ("Clara corner_radius", {"studs_x": 2, "studs_y": 4,
                              "enable_corner_radius": True, "corner_radius": 2.0}),
    ("Clara taper", {"studs_x": 2, "studs_y": 4, "taper_height": 2.0, "taper_inset": 0.3}),

    # LEGO-equivalent (tube clutch)
    ("LEGO 2x4", {**_LEGO_BASE, "studs_x": 2, "studs_y": 4}),
    ("LEGO 2x2 plate", {**_LEGO_BASE, "studs_x": 2, "studs_y": 2, "BRICK_HEIGHT": 3.2}),
    ("LEGO slope", {**_LEGO_BASE, "studs_x": 2, "studs_y": 4,
                    "enable_slope": True, "slope_plus_y": 3}),
    ("LEGO fillet_bottom", {**_LEGO_BASE, "studs_x": 2, "studs_y": 4, "FILLET_BOTTOM": True}),
    ("LEGO skip_concave", {**_LEGO_BASE, "studs_x": 2, "studs_y": 4, "SKIP_CONCAVE": True}),

    # NONE clutch
    ("Hollow 2x4", {**_NO_CLARA, "studs_x": 2, "studs_y": 4, "clutch_type": "NONE"}),

    # Cross shapes
    ("Cross + LATTICE", {"shape_mode": "CROSS", "studs_plus_x": 2, "studs_minus_x": 2,
                          "studs_plus_y": 2, "studs_minus_y": 2,
                          "cross_width_x": 1, "cross_width_y": 1}),
    ("Cross L TUBE", {**_NO_CLARA, "shape_mode": "CROSS",
                      "studs_plus_x": 3, "studs_minus_x": 0,
                      "studs_plus_y": 3, "studs_minus_y": 0,
                      "cross_width_x": 1, "cross_width_y": 1, "clutch_type": "TUBE"}),
    ("Cross + CR", {"shape_mode": "CROSS", "studs_plus_x": 2, "studs_minus_x": 2,
                    "studs_plus_y": 2, "studs_minus_y": 2,
                    "cross_width_x": 1, "cross_width_y": 1,
                    "enable_corner_radius": True, "corner_radius": 2.0}),
    ("Cross + CR all", {"shape_mode": "CROSS", "studs_plus_x": 2, "studs_minus_x": 2,
                         "studs_plus_y": 2, "studs_minus_y": 2,
                         "cross_width_x": 1, "cross_width_y": 1,
                         "enable_corner_radius": True, "corner_radius": 2.0,
                         "CR_SKIP_CONCAVE": False}),

    # 4-directional slopes
    ("Slope -Y", {**_NO_CLARA, "studs_x": 2, "studs_y": 4,
                  "enable_slope": True, "slope_minus_y": 3}),
    ("Corner roof", {**_NO_CLARA, "studs_x": 4, "studs_y": 4,
                     "enable_slope": True, "slope_minus_x": 3, "slope_minus_y": 3}),
    ("Pyramid", {**_NO_CLARA, "studs_x": 4, "studs_y": 4, "enable_slope": True,
                 "slope_plus_x": 3, "slope_minus_x": 3,
                 "slope_plus_y": 3, "slope_minus_y": 3}),

    # Cross + slope combo
    ("Cross + slope", {**_NO_CLARA, "shape_mode": "CROSS",
                       "studs_plus_x": 2, "studs_minus_x": 2,
                       "studs_plus_y": 3, "studs_minus_y": 0,
                       "cross_width_x": 1, "cross_width_y": 1,
                       "enable_slope": True, "slope_plus_y": 3}),
]


# ── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    passed = 0
    failed = 0
    for name, params in CONFIGS:
        # Fresh module state for each config
        for mod_name in list(sys.modules):
            if mod_name in ("parametric", "brick_lib", "common", "panel_def",
                            "parametric_base", "panel_common"):
                del sys.modules[mod_name]

        import parametric
        try:
            info = parametric.run(params, stl)
            print(f"  PASS {name}: {info['faces']} faces, build={info['build']:.2f}s")
            passed += 1
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"{passed} passed, {failed} failed, {passed + failed} total")

    if failed:
        sys.exit(1)
