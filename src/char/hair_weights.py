"""Smooth weights for the hair sway: assets/char/<pose>/hair_soft.png for every processed pose.

python hair_weights.py [pose ...]     (default: every pose folder with a hair.png)
The sway warps the drawing inside the hair. A hard mask makes the hair slide past what is drawn on
top of it (headphone band, hair clips) and past the face, which reads as a second, ghosted layer of
hair. These weights instead change slowly everywhere: holes in the mask (band, clips) are closed so
they ride along, hair near the face and the skin barely moves, the tips move most, and the whole
field is blurred so the warp bends lines instead of tearing them.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CHAR = ROOT / "assets" / "char"


def weights(d):
    hair = cv2.imread(str(d / "hair.png"), cv2.IMREAD_GRAYSCALE)
    if hair is None:
        return None
    h, w = hair.shape
    s = max(h, w)
    m = (hair > 127).astype(np.uint8)
    k = max(3, int(s * 0.03) | 1)
    closed = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    # fill enclosed holes (band, clips) completely
    ff = closed.copy()
    pad = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, pad, (0, 0), 1)
    closed = closed | (1 - ff)
    skin_p = d / "skin.png"
    if skin_p.exists():
        skin = (cv2.imread(str(skin_p), cv2.IMREAD_GRAYSCALE) > 127).astype(np.uint8)
        dist = cv2.distanceTransform(1 - skin, cv2.DIST_L2, 5)
        ramp = np.clip(dist / (s * 0.06), 0, 1)
        ramp = ramp * ramp * (3 - 2 * ramp)
    else:
        ramp = np.ones((h, w), np.float32)
    wgt = closed.astype(np.float32) * ramp
    wgt = cv2.GaussianBlur(wgt, (0, 0), s * 0.014)
    wgt /= max(1e-6, float(np.percentile(wgt[closed > 0], 98)) if closed.any() else 1.0)
    out = (np.clip(wgt, 0, 1) * 255 + 0.5).astype(np.uint8)
    cv2.imwrite(str(d / "hair_soft.png"), out)
    return out


def main():
    names = sys.argv[1:] or sorted(p.name for p in CHAR.iterdir() if (p / "hair.png").exists())
    for n in names:
        if weights(CHAR / n) is not None:
            print("wrote", n)


if __name__ == "__main__":
    main()
