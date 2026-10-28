"""Widen a pose's canvas without moving the figure, continuing a limb that runs into the border.

python src/char/extend_canvas.py rin_lighter_hand v2 v3 --pad 420 --slope 0.42

Equal margins go on the left and right, so the card's centre (and the shot's staging) stays where it
was. A limb cut by the left border is continued by extruding the border pixels along the limb: a plain
sleeve carries on as a sleeve, its outlines as straight lines. slope: how far the limb drops (in px)
per px it goes left. Then: process.process(name, new_version, ref=<old canvas size>).
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image

RAW = Path(__file__).resolve().parents[2] / "assets" / "char" / "raw"


def extend(name, src, dst, pad, slope, inset=3):
    im = np.asarray(Image.open(RAW / f"{name}_{src}.png").convert("RGBA")).astype(np.float32)
    h, w, _ = im.shape
    out = np.zeros((h, w + 2 * pad, 4), np.float32)
    out[:, pad:pad + w] = im
    rows = np.arange(h, dtype=np.float32)
    # the new margin and the old border columns (anti-aliased against the cut) take the colour of the
    # column `inset` px inside the old border, followed back along the limb
    for x in range(pad + inset):
        ys = rows - slope * ((pad + inset) - x)
        y0 = np.floor(ys).astype(int)
        fy = (ys - y0)[:, None]
        ok = (y0 >= 0) & (y0 + 1 <= h - 1)
        y0c = np.clip(y0, 0, h - 2)
        col = im[y0c, inset] * (1 - fy) + im[y0c + 1, inset] * fy
        col[~ok] = 0
        out[:, x] = col
    Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA").save(RAW / f"{name}_{dst}.png")
    return w


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--pad", type=int, default=400)
    ap.add_argument("--slope", type=float, default=0.0)
    a = ap.parse_args()
    w = extend(a.name, a.src, a.dst, a.pad, a.slope)
    print("extended", a.name, a.dst, "old width", w)
