"""
LEGO brick panel definition -- parameter declarations for Blender sidebar.

Query, specific. Pure data module (no bpy imports). Declares all parametric
LEGO brick dimensions, their ranges, and panel layout sections. Consumed by
blender_watcher.py's generic panel builder.

LEGO-specific: includes tube/ridge internal params, brick/plate/slope types.
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
                "key": "brick_type", "json_key": "brick_type", "type": "enum",
                "label": "Type", "default": "BRICK",
                "items": [
                    ("BRICK", "Brick", "Standard brick height"),
                    ("PLATE", "Plate", "1/3 brick height"),
                    ("SLOPE", "Slope", "Slope/wedge brick"),
                ],
            },
            {
                "key": "studs_x", "json_key": "studs_x", "type": "int",
                "label": "Studs X", "default": 2, "min": 1, "max": 16,
            },
            {
                "key": "studs_y", "json_key": "studs_y", "type": "int",
                "label": "Studs Y", "default": 4, "min": 1, "max": 16,
            },
            {
                "key": "flat_rows", "json_key": "flat_rows", "type": "int",
                "label": "Flat Rows", "default": 1, "min": 1, "max": 8,
                "description": "Number of flat stud rows on slope top",
            },
        ],
        "rows": [["studs_x", "studs_y"]],
        "visible_when": {"flat_rows": {"brick_type": "SLOPE"}},
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
            {
                "key": "plate_height", "json_key": "PLATE_HEIGHT", "type": "float",
                "label": "Plate Height", "default": 3.2, "min": 1.0, "max": 10.0,
                "step": 10, "precision": 2,
            },
        ],
    },
    WALLS_SECTION,
    {
        "label": "Internals",
        "icon": "MESH_CYLINDER",
        "params": [
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
    },
    text_section("LEGO"),
    POLISH_SECTION,
]
