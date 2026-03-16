"""
Shared parametric builder base -- override application and worker interface.

Command, general. Provides apply_overrides() and run() used by both LEGO and
Clara parametric.py. Override lists are derived from panel_def.SECTIONS
(type + json_key), so parameters are defined once (in panel_def.py) and
flow everywhere automatically -- no separate COMMON_FLOAT/STRING/BOOL_OVERRIDES.

Process boundary: this runs in the build_worker.py subprocess (with build123d).
"""

import time

from build123d import export_stl

# Type -> cast function for param overrides
_TYPE_CASTERS = {"float": float, "string": str, "bool": bool, "int": int}


def apply_overrides(params, common_mod, lib_mod, sections,
                    extra_overrides=None, derived_constants=None):
    """
    Command, general. Patch common + lib module constants from params.

    Override keys are derived from panel_def.SECTIONS by json_key case convention:
    UPPERCASE json_keys (PITCH, STUD_DIAMETER) are module constants to patch,
    lowercase json_keys (studs_x, corner_radius) are shape params read directly
    in _build(). Enum types are also skipped (no cast function).

    Args:
        params (dict): Key-value pairs from panel sliders.
        common_mod (module): The common.py module.
        lib_mod (module): The brick-specific lib module (lego_lib or clara_lib).
        sections (list[dict]): panel_def.SECTIONS -- source of truth for param types.
        extra_overrides (list[dict]|None): Additional {"json_key", "type"} for
            lib-only params (e.g. LEGO tube dimensions not in common).
        derived_constants (dict|None): {key: (module, compute_fn)} for values
            that must be recomputed after overrides (e.g. radii from diameters).

    Examples:
        >>> # apply_overrides(params, common, lego_lib, panel_def.SECTIONS)
    """
    for section in sections:
        for param in section["params"]:
            jk = param["json_key"]
            if jk not in params:
                continue
            # Only patch module constants (UPPERCASE json_keys like PITCH)
            # Shape params (lowercase: studs_x, corner_radius) read in _build()
            if not jk[0].isupper():
                continue
            cast = _TYPE_CASTERS.get(param["type"])
            if cast is None:
                continue
            val = cast(params[jk])
            setattr(common_mod, jk, val)
            if hasattr(lib_mod, jk):
                setattr(lib_mod, jk, val)

    if extra_overrides:
        for item in extra_overrides:
            jk = item["json_key"]
            if jk in params:
                cast = _TYPE_CASTERS.get(item["type"], float)
                setattr(lib_mod, jk, cast(params[jk]))

    if derived_constants:
        for key, (mod, compute) in derived_constants.items():
            setattr(mod, key, compute())
            if mod is common_mod and hasattr(lib_mod, key):
                setattr(lib_mod, key, compute())


def run(params, stl_path, build_fn, override_fn):
    """
    Command, general. Standard worker interface. Apply param overrides,
    build geometry, export STL, return timing info.

    Args:
        params (dict): All panel parameters.
        stl_path (str): Path to write the STL file.
        build_fn (callable): (params) -> Part.
        override_fn (callable): (params) -> None.

    Returns:
        dict: Build info -- faces count, timing.

    Examples:
        >>> # run(params, "/tmp/out.stl", _build, _apply_overrides)
    """
    override_fn(params)

    t0 = time.perf_counter()
    result = build_fn(params)
    t_build = time.perf_counter() - t0

    t1 = time.perf_counter()
    export_stl(result, stl_path)
    t_export = time.perf_counter() - t1

    faces = len(result.faces())
    return {"faces": faces, "build": round(t_build, 3), "export": round(t_export, 3)}


def standalone_main(run_fn, default_params, label):
    """
    Command, general. Shared __main__ block for parametric scripts. Reads
    params from BUILD123D_PARAMS env var or uses defaults, runs the build,
    prints timing info.

    Args:
        run_fn (callable): (params, stl_path) -> dict.
        default_params (dict): Fallback params when no JSON file provided.
        label (str): Display label (e.g. "LEGO", "Clara").

    Examples:
        >>> # standalone_main(run, {"studs_x": 2, "studs_y": 4}, "Clara")
    """
    import json
    import os

    params_path = os.environ.get("BUILD123D_PARAMS")
    if params_path and os.path.exists(params_path):
        with open(params_path) as f:
            params = json.load(f)
    else:
        params = default_params

    stl_path = os.environ.get("BUILD123D_PREVIEW_STL", "_preview.stl")
    info = run_fn(params, stl_path)
    studs_x = int(params.get("studs_x", 2))
    studs_y = int(params.get("studs_y", 4))
    print(f"{label} {studs_x}x{studs_y} -> {stl_path} ({info['faces']} faces)")
    print(f"  timing: build={info['build']:.2f}s  export={info['export']:.2f}s")
