#!/usr/bin/env bash
# render.sh — Render multi-angle PNGs from a build123d model for VLM verification
#
# Usage: ./render.sh <source.py>
#
# 1. Builds the model via `uv run` -> STL
# 2. Renders 4 diagnostic angles via headless Blender -> PNGs in renders/
#
# Prerequisites: uv, Blender, build123d submodule

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RENDER_SCRIPT="$SCRIPT_DIR/render_preview.py"
OUTPUT_DIR="$SCRIPT_DIR/renders"
BUILD123D_SUBMODULE="$SCRIPT_DIR/build123d"

# ── Validate arguments ────────────────────────────────────────────────────────

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <source.py>"
    echo ""
    echo "  Builds the model and renders 4 diagnostic angles as PNGs."
    echo "  Output goes to renders/ directory."
    echo ""
    echo "Example: $0 models/bricks/lego/brick_2x4.py"
    exit 1
fi

SOURCE_FILE="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"

if [[ ! -f "$SOURCE_FILE" ]]; then
    echo "ERROR: Source file not found: $1"
    exit 1
fi

# ── Check dependencies ────────────────────────────────────────────────────────

if ! command -v uv > /dev/null 2>&1; then
    echo "ERROR: uv not found. Install via: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if [[ ! -f "$BUILD123D_SUBMODULE/pyproject.toml" ]]; then
    echo "build123d submodule not initialized. Running git submodule update..."
    git -C "$SCRIPT_DIR" submodule update --init --recursive
fi

# ── Detect Blender ────────────────────────────────────────────────────────────

find_blender() {
    if [[ -x "/Applications/Blender.app/Contents/MacOS/Blender" ]]; then
        echo "/Applications/Blender.app/Contents/MacOS/Blender"
        return
    fi
    if command -v blender > /dev/null 2>&1; then
        command -v blender
        return
    fi
    echo ""
}

BLENDER_CMD="$(find_blender)"
if [[ -z "$BLENDER_CMD" ]]; then
    echo "ERROR: Blender not found."
    echo "Install via: brew install --cask blender"
    exit 1
fi

# ── Build STL ─────────────────────────────────────────────────────────────────

STL_PATH="/tmp/_render_preview.stl"

echo "Building model: $SOURCE_FILE"
BUILD123D_PREVIEW_STL="$STL_PATH" uv run --with "$BUILD123D_SUBMODULE" "$SOURCE_FILE"

if [[ ! -f "$STL_PATH" ]]; then
    echo "ERROR: Build produced no STL at $STL_PATH"
    exit 1
fi

# ── Render ────────────────────────────────────────────────────────────────────

echo "Rendering 4 diagnostic angles..."
"$BLENDER_CMD" \
    --background \
    --factory-startup \
    --python "$RENDER_SCRIPT" \
    -- "$STL_PATH" "$OUTPUT_DIR"
# NOTE: render.sh keeps --factory-startup because headless renders should
# not be affected by user addons/startup files (consistency + speed).

echo ""
echo "Renders saved to: $OUTPUT_DIR/"
ls -la "$OUTPUT_DIR/"*.png 2>/dev/null || true
