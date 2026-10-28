"""Print-production framing, title cards, telops and the drifting ember layer."""
import math
import sys
from pathlib import Path

import numpy as np
import skia

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typo.glyphs import glyph_matrix, layout  # noqa: E402

from canvas import H, W, paint  # noqa: E402


def _text(c, s, face, size, x, y, col, a=1.0, tracking=0.0, vertical=False, proportional=True):
    blk = layout(s, face, size, vertical=vertical, tracking=tracking, proportional=proportional)
    for g in blk.glyphs:
        m = glyph_matrix(g)
        m.postTranslate(x, y)
        p = skia.Path(g.path)
        p.transform(m)
        c.drawPath(p, paint(col, a))
    return blk


def print_marks(c, t, col=(0.93, 0.9, 0.83), a=0.7, sheet="", inks=(), margin=46):
    """Crop marks, registration targets, ink swatches and a small title block."""
    p = paint(col, a, stroke=1.2)
    L = 30
    for (x, y, dx, dy) in ((margin, margin, -1, -1), (W - margin, margin, 1, -1),
                           (margin, H - margin, -1, 1), (W - margin, H - margin, 1, 1)):
        c.drawLine(x, y + dy * 8, x, y + dy * (8 + L), p)
        c.drawLine(x + dx * 8, y, x + dx * (8 + L), y, p)
    for (x, y) in ((W / 2, margin / 2 + 4), (W / 2, H - margin / 2 - 4)):
        c.drawCircle(x, y, 9, p)
        c.drawLine(x - 15, y, x + 15, y, p)
        c.drawLine(x, y - 15, x, y + 15, p)
    for k, ink in enumerate(inks):
        c.drawRect(skia.Rect.MakeXYWH(margin + 60 + k * 26, H - margin + 10, 22, 12), paint(ink, a))
    if sheet:
        _text(c, sheet, "mono", 14, W - margin - 330, H - margin + 9, col, a * 0.9, proportional=False)


def title_card(c, t, u, col=(0.93, 0.9, 0.83), accent=(1.0, 0.83, 0.0), mode="ring", cx=W / 2, cy=H / 2, r=230,
               at=0.0, panel="left", size=150, plate_title=True):
    """The film title. mode 'ring': inside the opening ring; 'poster': full credits over the picture,
    coming up from shot fraction `at` (the end titles start once Rin has woken). `col` colours the big
    title; the credits always sit light on their dark plate, at the lower `panel` corner."""
    if mode == "ring":
        a = max(0.0, min(1.0, (u - 0.45) / 0.25))
        blk = layout("炉心融解", "mincho_b", 74, vertical=True, tracking=0.18)
        for g in blk.glyphs:
            k = max(0.0, min(1.0, (u - 0.45 - g.index * 0.06) / 0.2))
            m = glyph_matrix(g, dy=(1 - k) * -10)
            m.postTranslate(cx, cy - blk.height / 2)
            pth = skia.Path(g.path)
            pth.transform(m)
            c.drawPath(pth, paint(col, k))
        if a > 0:
            _text(c, "MELTDOWN", "shoulders_l", 22, cx - 58, cy + r + 26, accent, a, tracking=0.6)
        return
    # poster: big vertical title right, credits left-bottom, thin rules
    a = max(0.0, min(1.0, (u - at) * 3 / max(0.1, 1 - at))) * max(0.0, min(1.0, (1 - u) * 6))
    if a <= 0:
        return
    # the title and the credits each sit on a plate of the midnight ink, so they read over any picture
    ink, light = (0.05, 0.07, 0.17), (0.93, 0.9, 0.83)
    blk = layout("炉心融解", "mincho_b", size, vertical=True, tracking=0.08)
    tx, ty = W - 96 - size, 112
    # vertical glyphs are centred on their x: the plate is centred on tx too
    c.drawRect(skia.Rect.MakeXYWH(tx - size / 2 - 26, ty - 26, size + 52, blk.height + 52), paint(ink, a * 0.95))
    for g in blk.glyphs:
        m = glyph_matrix(g)
        m.postTranslate(tx, ty)
        pth = skia.Path(g.path)
        pth.transform(m)
        c.drawPath(pth, paint(light if plate_title else col, a))
    pw = 860
    px = 96 if panel == "left" else W - 96 - pw
    c.drawRect(skia.Rect.MakeXYWH(px, H - 344, pw, 264), paint(ink, a * 0.95))
    _text(c, "MELTDOWN", "shoulders", 64, px + 24, H - 310, accent, a, tracking=0.25)
    # the credits in one language (English), the song's own credit first, the video's last
    _text(c, "iroha(sasaki)  feat.  Kagamine Rin", "code_jp", 36, px + 28, H - 228, light, a)
    c.drawLine(px + 24, H - 246, px + pw - 24, H - 246, paint(light, a * 0.6, stroke=1.2))
    _text(c, "music iroha(sasaki) / lyrics kuma / vocal Kagamine Rin", "mono_l", 25, px + 28, H - 172,
          light, a, proportional=False)
    _text(c, "MV  RepressedAlliance  ×  Claude", "mono_l", 25, px + 28, H - 132, light, a, proportional=False)


def telop(c, line, t, x, y, w, size=46):
    """Japanese TV caption bar (the lyric appears on the TV): the bar comes up with the line and each
    character is typed onto it as it is sung."""
    from typo_fx import LEAD, char_times, clamp01
    t_in, t_out = line["start"] - 0.3, min(line["end"] + 1.2, line.get("next_start", 1e9) - 0.1)
    if t < t_in or t > t_out:
        return
    vis = min(clamp01((t - t_in) / 0.2), clamp01((t_out - t) / 0.3))
    ct = char_times(line)
    band = skia.Rect.MakeXYWH(x, y, w, size * 1.55)
    c.drawRect(band, paint((0.05, 0.06, 0.12), 0.85 * vis))
    c.drawRect(skia.Rect.MakeXYWH(x, y, 10, size * 1.55), paint((1.0, 0.75, 0.1), 0.95 * vis))
    blk = layout(line["text"], "gothic_k", size, tracking=0.02)
    ox = x + 30
    oy = y + size * 0.25
    for g in blk.glyphs:
        k = clamp01((t - ct[g.index] + LEAD) / 0.1)
        if k <= 0:
            continue
        m = glyph_matrix(g)
        m.postTranslate(ox, oy)
        pth = skia.Path(g.path)
        pth.transform(m)
        stroke = paint((0.02, 0.02, 0.05), vis * k, stroke=size * 0.16)
        stroke.setStrokeJoin(skia.Paint.kRound_Join)
        c.drawPath(pth, stroke)
        c.drawPath(pth, paint((1, 1, 1), vis * k))


class Embers:
    """A deterministic field of slow drifting motes (heat / dust in light)."""

    def __init__(self, n=260, seed=21):
        rng = np.random.default_rng(seed)
        self.x0 = rng.uniform(0, W, n)
        self.y0 = rng.uniform(0, H, n)
        self.vx = rng.normal(6, 10, n)
        self.vy = rng.uniform(-38, -10, n)
        self.r = rng.uniform(1.0, 3.2, n)
        self.ph = rng.uniform(0, 6.28, n)
        self.tw = rng.uniform(0.5, 2.0, n)

    def draw(self, c, t, amount=0.5, col=(1.0, 0.75, 0.35)):
        if amount <= 0:
            return
        x = (self.x0 + self.vx * t + 14 * np.sin(t * 0.7 + self.ph)) % (W + 40) - 20
        y = (self.y0 + self.vy * t) % (H + 40) - 20
        a = amount * (0.35 + 0.65 * (0.5 + 0.5 * np.sin(t * self.tw * 3 + self.ph)))
        n = int(len(x) * min(1.0, 0.25 + amount))
        for i in range(n):
            c.drawCircle(float(x[i]), float(y[i]), float(self.r[i]), paint(col, float(a[i])))


def stamp(c, t, u, text="臨界", x=W / 2, y=H / 2, size=260, col=(0.86, 0.12, 0.1), angle=-8.0, at=0.0):
    """A red hanko-style seal that slams onto the page at shot fraction `at`."""
    k = (u - at) / 0.08
    if k <= 0:
        return
    e = 1 - (1 - min(1.0, k)) ** 3
    sc = 1.0 + 0.6 * (1 - e)
    a = min(1.0, k * 2)
    c.save()
    c.translate(x, y)
    c.rotate(angle)
    c.scale(sc, sc)
    half = size / 2
    rect = skia.Rect.MakeXYWH(-half, -half, size, size)
    c.drawRoundRect(rect, size * 0.06, size * 0.06, paint(col, 0.92 * a))
    inner = skia.Rect.MakeXYWH(-half + 12, -half + 12, size - 24, size - 24)
    c.drawRoundRect(inner, size * 0.04, size * 0.04, paint((0.97, 0.94, 0.88), 0.9 * a, stroke=4))
    n = len(text)
    blk = layout(text, "oldmincho_k", size * 0.8 / max(1, n), vertical=True, tracking=0.02)
    for g in blk.glyphs:
        m = glyph_matrix(g)
        m.postTranslate(0, -blk.height / 2)
        p = skia.Path(g.path)
        p.transform(m)
        c.drawPath(p, paint((0.97, 0.94, 0.88), a))
    c.restore()
