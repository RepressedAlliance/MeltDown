"""Render one low-res still per shot (composition check) in a single Blender session.

blender -b --factory-startup -P stills_batch.py -- <out_dir> <u> <shot_id> [<shot_id> ...]
"""
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import bpy  # noqa: E402

import render_shot  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
out_dir, u, ids = Path(argv[0]), float(argv[1]), argv[2:]
out_dir.mkdir(parents=True, exist_ok=True)
for sid in ids:
    try:
        sc, shot, f0, f1 = render_shot.prepare(sid, preview=True, pct=40, samples=8)
        f = f0 + int(u * (f1 - f0))
        sc.frame_set(f)
        sc.render.filepath = str(out_dir / f"{sid}.png")
        bpy.ops.render.render(write_still=True)
        print("BATCH_OK", sid, f, flush=True)
    except Exception:
        print("BATCH_FAIL", sid, flush=True)
        traceback.print_exc()
