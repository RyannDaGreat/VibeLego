"""
Persistent build worker — keeps build123d imported across requests.

Command, general. Spawned by blender_watcher.py as a child process.
Imports a parametric script (specified as argv[1]) once — paying the
expensive build123d import cost a single time — then loops on stdin
accepting JSON build requests and writing JSON responses.

Protocol (newline-delimited JSON):
    → stdin:  {"stl_path": "/tmp/out.stl", "brick_type": "BRICK", ...}
    ← stdout: {"ok": true, "faces": 541, "build": 0.55, "export": 0.19}

Exits cleanly when stdin closes (Blender quit → pipe closed).

Usage (not directly — spawned by blender_watcher.py):
    uv run --with ./build123d build_worker.py models/lego/parametric.py
"""

import importlib.util
import json
import sys
import time


def load_module(script_path):
    """
    Query, general. Import a Python script as a module by file path.
    The module must expose a run(params, stl_path) function.

    Args:
        script_path (str): Absolute path to the parametric script.

    Returns:
        module: The loaded module with a run() function.

    Examples:
        >>> # mod = load_module("/path/to/parametric.py")
        >>> # mod.run({"studs_x": 2}, "/tmp/out.stl")
    """
    spec = importlib.util.spec_from_file_location("parametric", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "run") or not callable(mod.run):
        raise RuntimeError(f"{script_path} must expose a run(params, stl_path) function")
    return mod


def main():
    """
    Command, general. Worker entry point. Loads the parametric module,
    signals ready, then processes build requests until stdin closes.
    """
    if len(sys.argv) < 2:
        print("Usage: build_worker.py <parametric_script.py>", file=sys.stderr)
        sys.exit(1)

    script_path = sys.argv[1]

    t0 = time.perf_counter()
    mod = load_module(script_path)
    t_import = time.perf_counter() - t0

    # Signal ready
    print(json.dumps({"ready": True, "import_time": round(t_import, 3)}), flush=True)

    # Request loop
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        request = json.loads(line)
        stl_path = request.pop("stl_path")

        try:
            info = mod.run(request, stl_path)
            response = {"ok": True}
            if info:
                response.update(info)
        except Exception as e:
            response = {"ok": False, "error": f"{type(e).__name__}: {e}"}

        print(json.dumps(response), flush=True)


main()
