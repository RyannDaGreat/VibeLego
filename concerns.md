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
