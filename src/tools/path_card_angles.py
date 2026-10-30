"""How obliquely a camera on a path (flight.py) sees each character card, frame by frame (card_angles.py measures
the keyed cameras without Blender; a path needs Blender's mathutils).

blender -b --factory-startup -P src/tools/path_card_angles.py [-- S09]
A card is a flat drawing: seen far from straight on it reads as paper. For every frame a card is on (its `on`
intervals) and part of it is in the picture, this measures the angle between the line of sight and the card's
facing direction, and reports the worst angle per shot; over 35 degrees is flagged. The opening's camera once flew
toward the bed through her window and saw her lying drawing from 70-80 degrees ("穿帮", the director said).
Cards that turn to the camera (face_cam) always face it and are skipped. The part of a lying card under a tucked
quilt (setup quilt `edge`) is left out; other occlusion is not considered, so a flag can be a frame where a wall
hides her: check those frames by eye. Exits 1 if anything is flagged.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "blender"))
sys.path.insert(0, str(ROOT / "src"))
from mathutils import Euler, Vector  # noqa: E402

import flight  # noqa: E402
import storyboard  # noqa: E402

FPS = 24
LIMIT = 35.0


def card_points(spec, quilt_edge=None):
    """Points along the card's long axis (those under a tucked quilt left out), and the direction it faces."""
    rx, ry, rz = (math.radians(a) for a in spec.get("rot", (0, 0, 0)))
    rot = Euler((rx, ry, rz), "XYZ").to_matrix()
    if spec.get("tilt"):
        rot = rot @ Euler((math.radians(spec["tilt"]), 0, 0), "XYZ").to_matrix()
    up, normal = rot @ Vector((0, 1, 0)), rot @ Vector((0, 0, 1))
    base = Vector(spec["loc"])
    h = spec.get("h", 1.0)
    pts = [base + up * (h * f) for f in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9)]
    if quilt_edge is not None:
        pts = [pt for pt in pts if pt.y > quilt_edge]
    return pts, normal


def main():
    only = set(sys.argv[sys.argv.index("--") + 1].split(",")) if "--" in sys.argv[:-1] else None
    bad = 0
    for s in storyboard.resolved():
        cam = s.get("cam") or {}
        if not cam.get("path") or (only and s["id"] not in only):
            continue
        path = flight.PATHS[cam["path"]]
        for spec in s.get("cards", []):
            if not isinstance(spec, dict) or spec.get("face_cam") or spec.get("shadow_only"):
                continue
            quilt = (s.get("setup") or {}).get("quilt") or {}
            pts, normal = card_points(spec, quilt.get("edge") if quilt.get("mode") == "tucked" else None)
            worst = (0.0, None)
            for f in range(round(s["t0"] * FPS), round(s["t1"] * FPS)):
                t = f / FPS
                if spec.get("on") is not None and not any(a <= t < b for a, b in spec["on"]):
                    continue
                p, q, lens = path(t)
                if cam.get("frame") == "room":
                    p, q = flight.to_room(p, q)
                inv = q.inverted()
                seen = []
                for pt in pts:
                    v = inv @ (pt - p)
                    if v.z < -0.01 and abs(v.x / -v.z) < 18.0 / lens and abs(v.y / -v.z) < 10.125 / lens:
                        seen.append(math.degrees(abs(math.asin(max(-1.0, min(1.0, (p - pt).normalized().dot(normal)))))))
                if seen:
                    ang = 90.0 - min(seen)
                    if ang > worst[0]:
                        worst = (ang, t)
            flag = worst[0] > LIMIT
            bad += flag
            print(f"{s['id']:5s} {spec.get('pose', '?'):22s} worst {worst[0]:4.0f} deg"
                  + (f" at {worst[1]:.2f}s" if worst[1] is not None else " (never in the picture)")
                  + ("   << seen from the side" if flag else ""))
    print(f"path card angles: {bad} flagged")
    sys.exit(1 if bad else 0)


main()
