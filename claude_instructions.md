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

## Brick Anatomy (naming vocabulary)

Standard terms for communicating about brick regions. Use these names in code,
comments, and conversation for precision.

| Region | Name | Description |
|--------|------|-------------|
| Outer rectangular box | **Shell** | Outer walls + ceiling as one solid. Everything except internals and studs |
| Top flat surface | **Deck** | The ceiling/roof where studs sit |
| Outer vertical faces | **Walls** | The 4 outer vertical surfaces of the shell |
| Cylindrical bumps on top | **Studs** | Round pegs on the deck (industry standard term) |
| Raised text on studs | **Logo** | The "CLARA" embossed text on each stud top |
| Hollow interior (open bottom) | **Cavity** | The empty space inside, open from below |
| ±45° diagonal ribs (Clara) | **Lattice** | The crisscross strut pattern filling the cavity |
| Single diagonal rib | **Strut** | One thin wall at 45°, running wall-to-wall |
| Diamond opening in lattice | **Cell** | One opening where a stud fits (inscribed circle = STUD_DIAMETER) |
| Anti-stud cylinders (standard) | **Tubes** | Round hollow cylinders in standard bricks (not used in Clara) |
| Thin rail (1-wide bricks) | **Ridge** | Bottom grip rail for 1-wide standard bricks |
| Rounded edges | **Fillets** | Small radius on shell/stud edges (not on lattice) |

## Anatomy Highlight System (Blender viewport)

**Requirement**: Any brick model displayed in Blender must support a toggle that
colors each mesh face by anatomical region. This teaches users brick vocabulary
and helps debug geometry issues. The system is **generic** — it works on any
brick mesh (LEGO, Clara, future systems) by classifying faces using geometric
position and surface normal relative to the brick's parametric bounds.

**Panel controls** (in the "Anatomy" section, below parametric sections):
- **Show Anatomy Colors** checkbox — toggles coloring on/off, switches viewport
  shading between MATERIAL (colors visible) and SOLID (matcap)
- **Region** dropdown — "All Regions" colors everything; selecting a specific
  region (e.g. "Studs") highlights only that region and grays out the rest

**Regions and colors**:
| Region | Color | Classification rule |
|--------|-------|---------------------|
| Studs | Red | Face center Z > brick top |
| Logo | Gold | Face center Z > stud tops (text extrusion) |
| Deck | Green | Horizontal upward face at Z ≈ brick height |
| Walls | Blue | Face on outer perimeter, between Z=0 and top |
| Internals | Purple | Face inside cavity bounds (tubes, lattice, ridges) |
| Base | Gray | Horizontal downward face at Z ≈ 0 |
| Fillets/Other | Light gray | Unclassified (fillet transitions, etc.) |

**Implementation** (all in `blender_watcher.py`, not in model code):
- `_classify_face(mesh, poly, params)` — pure function, classifies by center/normal vs geometric bounds
- `_apply_anatomy_colors(obj, params, highlight_region)` — FLOAT_COLOR attribute on CORNER domain
- `_setup_anatomy_material(obj)` — ShaderNodeAttribute → Principled BSDF
- Colors auto-reapply after every mesh rebuild (slider change, file change)

**Design principle**: The anatomy system is a **Blender-side display feature**.
It does not touch the build pipeline (no changes to lego_lib, clara_lib, or
parametric.py). Any future brick system automatically gets anatomy highlighting
as long as it follows the standard coordinate convention (origin at center-bottom,
studs up +Z) and provides studs_x, studs_y, and dimension params.

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
            1. Run model.py via `uv run` subprocess (system Python, not Blender's)
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
  run.sh                    # Entry point: ./run.sh models/bricks/lego/lego.py
  blender_watcher.py        # Blender-side script (watches + reimports)
  render_preview.py         # Headless Blender render: STL -> multi-angle PNGs
  render.sh                 # Convenience wrapper for render_preview.py
  build_worker.py           # Persistent build subprocess (keeps build123d imported)
  models/                   # All build123d model scripts
    example_box.py          # Simple example: box with cylindrical hole
    bricks/                 # Brick systems (LEGO + Clara)
      common.py             # Shared constants + fillet_above_z (both systems)
      lego/                 # LEGO brick system (tube-based clutch)
        lego_lib.py         # lego_brick(), lego_slope() — pure geometry
        lego.py             # Default entry point for ./run.sh
        parametric.py       # Worker interface: run(params, stl_path)
        panel_def.py        # LEGO panel params (with tube/ridge internals)
        brick_2x4.py        # Convenience: classic 2x4 brick
        brick_2x2.py        # Convenience: 2x2 brick
        brick_1x1.py        # Convenience: 1x1 brick
        brick_1x2.py        # Convenience: 1x2 brick with ridge
        brick_1x4.py        # Convenience: 1x4 brick with ridge
        brick_2x3.py        # Convenience: 2x3 brick
        plate_1x1.py        # Convenience: 1x1 plate
        plate_2x4.py        # Convenience: 2x4 plate
        slope_2x2.py        # Convenience: 2x2 slope
        collection.py       # All LEGO types in display grid
      clara/                # Clara brick system (diagonal lattice clutch)
        clara_lib.py        # clara_brick() — pure geometry
        clara.py            # Default entry point for ./run.sh
        parametric.py       # Worker interface: run(params, stl_path)
        panel_def.py        # Clara panel params (no tube/ridge internals)
        clara_2x4.py        # Convenience: 2x4 Clara brick
        tests/              # Geometry math verification
          test_clara_lattice.py  # Lattice tangent/overlap/symmetry tests
  renders/                  # Multi-angle render output (gitignored)
  docs/                     # Reports and documentation
    architecture.html       # Architecture plan + alternatives report
  build123d/                # build123d source (git submodule, dev branch)
  CLAUDE.md                 # Local Claude instructions (VLM verification rule)
  claude_instructions.md    # This file
  concerns.md               # Research log + lessons learned
  .claude_todo.md           # Task tracking
```

### Why LEGO and Clara are separate directories

LEGO and Clara are different brick systems with different clutch mechanisms:
- LEGO uses **cylindrical tubes** (anti-stud tubes + ridges) for underside grip
- Clara uses a **diagonal lattice** (±45° crisscross struts) for underside grip

They share shell geometry, stud dimensions, and fillet logic (in `common.py`),
but their internal structures are fundamentally different. Mixing them in one
directory caused confusion: launching with a Clara script but getting LEGO
tubes when changing size, tube-related sliders appearing for Clara, etc.

### Why panel_def.py and parametric.py are separate files

Process boundary. They run in **different processes**:
- `panel_def.py` is imported by Blender's Python (no build123d available)
- `parametric.py` runs in a `build_worker.py` subprocess under `uv run` (with build123d)

Merging would require all build123d imports to be behind lazy-import guards
to avoid crashing Blender's Python.

### panel_def.py SECTIONS as Single Source of Truth (DRY principle)

The `SECTIONS` list in each `panel_def.py` is the **single source of truth**
for all parametric inputs — parameter names, types, defaults, min/max ranges,
and descriptions. Every consumer that needs to present or accept these
parameters must read from SECTIONS, not maintain its own copy:

```
panel_def.py (SECTIONS data)  ←  single source of truth
    ↓
    ├── Blender panel  (blender_watcher.py reads SECTIONS → PropertyGroup)
    ├── CLI            (reads SECTIONS → auto-generated CLI args)
    ├── Web UI         (reads SECTIONS → auto-generated form fields)
    └── Python API     (reads SECTIONS → function kwargs with defaults)
```

**Rules:**
- Never duplicate parameter names, types, or ranges in a second location.
  If you need a list of overridable constants, derive it from SECTIONS data.
- New parameters are added in ONE place (SECTIONS) and automatically appear
  in all consumers.
- Each consumer is a thin adapter — it reads the SECTIONS structure and
  generates its own interface. The adapter contains no domain knowledge
  about what the parameters mean.

### Interactive Parameter Panel

**Philosophy**: Sliders are for exploration. Permanent changes go through Claude editing code.

```
LEGO panel (Blender N-sidebar, "build123d" tab):
  ├── Reset to Defaults button
  ├── Shape: brick_type (BRICK/PLATE/SLOPE), studs_x, studs_y, flat_rows
  ├── Dimensions: pitch, stud_diameter, stud_height, brick_height, plate_height
  ├── Walls: wall_thickness, floor_thickness, clearance
  ├── Internals: tube_outer_diameter, tube_inner_diameter, ridge_width/height
  ├── Text: stud_text, stud_text_font, stud_text_font_size, stud_text_height
  ├── Polish: enable_fillet (checkbox), fillet_radius
  └── Anatomy: show_anatomy (checkbox), region selector dropdown

Clara panel (same tab, different layout):
  ├── Reset to Defaults button
  ├── Shape: studs_x, studs_y (no brick_type enum — always lattice)
  ├── Dimensions: pitch, stud_diameter, stud_height, brick_height (no plate_height)
  ├── Walls: wall_thickness, floor_thickness, clearance
  ├── Text: stud_text, stud_text_font, stud_text_font_size, stud_text_height
  ├── Polish: enable_fillet (checkbox), fillet_radius
  └── Anatomy: show_anatomy (checkbox), region selector dropdown
  (no Internals section — Clara has no tubes or ridges)
```

**Architecture**: Panel definitions are data-driven. Model-specific params live in `models/bricks/<system>/panel_def.py` (pure data, no bpy). General panel infrastructure in `blender_watcher.py` dynamically builds Blender PropertyGroup + Panel from any `panel_def.py` found in the watched directory.

**Persistent worker** (`build_worker.py`): Keeps build123d imported across slider changes. Spawned as a child process of Blender (stdin/stdout pipes, not sockets). Eliminates the 1.3s import cost per rebuild — steady-state ~0.9s vs ~2.5s without worker.

**Hot-reload**: When the file watcher detects .py changes in the model directory:
1. Worker is killed (respawns on next slider use with fresh imports)
2. Panel is unregistered and re-registered from updated `panel_def.py`
3. All slider values reset to defaults

**Files**:
- `build_worker.py` — general persistent worker (repo root)
- `models/bricks/lego/panel_def.py` — LEGO parameter definitions + layout (includes tube/ridge)
- `models/bricks/lego/parametric.py` — LEGO build entry point (exposes `run(params, stl_path)`)
- `models/bricks/clara/panel_def.py` — Clara parameter definitions (no tube/ridge internals)
- `models/bricks/clara/parametric.py` — Clara build entry point (exposes `run(params, stl_path)`)

## Clara Brick Features

**Brand**: "Clara" (not Lego). All studs have raised "CLARA" text.

### Stud Text Dimensions (from real Lego measurements)
- Raised height: **0.1mm** above stud top surface
- Text block length: ~77% of stud diameter (~3.7mm on a 4.8mm stud)
- Letter height: ~39% of stud diameter (~1.88mm)
- Stroke width: ~0.2mm
- Font: bold sans-serif, centered on stud top
- Implementation: `Text("CLARA", font_size, font_style=FontStyle.BOLD)` + `extrude(0.1)` on stud top face

### Clara Brick Lattice (Diagonal Clutch)

Clara bricks replace cylindrical tubes with a ±45° diagonal lattice — a different clutch mechanism optimized for 3D printing. Similar to Montini bricks, but with diagonals in BOTH directions (Montini only has one direction).

**Requirements** (user-specified):
- 45° crisscross struts forming diamonds on the underside
- Diamond openings exactly fit the stud (inscribed circle = STUD_DIAMETER) — tangent contact, no overlap, no gap
- For a 2x4: 6 diagonal struts per direction (12 total)
- Struts run continuously from wall to wall — one unbroken strip per strut
- **Fully wall-connected**: no floating parts. Z-plane cross-section through the bottom is ONE contiguous region (walls + struts). This is NOT like LEGO tubes which float in the middle.
- It's a 45° rotated grid of squares superimposed on the bottom
- More 3D-print-friendly than tubes (no unsupported overhangs)
- Struts must be optimally wide but non-intersecting with studs (tangent only)

**Math**:
- Strut thickness: `t = PITCH / √2 − STUD_DIAMETER` (≈ 0.857 mm at standard dims)
- Struts per direction: `studs_x + studs_y` (6 for a 2x4)
- Strut c-values (both families): `c_start + i * PITCH` for `i = 0..n-1`, where `c_start = −(n−1)/2 * PITCH`
- +45° strut at c: center at `(−c/2, c/2)`, rotated 45°. Line: `y − x = c`
- −45° strut at c: center at `(c/2, c/2)`, rotated −45°. Line: `y + x = c`
- Diamond inscribed circle radius = `PITCH/(2√2) − t/2 = STUD_DIAMETER/2` (proven algebraically)

**Implementation** (`clara_brick()` in `models/bricks/clara/clara_lib.py`):
1. Shell: solid outer box − cavity (same as `lego_brick`)
2. Lattice: 2D sketch with `Locations([Pos * Rot])` context managers (NOT algebra `Pos * Rot * Shape` which silently fails in sketches), clipped with `Rectangle(inner_x, inner_y, mode=Mode.INTERSECT)`, extruded to `cavity_z`
3. Fillet threshold = `cavity_z` (not 0) — lattice strut edges are too thin for OCCT filleter
4. Studs, text — same as `lego_brick`

**Tests**: `models/bricks/clara/tests/test_clara_lattice.py` — 7 tests verifying tangent contact, no overlap, diamond fit, symmetry, wall connectivity, strut count. All pass across brick sizes 1x1 to 8x16.

### Slope Bricks
- `lego_slope(studs_x, studs_y, height, flat_rows)`: creates wedge/slope bricks
- Build order: solid outer box → `split` slope → subtract cavity (split by OFFSET plane) → tubes (sketch → extrude → `& sloped_cavity`) → studs → fillet → text
- Slope terminates at `Z=WALL_THICKNESS` (not Z=0) — creates realistic lip at low end like Lego 3039
- Cavity cut plane is offset INWARD by `FLOOR_THICKNESS` along slope normal — ensures solid material between slope face and interior everywhere
- **Cannot use pure 2D sketch approach** for slopes — the implicit cavity can't be trimmed by a plane (see concerns.md for full explanation)
- Studs only on the flat (non-sloped) portion
- Tubes clipped to cavity via `&` (boolean intersection) — never use `split()` on tubes

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

### Geometry Library Architecture (2D sketch -> extrude)

Shared code in `models/bricks/common.py`:
- `fillet_above_z(part, radius, z_threshold)` — fillet edges above a Z plane
- All shared constants: PITCH, STUD_DIAMETER, STUD_HEIGHT, BRICK_HEIGHT, etc.

LEGO system (`models/bricks/lego/lego_lib.py`):
- `lego_brick()`, `lego_slope()` — import shared constants from common.py
- LEGO-only constants: TUBE_OUTER_DIAMETER, TUBE_INNER_DIAMETER, RIDGE_WIDTH, RIDGE_HEIGHT
- Standard bricks: 2D sketch (walls + tubes via `GridLocations` circles) -> extrude -> ceiling -> ridge -> studs -> fillet -> text
- Slopes: solid outer `Box` -> `split` slope -> subtract trimmed cavity -> tubes (sketch -> extrude -> `& sloped_cavity`) -> studs -> fillet -> text

Clara system (`models/bricks/clara/clara_lib.py`):
- `clara_brick()` — import shared constants from common.py
- No LEGO-specific constants (no tubes/ridges)
- Lattice: 2D sketch with `Locations([Pos * Rot])` for +/-45 deg struts, clipped with `Mode.INTERSECT` -> extrude to cavity_z

## build123d API Quick Reference (for Claude)

### Boolean Operations
- **`a + b`** or `a.fuse(b)` — union (Mode.ADD in builder)
- **`a - b`** or `a.cut(b)` — subtraction (Mode.SUBTRACT)
- **`a & b`** or `a.intersect(b)` — common volume / clip (Mode.INTERSECT)
- **`Mode.REPLACE`** — discard current solid, use new
- **`Mode.PRIVATE`** — build geometry without adding to context

### Clipping Geometry to a Bounding Volume
Use `&` (boolean intersection) to clip oversized features to a boundary:
```python
clipped = oversized_part & bounding_volume   # BRepAlgoAPI_Common
```
Do NOT use `Mode.INTERSECT` in BuildPart for this — it trims the *entire existing solid* to the overlap, not just the new shape. Instead, compute the intersection separately and `add()` the result.

### split() Caveat
`split()` does NOT call `clean()` (unlike `fuse`/`cut`/`intersect`). Splitting hollow geometry (e.g., tubes) produces non-manifold topology that corrupts subsequent boolean unions. Use `&` for clipping instead, or call `.clean()` on split results.

### Coplanar Face Caveat
Never construct two shapes that share an entire planar face and then boolean-union them. OCCT produces degenerate triangles at the shared boundary, causing missing/flipped faces in tessellation (STL export). Example: wall extrusion (Z=0 to 8.6) + ceiling box (Z=8.6 to 9.6) → degenerate triangles at Z=8.6. Fix: use subtraction instead (solid box - cavity), so the ceiling is integral.

### Algebra Mode Location * Shape Caveat (BuildSketch)
`Pos(x, y) * Rot(0, 0, angle) * Rectangle(w, h)` (algebra mode) does NOT apply the transform in a `BuildSketch`. The rotation and position are silently ignored — the rectangle stays at origin, unrotated. Use `with Locations([Pos(x, y) * Rot(0, 0, angle)]):` context manager instead. This only affects sketch mode — algebra mode works fine in `BuildPart`.

### Locations + BuildSketch Caveat
`Locations([Pos(0, 0, z)])` does **NOT** move a `BuildSketch(Plane.XY)` to Z=z. The sketch plane stays at Z=0 regardless. Use `BuildSketch(Plane.XY.offset(z))` to place a sketch at a specific Z. `Locations` only moves 3D shapes and sketch *contents* (shapes within a sketch), not the sketch plane itself.

### Built-in Features Used in lego_lib.py
- **`GridLocations(x_spacing, y_spacing, x_count, y_count)`** — centered grid positioning (replaces manual centered_grid function). No Z offset — use `Plane.XY.offset(z)` on the BuildSketch instead.
- **`offset(shape, amount, kind=Kind.INTERSECTION)`** — in 2D sketch: shrinks a rectangle to create wall profile. `Kind.INTERSECTION` = sharp corners, `Kind.ARC` = rounded. (Not currently used in lego_lib — shell is built via outer box minus cavity instead. Kept here as reference for future use.)
- **`Pos(x,y,z) * Shape`** — position a shape at a location inside BuildPart. Cleaner than `Locations` for single positions.
- **`Compound([parts])`** — groups without boolean (vs `+` which fuses)

### Cheat Sheet Highlights
- **`Wedge(dx, dy, dz, xmin, zmin, xmax, zmax)`** — built-in slope/wedge primitive. Defines two opposing rectangular faces. Oriented differently from our slope convention (our slopes use split planes), but useful for simple wedges.
- **`GridLocations(x_spacing, y_spacing, x_count, y_count)`** — built-in centered grid. Direct replacement for `centered_grid()`. Used as a context manager with `with GridLocations(...):`
- **`Until.NEXT` / `Until.LAST`** — extrude until hitting the next/last face in the context. Avoids hardcoding heights when geometry constrains the extent.
- **`Select.NEW`** — after creating geometry in a builder, select only the newly-created edges/faces for chamfer/fillet. Avoids manual edge filtering.
- **"2D before 3D"** — official tip: sketch the entire cross-section (walls, cavities, tubes) in 2D first, then extrude once. Prevents boundary violations because all features share one outline. The official LEGO tutorial uses this approach.

### Key Documentation
- Docs: https://build123d.readthedocs.io/en/latest/
- Tips: https://build123d.readthedocs.io/en/latest/tips.html
- Cheat sheet: https://build123d.readthedocs.io/en/latest/cheat_sheet.html
- Official LEGO tutorial: https://github.com/gumyr/build123d/blob/dev/examples/lego.py
- Boolean pitfalls: avoid coplanar faces (extend cutting tools by epsilon), avoid self-intersecting geometry

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
