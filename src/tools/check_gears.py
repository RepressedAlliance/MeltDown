"""Check the gear train for interpenetration without Blender: rasterise every gear's tooth outline
(the same polygon gear_mesh builds) at many moments and count overlapping pixels per pair.

python check_gears.py [out.png]
"""
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "blender"))
import scene_gears as G  # noqa: E402

PX = 1200  # pixels per metre


def outline(teeth):
    r_p = G.MODULE * teeth / 2
    r_o, r_r = r_p + G.MODULE, r_p - 1.25 * G.MODULE
    n = teeth * 4
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        phase = k % 4
        r = r_r if phase in (0, 3) else r_o
        da = (math.pi / n) * (0.25 if phase in (1, 2) else 0)
        aa = a + (da if phase == 1 else -da if phase == 2 else 0)
        pts.append((r * math.cos(aa), r * math.sin(aa)))
    return np.array(pts)


def mask(pts, x, y, rot, origin, size, px=PX):
    c, s = math.cos(rot), math.sin(rot)
    w = np.stack([pts[:, 0] * c - pts[:, 1] * s + x, pts[:, 0] * s + pts[:, 1] * c + y], axis=1)
    p = ((w - origin) * px).astype(np.int32)
    m = np.zeros(size, np.uint8)
    cv2.fillPoly(m, [p], 1)
    return m


def main():
    train = G.layout()
    outlines = [outline(t) for _, _, _, t, _, _ in train]
    r_out = [G.MODULE * (t / 2 + 1) for _, _, _, t, _, _ in train]
    # gears that do not mesh must not even reach each other
    for i in range(len(train)):
        for j in range(i + 2, len(train)):
            d = math.hypot(train[i][0] - train[j][0], train[i][1] - train[j][1])
            if d < r_out[i] + r_out[j]:
                print(f"gears {i}-{j} apart: footprints overlap (d={d:.3f} < {r_out[i] + r_out[j]:.3f})")
    # meshing pairs: rasterise only the window around the contact point
    for i in range(len(train) - 1):
        (xa, ya, ra0, _, _, sa), (xb, yb, rb0, _, _, sb) = train[i], train[i + 1]
        cx, cy = (xa + xb) / 2, (ya + yb) / 2
        half = (r_out[i] + r_out[i + 1]) / 2 + 0.05
        origin = np.array([cx - half, cy - half])
        size = (int(2 * half * PX), int(2 * half * PX))
        worst = 0
        for t in np.arange(0, 20, 0.04):
            ma = mask(outlines[i], xa, ya, ra0 + sa * t, origin, size)
            mb = mask(outlines[i + 1], xb, yb, rb0 + sb * t, origin, size)
            worst = max(worst, int(np.count_nonzero(ma & mb)))
        print(f"gears {i}-{i + 1} mesh: max overlap {worst} px ({worst / PX / PX * 1e4:.3f} cm2)")
    print("teeth", [t for _, _, _, t, _, _ in train])
    if len(sys.argv) > 1:
        lo = 120  # px per metre for the overview
        xs, ys = [x for x, *_ in train], [y for _, y, *_ in train]
        origin = np.array([min(xs) - 2, min(ys) - 2])
        size = (int((max(ys) - min(ys) + 4) * lo), int((max(xs) - min(xs) + 4) * lo))
        img = np.zeros(size + (3,), np.uint8)
        for k, (o, (x, y, rot, _, _, _)) in enumerate(zip(outlines, train)):
            img[mask(o, x, y, rot, origin, size, lo) > 0] = (60 + 20 * k, 140, 255 - 20 * k)
        cv2.imwrite(sys.argv[1], img[::-1])


if __name__ == "__main__":
    main()
