"""
1x2 Lego brick — with bottom ridge rail.

Command, specific. Generates and exports a 1x2 brick for Blender preview.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import export_stl
from lego_lib import lego_brick

result = lego_brick(1, 2)

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"1x2 brick -> {stl_path} ({len(result.faces())} faces)")
