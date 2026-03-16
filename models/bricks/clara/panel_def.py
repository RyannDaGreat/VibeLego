"""
Clara brick panel definition -- parameter declarations for Blender sidebar.

Query, specific. Pure data module (no bpy imports, no build123d imports).
Consumed by blender_watcher.py's generic panel builder.

Clara-specific: NO tube/ridge internal params. Only lattice brick type.
Includes 3D printing features (corner radius, wall taper, stud taper).
Shared sections (Walls, Text, Polish) imported from panel_common.py.

Defaults are "Mini Brick" — 3D print optimized with tapered walls/studs.
PRESETS provide named configurations (Mini Brick, LEGO Standard).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from panel_common import (
    WALLS_SECTION, text_section, POLISH_SECTION,
    classify_face, ANATOMY_COLORS, ANATOMY_REGION_ITEMS, ANATOMY_REGION_GROUPS,
)

# Relative to this file's directory
PARAMETRIC_SCRIPT = "parametric.py"

SECTIONS = [
    {
        "label": "Shape",
        "icon": "MESH_CUBE",
        "params": [
            {
                "key": "studs_x", "json_key": "studs_x", "type": "int",
                "label": "Studs X", "default": 2, "min": 1, "max": 16,
            },
            {
                "key": "studs_y", "json_key": "studs_y", "type": "int",
                "label": "Studs Y", "default": 4, "min": 1, "max": 16,
            },
        ],
        "rows": [["studs_x", "studs_y"]],
    },
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
    WALLS_SECTION,
    {
        "label": "Corner Radius",
        "icon": "MOD_BEVEL",
        "params": [
            {
                "key": "corner_radius", "json_key": "corner_radius", "type": "float",
                "label": "Radius", "default": 2.0, "min": 0.0, "max": 4.0,
                "step": 10, "precision": 2,
                "description": "2D corner rounding of brick outline (like CSS border-radius)",
            },
        ],
    },
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
    text_section("CLARA"),
    POLISH_SECTION,
]

# ── Presets ──────────────────────────────────────────────────────────────────
# Named configurations. Each preset's "params" dict overrides SECTIONS defaults.
# Apply a preset = reset all params to SECTIONS defaults, then apply overrides.
# Keys are json_key values from SECTIONS params.

PRESETS = [
    {
        "key": "MINI_BRICK",
        "label": "Mini Brick",
        "description": "3D print optimized with tapered walls and tall studs",
        "params": {},  # Matches defaults — no overrides needed
    },
    {
        "key": "LEGO_STANDARD",
        "label": "LEGO Standard",
        "description": "Standard LEGO-compatible dimensions (no taper, short studs)",
        "params": {
            "STUD_HEIGHT": 1.8,
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
]
