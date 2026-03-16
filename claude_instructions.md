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
| Hollow interior (open bottom) | **Cavity** | The empty void inside the brick, open from below. Not a face region — it's the absence of material |
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

**Overlapping regions (NOT mutually exclusive)**: Regions form a hierarchy.
A parent region (e.g. "Walls (all)") highlights all its children ("Walls (straight)"
+ "Wall Taper"). `classify_face()` returns the most specific region; parent
groups are resolved in the highlighting logic via `ANATOMY_REGION_GROUPS`.
Each sub-region has its own distinct color so they remain visually separable
even when shown together.

**Panel controls** (in the "Anatomy" section, below parametric sections):
Uses the generic `enable_key` section pattern (see below). The **Show Anatomy
Colors** checkbox in the section header toggles coloring on/off and switches
viewport shading between MATERIAL (colors visible) and SOLID (matcap). When
enabled, the **Region** dropdown appears — "All Regions" colors everything;
selecting a specific region highlights only that region and grays out the rest.

**Regions and colors**:
| Region | Color | Classification rule |
|--------|-------|---------------------|
| Studs (all) | — | Parent group: studs + stud_taper |
| Studs (straight) | Red | Straight cylinder portion of studs |
| Stud Taper | Pink | Tapered zone at stud tops (when stud_taper active) |
| Logo | Gold | Face center Z > stud tops (text extrusion) |
| Deck | Green | Horizontal upward face at Z ≈ brick height (top surface only) |
| Walls (all) | — | Parent group: walls + taper |
| Walls (straight) | Blue | Face on outer perimeter, below taper zone |
| Wall Taper | Light blue | Tapered zone at top of walls (when taper active) |
| Internals (all) | — | Parent group: internal_walls + internal_ceiling |
| Internal Walls | Purple | Vertical faces in cavity (tubes, lattice struts, ridges) |
| Internal Ceiling | Lavender | Underside of deck facing down into cavity |
| Base | Gray | Horizontal downward face at Z ≈ 0 |
| Fillets/Other | Light gray | Unclassified (fillet transitions, etc.) |

**Implementation**:
- `panel_common.py`: `classify_face(mesh, poly, params)`, `ANATOMY_COLORS`, `ANATOMY_REGION_ITEMS`,
  `ANATOMY_REGION_GROUPS` — shared definitions imported by each `panel_def.py`
- `blender_watcher.py`: generic Blender machinery only — color attributes, materials, viewport toggle
  — reads anatomy data from `panel_def` via `getattr()` (gated on availability)
- `_apply_anatomy_colors(obj, params, highlight_region)` — FLOAT_COLOR attribute on CORNER domain
- `_setup_material(obj, mat_name, configure_fn)` — shared material scaffold
- Colors auto-reapply after every mesh rebuild (slider change, file change)

**Design principle**: The anatomy system is **model-defined, generically displayed**.
Region definitions and classification live in `panel_common.py` (or per-system
`panel_def.py` overrides). `blender_watcher.py` handles only the Blender-side
machinery. Any future brick system gets anatomy by importing from `panel_common`
(or defining its own `classify_face`, `ANATOMY_COLORS`, `ANATOMY_REGION_ITEMS`).

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
  run.sh                    # Entry point: ./run.sh models/bricks/brick.py
  blender_watcher.py        # Blender-side script (watches + reimports)
  render_preview.py         # Headless Blender render: STL -> multi-angle PNGs
  render.sh                 # Convenience wrapper for render_preview.py
  build_worker.py           # Persistent build subprocess (keeps build123d imported)
  models/                   # All build123d model scripts
    example_box.py          # Simple example: box with cylindrical hole
    bricks/                 # Unified brick system
      common.py             # Shared constants + bevel_above_z
      panel_common.py       # Shared panel sections (Walls, Text, Fillet) + anatomy classification
      parametric_base.py    # Shared override application + worker interface (run, apply_overrides)
      brick_lib.py          # UNIFIED geometry: brick(), slope(), cross shapes, all clutch types
      parametric.py         # UNIFIED worker: _build() + overrides for all params
      panel_def.py          # UNIFIED panel sections + presets (LEGO Standard, Clara Mini, etc.)
      brick.py              # Default entry point for ./run.sh
      collection.py         # Multiple brick types in display grid
      tests/                # Geometry math verification
        test_lattice.py     # Lattice tangent/overlap/symmetry tests
  renders/                  # Multi-angle render output (gitignored)
  docs/                     # Reports and documentation
    architecture.html       # Architecture plan + alternatives report
  build123d/                # build123d source (git submodule, dev branch)
  CLAUDE.md                 # Local Claude instructions (VLM verification rule)
  claude_instructions.md    # This file
  concerns.md               # Research log + lessons learned
  .claude_todo.md           # Task tracking
```

### Unified brick system (replaced separate lego/ and clara/ dirs)

LEGO and Clara were separate directories with ~70% duplicated code. Now merged
into a single system where clutch type (TUBE/LATTICE/NONE) is a dropdown
parameter. LEGO and Clara are presets, not separate codebases. Clara-only
features (corner radius, wall taper, stud taper) are available with any clutch.
Cross-shaped bricks and 4-directional slopes added in the unified system.

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
Unified panel (Blender N-sidebar, "build123d" tab):
  ├── Preset dropdown (Clara Mini, LEGO Standard, etc.) + reset
  ├── Shape: shape_mode (RECTANGLE/CROSS), studs_x/y or directional params, cross widths
  ├── [✓] Slope: enable_slope, 4 directional sloped_rows (+Y/-Y/+X/-X), slope_min_z
  ├── Studs & Body: pitch, stud_diameter, stud_height, brick_height
  ├── Walls: wall_thickness, floor_thickness, clearance
  ├── Clutch: clutch_type (TUBE/LATTICE/NONE), tube params (visible when TUBE)
  ├── [✓] Corner Radius: enable_corner_radius, corner_radius
  ├── [✓] Wall Taper: enable_wall_taper, height, inset, curve (LINEAR/CURVED)
  ├── [✓] Stud Taper: enable_stud_taper, height, inset, curve (LINEAR/CURVED)
  ├── [✓] Text: enable_text, stud_text, font, font_size, text_height, rotation
  ├── [✓] Fillet: enable_fillet, edge_style (Rounded/Chamfer), fillet_radius, include_bottom, skip_concave
  └── [✓] Anatomy: show_anatomy, region selector dropdown
  [✓] = toggleable section (enable_key pattern, see below)
```

**Architecture**: Panel definitions are data-driven. Params live in `models/bricks/panel_def.py` (pure data, no bpy). General panel infrastructure in `blender_watcher.py` dynamically builds Blender PropertyGroup + Panel from any `panel_def.py` found in the watched directory.

**Section enable_key pattern**: Any section can have an `enable_key` field pointing
to a bool param in its `params` list. When present:
- The section header shows a checkbox + label (instead of just a label)
- When unchecked, all child params are hidden (section collapses)
- The enable param itself is drawn in the header, not in the body
- `parametric.py` reads the enable flag and zeros out dependent values when disabled

Anatomy uses this pattern too (built at registration time in `blender_watcher.py`
since it needs bpy callbacks), but it's display-only — not sent to the build worker.

**Preset system** (unified):
- `panel_def.py` exports a `PRESETS` list of `{key, label, description, params}` dicts
- Each preset's `params` dict contains json_key overrides (delta from SECTIONS defaults)
- Apply preset = reset all params to defaults, then apply overrides
- Clara Mini Brick preset has empty params (matches defaults), LEGO Standard overrides clutch/taper/radius
- Panel shows preset dropdown + reset icon
- `blender_watcher.py` loads PRESETS at registration and creates a PresetOp operator

**Persistent worker** (`build_worker.py`): Keeps build123d imported across slider changes. Spawned as a child process of Blender (stdin/stdout pipes, not sockets). Eliminates the 1.3s import cost per rebuild — steady-state ~0.9s vs ~2.5s without worker.

**Hot-reload**: When the file watcher detects .py changes in the model directory:
1. Worker is killed (respawns on next slider use with fresh imports)
2. Panel is unregistered and re-registered from updated `panel_def.py`
3. All slider values reset to defaults

**Files**:
- `build_worker.py` — general persistent worker (repo root)
- `models/bricks/panel_common.py` — shared panel sections (Walls, Text, Fillet) + anatomy
- `models/bricks/parametric_base.py` — shared `apply_overrides()` + `run()` + `standalone_main()`
  - Override keys derived from `panel_def.SECTIONS` (type + json_key) — no manual override lists
- `models/bricks/panel_def.py` — unified panel sections + presets (Shape, Slope, Clutch, etc.)
- `models/bricks/parametric.py` — unified `_build()` dispatching to `brick_lib.brick()` or `brick_lib.slope()`

## Unified Brick System (IMPLEMENTED)

### Motivation
LEGO and Clara share ~80% of their geometry code (shell, studs, fillets, text, slopes).
The only real difference is the clutch mechanism (tubes vs lattice). Merging them into
one unified system with a clutch dropdown eliminates code duplication and enables:
- Cross-shaped (L/T/+) bricks — same code path for any clutch type
- 4-directional slopes — works on any shape
- Any feature (corner radius, taper, stud taper) available to any brick, not just Clara
- LEGO and Clara become presets, not separate codebases

### Clutch Types (dropdown)
| Type | Description | Internal Geometry |
|------|-------------|-------------------|
| **TUBE** | Standard LEGO clutch | Cylindrical anti-stud tubes + ridge rail (1-wide) |
| **LATTICE** | Clara diagonal clutch | ±45° crisscross struts, diamond openings fit studs |
| **NONE** | Hollow (no clutch) | Empty cavity, just shell + studs |

### Cross-Shape System (L/T/+ bricks)

**Shape mode dropdown**: RECTANGLE (current, backwards compatible) or CROSS.

**RECTANGLE mode**: `studs_x`, `studs_y` — standard rectangular bricks. Internally
these are converted to the directional system for the geometry functions.

**CROSS mode parameters**:
- `studs_plus_x` (int, ≥0): arm length extending in +X from center
- `studs_plus_y` (int, ≥0): arm length extending in +Y from center
- `studs_minus_x` (int, ≥0): arm length extending in -X from center
- `studs_minus_y` (int, ≥0): arm length extending in -Y from center
- `cross_width_x` (int, ≥1, default 1): width of the vertical (Y-axis) arms in X
- `cross_width_y` (int, ≥1, default 1): width of the horizontal (X-axis) arms in Y
- Cross width sliders only visible when CROSS mode is enabled

**Origin**: center of the `cross_width_x × cross_width_y` center block. When all
directional params are 0, result is a `cross_width_x × cross_width_y` brick at origin
(1×1 when widths are 1).

**2D footprint** = union of two rectangles:
- **Horizontal bar**: X extent from `-studs_minus_x * PITCH` to `+(cross_width_x + studs_plus_x) * PITCH`,
  Y extent = `cross_width_y * PITCH`, centered on Y=0
- **Vertical bar**: Y extent from `-studs_minus_y * PITCH` to `+(cross_width_y + studs_plus_y) * PITCH`,
  X extent = `cross_width_x * PITCH`, centered on X=0
- The center block (`cross_width_x × cross_width_y`) is the overlap region

**Examples**:
- All zeros, widths=1: 1×1 brick
- `plus_x=1, plus_y=1, minus=0, widths=1`: 2×2 brick (bottom-left at origin)
- `plus_x=5, plus_y=5, minus=0, widths=1`: L-shape, 5+5+1=11 unique stud positions
- `all=3, widths=1`: + (plus/cross) shape
- `plus_x=5, minus_x=5, plus_y=3, minus_y=0, widths=1`: T-shape
- `plus_x=3, plus_y=3, widths=2`: L-shape with 2-wide arms

**Geometry construction for cross shapes**:
1. 2D polygon outline (union of two rects) → extrude → shell
2. Inset polygon by WALL_THICKNESS → extrude to cavity_z → subtract → cavity
3. Studs at all grid positions within the cross footprint
4. Tubes at all valid positions within the footprint (TUBE clutch)
5. Lattice struts clipped to non-rectangular cavity (LATTICE clutch)
6. Slope planes cut as needed → fillet → text

### 4-Directional Slopes

Replace single slope (+Y direction) with 4 independent slopes:
- `slope_plus_x` (int, sloped rows): slope descending toward +X
- `slope_plus_y` (int, sloped rows): slope descending toward +Y
- `slope_minus_x` (int, sloped rows): slope descending toward -X
- `slope_minus_y` (int, sloped rows): slope descending toward -Y

Each value = number of stud rows that are sloped in that direction.
0 = no slope in that direction. Internally converted to flat_rows = total_rows - sloped_rows.

**Multiple slopes active simultaneously**: slopes intersect. The brick is cut by
ALL active slope planes. This enables corner roof pieces (e.g., minus_x=1 + minus_y=1
creates a hip roof corner).

**`slope_min_z`** (float, default WALL_THICKNESS=1.5): how low the slope descends.
- Current behavior: slope terminates at WALL_THICKNESS (realistic lip at bottom)
- `slope_min_z=0`: slope goes all the way to Z=0 (sharp edge)
- Configurable for different printing/aesthetic needs

**Works on both RECTANGLE and CROSS shapes.** A slope on a cross-arm slopes that arm
independently. The slope plane applies to the entire brick and intersects with the
footprint naturally.

### Presets (unified system)
| Preset | Clutch | Stud Text | Corner Radius | Taper | Stud Height | Notes |
|--------|--------|-----------|---------------|-------|-------------|-------|
| LEGO Standard | TUBE | "LEGO" | 0 | off | 1.8 | Classic LEGO dimensions |
| Clara Mini Brick | LATTICE | "CLARA" | 2.0 | on | 4.0 | 3D-print optimized |
| Clara Mini Slope | LATTICE | "CLARA" | 2.0 | on | 4.0 | Mini Brick + slope |
| Hollow Shell | NONE | "" | 0 | off | 1.8 | No clutch, for testing |

### File Structure (after refactor — COMPLETED)
```
models/bricks/
  common.py             # Shared constants (unchanged)
  panel_common.py       # Shared panel helpers + anatomy
  parametric_base.py    # Override application (unchanged)
  brick_lib.py          # UNIFIED geometry: brick(), slope(), cross shapes, all clutch types
  parametric.py         # UNIFIED worker: _build() + overrides
  panel_def.py          # UNIFIED panel sections + presets
  brick.py              # Default entry point for ./run.sh
  collection.py         # Display grid of various brick types
  tests/
    test_lattice.py     # Lattice geometry tests (moved from clara/tests/)
```

Old directories (`lego/`, `clara/`) deleted.

## Brick Feature Details

**Stud text**: Configurable per brick ("CLARA", "LEGO", or custom). Raised embossed text on each stud.

### Stud Text Dimensions (from real Lego measurements)
- Raised height: **0.1mm** above stud top surface
- Text block length: ~77% of stud diameter (~3.7mm on a 4.8mm stud)
- Letter height: ~39% of stud diameter (~1.88mm)
- Stroke width: ~0.2mm
- Font: bold sans-serif, centered on stud top
- Implementation: `Text("CLARA", font_size, font_style=FontStyle.BOLD)` + `extrude(0.1)` on stud top face

### Lattice Clutch (LATTICE)

The LATTICE clutch uses ±45° diagonal lattice struts instead of cylindrical tubes — optimized for 3D printing. Similar to Montini bricks, but with diagonals in BOTH directions (Montini only has one direction).

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

**3D Printing Features** (available with any clutch type):
- **Corner radius** (`corner_radius`): 2D rounding of the brick outline (like CSS `border-radius`). Visible from top-down view. Uses `RectangleRounded(w, h, r)` for the outer sketch. Inner cavity stays sharp — thicker corners = stronger for printing. Clamped to half the smallest outer dimension.
- **Wall taper** (`taper_height` + `taper_inset` + `taper_curve`): Top portion of outer walls slopes inward. LINEAR = straight line. CURVED = quarter-circle profile `f(t) = 1 - sqrt(1 - t^2)` — tangent to wall at bottom, tangent to deck at top, no inflection point. Curved uses 8 intermediate loft profiles.
- **Stud taper** (`stud_taper_height` + `stud_taper_inset` + `stud_taper_curve`): Top portion of studs tapers inward (radius decreases). Same LINEAR/CURVED options. Built as a standalone lofted Part, placed via `add()` + `GridLocations`.
- When no taper/radius is active, `brick()` uses the fast `Box()` path (no loft overhead).

**Implementation** (`brick()` in `models/bricks/brick_lib.py`):
1. Shell: 3-branch construction — has_taper → multi-profile loft, corner_radius > 0 → rounded rect extrude, else → Box (fastest)
2. Cavity: sharp rectangle subtracted from shell (intentionally NOT rounded — thicker material at corners)
3. Clutch internals: TUBE → `_build_tubes()` + `_build_ridge()`, LATTICE → `_build_lattice()`, NONE → nothing
4. Fillet threshold: LATTICE → `cavity_z` (strut edges too thin), TUBE/NONE → 0
5. Studs (with optional stud taper via `_build_stud()`), text

### Slope Bricks

`slope()` in `brick_lib.py`. Supports 4-directional slopes with any clutch type.

**Build order** (critical):
1. Outer shell (with optional corner_radius + taper via loft) → sequential `split` by ALL active slope planes
2. Cavity box → sequential `split` by ALL OFFSET slope planes (FLOOR_THICKNESS gap)
3. Shell = sloped_outer - sloped_cavity
4. Clutch internals built separately → clipped with `& sloped_cavity`
5. Studs on flat portion only (positions computed per-direction from hinge points)
6. Fillet (may fail on slopes — known OCCT limitation, caught gracefully)
7. Text on flat stud positions

**Panel**: "Slope" section with `enable_key: "enable_slope"` (default False).
When enabled, 4 directional `flat_rows` sliders (+Y/-Y/+X/-X) + `slope_min_z`.

**Key lessons**:
- Clutch internals MUST be built in a separate `BuildPart` for slopes, boolean-intersected with `sloped_cavity`
- Slope terminates at `Z=slope_min_z` (default WALL_THICKNESS) — creates realistic lip at low end
- Cavity cut plane is offset INWARD by `FLOOR_THICKNESS` along slope normal
- **Cannot use pure 2D sketch approach** for slopes — the implicit cavity can't be trimmed by a plane
- Studs only on the flat (non-sloped) portion
- Clutch internals clipped to cavity via `&` — never use `split()` on tubes

**Tests**: `models/bricks/tests/test_lattice.py` — 7 tests verifying tangent contact, no overlap, diamond fit, symmetry, wall connectivity, strut count. All pass across brick sizes 1x1 to 8x16.

### Collection Display
- `collection.py`: generates all brick types in a grid layout
- Rows: bricks, plates, slopes — columns: different sizes
- Grid spacing: 5 × PITCH (40mm) between brick centers
- All parts combined into a single `Compound` for export

### Testing Strategy (3 layers)

1. **Pure math tests** (`models/bricks/tests/test_lattice.py`): Verify geometry
   algorithms without importing build123d. Fast, deterministic, no CAD kernel
   dependency. Use these for anything computable from first principles (strut
   dimensions, tangent contact, symmetry). Run with `uv run models/bricks/tests/test_lattice.py`.

2. **Integration tests** (`scratchpad.py`): Run every configuration through the
   full build pipeline (parametric.py → brick_lib → build123d → STL export).
   Catches build123d API issues, boolean failures, and unexpected face counts.
   Run with `uv run scratchpad.py`. Each config verified by face count + no exception.

3. **VLM render verification**: Visual inspection of multi-angle diagnostic renders.
   Catches visual bugs (exposed cavities, missing features, holes) that face counts
   miss. Use `./render.sh` + Read tool. Required for any new geometry.

Why 3 layers: math tests are fast but can't catch CAD kernel bugs. Integration tests
catch build failures but can't see visual problems. VLM catches what the other two miss.
New pure-math helpers should get their own test functions in `tests/`. New brick configs
should be added to `scratchpad.py`. New geometry changes always get VLM rendered.

### VLM Render Verification
- `render_preview.py`: headless Blender script, EEVEE engine
- 14 diagnostic angles: 6 cardinal (front/back/left/right/top/bottom) + 8 diagonal (±30° elevation at 45°/135°/225°/315° azimuth)
- Sun lights (no distance attenuation) + ambient world for consistent illumination
- Auto-smooth shading (30° angle threshold) for crisp edges on curved surfaces
- Plastic material: white Principled BSDF (0.95 albedo, Roughness 0.3)
- 1024×1024 PNG output to `renders/` directory
- Claude reads PNGs via Read tool for visual verification

### Geometry Library Architecture

**`models/bricks/common.py`** (shared constants + helpers):
- `bevel_above_z(part, radius, z_threshold, style, include_bottom, skip_concave)` — fillet or chamfer edges. Uses `filter_by_position(Axis.Z, ...)` for Z-threshold and `Edge.is_interior` for concavity detection. Handles boundary edges (<2 adjacent faces) gracefully.
- All shared constants: PITCH, STUD_DIAMETER, STUD_HEIGHT, BRICK_HEIGHT, SKIP_CONCAVE, etc.
- `fillet_above_z` kept as backwards compatibility alias

**`models/bricks/brick_lib.py`** (unified geometry):
- `brick()`, `slope()` — two main functions with clutch type as a parameter
- LEGO tube constants: TUBE_OUTER_DIAMETER, TUBE_INNER_DIAMETER, RIDGE_WIDTH, RIDGE_HEIGHT
- Standard bricks: Box - cavity → clutch internals → studs → fillet → text
- Cross-shape bricks: union of two Boxes → inset cavity → studs at grid positions within footprint
- Slopes: shell → split by slope planes → clutch `& sloped_cavity` → studs on flat portion
- Lattice: `_build_lattice()` — 2D sketch with `Locations([Pos * Rot])` for ±45° struts

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
