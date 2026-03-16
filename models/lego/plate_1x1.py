"""
1x1 Lego plate — the thinnest standard piece.

Command, specific. Generates and exports a 1x1 plate for Blender preview.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import export_stl
from lego_lib import lego_brick, PLATE_HEIGHT

result = lego_brick(1, 1, height=PLATE_HEIGHT)

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"1x1 plate -> {stl_path} ({len(result.faces())} faces)")
