"""Turn the TV host's black microphone silver, so it reads on the grey, halftone-printed TV screens.

python src/char/silver_mic.py            (after process.py rin_tv_host; then src/tools/make_tv_picture.py)
The drawing's mic is black against her black sailor collar: once the TV picture is grey and printed in
dots, the two merge and the mic disappears. The mic's shape (a ball grille, a band and a tapered handle,
in the drawing's pixels) is drawn as a mask; inside it the dark fill is lifted to a light metal while its
black outline and her fingers stay as drawn, and the grille's mesh texture is kept.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
POSE = ROOT / "assets" / "char" / "rin_tv_host"

# the mic in the drawing's own pixels (1024 x 1536)
GRILLE = ((391, 740), 47)                       # centre, radius
HANDLE = ((383, 776), (340, 1028), 23, 17)      # top centre, bottom centre, half-width at top and bottom


def mic_mask(h, w):
    m = np.zeros((h, w), np.uint8)
    (cx, cy), r = GRILLE
    cv2.circle(m, (cx, cy), r, 255, -1)
    (x0, y0), (x1, y1), w0, w1 = HANDLE
    d = np.array([x1 - x0, y1 - y0], np.float32)
    n = np.array([-d[1], d[0]], np.float32) / np.linalg.norm(d)
    poly = np.array([[x0, y0] + n * w0, [x1, y1] + n * w1, [x1, y1] - n * w1, [x0, y0] - n * w0], np.int32)
    cv2.fillPoly(m, [poly], 255)
    return m > 0


def main():
    src = POSE / "color.png"
    img = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    if img is None:
        sys.exit(f"missing {src}")
    bgr = img[..., :3].astype(np.float32)
    lum = bgr @ np.array([0.114, 0.587, 0.299], np.float32)
    inside = mic_mask(*lum.shape)
    # only the mic's own neutral greys: her fingers' warm outline and its soft edge stay as drawn
    neutral = (bgr.max(axis=2) - bgr.min(axis=2)) <= 14
    # the fill: dark but not the black outline, and not her (light) skin
    fill = inside & neutral & (lum > 30) & (lum < 140)
    # the deep shadow side: wide dark areas (the outline is a thin line, an opening removes it)
    dark = ((lum < 34) & inside & neutral).astype(np.uint8)
    shadow = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0
    k = np.clip((lum - 40) / 70, 0, 1)
    metal = 150 + 95 * k                          # 40 -> 150 (shadow side), 110+ -> 245 (highlight)
    metal = np.where(shadow, 100 + lum, metal)    # the darkest side stays a darker steel
    out = bgr.copy()
    tint = np.array([1.0, 0.985, 0.97], np.float32)  # a cool steel
    sel = fill | shadow
    out[sel] = (metal[sel, None] * tint).clip(0, 255)
    img[..., :3] = out.astype(np.uint8)
    cv2.imwrite(str(src), img)
    print("silver mic:", int(sel.sum()), "pixels recoloured in", src)


if __name__ == "__main__":
    main()
