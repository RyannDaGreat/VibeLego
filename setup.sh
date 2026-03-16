#!/usr/bin/env bash
# setup.sh — WOM-proof setup for build123d live Blender preview
#
# Platform: macOS (ARM64 tested), Linux (should work with path adjustments)
# Creates a Python venv, installs build123d, and verifies Blender is available.
# Idempotent: safe to run multiple times.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10
MAX_PYTHON_MINOR=14  # 3.14 needs dev branch

# ── Detect Python ──────────────────────────────────────────────────────────────

find_python() {
    # Try python3.13 first (best compatibility), then python3.12, etc.
    for minor in 13 12 11 10 14; do
        local cmd="python3.${minor}"
        if command -v "$cmd" > /dev/null 2>&1; then
            echo "$cmd"
            return
        fi
    done
    # Fall back to generic python3
    if command -v python3 > /dev/null 2>&1; then
        echo "python3"
        return
    fi
    echo ""
}

PYTHON_CMD="$(find_python)"
if [[ -z "$PYTHON_CMD" ]]; then
    echo "ERROR: No Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ found."
    echo "Install via: brew install python@3.13"
    exit 1
fi

PYTHON_VERSION="$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PYTHON_MINOR="$($PYTHON_CMD -c 'import sys; print(sys.version_info.minor)')"
echo "Found Python $PYTHON_VERSION at $(command -v "$PYTHON_CMD")"

if (( PYTHON_MINOR < MIN_PYTHON_MINOR )); then
    echo "ERROR: Python $PYTHON_VERSION is too old. Need ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+."
    exit 1
fi

# ── Create venv ────────────────────────────────────────────────────────────────

if [[ -d "$VENV_DIR" ]]; then
    echo "Venv already exists at $VENV_DIR"
else
    echo "Creating venv at $VENV_DIR..."
    "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo "Activated venv (Python $(python3 --version))"

pip install --upgrade pip --quiet

# ── Install build123d ──────────────────────────────────────────────────────────

if python3 -c "import build123d" 2>/dev/null; then
    echo "build123d already installed"
else
    if (( PYTHON_MINOR >= MAX_PYTHON_MINOR )); then
        echo "Python $PYTHON_VERSION detected — installing build123d from dev branch..."
        pip install "git+https://github.com/gumyr/build123d.git@dev"
    else
        echo "Installing build123d from PyPI..."
        pip install build123d
    fi
fi

# ── Verify build123d ──────────────────────────────────────────────────────────

echo "Verifying build123d..."
python3 -c "
from build123d import Box, export_stl
box = Box(10, 10, 10)
print(f'  build123d OK — created test box with {len(box.faces())} faces')
"

# ── Detect Blender ─────────────────────────────────────────────────────────────

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

# ── Done ───────────────────────────────────────────────────────────────────────

echo ""
echo "Setup complete."
echo "  Venv:    $VENV_DIR"
echo "  Python:  $(python3 --version) at $(command -v python3)"
echo "  Blender: ${BLENDER_CMD:-NOT FOUND}"
echo ""
echo "Usage: ./run.sh models/example_box.py"
