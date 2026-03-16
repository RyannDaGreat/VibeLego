"""Full integration test through unified parametric worker."""
import os
import sys
import tempfile

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(script_dir, "models", "bricks"))

stl = os.path.join(tempfile.gettempdir(), "_integration_test.stl")

configs = [
    # Backwards compat: Clara-equivalent configs
    ("Clara 2x4", {"studs_x": 2, "studs_y": 4}),
    ("Clara 2x4 chamfer", {"studs_x": 2, "studs_y": 4, "EDGE_STYLE": "CHAMFER"}),
    ("Clara slope", {"studs_x": 2, "studs_y": 4, "enable_slope": True, "slope_plus_y": 3}),
    ("Clara skip_concave", {"studs_x": 2, "studs_y": 4, "SKIP_CONCAVE": True}),
    ("Clara corner_radius", {"studs_x": 2, "studs_y": 4, "enable_corner_radius": True, "corner_radius": 2.0}),
    ("Clara taper", {"studs_x": 2, "studs_y": 4, "taper_height": 2.0, "taper_inset": 0.3}),

    # Backwards compat: LEGO-equivalent configs
    ("LEGO 2x4", {"studs_x": 2, "studs_y": 4, "clutch_type": "TUBE",
                   "STUD_TEXT": "LEGO", "STUD_HEIGHT": 1.8,
                   "enable_corner_radius": False, "enable_wall_taper": False, "enable_stud_taper": False}),
    ("LEGO 2x2 plate", {"studs_x": 2, "studs_y": 2, "clutch_type": "TUBE",
                          "BRICK_HEIGHT": 3.2,
                          "enable_corner_radius": False, "enable_wall_taper": False, "enable_stud_taper": False}),
    ("LEGO slope", {"studs_x": 2, "studs_y": 4, "clutch_type": "TUBE",
                     "enable_slope": True, "slope_plus_y": 3,
                     "enable_corner_radius": False, "enable_wall_taper": False, "enable_stud_taper": False}),
    ("LEGO fillet_bottom", {"studs_x": 2, "studs_y": 4, "clutch_type": "TUBE",
                             "FILLET_BOTTOM": True,
                             "enable_corner_radius": False, "enable_wall_taper": False, "enable_stud_taper": False}),
    ("LEGO skip_concave", {"studs_x": 2, "studs_y": 4, "clutch_type": "TUBE",
                            "SKIP_CONCAVE": True,
                            "enable_corner_radius": False, "enable_wall_taper": False, "enable_stud_taper": False}),

    # New: NONE clutch
    ("Hollow 2x4", {"studs_x": 2, "studs_y": 4, "clutch_type": "NONE",
                     "enable_corner_radius": False, "enable_wall_taper": False, "enable_stud_taper": False}),

    # New: Cross shapes
    ("Cross + LATTICE", {"shape_mode": "CROSS", "studs_plus_x": 2, "studs_minus_x": 2,
                          "studs_plus_y": 2, "studs_minus_y": 2,
                          "cross_width_x": 1, "cross_width_y": 1}),
    ("Cross L TUBE", {"shape_mode": "CROSS", "studs_plus_x": 3, "studs_minus_x": 0,
                       "studs_plus_y": 3, "studs_minus_y": 0,
                       "cross_width_x": 1, "cross_width_y": 1,
                       "clutch_type": "TUBE",
                       "enable_corner_radius": False, "enable_wall_taper": False, "enable_stud_taper": False}),

    # New: 4-dir slopes
    ("Slope -Y", {"studs_x": 2, "studs_y": 4, "enable_slope": True, "slope_minus_y": 3,
                   "enable_corner_radius": False, "enable_wall_taper": False, "enable_stud_taper": False}),
    ("Corner roof", {"studs_x": 4, "studs_y": 4, "enable_slope": True,
                      "slope_minus_x": 3, "slope_minus_y": 3,
                      "enable_corner_radius": False, "enable_wall_taper": False, "enable_stud_taper": False}),
    ("Pyramid", {"studs_x": 4, "studs_y": 4, "enable_slope": True,
                  "slope_plus_x": 3, "slope_minus_x": 3, "slope_plus_y": 3, "slope_minus_y": 3,
                  "enable_corner_radius": False, "enable_wall_taper": False, "enable_stud_taper": False}),

    # Cross + slope combo
    ("Cross + slope", {"shape_mode": "CROSS", "studs_plus_x": 2, "studs_minus_x": 2,
                        "studs_plus_y": 3, "studs_minus_y": 0,
                        "cross_width_x": 1, "cross_width_y": 1,
                        "enable_slope": True, "slope_plus_y": 3,
                        "enable_corner_radius": False, "enable_wall_taper": False, "enable_stud_taper": False}),
]

passed = 0
failed = 0
for name, params in configs:
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
