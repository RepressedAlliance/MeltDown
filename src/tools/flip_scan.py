"""Every Blender shot's camera, baked as for its render, frame by frame: any frame where the picture's up direction
turns by more than 20 degrees from the frame before. A camera looking almost straight down has no clear "up", and
Blender's track solution can turn the whole picture 90 degrees from one height to the next (S54's first frames did).

blender -b --factory-startup -P src/tools/flip_scan.py [-- S54,S09]
Builds only the cameras (no scenes), so it takes seconds.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "blender"))
sys.path.insert(0, str(ROOT / "src"))
import common  # noqa: E402
import render_shot  # noqa: E402
import storyboard  # noqa: E402
from mathutils import Vector  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
want = set(argv[0].split(",")) if argv else None
flips = 0
for shot in storyboard.resolved():
    if not shot.get("scene") or (want and shot["id"] not in want):
        continue
    t0, t1 = shot["t0"], max(shot["t1"], shot.get("render_to", 0.0))
    f0 = int(round(t0 * 24))
    f1 = int(round((t1 + shot.get("tail", 0.0)) * 24)) - 1
    sc = common.reset()
    sc.frame_start, sc.frame_end = f0, f1
    cam = render_shot.setup_camera(sc, shot, t0, t1 - t0, f0, f1)
    prev, bad = None, []
    for f in range(f0 - 1, f1 + 1):
        sc.frame_set(f)
        up = cam.matrix_world.to_3x3() @ Vector((0, 1, 0))
        if prev is not None and math.degrees(up.angle(prev)) > 20:
            bad.append((f, round(math.degrees(up.angle(prev)), 1)))
        prev = up
    if bad:
        flips += 1
        print("FLIP", shot["id"], bad[:6])
print(f"FLIP_SCAN_DONE {flips} shot(s) with a flip")
