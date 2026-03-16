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
