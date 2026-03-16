"""
Shared panel sections and anatomy classification for brick systems.

Query, general. Pure data module (no bpy or build123d imports). Provides
the Walls, Text, and Polish section dicts shared by both LEGO and Clara
panel_def.py files, plus the anatomy highlight classification used by
blender_watcher.py.

Defaults are imported from common.py at module load time. Safe because
common.py is also a pure data module (no heavy imports).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import (
    WALL_THICKNESS, FLOOR_THICKNESS, CLEARANCE,
    STUD_TEXT_FONT, STUD_TEXT_FONT_SIZE, STUD_TEXT_HEIGHT,
    FILLET_RADIUS, ENABLE_FILLET,
)


# ── Shared panel sections ────────────────────────────────────────────────────

WALLS_SECTION = {
    "label": "Walls",
    "icon": "MOD_SOLIDIFY",
    "params": [
        {
            "key": "wall_thickness", "json_key": "WALL_THICKNESS", "type": "float",
            "label": "Wall Thickness", "default": WALL_THICKNESS, "min": 0.3, "max": 5.0,
            "step": 10, "precision": 2,
        },
        {
            "key": "floor_thickness", "json_key": "FLOOR_THICKNESS", "type": "float",
            "label": "Floor Thickness", "default": FLOOR_THICKNESS, "min": 0.2, "max": 5.0,
            "step": 10, "precision": 2,
        },
        {
            "key": "clearance", "json_key": "CLEARANCE", "type": "float",
            "label": "Clearance", "default": CLEARANCE, "min": 0.0, "max": 1.0,
            "step": 1, "precision": 3,
        },
    ],
}


def text_section(stud_text_default):
    """
    Pure function, general. Build a Text panel section with a custom stud text default.

    Args:
        stud_text_default (str): Default text embossed on studs (e.g. "LEGO", "CLARA").

    Returns:
        dict: Section definition for the panel builder.

    Examples:
        >>> text_section("LEGO")["params"][0]["default"]
        'LEGO'
    """
    return {
        "label": "Text",
        "icon": "FONT_DATA",
        "params": [
            {
                "key": "stud_text", "json_key": "STUD_TEXT", "type": "string",
                "label": "Stud Text", "default": stud_text_default, "maxlen": 32,
                "description": "Text embossed on each stud top",
            },
            {
                "key": "stud_text_font", "json_key": "STUD_TEXT_FONT", "type": "string",
                "label": "Font", "default": STUD_TEXT_FONT, "maxlen": 256,
                "description": "Font name (e.g. Arial, Courier) or path to .ttf file",
            },
            {
                "key": "stud_text_font_size", "json_key": "STUD_TEXT_FONT_SIZE",
                "type": "float", "label": "Text Size",
                "default": STUD_TEXT_FONT_SIZE, "min": 0.1, "max": 5.0,
                "step": 10, "precision": 2,
            },
            {
                "key": "stud_text_height", "json_key": "STUD_TEXT_HEIGHT",
                "type": "float", "label": "Text Height",
                "default": STUD_TEXT_HEIGHT, "min": 0.01, "max": 1.0,
                "step": 1, "precision": 3,
            },
        ],
    }


POLISH_SECTION = {
    "label": "Polish",
    "icon": "MOD_SMOOTH",
    "params": [
        {
            "key": "enable_fillet", "json_key": "ENABLE_FILLET", "type": "bool",
            "label": "Enable Fillet", "default": ENABLE_FILLET,
            "description": "Apply edge rounding to the brick",
        },
        {
            "key": "fillet_radius", "json_key": "FILLET_RADIUS", "type": "float",
            "label": "Fillet Radius", "default": FILLET_RADIUS, "min": 0.0, "max": 2.0,
            "step": 1, "precision": 3,
        },
    ],
}


# ── Anatomy highlight system ─────────────────────────────────────────────────
# Defines regions, colors, and classification for the blender_watcher anatomy
# toggle. Shared by all brick systems (classification is geometry-based).

ANATOMY_COLORS = {
    "studs":     (0.90, 0.30, 0.30, 1.0),  # red
    "logo":      (0.95, 0.70, 0.20, 1.0),  # orange/gold
    "deck":      (0.30, 0.75, 0.40, 1.0),  # green
    "walls":     (0.35, 0.55, 0.90, 1.0),  # blue
    "internals": (0.70, 0.40, 0.85, 1.0),  # purple (tubes or lattice)
    "base":      (0.50, 0.50, 0.50, 1.0),  # gray (bottom face at Z=0)
    "default":   (0.85, 0.85, 0.85, 1.0),  # light gray (unclassified/fillets)
}

ANATOMY_REGION_ITEMS = [
    ("ALL",       "All Regions",  "Color all regions simultaneously"),
    ("studs",     "Studs",        "Cylindrical bumps on top of the brick"),
    ("logo",      "Logo",         "Raised text on each stud top"),
    ("deck",      "Deck",         "Flat top surface where studs sit"),
    ("walls",     "Walls",        "Outer vertical surfaces of the shell"),
    ("internals", "Internals",    "Cavity features: tubes (LEGO) or lattice (Clara)"),
    ("base",      "Base",         "Bottom face at Z=0"),
    ("default",   "Fillets/Other","Unclassified faces (fillets, transitions)"),
]


def classify_face(mesh, poly, params):
    """
    Pure function, general. Classify a mesh face into a brick anatomical region.

    Uses face center position and normal direction relative to brick geometry
    bounds derived from panel params (or defaults). Works for any brick system
    (LEGO tubes, Clara lattice, etc.) because classification is purely geometric.

    Args:
        mesh: The mesh data (bpy.types.Mesh).
        poly: The face to classify (bpy.types.MeshPolygon).
        params (dict): Panel params dict with studs_x, studs_y, PITCH, etc.

    Returns:
        str: Region name (key into ANATOMY_COLORS).

    Examples:
        >>> # classify_face(mesh, poly, {"studs_x": 2, "studs_y": 4})
    """
    cx, cy, cz = poly.center
    nx, ny, nz = poly.normal

    pitch = float(params.get("PITCH", 8.0))
    studs_x = int(params.get("studs_x", 2))
    studs_y = int(params.get("studs_y", 4))
    brick_height = float(params.get("BRICK_HEIGHT", 9.6))
    stud_height = float(params.get("STUD_HEIGHT", 1.8))
    wall_thickness = float(params.get("WALL_THICKNESS", 1.5))
    clearance = float(params.get("CLEARANCE", 0.1))
    floor_thickness = float(params.get("FLOOR_THICKNESS", 1.0))

    # Use the brick_type to get actual height (plate vs brick)
    brick_type = params.get("brick_type", "BRICK")
    if brick_type == "PLATE":
        height = float(params.get("PLATE_HEIGHT", 3.2))
    else:
        height = brick_height

    outer_x = studs_x * pitch - 2 * clearance
    outer_y = studs_y * pitch - 2 * clearance
    half_ox = outer_x / 2
    half_oy = outer_y / 2
    inner_x = outer_x - 2 * wall_thickness
    inner_y = outer_y - 2 * wall_thickness
    half_ix = inner_x / 2
    half_iy = inner_y / 2
    cavity_z = height - floor_thickness

    tol = 0.05  # classification tolerance (mm)

    # Logo: faces above stud tops (text extrusion)
    if cz > height + stud_height - tol:
        return "logo"

    # Studs: cylindrical faces above the deck
    if cz > height + tol:
        return "studs"

    # Deck: horizontal upward-facing faces at Z ~ height
    if abs(cz - height) < tol and nz > 0.9:
        return "deck"

    # Base: bottom face at Z ~ 0
    if abs(cz) < tol and nz < -0.9:
        return "base"

    # Walls vs internals: check if face is outside or inside the inner bounds
    inside_inner = (abs(cx) < half_ix + tol and abs(cy) < half_iy + tol)
    outside_outer = (abs(cx) > half_ox - tol or abs(cy) > half_oy - tol)

    # Walls: faces on the outer perimeter
    if outside_outer and cz > tol and cz < height - tol:
        return "walls"

    # Internals: faces inside the cavity (tubes, lattice, ridges, inner walls)
    if inside_inner and cz > tol and cz < cavity_z + tol:
        return "internals"

    # Deck underside / ceiling
    if abs(cz - cavity_z) < tol and nz < -0.5 and inside_inner:
        return "deck"

    # Inner wall faces (between outer and inner perimeter, below deck)
    if cz > tol and cz < height - tol:
        return "walls"

    return "default"
