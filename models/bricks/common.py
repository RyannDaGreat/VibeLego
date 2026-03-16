"""
Shared brick constants and helpers — used by both LEGO and Clara systems.

Query (constants) + Pure function (helpers), general. Dimensions from
LDraw (1 LDU = 0.4mm), OpenSCAD lego.scad, Bartneck measurements.

Coordinate convention: brick sits on XY plane, studs point up (+Z).
Origin at the center-bottom of the brick body (not including studs).
"""

# ── Dimension Constants (mm) ─────────────────────────────────────────────────
# Base unit: 1 LDU = 0.4mm. Stud pitch = 20 LDU = 8.0mm.

PITCH = 8.0             # stud center-to-center (20 LDU)
STUD_DIAMETER = 4.8     # stud outer diameter (12 LDU)
STUD_HEIGHT = 1.8       # stud protrusion above brick top
BRICK_HEIGHT = 9.6      # standard brick body (24 LDU, without stud)
PLATE_HEIGHT = 3.2      # plate body (8 LDU, 1/3 of brick)
WALL_THICKNESS = 1.5    # outer wall thickness
FLOOR_THICKNESS = 1.0   # top ceiling thickness
CLEARANCE = 0.1         # per-side fit clearance

FILLET_RADIUS = 0.15    # edge rounding
ENABLE_FILLET = True    # toggle fillets on/off
STUD_TEXT = "CLARA"
STUD_TEXT_FONT = "Arial"  # font name (system font) or path to .ttf file
STUD_TEXT_FONT_SIZE = 1.0
STUD_TEXT_HEIGHT = 0.1  # raised text height

STUD_RADIUS = STUD_DIAMETER / 2


# ── General helper ───────────────────────────────────────────────────────────

def fillet_above_z(part, radius, z_threshold=0.0, tolerance=0.01):
    """
    Pure function, general. Fillet all edges above a Z threshold.

    Keeps bottom edges sharp (build plate adhesion / clean base).

    Args:
        part (Part): Solid to fillet.
        radius (float): Fillet radius (mm).
        z_threshold (float): Edges at or below this Z are skipped.
        tolerance (float): Z comparison tolerance.

    Returns:
        Part: Filleted solid.

    Examples:
        >>> # fillet_above_z(box, 0.15) -> fillets everything except Z=0
        >>> # fillet_above_z(box, 0.5, z_threshold=2.0) -> skip Z<=2
    """
    edges = [e for e in part.edges() if e.center().Z > z_threshold + tolerance]
    return part.fillet(radius, edges)
