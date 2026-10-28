"""Contact sheets of composited stills across the whole film (for review).

python sweep_sheets.py <every_seconds> [start] [end]
Reads work/comp_stills/t*.png produced by render_comp.py --stills and tiles them, 24 per sheet.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]


def main():
    step = float(sys.argv[1])
    t0 = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    t1 = float(sys.argv[3]) if len(sys.argv) > 3 else 329.0
    ts = []
    t = t0
    while t < t1:
        ts.append(round(t, 2))
        t += step
    cw, ch, cols, per = 384, 216, 6, 24
    for k in range(0, len(ts), per):
        chunk = ts[k:k + per]
        rows = (len(chunk) + cols - 1) // cols
        sh = Image.new("RGB", (cols * cw, rows * (ch + 16)), (18, 18, 22))
        d = ImageDraw.Draw(sh)
        for i, tt in enumerate(chunk):
            p = ROOT / "work" / "comp_stills" / f"t{tt:07.2f}.png"
            if not p.exists():
                continue
            im = Image.open(p).convert("RGB").resize((cw, ch))
            x, y = (i % cols) * cw, (i // cols) * (ch + 16)
            sh.paste(im, (x, y))
            d.text((x + 4, y + ch + 2), f"{tt:.1f}s", fill=(230, 230, 230))
        out = ROOT / "work" / f"sweep_{k // per:02d}.png"
        sh.save(out)
        print(out)


if __name__ == "__main__":
    main()
