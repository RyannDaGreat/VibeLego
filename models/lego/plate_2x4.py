"""
2x4 Lego plate — 1/3 height of a standard brick.

Command, specific. Generates and exports a 2x4 plate for Blender preview.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import export_stl
from lego_lib import lego_brick, PLATE_HEIGHT

result = lego_brick(2, 4, height=PLATE_HEIGHT)

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"2x4 plate -> {stl_path} ({len(result.faces())} faces)")
