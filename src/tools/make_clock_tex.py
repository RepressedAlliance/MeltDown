"""Seven-segment clock face textures for the desk clock (e.g. 02:00)."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SEG = {  # a b c d e f g
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd",
    "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg",
}


def digit(d, x, y, w, h, lit, dim, draw):
    t = w * 0.18
    segs = {
        "a": [(x + t, y), (x + w - t, y), (x + w - 2 * t, y + t), (x + 2 * t, y + t)],
        "d": [(x + 2 * t, y + h - t), (x + w - 2 * t, y + h - t), (x + w - t, y + h), (x + t, y + h)],
        "g": [(x + t, y + h / 2), (x + 2 * t, y + h / 2 - t / 2), (x + w - 2 * t, y + h / 2 - t / 2),
              (x + w - t, y + h / 2), (x + w - 2 * t, y + h / 2 + t / 2), (x + 2 * t, y + h / 2 + t / 2)],
        "f": [(x, y + t), (x + t, y + 2 * t), (x + t, y + h / 2 - t), (x, y + h / 2 - t / 2)],
        "b": [(x + w, y + t), (x + w, y + h / 2 - t / 2), (x + w - t, y + h / 2 - t), (x + w - t, y + 2 * t)],
        "e": [(x, y + h / 2 + t / 2), (x + t, y + h / 2 + t), (x + t, y + h - 2 * t), (x, y + h - t)],
        "c": [(x + w, y + h / 2 + t / 2), (x + w, y + h - t), (x + w - t, y + h - 2 * t), (x + w - t, y + h / 2 + t)],
    }
    for k, poly in segs.items():
        draw.polygon(poly, fill=lit if k in SEG[d] else dim)


def make(text, out):
    W, H = 512, 220
    im = Image.new("RGB", (W, H), (8, 4, 3))
    dr = ImageDraw.Draw(im)
    lit, dim = (255, 92, 40), (30, 12, 8)
    x = 40
    for ch in text:
        if ch == ":":
            dr.ellipse([x + 8, 70, x + 22, 84], fill=lit)
            dr.ellipse([x + 8, 136, x + 22, 150], fill=lit)
            x += 34
            continue
        digit(ch, x, 30, 90, 160, lit, dim, dr)
        x += 108
    glow = im.filter(ImageFilter.GaussianBlur(6))
    im = Image.fromarray(np.clip(np.asarray(im, np.float32) + np.asarray(glow, np.float32) * 0.6, 0, 255)
                         .astype(np.uint8))
    im.save(out)


if __name__ == "__main__":
    d = ROOT / "assets" / "plates"
    d.mkdir(parents=True, exist_ok=True)
    for txt in sys.argv[1:] or ["02:00"]:
        make(txt, d / f"clock_{txt.replace(':', '')}.png")
        print("made", txt)
