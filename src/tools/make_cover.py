"""Video cover (1920x1080 and 1146x717 for Bilibili) from a frame of the film plus title type.

python make_cover.py <frame.png|jpg> [out_dir]
python make_cover.py --time 78.3 [out_dir]     composite that moment without lyrics, HUD or titles
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np
import skia
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "comp"))
from canvas import paint, surface, to_array  # noqa: E402
from typo.glyphs import glyph_matrix, layout  # noqa: E402


def text(c, s, face, size, x, y, col, a=1.0, vertical=False, tracking=0.0):
    blk = layout(s, face, size, vertical=vertical, tracking=tracking)
    for g in blk.glyphs:
        m = glyph_matrix(g)
        m.postTranslate(x, y)
        p = skia.Path(g.path)
        p.transform(m)
        c.drawPath(p, paint((0, 0, 0), a * 0.6, blur=size * 0.08))
        c.drawPath(p, paint(col, a))
    return blk


def clean_frame(t):
    """The film's frame at t with the type layer emptied: no lyrics, HUD, titles, stamps or marks."""
    import render_comp
    import storyboard
    storyboard.LYRIC_STYLES.clear()
    storyboard.EXTRA_LINES.clear()       # sung words off the lyric sheet are lyrics too
    shots = storyboard.resolved()
    for s in shots:
        for k in ("hud", "title", "stamps", "marks"):
            s.pop(k, None)
    return np.clip(render_comp.render_frame(shots, int(round(t * 24)), False), 0, 1).astype(np.float32)


def main():
    args = sys.argv[1:]
    if args[0] == "--time":
        base = clean_frame(float(args[1]))
        args = args[2:]
    else:
        base = np.asarray(Image.open(args[0]).convert("RGB").resize((1920, 1080)), np.float32) / 255
        args = args[1:]
    out_dir = Path(args[0]) if args else ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    s = surface()
    c = s.getCanvas()
    paper = (0.95, 0.92, 0.85)
    # the same midnight-ink plate as the film's poster card, so the credits read over any frame
    c.drawRect(skia.Rect.MakeXYWH(80, 760, 860, 230), paint((0.05, 0.07, 0.17), 0.88))
    text(c, "炉心融解", "mincho_b", 210, 1560, 90, paper, vertical=True, tracking=0.06)
    text(c, "MELTDOWN", "shoulders", 84, 110, 820, (1.0, 0.83, 0.0), tracking=0.22)
    text(c, "iroha(sasaki)  feat.  Kagamine Rin", "code_jp", 40, 116, 930, paper)
    c.drawLine(110, 905, 900, 905, paint(paper, 0.7, stroke=2))
    lay = to_array(s)
    img = base * (1 - lay[..., 3:4]) + lay[..., :3]
    im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    im.save(out_dir / "cover_1920x1080.png")
    im.resize((1146, 717), Image.LANCZOS).save(out_dir / "cover_1146x717.png")
    print("cover written", out_dir)


if __name__ == "__main__":
    main()
