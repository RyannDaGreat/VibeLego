"""
Clara 2x4 brick — diagonal lattice clutch demonstration.

Command, specific. Builds a 2x4 Clara brick and exports to STL.
The lattice bottom uses 45-degree crisscross struts instead of tubes.

Usage:
    uv run --with ./build123d models/lego/clara_2x4.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import export_stl
from lego_lib import clara_brick

result = clara_brick(2, 4)

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"Clara 2x4 brick -> {stl_path} ({len(result.faces())} faces)")
