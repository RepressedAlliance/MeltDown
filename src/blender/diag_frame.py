"""Diagnose a black final frame: render one frame without compositing to EXR and report NaN/Inf.

blender -b --factory-startup -P diag_frame.py -- <shot_id> <frame> <out.exr> [nocomp=1] [rt=0|1] [vol=8|16]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import render_shot  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
sid, frame, out = argv[0], int(argv[1]), argv[2]
opts = dict(a.split("=", 1) for a in argv[3:])
sc, shot, f0, f1 = render_shot.prepare(sid, preview=False, pct=opts.get("pct"))
ee = sc.eevee
if "rt" in opts:
    ee.use_raytracing = opts["rt"] == "1"
if "vol" in opts:
    ee.volumetric_tile_size = opts["vol"]
if opts.get("nocomp") == "1":
    sc.render.use_compositing = False
sc.render.image_settings.file_format = "OPEN_EXR"
sc.render.image_settings.color_depth = "32"
sc.render.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "Standard"
sc.frame_set(frame)
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
img = bpy.data.images.load(out)
px = np.array(img.pixels[:], dtype=np.float32).reshape(-1, 4)[:, :3]
print("DIAG", sid, frame, opts, "nan", int(np.isnan(px).any(axis=1).sum()), "inf", int(np.isinf(px).any(axis=1).sum()),
      "mean", float(np.nanmean(px)), "max", float(np.nanmax(px)))
