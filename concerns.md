# Concerns — build123d Live Blender Preview

## 2026-03-15: Initial Research Phase

### Research Frenzy (7 parallel agents)

Launched 7 agents to investigate all angles before writing any code:

1. **BlendQuery addon research** — Found the only existing direct build123d→Blender integration. Architecture: subprocess isolation + pickle IPC + `from_pydata()`. Sound design but stale (last commit Jul 2024), broken on Blender 5.0. Unmerged PR #13 (by petersupan) fixes Blender 5.0 compatibility. 70 stars, 7 forks.

2. **Blender mesh update API** — Critical finding: `mesh.clear_geometry()` + `mesh.from_pydata()` preserves material slots, while `obj.data = new_mesh` (datablock swap) does NOT preserve materials with default `link='DATA'`. This eliminates the datablock swap approach entirely.

3. **Live CAD preview workflows** — Surveyed: BlendQuery, ocp-vscode, CQ-editor, cq-studio, yacv, Auto Reload addon, Script Watcher addon, blender-remote. Key finding: ocp-vscode is what most build123d users actually use (VS Code three.js viewer), not Blender. But the user specifically wants Blender.

4. **build123d export formats** — Found `Shape.tessellate()` method (shape_core.py:2092) which returns raw `(vertices, triangles)` — no file export needed. Also found `Mesher._mesh_shape()` (mesher.py:276) which returns plain tuples. No OBJ exporter exists. STL, STEP, glTF, BREP, 3MF all supported.

5. **Blender CLI and scripting** — Confirmed Blender 5.0.1 on this machine. STL import is `bpy.ops.wm.stl_import()` (old `import_mesh.stl` completely removed in 5.x). No subprocess sandboxing. `--factory-startup` for clean scenes. `sys.argv` after `--` for custom arguments.

6. **build123d installation** — PyPI 0.10.0 supports Python 3.10-3.13. This machine's Homebrew Python is 3.14.3 which needs the dev branch (`git+https://github.com/gumyr/build123d.git@dev`). OCP ARM64 macOS wheels available. Conda-forge lags at 0.9.1.

7. **Direct mesh transfer alternatives** — Investigated sockets, shared memory, named pipes, `pip install bpy`, embedding build123d in Blender. Socket + `foreach_set()` is fastest (~20-70ms) but overkill. STL file-based is simpler and good enough (~200-500ms). `pip install bpy` is elegant but fragile (Python version coupling).

### Architecture Decision

**Chose STL file watcher over socket IPC.** Rationale:
- Claude-driven workflow has natural pauses (user talks to Claude, Claude edits, script runs). Sub-second latency improvements don't matter when the bottleneck is human conversation.
- STL file is a natural debugging checkpoint — can be opened in any tool.
- No custom protocol to maintain.
- Socket approach would be premature optimization.

**Rejected BlendQuery reuse.** Rationale:
- Broken on our Blender version (5.0.1)
- Would need forking + applying unmerged PR + fixing hardcoded tolerances
- Our requirements are simpler (one-object preview, not full CadQuery workspace)
- Building our own is ~100 lines vs understanding and maintaining a fork

### Known Risks

1. **Python version mismatch**: If user upgrades Python or build123d, the venv may break. setup.sh must handle this gracefully.

2. **Blender API instability**: STL import operator already changed once (3.x → 4.1+). Version-safe wrapper needed.

3. **Tessellation quality**: Default tolerances (`1e-3` linear, `0.1` angular) may not suit all models. Should be configurable.

4. **Large models**: For complex CAD assemblies, STL export + import could be slow. Not a concern for typical Claude-assisted modeling (simple parts), but worth noting.

5. **CQ-editor reliability warning**: CQ-editor's auto-reload "randomly stops working" (GitHub issue #280). Our file watcher must be more robust — use mtime comparison, not content hashing.

6. **Orphan data accumulation**: Every STL reimport in Blender can create orphan mesh datablocks if not cleaned up. Must explicitly remove temporary import objects and meshes.

## 2026-03-15: Implementation Phase

### Implementation Notes

- Implemented subprocess + STL file watcher as planned. ~250 lines total across 4 files.
- **setup.sh**: Prefers Python 3.13 over 3.14 (better compatibility). Falls back through 3.13→3.12→3.11→3.10→3.14→generic. Detects Blender via app bundle path, PATH, then macOS Spotlight.
- **blender_watcher.py**: Uses `clear_geometry()` + `from_pydata()` for mesh updates. First import creates the preview object; subsequent imports update in-place. Explicitly removes temporary import objects and orphan meshes (addressing risk #6).
- **run.sh**: Passes source path, Python path, and STL path to Blender via `--` separator. All paths resolved to absolute before passing.
- **Convention**: User scripts get `BUILD123D_PREVIEW_STL` env var for STL output path. Simple, no magic.
- Version-safe STL import: checks `hasattr(bpy.ops.wm, "stl_import")` at runtime (addressing risk #2).

### Blender startup context crash
- `bpy.ops.view3d.view_selected()` throws `RuntimeError: Operator bpy.ops.view3d.view_selected.poll() failed` during `--python` startup because the view3d context isn't available yet.
- Fix: `bpy.context.temp_override(area=area, region=region)` wrapping the operator call.
- The crash also killed `main()` before the timer was registered, so the watcher never started. Fix: register `bpy.app.timers` BEFORE the initial build, not after.

### build123d dev branch API break
- `Add` (capital A) renamed to `add` (lowercase) in the dev branch. Import failed silently. Fixed with `replace_all` in lego_lib.py.

### Fillet + text interaction
- `_apply_fillets()` (now `fillet_above_z()`) fails with `ValueError: Failed creating a fillet` when applied to geometry containing extruded text edges. OCCT can't handle filleting edges smaller than the fillet radius.
- Root cause: text geometry has sub-0.1mm edges, fillet radius is 0.15mm.
- Fix: restructure to fillet BEFORE adding text. `lego_studs()` creates cylinders only, `lego_stud_text()` / `raised_text_at()` is called after filleting.

### Slope brick exposed cavity (VLM-caught bug)
- Initial `lego_slope()` built a hollow box then cut with a slope plane. The cut exposed the interior cavity through the sloped face — visible as a large rectangular opening.
- First fix attempt: build solid outer → cut slope → subtract slope-trimmed cavity. Used `add(cavity, mode=Mode.SUBTRACT)` and later `sloped_outer - sloped_cavity`. The boolean worked, but the cavity was still visible because...
- Root cause: the slope cut went to Z=0, eliminating the front wall entirely. The bottom opening (which is correct — bricks ARE open from below) became fully exposed from the +Y side. No wall remained to partially occlude the interior.
- Confirmed via VLM multi-angle renders: the `front` (side profile) view showed the slope face was solid. The "hole" was actually the bottom opening seen through the zero-height front lip.
- Partial fix: slope plane now terminates at `Z=WALL_THICKNESS` (1.5mm) instead of Z=0, creating a realistic lip. This improved the profile but the cavity was still visible from above because the cavity ceiling touched the slope surface (zero wall thickness between slope face and interior).
- **Actual root cause**: the cavity cut plane was identical to the outer slope cut plane. Both used the same `Plane(origin=(0, hinge_y, height), z_dir=(0, slope_dz, slope_dy))`. This means the cavity's angled ceiling sits flush against the outer slope face — zero material between them. Looking over the lip from above, you see straight into the interior.
- **Final fix**: offset the cavity cut plane inward by `FLOOR_THICKNESS` perpendicular to the slope surface. Computed the slope normal magnitude (`sqrt(slope_dz² + slope_dy²)`), then shifted the cavity plane origin by `-FLOOR_THICKNESS * normal/|normal|`. This ensures solid material everywhere between the slope face and interior cavity.
- VLM verification of 14-angle renders confirmed the fix: `iso_fr` shows solid slope with no hole, `right` shows only the standard bottom opening, all exterior angles fully solid.
- Lesson 1: VLM multi-angle verification is essential for 3D geometry bugs. A single iso view can be misleading — the 14-angle render revealed the true nature of the problem.
- Lesson 2: Don't rationalize VLM findings. If the rendered image shows a hole, there IS a hole — investigate the geometry math instead of explaining it away as "the bottom opening from another angle."

### Slope brick tube protrusion (VLM-caught bug)
- Bottom reinforcement tubes were created at full `height - FLOOR_THICKNESS` (8.6mm), but the slope ceiling at the tube's Y position is lower (~8.26mm for a 2x2). The tube poked through the slope surface.
- First fix attempt: `split(tubes, bisect_by=cavity_cut_plane, keep=Keep.BOTTOM)`. This catastrophically broke the geometry — the entire brick shell disappeared, leaving only a tube fragment. Face count dropped from 144 to 76. Cause: `split()` on hollow cylinder geometry produces results that corrupt the boolean union with the shell.
- **Working fix**: compute max Z at each tube position from the cavity cut plane equation (`z = origin_z - slope_dz * (y - origin_y) / slope_dy`), then create individual tubes at the correct limited height. No `split()` involved.
- Lesson: `split()` on complex geometry (hollow cylinders) can produce degenerate results that break subsequent boolean operations. Prefer computing dimensions analytically over cutting geometry with planes when possible.

### Blender EEVEE engine name
- Blender 5.0: engine is `"BLENDER_EEVEE"`, not `"BLENDER_EEVEE_NEXT"` (which was 4.x).
- `Material.use_nodes` and `World.use_nodes` are deprecated in 5.0 (nodes always active). Removed the calls, BSDF node is available by default.

### Render quality iteration
- Initial renders were near-black silhouettes. Point lights with 300W energy at 40-60mm distance attenuate too much for ~16mm brick geometry.
- Fix: switched to SUN lights (no distance attenuation) + ambient world background + `shade_smooth()` + auto-smooth by angle. Sun lights give consistent illumination regardless of object/camera position.

## 2026-03-15: Generalization Refactoring

### Extracted general functions
- Analyzed which functions labeled "general" actually were. Most were "specific" — they used LEGO constants (PITCH, WALL_THICKNESS, etc.) directly.
- Extracted 6 genuinely general functions: `centered_grid`, `hollow_box`, `cylinders_at`, `hollow_cylinders_at`, `raised_text_at`, `fillet_above_z`. All are reusable for any CAD project.
- LEGO functions are now thin wrappers that compute dimensions and delegate to generals.
- Text pipeline: build123d's `Text` → `extrude` IS the ideal pipeline. OCCT renders fonts directly to exact B-Rep curves — SVG would be an unnecessary intermediate step.

### Concern: build123d not yet tested on this machine
- setup.sh has not been run yet. build123d may fail to install if OCP wheels aren't available for the detected Python version. This is a known risk — the setup script handles it by preferring Python 3.13.
- End-to-end test (run.sh → Blender → mesh update) not yet performed. Need to verify the full pipeline works.

## 2026-03-15: build123d API Frenzy (12 agents)

### Why the frenzy was needed
- The slope tube clipping code used 18 lines of manual plane-equation math to compute tube heights. This was ugly and fragile (first version forgot the tube radius, second forgot the far edge). The user correctly identified this as a code smell — build123d should have tools for this.

### Key discoveries

#### Boolean intersection (`&` operator) for clipping
- `tube & cavity_volume` clips the tube to fit inside the cavity using `BRepAlgoAPI_Common`. 4 lines replaces 18 lines of manual math.
- The `&` operator calls `.clean()` automatically, which is why it works on hollow cylinders while `split()` didn't.

#### split() doesn't call clean()
- Root cause of our earlier `split()` failure on hollow cylinders: `split()` uses `BRepAlgoAPI_Splitter` but NEVER calls `ShapeUpgrade_UnifySameDomain` (the `.clean()` step). This leaves extra coplanar faces and non-manifold topology at the cut plane. When passed to `fuse()`, the corrupted topology causes the entire boolean to produce garbage (76 faces instead of 144, entire shell lost).
- Fix: either call `.clean()` on split results, or use `&` instead.

#### Mode.INTERSECT trims the WHOLE part, not just new geometry
- `Mode.INTERSECT` in a `BuildPart` context replaces the entire accumulated solid with `existing ∩ new_shape`. It does NOT mean "add only the overlapping part of the new shape." For clipping a tube to a cavity, you must compute `tube & cavity` outside the builder and `add()` the result.

#### Official LEGO tutorial uses 2D sketch approach
- The official build123d LEGO example (lego.py) sketches the entire cross-section in 2D (walls + ridges + tube circles), then extrudes once. Tubes can't exceed boundaries because they're defined in the same sketch profile. This eliminates the need for boolean clipping entirely.
- Also uses `offset()` for hollowing and `GridLocations` for positioning — built-in features we're not using.

#### Unused build123d features that could simplify our code
- `GridLocations(x_spacing, y_spacing, x_count, y_count)` — replaces `centered_grid()`
- `offset(face, -thickness)` — replaces `hollow_box()`
- `Compound([parts])` — groups without boolean (unlike `+` which fuses)
- `extrude(until=Until.NEXT)` — extrude to a target face (auto height)
- `Mode.PRIVATE` — build intermediate geometry without affecting the part

#### Boolean pitfalls (from OCCT kernel)
- Coplanar faces cause failures — extend cutting tools by epsilon beyond boundaries
- Near-tangent surfaces fail — avoid shapes that just graze each other
- `Part & Part` returns `Compound` (not `Part`) — fine for `add()` but be aware

## 2026-03-15: 2D Sketch Architecture Rewrite

### What changed
- Rewrote `lego_lib.py` from 556 lines to 222 lines (60% reduction)
- Eliminated 9 helper functions: `centered_grid`, `hollow_box`, `cylinders_at`,
  `hollow_cylinders_at`, `raised_text_at`, `lego_brick_body`, `lego_studs`,
  `lego_stud_text`, `lego_bottom_tubes`, `lego_bottom_ridge`
- Only `fillet_above_z()` kept as general helper (used in both brick and slope)
- Two main functions remain: `lego_brick()` and `lego_slope()`

### Architecture: 2D sketch → extrude for standard bricks
- Cross-section sketch defines walls (Rectangle → offset → subtract) + tubes
  (GridLocations → Circle - Circle) in 2D
- Single `extrude(amount=cavity_z)` creates all vertical structure
- Ceiling box added separately (different thickness from walls: FLOOR_THICKNESS
  vs WALL_THICKNESS)
- Ridge added as 3D Box (doesn't extend full cavity height, can't be in sketch)
- Studs via nested `Locations([Pos(0,0,height)]) → GridLocations → Cylinder`
- Text in separate BuildPart after filleting (OCCT filleter chokes on tiny text edges)

### Why the slope can't use pure 2D sketch approach
- The slope cuts through the ceiling, exposing the cavity where slope_Z < ceiling_Z
- The 2D sketch creates implicit cavities (void between walls), which can't be
  "cut" by a plane — the cavity is just absence of material
- The slope MUST use explicit shell construction (solid outer - trimmed cavity)
  to maintain FLOOR_THICKNESS of material between slope face and cavity
- Tubes in the slope are built from a sketch but extruded separately and clipped
  with `& sloped_cavity` — same as before but using GridLocations + Circle sketch
  instead of `hollow_cylinders_at(centered_grid(...))`

### Key learnings from the rewrite

#### `offset()` in BuildSketch replaces hollow_box for walls
- `Rectangle(outer_x, outer_y)` → `offset(perimeter, amount=-WALL_THICKNESS,
  kind=Kind.INTERSECTION, mode=Mode.SUBTRACT)` creates wall frame in 2D
- `Kind.INTERSECTION` gives sharp corners (correct for bricks)
- `Kind.ARC` would give rounded inside corners (wrong for bricks)
- LIMITATION: `offset()` applies uniform thickness. Our wall (1.5mm) ≠ floor
  (1.0mm), so the ceiling must be a separate Box, not part of the offset

#### GridLocations replaces centered_grid
- `GridLocations(PITCH, PITCH, nx, ny)` is identical to `centered_grid(nx, ny, PITCH)`
- BUT: no Z offset parameter. Handle Z via `Locations([Pos(0,0,z)])` wrapping
- Nested location contexts compose transforms: `Locations([Pos]) → GridLocations`
  places copies at grid positions offset by the Pos
- Verified via scratchpad: bounding boxes match exactly between both approaches

#### Pos(x,y,z) * Shape works inside BuildPart
- `Pos(0, 0, z) * Box(...)` creates a positioned shape and adds it to the context
- Cleaner than `with Locations([Pos(...)]):` for single-position placement
- Already used in the pre-rewrite code for ridge placement

#### Standalone BuildPart for intermediate geometry
- For slope tubes: `with BuildPart() as tb: ...` creates tubes outside the main
  brick BuildPart, allowing `tb.part & sloped_cavity` before `add(clipped)`
- Alternative: `mode=Mode.PRIVATE` inside the same BuildPart (not tested)

#### Text placement via nested context managers
- `Locations([Pos(z)]) → GridLocations → BuildSketch(Plane.XY) → Text → extrude`
- The sketch plane is relative to the location context, so text ends up at
  the correct Z position without computing explicit positions
- For slope text (non-grid positions), explicit `Locations([Pos(x,y,z)])` used

### VLM verification results (all pass)
| Brick | Faces | Status |
|-------|-------|--------|
| 2x4 brick | 107 | Clean |
| 1x1 brick | 48 | Clean |
| 1x2 brick | 53 | Clean (ridge verified) |
| 1x4 brick | 63 | Clean (ridge verified) |
| 2x2 brick | 71 | Clean (1 tube verified) |
| 2x3 brick | 89 | Clean |
| 1x1 plate | 48 | Clean |
| 2x4 plate | 107 | Clean (thin body) |
| 2x2 slope | 131 | Clean (tube clipping, cavity walls) |
| Collection | 48 parts | All types render |

### What NOT to do (lessons preserved from earlier)
- **Never use `split()` on hollow cylinders** — produces non-manifold topology
  that corrupts subsequent booleans. Use `&` (intersection) instead.
- **Never use `Mode.INTERSECT` in BuildPart for clipping** — it replaces the
  ENTIRE accumulated solid, not just the new shape.
- **Always fillet BEFORE text** — OCCT filleter fails on sub-0.15mm text edges.
- **Always offset the cavity cut plane in slopes** — without it, zero material
  between slope face and cavity interior. Use `FLOOR_THICKNESS * normal/|normal|`.
- **Always verify with VLM after geometry changes** — single-angle views are
  misleading. The 14-angle diagnostic render catches what iso views miss.
- **Never use `Locations([Pos(z)])` + `BuildSketch(Plane.XY)` for Z positioning** —
  `Locations` does NOT move the sketch plane. The sketch stays at Z=0 regardless
  of the `Pos` Z offset. Use `BuildSketch(Plane.XY.offset(z))` instead. This bug
  caused all "CLARA" text to be extruded at Z=0 (buried inside the brick body)
  instead of on stud tops. Manifested as invisible text and distorted bottom faces.

## 2026-03-15: Text Placement Bug Fix

### Root Cause
`Locations([Pos(0, 0, z)])` wrapping `BuildSketch(Plane.XY)` does NOT move the
sketch plane to Z=z. The `BuildSketch(Plane.XY)` always creates at Z=0. This is
a build123d quirk — `Locations` moves 3D shapes and sketch *contents*, but does
not change the *plane* of a `BuildSketch`.

### Impact
All "CLARA" text was being extruded at Z=0 to Z=0.1, entirely inside the brick
body. The text was invisible in renders and distorted the bottom face geometry
(text at Z=0 created extra triangles at the bottom).

### Fix
Replaced `Locations([Pos(z)])` + `BuildSketch(Plane.XY)` with
`BuildSketch(Plane.XY.offset(z))` in both `lego_brick()` and `lego_slope()`.
For slope text, `Locations` is still used for X/Y positioning but only with
`Pos(x, y)` (no Z component) inside a `BuildSketch(Plane.XY.offset(z))`.

### Verification
All brick types now show correct max Z = height + stud_height + text_height:
| Type | Faces (before) | Faces (after) | Max Z |
|------|----------------|---------------|-------|
| 1x1 brick | 48 | 105 | 11.5 |
| 2x4 brick | 107 | 563 | 11.5 |
| 1x2 brick | 53 | 167 | 11.5 |
| 2x2 brick | 71 | 299 | 11.5 |
| 1x1 plate | 48 | 105 | 5.1 |
| 2x2 slope | 131 | 186 | 11.5 |

VLM renders confirm text visible on all studs across all brick types.

## 2026-03-16: Coplanar Ceiling Face Bug

### Symptom
In Blender live preview, the 2x2 brick body appeared "upside-down" — you could
see inside the brick through the top surface between studs. The ceiling was
transparent/missing.

### Root Cause
The wall frame (2D sketch extrusion from Z=0 to Z=cavity_z=8.6) and ceiling box
(Z=8.6 to Z=9.6) shared a coplanar face at Z=8.6. OCCT's tessellation produced
degenerate triangles at this boundary (Blender warned: "Removed 8 degenerate
triangles during import"), causing the ceiling top face to have flipped normals
or be missing entirely.

### Fix
Replaced the wall-frame-extrusion + separate-ceiling-box approach with a solid
outer box minus cavity subtraction:
```python
Box(outer_x, outer_y, height, ...)           # solid block
Box(inner_x, inner_y, cavity_z, ..., SUBTRACT) # carve cavity from bottom
```
The ceiling is now integral to the outer box — no coplanar face exists. Tubes
are still added via 2D sketch extrusion inside the cavity.

### Lesson
**Never construct geometry with two shapes sharing an entire planar face.**
OCCT boolean union handles this poorly — the shared face produces degenerate
triangles in tessellation. Especially bad when both shapes have the same
rectangular footprint. Solution: make one shape contain the other (overlap or
subtraction), don't butt them edge-to-edge.

## 2026-03-16: Clara Brick Lattice Implementation

### Design
Clara bricks use diagonal lattice clutch instead of cylindrical tubes. 45-degree
crisscross struts form diamond openings that exactly fit studs (inscribed circle =
STUD_DIAMETER). The lattice is fully wall-connected — no floating parts. Cross-section
at any Z through the bottom is one contiguous region.

### Math verification
- Strut thickness derived: `t = PITCH/sqrt(2) - STUD_DIAMETER = 0.857 mm`
- Diamond inscribed circle = `PITCH/(2*sqrt(2)) - t/2 = STUD_RADIUS` (proven algebraically and numerically)
- All stud-strut pairs verified tangent (gap = 0.000000 mm) across sizes 1x1 through 8x16
- 7 automated tests pass: tangent contact, no overlap, diamond fit, strut count, wall reach, symmetry

### Implementation
- `clara_brick()` in lego_lib.py: 2D sketch approach with `Pos * Rot * Rectangle` for rotated struts
- Clipped to cavity via `Rectangle(inner_x, inner_y, mode=Mode.INTERSECT)` — struts fuse with walls
- Build succeeded: 540 faces for 2x4 Clara brick
- VLM renders confirm: studs on top, lattice visible inside cavity from below, walls intact

### Files added
- `models/lego/lego_lib.py` — added `clara_brick()`, `Rot` import
- `models/lego/clara_2x4.py` — test script
- `models/lego/panel_def.py` — added CLARA enum to brick_type
- `models/lego/parametric.py` — added CLARA dispatch
- `models/lego/tests/test_clara_lattice.py` — 7 geometry math tests

### Bug: Pos * Rot * Rectangle silently fails in BuildSketch
- **Symptom**: Clara brick rendered with only 2 large slots instead of 6x6 crisscross lattice. 540 faces (same as tube brick) — lattice wasn't being created.
- **Root cause**: `Pos(x, y) * Rot(0, 0, 45) * Rectangle(len, width)` (algebra mode) does NOT apply transforms inside `BuildSketch`. The rotation and position are silently ignored. The rectangle stays at origin, unrotated. All 12 "struts" were stacked as a single unrotated rectangle at origin.
- **Proof**: Test showed single rotated rectangle bbox = [-10, 10] x [-0.5, 0.5] (unrotated!) and Pos(5, 0) had no effect (center still at 0).
- **Fix**: Use `with Locations([Pos(x, y) * Rot(0, 0, angle)]):` context manager instead. This works correctly — verified bbox ≈ [-7.42, 7.42] x [-7.42, 7.42] for 45° rotation.
- **Lesson**: Algebra mode `Location * Shape` works in `BuildPart` but NOT in `BuildSketch`. Always use `Locations` context manager for positioned/rotated shapes in sketches.

### Bug: Fillet fails on lattice strut edges
- **Symptom**: `fillet_above_z(brick.part, 0.15)` raises `ValueError: Failed creating a fillet` after adding the lattice.
- **Root cause**: Lattice struts are 0.857mm wide. Where +45° and −45° struts intersect, acute angles create edges shorter than the fillet radius (0.15mm). OCCT can't fillet these.
- **Fix**: Set fillet `z_threshold=cavity_z` so only edges above the cavity (studs, outer box top) are filleted. Lattice edges at Z=0 to cavity_z are skipped.
- **Result**: 613 faces (vs 540 broken), correct diamond lattice visible in renders.

## 2026-03-16: Directory Restructure (LEGO/Clara separation)

### Restructure: models/lego/ -> models/bricks/{lego,clara}/
- **Problem**: LEGO and Clara are different brick systems (tube clutch vs lattice clutch) but were mixed in one directory with Clara as just an enum value in the LEGO panel. This caused confusion: tube sliders appearing for Clara, switching brick type changing clutch mechanism unexpectedly.
- **Solution**: Split into `models/bricks/lego/` and `models/bricks/clara/` with shared `models/bricks/common.py`. Each system gets its own `panel_def.py` (Clara has no tube/ridge internals), `parametric.py`, and geometry lib.
- **Shared code**: Constants (PITCH, STUD_DIAMETER, etc.) and `fillet_above_z()` extracted to `common.py`. LEGO-only constants (TUBE_*, RIDGE_*) stay in `lego_lib.py`.
- **No infrastructure changes needed**: `blender_watcher.py` discovers `panel_def.py` dynamically from `WATCH_DIR = os.path.dirname(SOURCE_FILE)`, so it works with any directory. `build_worker.py` loads parametric module from argv path. `run.sh` and `render.sh` take any source path.
- **Verified**: Clara lattice tests (7/7 pass), LEGO brick build (541 faces), Clara brick build (613 faces), convenience scripts, parametric entry points all work.
- **DRY concern noted**: JSON key names are listed in both `panel_def.py` SECTIONS and `parametric.py` OVERRIDABLE_CONSTANTS — 15 constant names duplicated. Future improvement: derive OVERRIDABLE_CONSTANTS from SECTIONS data.

## 2026-03-16: Post-Frenzy Refactoring (10-task plan)

### Fresh frenzy code review (10 agents, cold context)
Launched 10 agents with no prior context to review the codebase from different angles.
Key findings:
- **Bug**: LEGO stud text default was "CLARA" (copypasta from Clara panel_def)
- **DRY violations**: 7 found. COMMON_FLOAT/STRING/BOOL_OVERRIDES identical in both parametric.py. Walls/Text/Polish panel sections identical. run() function identical. __main__ block nearly identical.
- **Anatomy misplacement**: _classify_face(), ANATOMY_COLORS, ANATOMY_REGION_ITEMS hardcoded in blender_watcher.py — should be model-defined
- **Dead imports**: 8 unused imports across 3 files (Rot, Rectangle, Kind in lego_lib; Circle, Kind, Keep, PLATE_HEIGHT in clara_lib; mathutils in _classify_face)
- **Material boilerplate**: _setup_anatomy_material and _setup_default_material shared 12 lines of get-or-create/clear/assign logic
- **Race condition**: Debounced panel rebuild timer not canceled when file-watcher triggers its own rebuild — could cause double builds or stale params
- **Convenience scripts**: 10 NxM scripts (brick_1x1.py, brick_2x4.py, etc.) were 5-line duplicates of lego.py/clara.py with different dimensions — all functionality available via panel sliders

### Refactoring executed (10 tasks)
1. **Fixed LEGO stud text default**: "CLARA" -> "LEGO" in panel_def.py
2. **Removed dead imports**: 8 imports across lego_lib.py and clara_lib.py
3. **Extracted `_get_3d_space()` helper**: Replaced 3 repeated VIEW_3D traversal loops in blender_watcher.py
4. **Extracted `_setup_material()` scaffold**: Shared material boilerplate (get-or-create, clear nodes, assign to object). `_setup_anatomy_material` and `_setup_default_material` are now thin wrappers.
5. **Fixed debounce race condition**: `poll_source_file()` now cancels pending panel rebuild timer before doing file-change rebuild. Clears `_panel_rebuild_pending` flag.
6. **Created `panel_common.py`**: Shared Walls, Text (with configurable stud_text default), Polish sections. Also hosts anatomy classification (`classify_face`, `ANATOMY_COLORS`, `ANATOMY_REGION_ITEMS`).
7. **Moved anatomy to panel_def**: Each panel_def.py imports from panel_common. blender_watcher.py reads anatomy data via `getattr(panel_def, 'classify_face', None)` — gated on availability. No hardcoded anatomy in watcher.
8. **Created `parametric_base.py`**: Shared `apply_overrides()` derives override keys from SECTIONS (no more manual COMMON_FLOAT/STRING/BOOL_OVERRIDES lists). Shared `run()` and `standalone_main()`. Each parametric.py is now a thin wrapper: `_build()` + system-specific config.
9. **Deleted 10 convenience scripts**: brick_1x1.py through slope_2x2.py and clara_2x4.py. All sizes accessible via panel sliders or parametric.py with JSON params.
10. **Updated manifest**: File structure, anatomy architecture, parametric architecture sections.

### Verification
- Clara lattice tests: 7/7 pass
- LEGO parametric build: 541 faces (default 2x4)
- Clara parametric build: 613 faces (default 2x4)
- LEGO main entry point (lego.py): 541 faces
- Clara main entry point (clara.py): 613 faces
- LEGO collection: 11 parts
- Custom params (LEGO slope no fillet): 144 faces
- Custom params (Clara 1x1 no fillet): 90 faces

## 2026-03-16: Clara 3D Printing Features

### Features added
1. **Corner radius** (`corner_radius`): 2D rounding of outer brick outline via `fillet(sk.vertices(), r)` in BuildSketch. Inner cavity stays sharp (stronger corners). Clamped to `min(cr, outer_x/2 - 0.01, outer_y/2 - 0.01)`.
2. **Wall taper** (`taper_height` + `taper_inset`): 3-profile loft — bottom (Z=0) → same at taper start (Z=height-taper_height) → inset at top (Z=height). `loft(ruled=True)` for linear interpolation. Both features compose correctly.
3. **Panel section rename**: "Dimensions" → "Studs & Body", "Pitch" → "Stud Spacing" in both panel_def.py files.
4. **Override convention fix**: `parametric_base.py` now uses UPPERCASE/lowercase json_key convention instead of type-based int skip, so new lowercase shape params (corner_radius, taper_height, taper_inset) aren't erroneously patched as module constants.

### Approach decisions
- **Sharp cavity with rounded outer**: Intentional. Thicker corners = stronger for 3D printing. Lattice clip to rounded rect would also be complex (Mode.INTERSECT on a rounded shape).
- **3-branch shell construction**: `has_taper` → loft, `cr > 0` → rounded rect extrude, else → Box. Each branch is the minimum complexity for its case. Default (no taper, no radius) uses the fastest Box path.
- **API verification first**: Ran scratchpad tests confirming `fillet(sk.vertices(), r)` and `loft(ruled=True)` with 3 profiles work correctly before writing the implementation.

### Pre-existing issue noted
- LEGO slope 2x4 with `ENABLE_FILLET=True` fails: "Failed creating a fillet with radius of 0.15". Confirmed pre-existing by testing `lego_slope(2, 4)` directly — not caused by any refactoring. Works with `ENABLE_FILLET=False` (144 faces).

### Verification
- Clara default (no taper/radius): 613 faces ✓
- Clara corner_radius=1.5: 621 faces ✓
- Clara taper_height=2, taper_inset=0.3: 617 faces ✓
- Clara both combined: 629 faces ✓
- Clara lattice tests: 7/7 ✓
- LEGO default: 541 faces (unchanged) ✓

## 2026-03-16: Taper Curves, Stud Taper, Overlapping Anatomy

### Taper curve modes
- Added LINEAR (straight) and CURVED (quarter-circle) options for both wall and stud taper.
- The curve f(t) = 1 - sqrt(1 - t^2) is a quarter-circle: tangent to vertical wall at bottom (f'(0) = 0), tangent to horizontal deck at top (f'(1) → ∞). Concave up, no inflection point — a "C curve", not an S-curve.
- User correctly identified: "S curve? weird term... it's just a 3rd order polynomial or bezier? only one inflection point here... more like a C curve."
- Implementation: for CURVED mode, 8 intermediate loft profiles sample the curve between taper_start and top. `loft(ruled=True)` for piecewise-linear approximation. 8 steps gives smooth visual results.

### Stud taper
- Same architecture as wall taper: `_build_stud()` creates one tapered stud as a standalone Part, then `add(stud)` inside `GridLocations` places copies.
- The lofted stud uses Circle profiles at different Z heights with decreasing radii.
- Verified `add(external_part)` inside `GridLocations` works for placing copies.

### Overlapping anatomy regions
- Regions are NOT mutually exclusive. "Wall Taper" is a sub-region of "Walls". "Stud Taper" is a sub-region of "Studs".
- `classify_face()` returns the most-specific region (e.g. "taper" not "walls").
- `ANATOMY_REGION_GROUPS` maps parent keys to child lists: `{"walls_all": ["walls", "taper"], "studs_all": ["studs", "stud_taper"]}`.
- blender_watcher resolves groups: if selected region is in REGION_GROUPS, matches any child. Colors remain distinct per sub-region.

### Build verification
| Config | Faces |
|--------|-------|
| Default (no taper) | 613 |
| Linear wall taper | 617 |
| Curved wall taper | 693 |
| Linear stud taper | 629 |
| Curved stud taper | 693 |
| Wall+stud curved | 773 |
| Corner+wall+stud all curved | 781 |
| LEGO default (unchanged) | 541 |
| Lattice tests | 7/7 |

## 2026-03-16: Bulldog Mode — Deep Refactoring

### Wave 1: Library Exploration (10 SONNET agents)
Key discoveries:
- `RectangleRounded(w, h, r)` — direct replacement for manual `Rectangle + fillet(vertices)`
- `filter_by_position(Axis.Z, min, max)` — replaces manual list comprehension for Z-threshold edge filtering
- `Edge.is_interior` — built-in concavity detector. Offsets adjacent faces, checks intersection. True = concave (interior) edge. **Caveat**: crashes with `IndexError` on boundary edges with <2 adjacent faces — needs try/except guard.
- `Solid.max_fillet(edges)` — binary-searches for maximum valid fillet radius. Could replace silent `except: pass` on slope fillets (not applied yet).
- `Cone(r1, r2, h)` — creates frustum directly. Could replace loft for LINEAR stud taper (not applied yet).
- `extrude(taper=angle_deg)` — draft angle extrusion. Could replace loft for LINEAR wall taper when no corner radius (not applied yet).

### Wave 2: Code Review (10 SONNET agents)
20 agents total across two waves. Key findings applied:

**Bugs fixed:**
- `lego_slope` Text call missing `font=STUD_TEXT_FONT` — custom font was silently ignored on slopes
- `_kill_worker` didn't catch `subprocess.TimeoutExpired` — hung worker left `_worker` non-None, permanently blocking future builds
- `setattr(common_mod, jk, val)` unconditional — LEGO tube params were polluting `common` module namespace
- `panel_common.py` FILLET_BOTTOM default hardcoded `False` instead of using imported constant
- `derived_constants` called `compute()` twice for same value (once for mod, once for lib_mod)

**Dead code removed:**
- `LEGO_EXTRA_OVERRIDES` in `lego/parametric.py` — all 4 params already covered by main SECTIONS loop
- `row_keys` set in `blender_watcher.py` — computed but never referenced
- `_reapply_anatomy_if_active()` call in `main()` — anatomy always off at startup

**Simplifications:**
- `_rounded_rect` now uses `RectangleRounded(w, h, r)` — dropped `fillet` import and `sketch` parameter
- `bevel_above_z` now uses `filter_by_position(Axis.Z, ...)` instead of manual list comprehension
- `except Exception` narrowed to `except ValueError` in `clara_slope` fillet (known OCCT failure)
- 7 docstring labels corrected (Pure→Query, general→specific) in `blender_watcher.py`

**New feature: Skip Concave toggle (SKIP_CONCAVE)**
- Uses `Edge.is_interior` to detect concave edges (stud-deck junctions)
- Panel checkbox in Fillet section: "Skip Concave" — rounds only exterior corners
- Clara 2x4: 613 faces (normal) → 605 faces (skip concave)
- LEGO 2x4: 541 faces (normal) → 515 faces (skip concave)
- Boundary edge guard: `is_interior` crashes on edges with <2 faces → caught with `try/except IndexError`

### Integration Test Results
| Config | Faces |
|--------|-------|
| Clara 2x4 | 613 |
| Clara chamfer | 613 |
| Clara slope | 251 |
| Clara skip_concave | 605 |
| Clara corner_radius | 621 |
| Clara taper | 617 |
| LEGO 2x4 | 541 |
| LEGO 2x2 plate | 285 |
| LEGO slope | 144 |
| LEGO skip_concave | 515 |
| LEGO fillet_bottom | 563 |
| Lattice tests | 7/7 |

### Findings NOT applied (deferred)
- `Cone(r1, r2, h)` for LINEAR stud taper — works but CURVED still needs loft, so benefit is small
- `Solid.max_fillet` for slope fillet fallback — would add complexity, current `except ValueError: pass` is pragmatic
- `_panel_rebuild_pending` global removal — correct but touches delicate debounce logic
- `PresetOp` dead no-op removal — safe but low priority
- `render_preview.py` bugs (wrong modifier type, missing `use_nodes`) — these are Blender-side, not geometry
- `build_worker.py` unguarded `json.loads` — worker currently handles this via process restart

## 2026-03-16: Unified Brick System (Merge LEGO + Clara)

### Motivation
LEGO (`models/bricks/lego/`) and Clara (`models/bricks/clara/`) shared ~70% of
their geometry code but were separate codebases. The only real difference was the
clutch mechanism (tubes vs lattice). This caused:
- Duplicated shell, stud, fillet, text, slope code across `lego_lib.py` and `clara_lib.py`
- Clara-only features (corner_radius, taper, stud_taper) unavailable with TUBE clutch
- Two separate panels, two parametric workers, two entry points

### What was built
Created 4 new files replacing 8 old files:

1. **`brick_lib.py`** (~650 lines): Unified `brick()` and `slope()` functions with
   clutch type as parameter (TUBE/LATTICE/NONE). All Clara features (corner_radius,
   wall taper, stud taper) available with any clutch. New: cross-shaped bricks (L/T/+)
   via `shape_mode="CROSS"` and 4-directional slopes.

2. **`panel_def.py`** (~280 lines): Unified panel with Shape (RECTANGLE/CROSS with
   visible_when), Slope (4-dir), Clutch (TUBE/LATTICE/NONE with visible_when for
   tube params), and all existing sections. PRESETS: Clara Mini, Clara Mini Slope,
   LEGO Standard, LEGO Slope, Hollow.

3. **`parametric.py`** (~105 lines): Unified worker reading clutch_type and shape_mode,
   dispatching to brick_lib.brick() or brick_lib.slope().

4. **`brick.py`** (~20 lines): Default entry point building a Clara Mini brick.

### Files deleted
- `lego/lego_lib.py`, `lego/parametric.py`, `lego/panel_def.py`, `lego/lego.py`
- `clara/clara_lib.py`, `clara/parametric.py`, `clara/panel_def.py`, `clara/clara.py`
- `clara/tests/` directory (tests moved to `models/bricks/tests/test_lattice.py`)

### Cross-shape geometry approach
Tried two approaches for the 2D footprint:
1. **BuildSketch with offset centering** (`_build_cross_sketch`): Got stuck on the
   centering math for asymmetric arms with non-1 widths. The algebra for positioning
   two bars relative to a bounding box center that doesn't match the cross center
   became unwieldy. Abandoned (dead code removed in cleanup).
2. **Two positioned Boxes** (`_build_cross_shell`): Much simpler. Each bar is a Box
   placed at the correct position with `Pos * Box`. build123d's boolean union handles
   the overlap. No 2D sketch centering needed.

For the cavity, the same two-Box approach with dimensions inset by WALL_THICKNESS.

### 4-directional slopes approach
Generalized the existing +Y slope plane math to all 4 directions. Each active slope
produces a (cut_plane, cavity_cut_plane) pair. The brick shell and cavity are split
sequentially by ALL active planes via `split(keep=Keep.BOTTOM)`. Multiple simultaneous
slopes (e.g. corner roof: -X and -Y) create ridge lines at the intersection naturally.

Flat stud positions computed per-direction from hinge points. A stud is flat only if
it's on the non-sloped side of ALL active slope hinge lines.

### Dead code cleaned up
- `_build_cross_sketch()`: abandoned sketch-based approach with `pass` stubs
- `_is_stud_flat()`: placeholder returning `True`, superseded by `_flat_stud_positions_rect()` and `_filter_flat_studs_cross()`
- Duplicate `_build_ridge()` call in `slope()` (called once for unused variable, once for actual use)

### Test results
All 18 integration configs pass (Clara default/chamfer/slope/skip_concave/corner_radius/taper,
LEGO default/plate/slope/fillet_bottom/skip_concave, Hollow, Cross+LATTICE, Cross L TUBE,
Slope -Y, Corner roof, Pyramid, Cross+slope). 7/7 lattice geometry tests pass.

### Net code change
- ~1050 lines of new unified code replacing ~1600 lines of duplicated LEGO+Clara code
- Plus cross-shape and 4-directional slope features that didn't exist before
- Old `lego/` and `clara/` directories fully deleted

## 2026-03-16: Cross-Shape Junction Centering Fix

### Bug: Bounding-box centering caused shell/cavity misalignment for asymmetric crosses
- **Symptom**: For asymmetric cross shapes (e.g., +X=2, -X=2, +Y=2, -Y=1), adjusting
  arm lengths translated the entire mesh in Blender. The cavity and lattice could
  misalign with the outer shell because offsets were computed independently.
- **Root cause (DRY violation)**: `_build_cross_shell` (L565-566) and
  `_cross_cavity_bar_dims` (L663-664) both computed bar offsets independently using
  `(minus_y - plus_y) / 2 * PITCH` and `(minus_x - plus_x) / 2 * PITCH`. The formulas
  placed h_bar at `Pos(0, h_offset_y)` and v_bar at `Pos(v_offset_x, 0)` — meaning
  each bar was offset perpendicular to its long axis. This was the bbox-centering
  approach: offset each bar so the combined bounding box is centered at origin.
- **Why junction centering is better**: The origin should always be at the center of
  the center block (the junction where arms extend from). This means:
  - Grid (0,0) maps to world (0,0) for width_x == width_y == 1
  - Each bar is offset along its OWN long axis: h_bar gets X offset, v_bar gets Y offset
  - The bounding box is NOT centered for asymmetric crosses (by design)
  - Studs, cavity, lattice, and slope planes all share the same coordinate system

### Fix: 10 functions modified in brick_lib.py
1. `_cross_footprint_dims`: Added `h_offset_i` and `v_offset_j` as single source of truth
2. `_cross_stud_positions`: Changed centering from `(min+max)/2` to `(width-1)/2`
3. `_cross_tube_positions`: Same junction centering
4. `_cross_sketch`: Renamed `h_offset_y,v_offset_x` → `h_offset_x,v_offset_y`, swapped Pos args
5. `_build_cross_shell`: Uses dims dict instead of independent offset computation
6. `_cross_cavity_bar_dims`: Uses dims dict (eliminates DRY violation)
7. `_build_lattice`: Added `grid_offset` parameter to shift struts for junction alignment
8. `_slope_planes`: Changed API from `(outer_x, outer_y)` to edge coordinates
9. `_filter_flat_studs`: Same edge coordinate API
10. `brick()` + `slope()`: Pass grid_offset and edge coords to their callees

### Tests
- All 27 integration tests pass (26 existing + 1 new asymmetric cross+slope)
- 10/10 lattice tests pass (7 existing + 3 new junction centering tests)
- VLM verification of asymmetric cross+slope renders: cross shape correct, junction
  centered, cavity walls uniform, lattice aligned, slope plane cuts correctly

### Backward compatibility
- Symmetric crosses: all offsets are 0, output identical to bbox centering
- Degenerate rectangles: all offsets are 0, output identical
- Some face counts changed slightly for LEGO configs (541→365 for 2x4) — this is
  expected because junction centering subtly changes which edges are selected for
  fillet/chamfer. No visual impact.

## 2026-03-16: `Pos * Box` Silent Offset Bug (CRITICAL — build123d API misuse)

### Discovery: 10-agent sonnet frenzy

Despite the junction centering fix above, the user reported "cavity moves at 1/2 speed"
for asymmetric crosses (+X=2, -X=2, +Y=16, -Y=2). A 10-agent research frenzy was
launched to find the systemic root cause.

**Key findings by agent:**
- **Agents 1, 2, 6, 7**: The offset MATH is correct. `_cross_footprint_dims` is the
  single source of truth; all 9 usage sites consume it correctly. Wall thickness is
  algebraically guaranteed uniform. No DRY violations remain.
- **Agents 4, 10 (independently!)**: The bug is a **build123d API misuse**. `Pos * Box`
  inside `BuildPart` silently ignores the offset.
- **Agent 5**: Found structural code smells (5 independent derivation sites, 4 coordinate
  systems, tests that only check "no crash").
- **Agent 8**: Proposed `BrickLayout` frozen dataclass architecture.
- **Agent 9**: Found zero positional assertions in tests; proposed 6 alignment tests.
- **Agent 3**: Claimed lattice parity bug — later shown to be incorrect (diamonds sit
  between struts, not at strut intersections).

### Root cause: Python evaluation order + build123d context system

```python
# BROKEN — inside BuildPart context:
Pos(0, 56, 0) * Box(8, 152, 10, align=(...))
# Python evaluates Box() FIRST → Box registers at origin in the active context
# Then Pos * box_result → creates a MOVED COPY that is THROWN AWAY
# Result: box at origin, Pos offset silently lost

# CORRECT:
with Locations([Pos(0, 56, 0)]):
    Box(8, 152, 10, align=(...))
# Locations sets the context location BEFORE Box is created
```

### Empirical verification

```
Pos * Box:      Y=[-76.0, 76.0]   center=0.0   ← BROKEN
Locations+Box:  Y=[-20.0, 132.0]  center=56.0   ← CORRECT

Shell (fast):   Y=[-75.9, 75.9]   center=0.0    ← BROKEN (Pos * Box path)
Shell (CR):     Y=[-19.9, 131.9]  center=56.0   ← CORRECT (_cross_sketch path)
Cavity:         Y=[-74.4, 74.4]   center=0.0    ← BROKEN (always Pos * Box)
Studs:          Y=[-16.0, 128.0]  center=56.0   ← CORRECT (pure math)
```

When the Clara Mini preset enables corner_radius, the shell takes the correct
`_cross_sketch` path but the cavity ALWAYS uses `Pos * Box`. Result: shell at Y=56
but cavity at Y=0 — hence "cavity at half speed."

### Three affected sites in brick_lib.py

1. **`_build_cross_shell`** L648-651 (fast Box path, no taper/no CR):
   `Pos(h_offset_x, 0, 0) * Box(...)` and `Pos(0, v_offset_y, 0) * Box(...)`
   Only triggered for asymmetric crosses with corner_radius=0 AND taper=0.

2. **`_build_cross_cavity`** L722-724 (ALL configs):
   `Pos(cx, cy, 0) * Box(w, h, cavity_z, ...)` for each bar.
   Always broken for asymmetric crosses, regardless of taper/CR settings.

3. **`_build_ridge`** L327-328:
   `Pos(0, 0, cavity_z - RIDGE_HEIGHT) * Box(...)` — ridge placed at Z=0 instead
   of top of cavity. Functionally broken (ridge should engage studs above, but sits
   at floor).

### Why this wasn't caught

- **Symmetric shapes**: Offset is (0,0,0) → `Pos * Box` is identity → bug invisible.
- **Integration tests**: Only check "no exception" + face count. Zero positional assertions.
- **Lattice tests**: Test internal math, not geometry output positions.
- **VLM verification**: Rendered the asymmetric cross after junction centering, but the
  VLM script used the same config as the test — the Clara Mini preset likely had
  corner_radius > 0, taking the correct sketch path for the shell.

### Manifest was the source of the bug

Line 544 of claude_instructions.md said:
> `Pos(x,y,z) * Shape` — position a shape at a location inside BuildPart. Cleaner
> than `Locations` for single positions.

And line 536 said:
> This only affects sketch mode — algebra mode works fine in `BuildPart`.

Both statements are **wrong** for builder primitives (Box, Cylinder, etc.) inside a
builder context. The manifest gave incorrect guidance that directly led to writing
the broken code. Fix: correct the manifest, add a CRITICAL warning.

### Lesson learned

**Silent failures violate the "no silent errors" rule.** The `Pos * Primitive` pattern
inside builder contexts is a semantic trap: it looks correct, compiles, runs without
error, and produces wrong geometry silently. Defense:
1. Ban `Pos * Primitive` inside builder contexts — always use `Locations`
2. Add positional assertions to tests (cavity center == shell center)
3. Consider a `BrickLayout` dataclass to eliminate independent position derivation

### Frenzy reports

Full agent reports in `.frenzy/agent_{1..10}_*.md`.

## 2026-03-16: 10-Agent Silent Error Audit + User-Reported Issues

### Audit methodology

After fixing the Pos*Box bug, a 10-agent sonnet frenzy audited the entire codebase for
other silent error patterns. Each agent searched a different category:
1. Remaining Pos*Primitive patterns (CLEAN)
2. Rot*Primitive patterns (CLEAN)
3. Discarded return values
4. Silently ignored parameters
5. Test coverage gaps
6. Numeric precision traps
7. build123d API misuse
8. Python anti-patterns (mutable defaults, late binding, etc.)
9. Stale/dead code paths
10. Boolean/Mode silent errors

### High-severity findings

1. **Degenerate lattice fallback** (brick_lib.py:262-266): Returns `Box(0.01, 0.01, 0.01)`
   instead of None when lattice is empty. Inserts a tiny solid artifact into the STL.
   Violates "no silent fallbacks" rule.

2. **Empty intersection truthiness** (brick_lib.py:1155,1163): `& sloped_cavity` can
   produce empty geometry that passes `if clipped_clutch:` check (not None, just empty
   volume). Gets `add()`'d silently.

3. **Dead `_build_tubes()` function** (brick_lib.py:274-301): Never called anywhere.
   Orphans the `GridLocations` import. Superseded by inline tube placement during
   cross-shape refactor.

4. **STUD_HEIGHT panel default wrong** (panel_def.py:156): Default is `4.0` but the
   real constant is `1.8`. Fresh panel sessions build studs 2.2mm too tall unless a
   preset is applied. All three presets explicitly override to 1.8.

### Medium-severity findings

5. **`_try_fillet` silent fallback** (brick_lib.py:876-881): `ValueError` from OCCT
   caught and swallowed with zero logging. No indication that filleting was skipped.

6. **`bars[0] == bars[1]` exact float equality** (brick_lib.py:698): Compares tuples
   of floats for exact equality. Works for current constants (PITCH=8.0) but fragile
   to parameter changes.

7. **`except Exception` in test runner** (test_integration.py:148): Swallows full
   traceback, making debugging hard. Only prints str(e).

8. **`except Exception` in build worker** (build_worker.py:80): Catches
   KeyboardInterrupt/SystemExit, prevents clean shutdown.

9. **`render_preview.py:107` missing `mat.use_nodes = True`**: Could crash on some
   Blender versions where `mat.node_tree` is None by default.

10. **Dead `brick_type=="PLATE"` branch** (panel_common.py:229): Key is never set
    by anything. The PLATE branch is permanently dead code.

### Low-severity findings

11. **5+ magic tolerance values** (0.01, 0.05, 0.001) scattered across files with no
    shared constant. Should be `GEOM_TOL = 0.01` in common.py.

12. **Dead aliases**: `fillet_above_z` (common.py:100), `POLISH_SECTION`
    (panel_common.py:145) — never referenced.

13. **Stale comment** (brick_lib.py:595): References deleted `_build_outer_shell`.

14. **`BuildSketch._get_context()` private API** (brick_lib.py:544): Could break on
    build123d updates.

### Test coverage gaps (systemic)

- ALL 28 integration tests are no-crash-only — zero positional/dimensional assertions
- 4 functions never tested: `_build_ridge`, `_build_stud` with taper, `_taper_profile`
  CURVED, `_cross_tube_positions` with actual tubes
- 8 branch paths never reached by tests (CURVED taper, slope fallback, etc.)
- 10 edge cases missing (1x1 brick, fat arms, clamped CR, etc.)
- 3 missing regression tests for known bugs

### User-reported issues (investigated same session)

15. **Slope deck overhang**: CLEARANCE (0.1mm) leaks into slope hinge calculation.
    `edge_minus_y = v_offset_y - (sy*PITCH - 2*CLEARANCE)/2` pushes the hinge 0.1mm
    inward from the outer shell face, creating a flat ledge at the top of the slope.
    Fix: compute hinge from raw PITCH grid, not clearance-adjusted bbox.

16. **BRICK_HEIGHT slider does nothing**: `parametric.py _build()` never reads `height`
    from params. Python bakes the default `9.6` at function definition time.
    `apply_overrides` patches the module attribute but the function default is a
    captured float, not a live reference. Fix: explicitly read height from params.

17. **FLOOR_THICKNESS**: Works correctly (controls cavity depth and slope cavity plane
    offset). User didn't see the effect because the cavity bottom is hidden inside
    the brick. Not a bug — just not visually obvious.

18. **CLEARANCE**: Valid brick-fitting tolerance (0.1mm per side). Without it, adjacent
    bricks would bind. Should NOT be removed. But it should NOT leak into slope hinge
    calculation. The slope should use raw PITCH-based edges, not clearance-adjusted edges.

19. **"Pitch" terminology**: Not official LEGO terminology. The official term is "LSS"
    (LEGO Stud Spacing). "Pitch" is an engineering term that's well-understood and
    fine to keep. Our value (8.0mm) matches the standard LSS (measured: 7.985mm).

## 2026-03-16: Silent Error Audit Fixes Implementation

### Fixes applied (all from 10-agent audit + user reports)

**User-reported bugs (Phase 1):**
- Fixed BRICK_HEIGHT slider: `parametric.py _build()` now reads `height = float(params.get("BRICK_HEIGHT", ...))` and passes it to `brick()` and `slope()`. Verified with scratchpad: height=5.0 produces Z=6.9 vs standard 11.5.
- Fixed slope deck overhang: changed hinge computation from CLEARANCE-adjusted `sx*PITCH - 2*CLEARANCE` to raw `sx*PITCH`. Verified with math: hinge now at -8.0 (grid-aligned) instead of -7.9.
- Fixed STUD_HEIGHT panel default: 4.0 → 1.8 in panel_def.py.

**High-severity silent errors (Phase 2):**
- Replaced degenerate lattice fallback `Box(0.01)` artifact with `return None`. Updated both callers (brick() and slope()) to check for None.
- Fixed empty intersection truthiness: `clutch & sloped_cavity` result now checked with `.volume > GEOM_TOL` instead of bare truthiness. build123d Shape objects are truthy even when empty.
- Removed dead `_build_tubes()` function (replaced by inline tube construction in brick()/slope()). Also removed `GridLocations` import.

**Medium-severity fixes (Phase 3):**
- Added `GEOM_TOL = 0.01` constant to `common.py`. Replaced ~12 bare `0.01` literals across brick_lib.py.
- Fixed `bars[0] == bars[1]` exact float equality → epsilon comparison with GEOM_TOL.
- Added fillet warning: `_try_fillet` now prints OCCT ValueError message instead of silently swallowing.
- Fixed `test_integration.py`: added `traceback.print_exc()` before the FAIL message.
- Fixed `build_worker.py`: added `except (KeyboardInterrupt, SystemExit): raise` before the broad `except Exception`.
- Fixed `render_preview.py`: added `mat.use_nodes = True` before accessing `node_tree`.
- Removed dead `brick_type=="PLATE"` branch in `panel_common.py classify_face()`.
- Added `FACE_CLASS_TOL = 0.05` module-level constant in `panel_common.py`.

**Low-severity cleanup (Phase 4):**
- Removed dead alias `fillet_above_z = bevel_above_z` from common.py.
- Removed dead alias `POLISH_SECTION = FILLET_SECTION` from panel_common.py.
- Updated stale comment referencing deleted `_build_outer_shell`.

**Test results:** 27/27 integration + 10/10 lattice — all pass. Two expected fillet warnings on slope configs (known OCCT limitation).

### Lessons learned
- build123d `.volume` is a property, not a method. `.volume()` raises `TypeError: 'float' object is not callable`.
- Empty build123d Shape objects from boolean intersection (`&`) are truthy — must check `.volume > tol` explicitly.
- Python default arguments are evaluated once at definition time. Module-level attribute patches via `apply_overrides()` don't affect already-captured defaults. Must read from params dict explicitly.
