"""
Shared brick constants and helpers — used by both LEGO and Clara systems.

Query (constants) + Pure function (helpers), general. Dimensions from
LDraw (1 LDU = 0.4mm), OpenSCAD lego.scad, Bartneck measurements.

Coordinate convention: brick sits on XY plane, studs point up (+Z).
Origin at the center-bottom of the brick body (not including studs).
"""

# NOTE: No build123d imports at module level — this file is imported by
# panel_common.py → panel_def.py which runs in Blender's Python (no build123d).

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
EDGE_STYLE = "FILLET"   # "FILLET" (rounded) or "CHAMFER" (straight bevel)
FILLET_BOTTOM = False   # include bottom (Z=0) edges in fillet/chamfer
SKIP_CONCAVE = False    # skip interior (concave) edges (stud-deck junctions)
CR_SKIP_CONCAVE = True  # skip concave (reentrant) corners in cross-shape corner radius
ENABLE_STUDS = True     # toggle studs on/off
ENABLE_TEXT = True      # toggle stud text on/off
STUD_TEXT = "CLARA"
STUD_TEXT_FONT = "Arial"  # font name (system font) or path to .ttf file
STUD_TEXT_FONT_SIZE = 1.0
STUD_TEXT_HEIGHT = 0.1  # raised text height
STUD_TEXT_ROTATION = 0.0  # text rotation angle (degrees)

STUD_RADIUS = STUD_DIAMETER / 2


# ── General helper ───────────────────────────────────────────────────────────

def bevel_above_z(part, radius, z_threshold=0.0, tolerance=0.01,
                  style="FILLET", include_bottom=False, skip_concave=False):
    """
    Pure function, general. Fillet or chamfer edges, optionally including bottom.

    By default keeps bottom edges sharp (build plate adhesion / clean base).
    Set include_bottom=True to bevel all edges including Z=0.
    Set skip_concave=True to skip interior (concave) edges — useful to leave
    stud-deck junctions unfilleted while rounding all exterior corners.

    Args:
        part (Part): Solid to bevel.
        radius (float): Fillet radius or chamfer length (mm).
        z_threshold (float): Edges at or below this Z are skipped (unless include_bottom).
        tolerance (float): Z comparison tolerance.
        style (str): "FILLET" (rounded) or "CHAMFER" (straight 45° bevel).
        include_bottom (bool): If True, bevel all edges including bottom.
        skip_concave (bool): If True, skip interior (concave) edges.

    Returns:
        Part: Beveled solid.

    Examples:
        >>> # bevel_above_z(box, 0.15) -> fillets everything except Z=0
        >>> # bevel_above_z(box, 0.15, style="CHAMFER") -> chamfers instead
        >>> # bevel_above_z(box, 0.15, include_bottom=True) -> fillets ALL edges
        >>> # bevel_above_z(box, 0.15, skip_concave=True) -> exterior corners only
    """
    from build123d import Axis
    above = part.edges().filter_by_position(
        Axis.Z, z_threshold + tolerance, float('inf'), inclusive=(False, True)
    )
    if include_bottom:
        bottom = part.edges().filter_by_position(
            Axis.Z, float('-inf'), tolerance, inclusive=(True, False)
        )
        edges = above + bottom
    else:
        edges = above

    if skip_concave:
        def _is_convex(e):
            """Boundary edges (<2 faces) are treated as convex (not interior)."""
            try:
                return not e.is_interior
            except IndexError:
                return True
        edges = edges.filter_by(_is_convex)

    if style == "CHAMFER":
        return part.chamfer(radius, None, edges)
    return part.fillet(radius, edges)


# Backwards compatibility alias
fillet_above_z = bevel_above_z
