"""Flip-book review of the composite without encoding video: full-quality frames at a fixed step,
downsized and tiled into labelled sheets (time, shot, lyric line).

python review_sheets.py [--from 0] [--to 329] [--every 1.0] [--out work/review] [--cols 4] [--rows 6]
python review_sheets.py --times 72.25,72.29,72.33 --out work/review/s23   exact times
"""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "comp"))
sys.path.insert(0, str(ROOT / "src"))
import render_comp  # noqa: E402
import storyboard  # noqa: E402
import timeline as TL  # noqa: E402

FPS = 24
CW, CH = 480, 270


def line_at(t):
    cur = [ln["i"] for ln in TL.LINES if ln["start"] - 0.2 <= t <= ln["end"] + 0.2]
    return f"L{cur[-1]}" if cur else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--every", type=float, default=1.0)
    ap.add_argument("--times", default=None)
    ap.add_argument("--out", default=str(ROOT / "work" / "review"))
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--rows", type=int, default=6)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    shots = storyboard.resolved()
    if args.times:
        times = [float(x) for x in args.times.split(",")]
    else:
        t1 = args.t1 if args.t1 is not None else TL.DURATION
        times = list(np.arange(args.t0, t1, args.every))
    per = args.cols * args.rows
    lab = 18
    for k in range(0, len(times), per):
        chunk = times[k:k + per]
        rows = (len(chunk) + args.cols - 1) // args.cols
        sheet = Image.new("RGB", (args.cols * (CW + 4) - 4, rows * (CH + lab + 4)), (40, 40, 44))
        d = ImageDraw.Draw(sheet)
        for i, t in enumerate(chunk):
            f = int(round(t * FPS))
            img = render_comp.render_frame(shots, f, False)
            small = cv2.resize(np.clip(img, 0, 1), (CW, CH), interpolation=cv2.INTER_AREA)
            cell = Image.fromarray((small * 255 + 0.5).astype(np.uint8))
            x, y = (i % args.cols) * (CW + 4), (i // args.cols) * (CH + lab + 4)
            sheet.paste(cell, (x, y + lab))
            sid = next((s["id"] for s in shots if s["t0"] <= f / FPS < s["t1"]), "?")
            d.text((x + 4, y + 3), f"{f / FPS:7.2f}s  {sid}  {line_at(f / FPS)}", fill=(235, 235, 235))
        name = out / f"review{args.tag}_{chunk[0]:07.2f}.png"
        sheet.save(name)
        print("sheet", name, flush=True)


if __name__ == "__main__":
    main()
