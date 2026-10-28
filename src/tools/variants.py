"""Compare look variants side by side on chosen frames before committing a change to the storyboard.

python variants.py <out.png> <times> <variants.json>
times: comma list of seconds. variants.json: {"name": {"shot": {...overrides for every shot...},
"by_id": {"S23": {...}}, "chorus": {...replaces storyboard.CHORUS burn...}}, ...}
Each row is one time, each column one variant.
"""
import copy
import json
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

CW, CH = 640, 360


def main():
    out, times, spec = Path(sys.argv[1]), [float(x) for x in sys.argv[2].split(",")], sys.argv[3]
    variants = json.loads(Path(spec).read_text(encoding="utf-8")) if spec.endswith(".json") else json.loads(spec)
    base_chorus = dict(storyboard.CHORUS)
    cols = []
    for name, v in variants.items():
        storyboard.CHORUS.clear()
        storyboard.CHORUS.update(v.get("chorus", base_chorus))
        shots = copy.deepcopy(storyboard.resolved())
        for s in shots:
            s.update(v.get("shot", {}))
            s.update(v.get("by_id", {}).get(s["id"], {}))
        cells = []
        for t in times:
            img = render_comp.render_frame(shots, int(round(t * 24)), False)
            small = cv2.resize(np.clip(img, 0, 1), (CW, CH), interpolation=cv2.INTER_AREA)
            cells.append(Image.fromarray((small * 255 + 0.5).astype(np.uint8)))
            print(name, t, flush=True)
        cols.append((name, cells))
    lab = 18
    sheet = Image.new("RGB", (len(cols) * (CW + 4) - 4, len(times) * (CH + lab + 4)), (40, 40, 44))
    d = ImageDraw.Draw(sheet)
    for ci, (name, cells) in enumerate(cols):
        for ri, cell in enumerate(cells):
            x, y = ci * (CW + 4), ri * (CH + lab + 4)
            sheet.paste(cell, (x, y + lab))
            d.text((x + 4, y + 3), f"{name}  {times[ri]:.2f}s", fill=(235, 235, 235))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print("sheet", out)


if __name__ == "__main__":
    main()
