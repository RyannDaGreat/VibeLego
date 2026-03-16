"""
Example build123d model for live Blender preview.

Command, specific. Creates a box with a cylindrical hole and exports
to STL at the path specified by $BUILD123D_PREVIEW_STL.

Usage:
    BUILD123D_PREVIEW_STL=_preview.stl python models/example_box.py
    (or via ./run.sh models/example_box.py)
"""

import os
from build123d import Box, Cylinder, export_stl, Pos

# ── Model ──────────────────────────────────────────────────────────────────────

BOX_SIZE = (30, 20, 10)
HOLE_RADIUS = 5
HOLE_DEPTH = 20

result = Box(*BOX_SIZE) - Pos(0, 0, 0) * Cylinder(HOLE_RADIUS, HOLE_DEPTH)

# ── Export ─────────────────────────────────────────────────────────────────────

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"Exported to {stl_path} ({len(result.faces())} faces)")
