"""
Lego brick panel definition — parameter declarations for Blender sidebar.

Query, specific. Pure data module (no bpy imports). Declares all parametric
brick dimensions, their ranges, and panel layout sections. Consumed by
blender_watcher.py's generic panel builder.

Each param dict:
    key:         Blender property name (snake_case)
    json_key:    Key in the JSON params file sent to parametric.py
    type:        "float", "int", or "enum"
    label:       Display name in panel
    default:     Default value
    min, max:    Range limits
    step:        Slider step (Blender convention: 10 = 1.0 for floats)
    precision:   Decimal places (floats only)
    description: Tooltip text
    items:       List of (value, label, description) tuples (enums only)

Layout hints (optional per-section):
    rows:         List of [key, key, ...] to put on one row
    visible_when: Dict of {key: {condition_key: value}} — conditional visibility
"""

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
    {
        "label": "Walls",
        "icon": "MOD_SOLIDIFY",
        "params": [
            {
                "key": "wall_thickness", "json_key": "WALL_THICKNESS", "type": "float",
                "label": "Wall Thickness", "default": 1.5, "min": 0.3, "max": 5.0,
                "step": 10, "precision": 2,
            },
            {
                "key": "floor_thickness", "json_key": "FLOOR_THICKNESS", "type": "float",
                "label": "Floor Thickness", "default": 1.0, "min": 0.2, "max": 5.0,
                "step": 10, "precision": 2,
            },
            {
                "key": "clearance", "json_key": "CLEARANCE", "type": "float",
                "label": "Clearance", "default": 0.1, "min": 0.0, "max": 1.0,
                "step": 1, "precision": 3,
            },
        ],
    },
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
    {
        "label": "Polish",
        "icon": "MOD_SMOOTH",
        "params": [
            {
                "key": "fillet_radius", "json_key": "FILLET_RADIUS", "type": "float",
                "label": "Fillet Radius", "default": 0.15, "min": 0.0, "max": 2.0,
                "step": 1, "precision": 3,
            },
            {
                "key": "stud_text_font_size", "json_key": "STUD_TEXT_FONT_SIZE",
                "type": "float", "label": "Text Size",
                "default": 1.0, "min": 0.1, "max": 5.0, "step": 10, "precision": 2,
            },
            {
                "key": "stud_text_height", "json_key": "STUD_TEXT_HEIGHT",
                "type": "float", "label": "Text Height",
                "default": 0.1, "min": 0.01, "max": 1.0, "step": 1, "precision": 3,
            },
        ],
    },
]
