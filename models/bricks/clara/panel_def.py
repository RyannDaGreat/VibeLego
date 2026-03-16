"""
Clara brick panel definition -- parameter declarations for Blender sidebar.

Query, specific. Pure data module (no bpy imports, no build123d imports).
Consumed by blender_watcher.py's generic panel builder.

Clara-specific: NO tube/ridge internal params. Only lattice brick type.
Includes 3D printing features (corner radius, wall taper).
Shared sections (Walls, Text, Polish) imported from panel_common.py.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from panel_common import (
    WALLS_SECTION, text_section, POLISH_SECTION,
    classify_face, ANATOMY_COLORS, ANATOMY_REGION_ITEMS,
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
                "label": "Stud Height", "default": 1.8, "min": 0.5, "max": 5.0,
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
        "label": "3D Printing",
        "icon": "MOD_BEVEL",
        "params": [
            {
                "key": "corner_radius", "json_key": "corner_radius", "type": "float",
                "label": "Corner Radius", "default": 0.0, "min": 0.0, "max": 4.0,
                "step": 10, "precision": 2,
                "description": "2D corner rounding of brick outline (like CSS border-radius)",
            },
            {
                "key": "taper_height", "json_key": "taper_height", "type": "float",
                "label": "Taper Height", "default": 0.0, "min": 0.0, "max": 5.0,
                "step": 10, "precision": 2,
                "description": "How far down from top the wall taper begins (mm)",
            },
            {
                "key": "taper_inset", "json_key": "taper_inset", "type": "float",
                "label": "Taper Inset", "default": 0.0, "min": 0.0, "max": 2.0,
                "step": 10, "precision": 2,
                "description": "How far walls narrow at the top (mm per side)",
            },
        ],
    },
    text_section("CLARA"),
    POLISH_SECTION,
]
