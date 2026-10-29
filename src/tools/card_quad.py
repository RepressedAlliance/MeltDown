"""Where a shot's first card lands in the frame: its four corners (the drawing's top-left, top-right,
bottom-right, bottom-left) in 1920x1080 pixels at a given frame, with the camera and the card's tracking
evaluated. A 2D shot can then lay the same drawing exactly over that frame (scenes2d.chest_core `quad`).

blender -b --factory-startup -P src/tools/card_quad.py -- S56:6434 S15:1128
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC / "blender"))
sys.path.insert(0, str(SRC))

import bpy  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Vector  # noqa: E402

import render_shot  # noqa: E402

for arg in sys.argv[sys.argv.index("--") + 1:]:
    sid, f = arg.split(":")
    sc, shot, f0, f1 = render_shot.prepare(sid, preview=True, pct=40, samples=1)
    sc.frame_set(int(f))
    bpy.context.view_layer.update()
    card = next(o for o in sc.objects if o.name.startswith("Rin_"))
    cam = sc.camera
    me = card.data
    xs = [v.co.x for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    pts = []
    for lx, lz in ((x0, z1), (x1, z1), (x1, z0), (x0, z0)):
        p = world_to_camera_view(sc, cam, card.matrix_world @ Vector((lx, 0.0, lz)))
        pts.append((round(p.x * 1920, 1), round((1 - p.y) * 1080, 1)))
    print("QUAD", sid, f, card.name, pts, flush=True)
