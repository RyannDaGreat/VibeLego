"""
LEGO 2x4 brick -- default entry point for ./run.sh.

Command, specific. Builds a default 2x4 LEGO brick and exports to STL.
Pass this file to run.sh for interactive Blender work with the LEGO panel.

Usage:
    ./run.sh models/bricks/lego/lego.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import export_stl
from lego_lib import lego_brick

result = lego_brick(2, 4)

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"LEGO 2x4 brick -> {stl_path} ({len(result.faces())} faces)")
