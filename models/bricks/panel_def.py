"""
Unified brick panel definition — all clutch systems + cross shapes + 4-dir slopes.

Query, specific. Pure data module (no bpy or build123d imports). Declares all
parametric brick dimensions, ranges, and panel layout sections. Consumed by
blender_watcher.py's generic panel builder.

Replaces the separate lego/panel_def.py and clara/panel_def.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from panel_common import (
    WALLS_SECTION, text_section, FILLET_SECTION,
    classify_face, ANATOMY_COLORS, ANATOMY_REGION_ITEMS, ANATOMY_REGION_GROUPS,
)

# Relative to this file's directory
PARAMETRIC_SCRIPT = "parametric.py"

SECTIONS = [
    # ── Shape ────────────────────────────────────────────────────────────────
    {
        "label": "Shape",
        "icon": "MESH_CUBE",
        "params": [
            {
                "key": "shape_mode", "json_key": "shape_mode", "type": "enum",
                "label": "Mode", "default": "RECTANGLE",
                "items": [
                    ("RECTANGLE", "Rectangle", "Standard rectangular brick"),
                    ("CROSS", "Cross", "L/T/+ cross-shaped brick"),
                ],
            },
            # RECTANGLE mode params
            {
                "key": "studs_x", "json_key": "studs_x", "type": "int",
                "label": "Studs X", "default": 2, "min": 1, "max": 16,
            },
            {
                "key": "studs_y", "json_key": "studs_y", "type": "int",
                "label": "Studs Y", "default": 4, "min": 1, "max": 16,
            },
            # CROSS mode params
            {
                "key": "studs_plus_x", "json_key": "studs_plus_x", "type": "int",
                "label": "+X Arm", "default": 2, "min": 0, "max": 16,
                "description": "Arm length extending in +X from center block",
            },
            {
                "key": "studs_minus_x", "json_key": "studs_minus_x", "type": "int",
                "label": "-X Arm", "default": 2, "min": 0, "max": 16,
                "description": "Arm length extending in -X from center block",
            },
            {
                "key": "studs_plus_y", "json_key": "studs_plus_y", "type": "int",
                "label": "+Y Arm", "default": 2, "min": 0, "max": 16,
                "description": "Arm length extending in +Y from center block",
            },
            {
                "key": "studs_minus_y", "json_key": "studs_minus_y", "type": "int",
                "label": "-Y Arm", "default": 2, "min": 0, "max": 16,
                "description": "Arm length extending in -Y from center block",
            },
            {
                "key": "cross_width_x", "json_key": "cross_width_x", "type": "int",
                "label": "Width X", "default": 1, "min": 1, "max": 8,
                "description": "Width of Y-axis arms in X direction (studs)",
            },
            {
                "key": "cross_width_y", "json_key": "cross_width_y", "type": "int",
                "label": "Width Y", "default": 1, "min": 1, "max": 8,
                "description": "Width of X-axis arms in Y direction (studs)",
            },
        ],
        "rows": [["studs_x", "studs_y"]],
        "visible_when": {
            "studs_x": {"shape_mode": "RECTANGLE"},
            "studs_y": {"shape_mode": "RECTANGLE"},
            "studs_plus_x": {"shape_mode": "CROSS"},
            "studs_minus_x": {"shape_mode": "CROSS"},
            "studs_plus_y": {"shape_mode": "CROSS"},
            "studs_minus_y": {"shape_mode": "CROSS"},
            "cross_width_x": {"shape_mode": "CROSS"},
            "cross_width_y": {"shape_mode": "CROSS"},
        },
    },
    # ── Slope (4-directional) ────────────────────────────────────────────────
    {
        "label": "Slope",
        "icon": "MESH_CONE",
        "enable_key": "enable_slope",
        "params": [
            {
                "key": "enable_slope", "json_key": "enable_slope",
                "type": "bool", "label": "Enable", "default": False,
            },
            {
                "key": "slope_plus_y", "json_key": "slope_plus_y", "type": "int",
                "label": "+Y Sloped Rows", "default": 0, "min": 0, "max": 8,
                "description": "Number of rows sloped toward +Y (0 = no slope)",
            },
            {
                "key": "slope_minus_y", "json_key": "slope_minus_y", "type": "int",
                "label": "-Y Sloped Rows", "default": 0, "min": 0, "max": 8,
                "description": "Number of rows sloped toward -Y (0 = no slope)",
            },
            {
                "key": "slope_plus_x", "json_key": "slope_plus_x", "type": "int",
                "label": "+X Sloped Rows", "default": 0, "min": 0, "max": 8,
                "description": "Number of rows sloped toward +X (0 = no slope)",
            },
            {
                "key": "slope_minus_x", "json_key": "slope_minus_x", "type": "int",
                "label": "-X Sloped Rows", "default": 0, "min": 0, "max": 8,
                "description": "Number of rows sloped toward -X (0 = no slope)",
            },
            {
                "key": "slope_min_z", "json_key": "slope_min_z", "type": "float",
                "label": "Slope Floor", "default": 1.5, "min": 0.0, "max": 5.0,
                "step": 10, "precision": 2,
                "description": "Z height where slope terminates (0 = sharp edge to ground)",
            },
        ],
    },
    # ── Studs & Body ─────────────────────────────────────────────────────────
    {
        "label": "Studs & Body",
        "icon": "ARROW_LEFTRIGHT",
        "params": [
            {
                "key": "pitch", "json_key": "PITCH", "type": "float",
                "label": "Stud Spacing", "default": 8.0, "min": 1.0, "max": 20.0,
                "step": 10, "precision": 2,
                "description": "Distance between stud centers (mm)",
            },
            {
                "key": "stud_diameter", "json_key": "STUD_DIAMETER", "type": "float",
                "label": "Stud Diameter", "default": 4.8, "min": 1.0, "max": 10.0,
                "step": 10, "precision": 2,
            },
            {
                "key": "stud_height", "json_key": "STUD_HEIGHT", "type": "float",
                "label": "Stud Height", "default": 4.0, "min": 0.5, "max": 8.0,
                "step": 10, "precision": 2,
            },
            {
                "key": "brick_height", "json_key": "BRICK_HEIGHT", "type": "float",
                "label": "Brick Height", "default": 9.6, "min": 2.0, "max": 30.0,
                "step": 10, "precision": 2,
            },
        ],
    },
    # ── Walls ────────────────────────────────────────────────────────────────
    WALLS_SECTION,
    # ── Clutch ───────────────────────────────────────────────────────────────
    {
        "label": "Clutch",
        "icon": "MESH_CYLINDER",
        "params": [
            {
                "key": "clutch_type", "json_key": "clutch_type", "type": "enum",
                "label": "Type", "default": "LATTICE",
                "items": [
                    ("TUBE", "Tubes", "LEGO-style anti-stud tubes + ridges"),
                    ("LATTICE", "Lattice", "Diagonal crisscross struts"),
                    ("NONE", "None", "Hollow shell (no internal features)"),
                ],
            },
            {
                "key": "tube_outer_diameter", "json_key": "TUBE_OUTER_DIAMETER",
                "type": "float", "label": "Tube Outer Dia",
                "default": 6.31, "min": 2.0, "max": 12.0, "step": 10, "precision": 2,
            },
            {
                "key": "tube_inner_diameter", "json_key": "TUBE_INNER_DIAMETER",
                "type": "float", "label": "Tube Inner Dia",
                "default": 4.8, "min": 1.0, "max": 10.0, "step": 10, "precision": 2,
            },
            {
                "key": "ridge_width", "json_key": "RIDGE_WIDTH", "type": "float",
                "label": "Ridge Width", "default": 0.8, "min": 0.1, "max": 3.0,
                "step": 10, "precision": 2,
            },
            {
                "key": "ridge_height", "json_key": "RIDGE_HEIGHT", "type": "float",
                "label": "Ridge Height", "default": 0.8, "min": 0.1, "max": 3.0,
                "step": 10, "precision": 2,
            },
        ],
        "visible_when": {
            "tube_outer_diameter": {"clutch_type": "TUBE"},
            "tube_inner_diameter": {"clutch_type": "TUBE"},
            "ridge_width": {"clutch_type": "TUBE"},
            "ridge_height": {"clutch_type": "TUBE"},
        },
    },
    # ── Corner Radius (was Clara-only, now general) ──────────────────────────
    {
        "label": "Corner Radius",
        "icon": "MOD_BEVEL",
        "enable_key": "enable_corner_radius",
        "params": [
            {
                "key": "enable_corner_radius", "json_key": "enable_corner_radius",
                "type": "bool", "label": "Enable", "default": True,
            },
            {
                "key": "corner_radius", "json_key": "corner_radius", "type": "float",
                "label": "Radius", "default": 2.0, "min": 0.1, "max": 4.0,
                "step": 10, "precision": 2,
                "description": "2D corner rounding of brick outline (like CSS border-radius)",
            },
        ],
    },
    # ── Wall Taper (was Clara-only, now general) ─────────────────────────────
    {
        "label": "Wall Taper",
        "icon": "SORT_DESC",
        "enable_key": "enable_wall_taper",
        "params": [
            {
                "key": "enable_wall_taper", "json_key": "enable_wall_taper",
                "type": "bool", "label": "Enable", "default": True,
            },
            {
                "key": "taper_height", "json_key": "taper_height", "type": "float",
                "label": "Height", "default": 2.0, "min": 0.1, "max": 5.0,
                "step": 10, "precision": 2,
                "description": "How far down from top the wall taper begins (mm)",
            },
            {
                "key": "taper_inset", "json_key": "taper_inset", "type": "float",
                "label": "Inset", "default": 0.5, "min": 0.01, "max": 2.0,
                "step": 10, "precision": 2,
                "description": "How far walls narrow at the top (mm per side)",
            },
            {
                "key": "taper_curve", "json_key": "taper_curve", "type": "enum",
                "label": "Curve", "default": "LINEAR",
                "items": [
                    ("LINEAR", "Linear", "Straight-line taper"),
                    ("CURVED", "Curved", "Quarter-circle: tangent to wall at bottom, tangent to deck at top"),
                ],
            },
        ],
    },
    # ── Stud Taper (was Clara-only, now general) ─────────────────────────────
    {
        "label": "Stud Taper",
        "icon": "SORT_DESC",
        "enable_key": "enable_stud_taper",
        "params": [
            {
                "key": "enable_stud_taper", "json_key": "enable_stud_taper",
                "type": "bool", "label": "Enable", "default": True,
            },
            {
                "key": "stud_taper_height", "json_key": "stud_taper_height",
                "type": "float",
                "label": "Height", "default": 1.5, "min": 0.1, "max": 4.0,
                "step": 10, "precision": 2,
                "description": "Height of tapered zone at top of studs (mm)",
            },
            {
                "key": "stud_taper_inset", "json_key": "stud_taper_inset",
                "type": "float",
                "label": "Inset", "default": 0.4, "min": 0.01, "max": 1.0,
                "step": 10, "precision": 2,
                "description": "How far stud radius narrows at top (mm)",
            },
            {
                "key": "stud_taper_curve", "json_key": "stud_taper_curve",
                "type": "enum",
                "label": "Curve", "default": "CURVED",
                "items": [
                    ("LINEAR", "Linear", "Straight-line stud taper"),
                    ("CURVED", "Curved", "Quarter-circle profile"),
                ],
            },
        ],
    },
    # ── Text ─────────────────────────────────────────────────────────────────
    text_section("CLARA"),
    # ── Fillet ───────────────────────────────────────────────────────────────
    FILLET_SECTION,
]


# ── Presets ──────────────────────────────────────────────────────────────────
# Named configurations. Each preset's "params" dict overrides SECTIONS defaults.
# Apply a preset = reset all params to SECTIONS defaults, then apply overrides.
# Keys are json_key values from SECTIONS params.

PRESETS = [
    {
        "key": "CLARA_MINI",
        "label": "Clara Mini Brick",
        "description": "3D print optimized with diagonal lattice, tapered walls and tall studs",
        "params": {},  # Matches defaults — no overrides needed
    },
    {
        "key": "CLARA_MINI_SLOPE",
        "label": "Clara Mini Slope",
        "description": "Clara Mini Brick with slope enabled",
        "params": {
            "enable_slope": True,
            "slope_plus_y": 3,
        },
    },
    {
        "key": "LEGO_STANDARD",
        "label": "LEGO Standard",
        "description": "Standard LEGO-compatible dimensions with tube clutch",
        "params": {
            "clutch_type": "TUBE",
            "STUD_TEXT": "LEGO",
            "STUD_HEIGHT": 1.8,
            "enable_corner_radius": False,
            "corner_radius": 0.0,
            "enable_wall_taper": False,
            "taper_height": 0.0,
            "taper_inset": 0.0,
            "taper_curve": "LINEAR",
            "enable_stud_taper": False,
            "stud_taper_height": 0.0,
            "stud_taper_inset": 0.0,
            "stud_taper_curve": "LINEAR",
        },
    },
    {
        "key": "LEGO_SLOPE",
        "label": "LEGO Slope",
        "description": "Standard LEGO slope with tube clutch",
        "params": {
            "clutch_type": "TUBE",
            "STUD_TEXT": "LEGO",
            "STUD_HEIGHT": 1.8,
            "enable_corner_radius": False,
            "enable_wall_taper": False,
            "enable_stud_taper": False,
            "enable_slope": True,
            "slope_plus_y": 3,
        },
    },
    {
        "key": "HOLLOW",
        "label": "Hollow Shell",
        "description": "No clutch mechanism, just shell + studs",
        "params": {
            "clutch_type": "NONE",
            "STUD_TEXT": "",
            "STUD_HEIGHT": 1.8,
            "enable_corner_radius": False,
            "enable_wall_taper": False,
            "enable_stud_taper": False,
            "ENABLE_TEXT": False,
        },
    },
]
