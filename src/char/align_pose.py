"""Align a processed pose to a reference pose by the eyes, so it can replace the reference in a shot
without re-framing the camera.

python align_pose.py <pose> <reference pose> [--profile]
Finds both irises (Rin's aqua) in each color.png, then scales and moves every layer of <pose>
(color, color_blink, normal, edge, hair, skin, cloth) so its eye midpoint and eye spacing match the
reference, on a canvas the reference's size. No rotation: a tilted head stays tilted. --profile: side
views show one eye, so scale by the distance from the top of the silhouette (the bow) to the eye.
If the scaled figure would run past the left or right border (an arm cut off by the canvas edge), the
canvas is widened equally on both sides instead: the card stays centred, so the shot's staging holds.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process import OUT  # noqa: E402

LAYERS = ("color.png", "color_blink.png", "normal.png", "edge.png", "hair.png", "skin.png", "cloth.png")


def eyes(pose, count=2):
    im = cv2.imread(str(OUT / pose / "color.png"), cv2.IMREAD_UNCHANGED)
    a = im[..., 3]
    hsv = cv2.cvtColor(im[..., :3], cv2.COLOR_BGR2HSV)
    ys = np.nonzero(a > 128)[0]
    top, bot = ys.min(), ys.min() + (ys.max() - ys.min()) * 0.6
    m = ((hsv[..., 0] >= 78) & (hsv[..., 0] <= 102) & (hsv[..., 1] > 90) & (hsv[..., 2] > 50) & (a > 128))
    m[: int(top)] = False
    m[int(bot):] = False
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m)
    order = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])[:count]
    if len(order) < count:
        raise SystemExit(f"{pose}: found {len(order)} iris blobs")
    pts = sorted((tuple(cent[i]) for i in order), key=lambda p: p[0])
    return np.array(pts, np.float64), [int(stats[i, cv2.CC_STAT_AREA]) for i in order], float(top)


def main(pose, ref, profile=False):
    k = 1 if profile else 2
    e_new, area_new, top_new = eyes(pose, k)
    e_ref, area_ref, top_ref = eyes(ref, k)
    if profile:
        s = (e_ref[0][1] - top_ref) / (e_new[0][1] - top_new)
    else:
        s = np.linalg.norm(e_ref[1] - e_ref[0]) / np.linalg.norm(e_new[1] - e_new[0])
    c_new, c_ref = e_new.mean(axis=0), e_ref.mean(axis=0)
    M = np.array([[s, 0, c_ref[0] - s * c_new[0]], [0, s, c_ref[1] - s * c_new[1]]], np.float64)
    ref_im = cv2.imread(str(OUT / ref / "color.png"), cv2.IMREAD_UNCHANGED)
    h_ref, w_ref = ref_im.shape[:2]
    a_new = cv2.imread(str(OUT / pose / "color.png"), cv2.IMREAD_UNCHANGED)[..., 3]
    xs = np.nonzero((a_new > 128).any(axis=0))[0]
    x_lo, x_hi = s * xs.min() + M[0, 2], s * xs.max() + M[0, 2]
    pad = int(np.ceil(max(0.0, 12 - x_lo, x_hi - (w_ref - 1) + 12)))
    M[0, 2] += pad
    print(f"{pose}: eyes {e_new.round(0).tolist()} (areas {area_new}) -> ref {e_ref.round(0).tolist()} "
          f"scale {s:.3f} shift {M[0, 2]:.0f},{M[1, 2]:.0f} widened {2 * pad}px")
    d = OUT / pose
    size = None
    for name in LAYERS:
        p = d / name
        if not p.exists():
            continue
        im = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        w, h = w_ref + 2 * pad, h_ref
        size = (w, h)
        if im.ndim == 3 and im.shape[2] == 4:
            # warp premultiplied so the cut-out edge does not pick up dark fringes
            a = im[..., 3:4].astype(np.float32) / 255
            rgbp = im[..., :3].astype(np.float32) * a
            rgbp = cv2.warpAffine(rgbp, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
            a2 = cv2.warpAffine(a[..., 0], M, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)[..., None]
            rgb = np.where(a2 > 1e-4, rgbp / np.maximum(a2, 1e-4), 0)
            out = np.dstack([np.clip(rgb, 0, 255), a2 * 255]).astype(np.uint8)
        else:
            out = cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
        cv2.imwrite(str(p), out)
    meta_p = d / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    a = cv2.imread(str(d / "color.png"), cv2.IMREAD_UNCHANGED)[..., 3]
    ys, xs = np.nonzero(a > 128)
    meta.update(size=list(size), bbox=[int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                aligned_to=ref, align_scale=round(float(s), 4))
    meta_p.write_text(json.dumps(meta, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--profile" in sys.argv)
