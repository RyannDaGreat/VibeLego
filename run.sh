#!/usr/bin/env bash
# run.sh — Launch Blender with live build123d preview
#
# Usage: ./run.sh <source.py>
#
# Opens Blender watching the given build123d script. When the script changes,
# it auto-rebuilds via `uv run` and updates the mesh in Blender (preserving
# materials). No venv or setup step required — just uv and Blender.
#
# Prerequisites: uv, Blender

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WATCHER_SCRIPT="$SCRIPT_DIR/blender_watcher.py"

# ── Validate arguments ────────────────────────────────────────────────────────

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <source.py>"
    echo ""
    echo "  source.py  Path to a build123d Python script."
    echo "             The script should export its result to the path in"
    echo "             \$BUILD123D_PREVIEW_STL (set automatically)."
    echo ""
    echo "Example: $0 models/example_box.py"
    exit 1
fi

SOURCE_FILE="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"

if [[ ! -f "$SOURCE_FILE" ]]; then
    echo "ERROR: Source file not found: $1"
    exit 1
fi

# ── Check uv ──────────────────────────────────────────────────────────────────

if ! command -v uv > /dev/null 2>&1; then
    echo "ERROR: uv not found. Install via: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# ── Check submodule ───────────────────────────────────────────────────────────

if [[ ! -f "$SCRIPT_DIR/build123d/pyproject.toml" ]]; then
    echo "build123d submodule not initialized. Running git submodule update..."
    git -C "$SCRIPT_DIR" submodule update --init --recursive
fi

if [[ ! -f "$SCRIPT_DIR/build123d/pyproject.toml" ]]; then
    echo "ERROR: build123d submodule missing. Run: git submodule update --init"
    exit 1
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
    if command -v mdfind > /dev/null 2>&1; then
        local found
        found="$(mdfind "kMDItemFSName == 'Blender.app'" 2>/dev/null | head -1)"
        if [[ -n "$found" && -x "$found/Contents/MacOS/Blender" ]]; then
            echo "$found/Contents/MacOS/Blender"
            return
        fi
    fi
    echo ""
}

BLENDER_CMD="$(find_blender)"
if [[ -z "$BLENDER_CMD" ]]; then
    echo "ERROR: Blender not found."
    echo "Install via: brew install --cask blender"
    exit 1
fi

# ── Determine STL output path ────────────────────────────────────────────────

STL_PATH="$(dirname "$SOURCE_FILE")/_preview.stl"

# ── Launch ────────────────────────────────────────────────────────────────────

echo "Launching Blender with live preview..."
echo "  Source:  $SOURCE_FILE"
echo "  STL:     $STL_PATH"
echo "  Blender: $BLENDER_CMD"
echo ""
echo "Edit your source file — changes will appear in Blender automatically."
echo ""

"$BLENDER_CMD" \
    --factory-startup \
    --python "$WATCHER_SCRIPT" \
    -- "$SOURCE_FILE" "$STL_PATH"
