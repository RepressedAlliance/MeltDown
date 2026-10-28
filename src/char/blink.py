"""Build color_blink.png for a pose: the edited closed-eye image, aligned to the
processed original and patched in only where the eyes changed.

python blink.py <pose> [band]   (expects assets/char/raw/<pose>_blink_v1.png)
band: the share of the figure's height, from the top, where the eyes may be (default 0.65; use 1.0
for a pose lying on its side, where one eye sits low in the image)
"""
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from celify import celify  # noqa: E402
from process import OUT, RAW, clean_alpha, decontaminate, load_rgba  # noqa: E402


def main(pose, band=0.65):
    base = cv2.imread(str(OUT / pose / "color.png"), cv2.IMREAD_UNCHANGED)
    base_rgb = cv2.cvtColor(base[..., :3], cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    base_a = base[..., 3].astype(np.float32) / 255
    rgb, a = load_rgba(RAW / f"{pose}_blink_v1.png")
    if rgb.shape[:2] != base_rgb.shape[:2]:
        rgb = cv2.resize(rgb, (base_rgb.shape[1], base_rgb.shape[0]), interpolation=cv2.INTER_CUBIC)
        a = cv2.resize(a, (base_rgb.shape[1], base_rgb.shape[0]), interpolation=cv2.INTER_CUBIC)
    a = clean_alpha(a)
    rgb = decontaminate(rgb, a)
    sty, a, _ = celify(rgb, a, scale=max(a.shape) / 1200.0)
    # align the edit to the original (affine ECC on grey + alpha)
    g0 = cv2.cvtColor((base_rgb * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    g1 = cv2.cvtColor((sty * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(g0 * base_a, g1 * a, warp, cv2.MOTION_AFFINE,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5)
    except cv2.error as e:
        print("ECC failed, using identity:", e)
    h, w = g0.shape
    sty_al = cv2.warpAffine(sty, warp, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    diff = np.abs(sty_al - base_rgb).max(axis=2) * (base_a > 0.5)
    m = (diff > 0.18).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m)
    # keep the eye regions: the largest changed blobs in the upper half of the figure
    ys = np.nonzero(base_a > 0.5)[0]
    top, bot = ys.min(), ys.min() + (ys.max() - ys.min()) * band
    keep = np.zeros_like(m)
    order = sorted(range(1, n), key=lambda i: -stats[i, cv2.CC_STAT_AREA])
    for i in order[:4]:
        if top <= cent[i][1] <= bot and stats[i, cv2.CC_STAT_AREA] > 0.0004 * m.size:
            keep[lab == i] = 1
    keep = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    mask = cv2.GaussianBlur(keep.astype(np.float32), (0, 0), 6)[..., None]
    out = base_rgb * (1 - mask) + sty_al * mask
    rgba = np.dstack([out, base_a])
    rgba = (np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8)
    cv2.imwrite(str(OUT / pose / "color_blink.png"), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    print("blink written", pose, "patched px:", int(keep.sum()))


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.65)
