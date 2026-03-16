#!/usr/bin/env bash
# setup.sh — WOM-proof setup for build123d live Blender preview
#
# Platform: macOS (ARM64 tested), Linux (should work with path adjustments)
# Uses uv for fast venv creation and dependency installation.
# Installs build123d from the local git submodule.
# Idempotent: safe to run multiple times.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
SUBMODULE_DIR="$SCRIPT_DIR/build123d"

# ── Check uv ──────────────────────────────────────────────────────────────────

if ! command -v uv > /dev/null 2>&1; then
    echo "ERROR: uv not found. Install via: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "Found uv $(uv --version)"

# ── Check submodule ───────────────────────────────────────────────────────────

if [[ ! -f "$SUBMODULE_DIR/pyproject.toml" ]]; then
    echo "build123d submodule not initialized. Running git submodule update..."
    git -C "$SCRIPT_DIR" submodule update --init --recursive
fi

if [[ ! -f "$SUBMODULE_DIR/pyproject.toml" ]]; then
    echo "ERROR: build123d submodule missing. Run: git submodule update --init"
    exit 1
fi

# ── Create venv + install ────────────────────────────────────────────────────

if [[ -d "$VENV_DIR" ]]; then
    echo "Venv already exists at $VENV_DIR"
else
    echo "Creating venv at $VENV_DIR..."
    uv venv "$VENV_DIR"
fi

echo "Installing build123d from local submodule..."
uv pip install --python "$VENV_DIR/bin/python3" -e "$SUBMODULE_DIR"

# ── Verify build123d ─────────────────────────────────────────────────────────

echo "Verifying build123d..."
"$VENV_DIR/bin/python3" -c "
from build123d import Box, export_stl
box = Box(10, 10, 10)
print(f'  build123d OK — created test box with {len(box.faces())} faces')
"

# ── Detect Blender ────────────────────────────────────────────────────────────

find_blender() {
    # macOS app bundle
    if [[ -x "/Applications/Blender.app/Contents/MacOS/Blender" ]]; then
        echo "/Applications/Blender.app/Contents/MacOS/Blender"
        return
    fi
    # PATH (homebrew, linux package manager, etc.)
    if command -v blender > /dev/null 2>&1; then
        command -v blender
        return
    fi
    # macOS Spotlight search
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
    echo "WARNING: Blender not found."
    echo "Install via: brew install --cask blender"
    echo "  or download from https://www.blender.org/download/"
    echo "  (setup.sh will still complete — Blender is needed only at runtime)"
else
    BLENDER_VERSION="$("$BLENDER_CMD" --version 2>/dev/null | head -1)"
    echo "Found Blender: $BLENDER_VERSION at $BLENDER_CMD"
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "Setup complete."
echo "  Venv:    $VENV_DIR"
echo "  Python:  $("$VENV_DIR/bin/python3" --version)"
echo "  Blender: ${BLENDER_CMD:-NOT FOUND}"
echo ""
echo "Usage: ./run.sh models/example_box.py"
