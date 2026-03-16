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
