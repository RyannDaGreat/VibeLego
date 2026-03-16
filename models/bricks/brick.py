"""
Unified brick — default entry point for ./run.sh.

Command, specific. Builds a default 2x4 Clara Mini brick and exports to STL.
Pass this file to run.sh for interactive Blender work with the unified panel.

Usage:
    ./run.sh models/bricks/brick.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from build123d import export_stl
from brick_lib import brick

result = brick(2, 4)

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
print(f"Brick 2x4 -> {stl_path} ({len(result.faces())} faces)")
