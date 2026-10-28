"""Render one test still of a scene: blender -b -P still.py -- <scene> <out.png> [key=value ...]."""
import importlib
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    scene_name, out = argv[0], argv[1]
    opts = dict(a.split("=", 1) for a in argv[2:])
    sc = common.reset()
    common.setup_render(sc, preview=opts.get("preview", "1") == "1", pct=int(opts.get("pct", 50)))
    mod = importlib.import_module(f"scene_{scene_name}")
    fn = getattr(mod, opts.get("fn", "test_view"))
    view = fn(sc, opts)
    frame = int(opts.get("frame", 1))
    sc.frame_set(frame)
    sc.render.filepath = out
    import bpy
    bpy.ops.render.render(write_still=True)
    print("STILL_OK", out)


main()
