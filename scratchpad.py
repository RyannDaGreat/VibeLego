"""Test fillet toggle on Clara brick."""
import json, os, sys, tempfile

sys.path.insert(0, "models/bricks/clara")
sys.path.insert(0, "models/bricks")

params_on = {"studs_x": 2, "studs_y": 2, "ENABLE_FILLET": True}
params_off = {"studs_x": 2, "studs_y": 2, "ENABLE_FILLET": False}

import parametric
info_on = parametric.run(params_on, "/tmp/test_clara_fillet_on.stl")
print(f"Clara fillet ON:  {info_on['faces']} faces, build={info_on['build']:.2f}s")

import common
common.ENABLE_FILLET = True
import clara_lib
clara_lib.ENABLE_FILLET = True

info_off = parametric.run(params_off, "/tmp/test_clara_fillet_off.stl")
print(f"Clara fillet OFF: {info_off['faces']} faces, build={info_off['build']:.2f}s")

assert info_on['faces'] != info_off['faces'], f"Expected different face counts"
print("PASS: Clara fillet toggle works")
