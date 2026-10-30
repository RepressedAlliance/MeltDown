"""How squashed each character card looks from its shot's camera (no Blender needed).

python card_angles.py [--all]
A card is a flat cut-out: seen at an angle it is foreshortened. For every card at the start,
middle and end of its shot this prints the apparent aspect against the true one
(1.00 = undistorted, 0.80 = 20 % thinner, 1.25 = 20 % flatter) and the angle between the card's
normal and the line to the camera. Cards that track the camera (face_cam) count as tracked.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import storyboard  # noqa: E402


def rot_xyz(rx, ry, rz):
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    # Blender XYZ Euler: R = Rz @ Ry @ Rx
    return [[cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
            [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
            [-sy, cy * sx, cy * cx]]


def mv(m, v):
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


def sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def norm(a):
    n = math.sqrt(dot(a, a)) or 1.0
    return [x / n for x in a]


def lerp_keys(keys, u):
    ks = sorted(keys, key=lambda k: k[0] if not isinstance(k[0], (list, tuple)) else k[0][1])
    us = [k[0] if not isinstance(k[0], (list, tuple)) else None for k in ks]
    if any(x is None for x in us):
        return ks[0][1], ks[0][2]
    if u <= us[0]:
        return ks[0][1], ks[0][2]
    for a, b in zip(ks, ks[1:]):
        if a[0] <= u <= b[0]:
            w = (u - a[0]) / max(1e-9, b[0] - a[0])
            return ([a[1][i] + (b[1][i] - a[1][i]) * w for i in range(3)],
                    [a[2][i] + (b[2][i] - a[2][i]) * w for i in range(3)])
    return ks[-1][1], ks[-1][2]


def card_aspect(spec, campos, aim=None):
    rot = spec.get("rot", (90, 0, 0))
    R = rot_xyz(math.radians(rot[0] - 90), math.radians(rot[1]), math.radians(rot[2]))
    right, up, normal = mv(R, [1, 0, 0]), mv(R, [0, 0, 1]), mv(R, [0, -1, 0])
    h = spec.get("h", 1.5) * spec.get("stretch", 1.0)
    loc = spec.get("loc", (0, 0, 0))
    center = [loc[i] + up[i] * h / 2 for i in range(3)]
    if aim is not None and not spec.get("face_cam"):
        # in a close-up only the part of the card at the middle of the frame is seen: measure there (where
        # the line of sight meets the card), not at the middle of a card mostly out of frame
        d = norm(sub(aim, campos))
        den = dot(d, normal)
        if abs(den) > 1e-6:
            t = dot(sub(loc, campos), normal) / den
            hit = [campos[i] + d[i] * t for i in range(3)]
            rel = sub(hit, loc)
            if 0 <= dot(rel, up) <= h and abs(dot(rel, right)) <= h:
                center = hit
    v = norm(sub(campos, center))
    fc = spec.get("face_cam")
    if fc == "full":
        return 1.0, 0.0
    if fc:
        # yaw about the card's up axis toward the camera
        vp = norm([v[i] - dot(v, up) * up[i] for i in range(3)])
        normal = vp
        right = norm([up[1] * normal[2] - up[2] * normal[1], up[2] * normal[0] - up[0] * normal[2],
                      up[0] * normal[1] - up[1] * normal[0]])
    lr = math.sqrt(max(0.0, 1 - dot(right, v) ** 2))
    lu = math.sqrt(max(0.0, 1 - dot(up, v) ** 2))
    ang = math.degrees(math.acos(max(-1.0, min(1.0, abs(dot(normal, v))))))
    lu *= spec.get("stretch", 1.0)          # a card lengthened along its up axis (render_shot, stretch)
    return (lr / lu if lu > 1e-6 else 9.9), ang


def main():
    show_all = "--all" in sys.argv
    for s in storyboard.resolved():
        if not s.get("cards") or not s.get("cam"):
            continue
        if s["cam"].get("path"):
            # a camera on one of flight.py's paths needs Blender's mathutils: src/tools/path_card_angles.py
            print(f"{s['id']:5s} camera on the path {s['cam']['path']!r}: measured by path_card_angles.py (Blender)")
            continue
        for spec in s["cards"]:
            if spec.get("shadow_only"):
                continue
            rows = []
            for u in (0.0, 0.5, 1.0):
                p, q = lerp_keys(s["cam"]["keys"], u)
                rows.append(card_aspect(spec, p, q))
            worst = min(rows, key=lambda r: min(r[0], 1 / max(r[0], 1e-6)))
            bad = worst[0] < 0.95 or worst[0] > 1.053      # more than 5 % out of true is visible
            if bad or show_all:
                print(f"{s['id']:5s} {spec['pose']:24s} face_cam={str(spec.get('face_cam')):5s} "
                      + "  ".join(f"aspect {a:4.2f} angle {g:4.0f}" for a, g in rows) + ("   <<" if bad else ""))


if __name__ == "__main__":
    main()
