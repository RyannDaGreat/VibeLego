# build123d Live Blender Preview

## Problem

When using Claude to write build123d CAD models, there's no way to see the 3D result without manually running scripts and opening files. The goal is a **zero-button workflow**: Claude edits a `.py` source file, the model automatically rebuilds, and the updated mesh appears in Blender — preserving any materials, transforms, and scene setup the user has configured.

## Glossary

- **build123d**: Python CAD library for parametric 3D modeling. Uses OpenCASCADE (OCP) as its geometry kernel. Successor to CadQuery.
- **OCP / cadquery-ocp**: Python bindings for OpenCASCADE Technology (OCCT), the C++ 3D geometry kernel. Heavy binary dependency.
- **WOM (Works On My Machine)**: Anti-pattern where code only works on the developer's machine due to undocumented dependencies. This project must be WOM-proof.
- **tessellate**: Converting exact B-Rep (boundary representation) geometry into a triangle mesh (vertices + faces). The bridge between CAD precision and renderable geometry.
- **mesh-only update**: Replacing the vertex/face data of a Blender object without touching the object itself — preserving materials, modifiers, transforms, parent relationships.
- **`from_pydata()`**: Blender Python API method to create mesh geometry from raw Python lists of vertices, edges, and faces.
- **`clear_geometry()`**: Blender Python API method (since 2.81) that clears vertices/edges/faces from a mesh datablock but preserves material slots.
- **`bpy.app.timers`**: Blender's built-in polling mechanism. Register a function that returns a float (seconds until next call) or None (stop).
- **BlendQuery**: Existing (but stale) Blender addon that does build123d/CadQuery → Blender via subprocess + pickle. Reference implementation, not used directly.

## Architecture

### Chosen Approach: Subprocess + STL + File Watcher

```
run.sh <model.py>
  |
  +-- Launches Blender with blender_watcher.py
       |
       +-- Clears default scene, sets up CAD-friendly viewport
       +-- Registers bpy.app.timers callback (polls every 0.5s)
       |
       +-- On source file change (mtime):
            |
            1. Run model.py via subprocess (system Python in venv)
            2. model.py exports STL to _preview.stl
            3. Blender detects new STL, imports it
            4. mesh.clear_geometry() + mesh.from_pydata() on existing object
            5. Materials, transforms preserved
```

### Why This Approach (and not alternatives)

| Approach | Verdict | Why |
|----------|---------|-----|
| **STL file watcher** (chosen) | Best balance | Simple, debuggable, decoupled. STL is a natural checkpoint. ~200-500ms latency is fine for Claude-driven workflow. |
| **Socket/IPC (raw bytes)** | Overkill | ~20-70ms latency is nice but unnecessary. Adds custom protocol complexity. No natural checkpoint file for debugging. |
| **BlendQuery addon** | Stale/broken | Broken on Blender 5.0 (this machine). Unmerged fix PR. Hardcoded tolerances, no normals, no assembly locations. Would need forking. |
| **`pip install bpy` + build123d** | Fragile | Requires exact Python version match between OCP and bpy wheels. Would eliminate IPC entirely but version coupling is a maintenance nightmare. |
| **blender-remote (JSON-RPC)** | External dep | Adds a pip dependency for what's essentially a socket wrapper. |
| **Shared memory** | Way overkill | Only makes sense for millions of vertices per frame. |

### Key Design Decisions

1. **Subprocess isolation**: build123d runs in system Python (not Blender's Python 3.11). This avoids OCP ↔ Blender conflicts. BlendQuery proved this architecture works.

2. **STL as interchange format**: Binary STL is compact, build123d exports it natively, Blender imports it natively. No custom serialization needed.

3. **Watch source file, not output file**: The Blender watcher watches the `.py` source file's mtime. When it changes, it runs the script (which produces `_preview.stl`), then imports the STL. This means the user doesn't need to manually run the script.

4. **`clear_geometry()` + `from_pydata()`**: This is strictly better than datablock swapping (`obj.data = new_mesh`) because material slots with `link='DATA'` (the default) are preserved automatically. No manual material copying needed.

5. **Blender STL import API**: On Blender 4.1+ / 5.x, the operator is `bpy.ops.wm.stl_import()` (not the old `bpy.ops.import_mesh.stl`). Version-safe wrapper needed.

6. **Convention for user scripts**: User's build123d script must export to `_preview.stl` in the same directory. We provide a helper/wrapper so the user can just define `result = Box(10, 20, 30)` and the export happens automatically.

## File Structure

```
build123d_tests/
  run.sh                    # Entry point: ./run.sh models/lego/brick_2x4.py
  blender_watcher.py        # Blender-side script (watches + reimports)
  render_preview.py         # Headless Blender render: STL -> multi-angle PNGs
  render.sh                 # Convenience wrapper for render_preview.py
  models/                   # All build123d model scripts
    example_box.py          # Simple example: box with cylindrical hole
    lego/                   # Anatomically correct Clara brick collection
      lego_lib.py           # Shared brick geometry (pure functions, general)
      brick_2x4.py          # Classic 2x4 brick
      brick_2x2.py          # 2x2 brick
      brick_1x1.py          # 1x1 brick
      brick_1x2.py          # 1x2 brick with ridge rail
      brick_1x4.py          # 1x4 brick with ridge rail
      brick_2x3.py          # 2x3 brick
      plate_1x1.py          # 1x1 plate (1/3 height)
      plate_2x4.py          # 2x4 plate
      slope_2x2.py          # 2x2 slope brick (45-degree)
      collection.py         # All brick types in display grid
  renders/                  # Multi-angle render output (gitignored)
  docs/                     # Reports and documentation
    architecture.html       # Architecture plan + alternatives report
  build123d/                # build123d source (git submodule, dev branch)
  CLAUDE.md                 # Local Claude instructions (VLM verification rule)
  claude_instructions.md    # This file
  concerns.md               # Research log + lessons learned
  .claude_todo.md           # Task tracking
```

## Clara Brick Features

**Brand**: "Clara" (not Lego). All studs have raised "CLARA" text.

### Stud Text Dimensions (from real Lego measurements)
- Raised height: **0.1mm** above stud top surface
- Text block length: ~77% of stud diameter (~3.7mm on a 4.8mm stud)
- Letter height: ~39% of stud diameter (~1.88mm)
- Stroke width: ~0.2mm
- Font: bold sans-serif, centered on stud top
- Implementation: `Text("CLARA", font_size, font_style=FontStyle.BOLD)` + `extrude(0.1)` on stud top face

### Slope Bricks
- `lego_slope(studs_x, studs_y, height, flat_rows)`: creates wedge/slope bricks
- Build order: solid outer box → cut slope → subtract slope-trimmed cavity → add studs/tubes
- Slope terminates at `Z=WALL_THICKNESS` (not Z=0) — creates realistic lip at low end like Lego 3039
- Uses `split()` with a custom `Plane` to cut the angled surface
- Cavity also split by the same plane to prevent exposed interior through slope face
- Studs only on the flat (non-sloped) portion
- Bottom tubes/ridges still present, fillets applied (skip Z=0)

### Collection Display
- `collection.py`: generates all brick types in a grid layout
- Rows: bricks, plates, slopes — columns: different sizes
- Grid spacing: 5 × PITCH (40mm) between brick centers
- All parts combined into a single `Compound` for export

### VLM Render Verification
- `render_preview.py`: headless Blender script, EEVEE engine
- 14 diagnostic angles: 6 cardinal (front/back/left/right/top/bottom) + 8 diagonal (±30° elevation at 45°/135°/225°/315° azimuth)
- Sun lights (no distance attenuation) + ambient world for consistent illumination
- Auto-smooth shading (30° angle threshold) for crisp edges on curved surfaces
- Plastic material: white Principled BSDF (0.95 albedo, Roughness 0.3)
- 1024×1024 PNG output to `renders/` directory
- Claude reads PNGs via Read tool for visual verification

### General Geometry Functions (reusable outside lego_lib)
- `centered_grid(nx, ny, spacing, z)` — grid positions centered on XY origin
- `hollow_box(outer_x, outer_y, outer_z, wall, floor)` — shell with cavity
- `cylinders_at(radius, height, positions)` — cylinders at arbitrary positions
- `hollow_cylinders_at(outer_r, inner_r, height, positions)` — tubes at positions
- `raised_text_at(text, font_size, height, positions)` — extruded text at positions (OCCT font→B-Rep, no SVG intermediate)
- `fillet_above_z(part, radius, z_threshold)` — fillet edges above a Z plane

## Convention for User Scripts

User scripts receive the STL output path via the `BUILD123D_PREVIEW_STL` environment variable.
The standard pattern:

```python
import os
from build123d import *

result = Box(10, 20, 30) - Cylinder(5, 40)

stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
export_stl(result, stl_path)
```

## System Requirements (WOM Documentation)

### Platform
- **macOS** (tested on Darwin 25.3.0, Apple Silicon ARM64)
- Should work on Linux with path adjustments
- Windows not tested

### Dependencies

| Dependency | Version | How to Install | Purpose |
|------------|---------|----------------|---------|
| **Blender** | 5.0+ (4.1+ minimum) | `brew install --cask blender` or download from blender.org | 3D viewport |
| **Python** | 3.10-3.13 (3.14 needs dev branch) | System Python or `brew install python@3.13` | Runs build123d scripts |
| **build123d** | 0.10.0+ | `pip install build123d` | CAD modeling library |
| **cadquery-ocp** | 7.8+ | Installed automatically with build123d | OCCT bindings |

### Blender Details (This Machine)
- Executable: `/Applications/Blender.app/Contents/MacOS/Blender`
- Version: 5.0.1
- Embedded Python: 3.11.13
- STL import operator: `bpy.ops.wm.stl_import()` (C++ rewrite, 3-10x faster than old Python version)
- No sandboxing on subprocess calls

### Python / build123d Details
- Homebrew Python: 3.14.3 (needs dev branch: `pip install git+https://github.com/gumyr/build123d.git@dev`)
- Alternative: use Python 3.13 for stable release compatibility
- OCP ARM64 macOS wheels available on PyPI (no Rosetta needed)

## Research Findings Summary

### build123d Export Capabilities
- **STL**: `export_stl(shape, path, tolerance=1e-3, angular_tolerance=0.1)` — binary or ASCII
- **STEP**: `export_step(shape, path)` — full XDE with colors/labels/assemblies
- **glTF**: `export_gltf(shape, path)` — mesh + colors, coordinate system rotation handled
- **BREP**: `export_brep(shape, path)` — exact OpenCASCADE native format
- **3MF**: Via `Mesher` class
- **No OBJ exporter**
- **Raw mesh data**: `shape.tessellate(tolerance)` returns `(list[Vector], list[tuple[int,int,int]])` — vertices and triangle indices directly

### Blender Mesh Update API
- `mesh.clear_geometry()` clears verts/edges/faces, **preserves material slots** (since Blender 2.81)
- `mesh.from_pydata(verts, edges, faces)` rebuilds geometry from Python lists
- `obj.data = new_mesh` (datablock swap) does NOT preserve materials with default `link='DATA'` — **avoid this**
- BMesh alternative exists but `clear_geometry() + from_pydata()` is simpler

### Blender Timer API
- `bpy.app.timers.register(fn, first_interval=0, persistent=False)`
- Callback returns `float` (seconds to next call) or `None` (unregister)
- Stable across all Blender versions since 2.80
- Cannot reliably use `bpy.context` from timer callbacks — use `bpy.data` directly

### Blender CLI
- Launch: `/Applications/Blender.app/Contents/MacOS/Blender --python script.py -- custom_args`
- Clean scene: `--factory-startup` + programmatic object removal
- Arguments after `--` go to `sys.argv` for the script
- No splash suppression flag, but it doesn't block script execution

### Existing Solutions Surveyed
- **BlendQuery**: Subprocess + pickle + `from_pydata()`. Broken on Blender 5.0. Stale (Jul 2024). 70 GitHub stars.
- **ocp-vscode**: The dominant build123d viewer (VS Code extension + WebSocket). Not Blender-based.
- **blender-remote**: JSON-RPC for remote-controlling Blender. Could work but adds a dependency.
- **Script Watcher addon**: Watches .py files for changes, re-runs them. Good reference for file watching pattern.
- **CQ-editor**: Uses QFileSystemWatcher. Known reliability issues with auto-reload.
