"""
2x2 Clara slope brick — 45-degree wedge with 1 flat row.

Command, specific. Generates and exports a 2x2 slope (like Lego 3039).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import export_stl
from lego_lib import lego_slope

result = lego_slope(2, 2)

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"2x2 slope -> {stl_path} ({len(result.faces())} faces)")
