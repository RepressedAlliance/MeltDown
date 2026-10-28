"""Plot vocal energy with aligned lyric line spans (labelled by line index only)."""
import json
from pathlib import Path

import librosa
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]


def main():
    y, sr = librosa.load(ROOT / "work" / "stems" / "vocals.wav", sr=22050, mono=True)
    hop = 256
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms = rms / (np.percentile(rms, 99) + 1e-9)
    t_r = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    lines = json.loads((ROOT / "work" / "analysis" / "lyrics_timed.json").read_text(encoding="utf-8"))
    row_s, W, H = 30, 1800, 110
    dur = len(y) / sr
    rows = int(np.ceil(dur / row_s))
    img = Image.new("RGB", (W, H * rows), (12, 12, 16))
    d = ImageDraw.Draw(img)
    for r in range(rows):
        y0, t0 = r * H, r * row_s
        pts = []
        for x in range(W):
            tt = t0 + x / W * row_s
            i = min(np.searchsorted(t_r, tt), len(rms) - 1)
            pts.append((x, y0 + H - 10 - min(1.0, rms[i]) * (H - 40)))
        d.line(pts, fill=(200, 200, 210))
        for ln in lines:
            if ln["end"] < t0 or ln["start"] > t0 + row_s:
                continue
            xa = (ln["start"] - t0) / row_s * W
            xb = (ln["end"] - t0) / row_s * W
            col = (255, 120, 60) if ln["i"] % 2 else (80, 170, 255)
            d.rectangle([xa, y0 + 4, xb, y0 + 16], outline=col)
            d.text((xa + 2, y0 + 18), str(ln["i"]), fill=col)
            for c in ln["ct"]:
                xc = (c - t0) / row_s * W
                d.line([(xc, y0 + 4), (xc, y0 + 10)], fill=col)
        for s in range(0, row_s, 5):
            d.text((s / row_s * W + 2, y0 + H - 22), f"{t0 + s}s", fill=(90, 90, 90))
    img.save(ROOT / "work" / "analysis" / "lyrics_check.png")


if __name__ == "__main__":
    main()
