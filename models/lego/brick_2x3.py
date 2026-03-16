"""
2x3 Lego brick.

Command, specific. Generates and exports a 2x3 brick for Blender preview.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import export_stl
from lego_lib import lego_brick

result = lego_brick(2, 3)

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"2x3 brick -> {stl_path} ({len(result.faces())} faces)")
