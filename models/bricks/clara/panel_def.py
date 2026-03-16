"""
Clara brick panel definition -- parameter declarations for Blender sidebar.

Query, specific. Pure data module (no bpy imports, no build123d imports).
Consumed by blender_watcher.py's generic panel builder.

Clara-specific: NO tube/ridge internal params. Only lattice brick type.
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
        "label": "Dimensions",
        "icon": "ARROW_LEFTRIGHT",
        "params": [
            {
                "key": "pitch", "json_key": "PITCH", "type": "float",
                "label": "Pitch", "default": 8.0, "min": 1.0, "max": 20.0,
                "step": 10, "precision": 2,
                "description": "Stud center-to-center (mm)",
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
    text_section("CLARA"),
    POLISH_SECTION,
]
