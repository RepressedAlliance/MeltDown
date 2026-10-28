"""Kinetic lyric styles.

A `line` is a dict from the lyric timeline: text, start, end and per-character
times `ct` (seconds). Every style draws one line at song time `t` onto a skia
canvas (or returns a layer for effects that need pixel work). Positions are px
in the 1920x1080 frame.
"""
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import skia

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typo.glyphs import glyph_matrix, layout  # noqa: E402

from canvas import H, W, paint, surface, to_array  # noqa: E402


def clamp01(x):
    return max(0.0, min(1.0, x))


def ease_out(x, p=3):
    x = clamp01(x)
    return 1 - (1 - x) ** p


def ease_in(x, p=3):
    return clamp01(x) ** p


def expo_out(x):
    x = clamp01(x)
    return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)


# A character starts coming in a little before its note (consonants lead the beat by 10-60 ms and
# the eye needs a frame or two): it is fully there as the vowel lands.
LEAD = 0.07


def char_times(line):
    ct = line.get("ct")
    if ct and len(ct) == len(line["text"]):
        return ct
    n = max(1, len(line["text"]))
    dur = max(0.3, (line["end"] - line["start"]) * 0.8)
    return [line["start"] + dur * i / n for i in range(n)]


def _draw_glyph(c, g, m, p):
    path = skia.Path(g.path)
    path.transform(m)
    c.drawPath(path, p)


def _fade_window(line, t, fade_in=0.0, hold=0.6, fade_out=0.45):
    """Overall line opacity: visible from start-fade_in until end+hold, then fades."""
    if t < line["start"] - fade_in - 0.5:
        return 0.0
    end = line.get("hold_until", line["end"] + hold)
    return 1.0 - ease_in((t - end) / fade_out, 2) if t > end else 1.0


# ---------------------------------------------------------------- 1. vertical mincho

def tate(c, line, t, x, y, size=56, face="mincho", color=(0.95, 0.96, 1.0), tracking=0.06,
         attack=0.16, drift=12.0, accent=True, index=None, hold=0.7, fade_out=0.5, shadow=0.55):
    """Vertical text revealed character by character on its note (quick focus pull + drop-in).
    A column too long for the frame is set smaller so it ends above the bottom margin."""
    blk = layout(line["text"], face, size, vertical=True, tracking=tracking)
    room = H - 48 - y
    if blk.height > room:
        size *= room / blk.height
        blk = layout(line["text"], face, size, vertical=True, tracking=tracking)
    ct = char_times(line)
    vis = _fade_window(line, t, hold=hold, fade_out=fade_out)
    if vis <= 0:
        return
    shown = 0.0
    for g in blk.glyphs:
        k = (t - ct[g.index] + LEAD) / attack
        if k <= 0:
            continue
        e = ease_out(k, 3)
        a = e * vis
        shown = max(shown, g.y + g.adv)
        m = glyph_matrix(g, dy=-(1 - e) * drift)
        m.postTranslate(x, y)
        blur = (1 - e) * 4.0
        if shadow > 0:
            c.save()
            _draw_glyph(c, g, m, paint((0, 0, 0), a * shadow, blur=6))
            c.restore()
        _draw_glyph(c, g, m, paint(color, a, blur=blur))
    if accent and shown > 0:
        top = y - 18
        c.drawLine(x + size * 0.85, top, x + size * 0.85, y + blk.height, paint(color, 0.25 * vis, stroke=1.2))
        # sung-so-far progress in Rin's yellow, following the vocal character by character
        sung = 0.0
        for g in blk.glyphs:
            k = clamp01((t - ct[g.index]) / 0.18)
            if k > 0:
                sung = max(sung, g.y - blk.glyphs[0].y + g.adv * k)
        if sung > 0:
            c.drawLine(x + size * 0.85, top, x + size * 0.85, y + sung, paint((1.0, 0.83, 0.05), 0.95 * vis, stroke=3.0))
        if index is not None:
            ib = layout(f"{index:02d}", "mono_l", 15)
            for g in ib.glyphs:
                m = glyph_matrix(g)
                m.postTranslate(x + size * 0.85 - 9, top - 26)
                _draw_glyph(c, g, m, paint(color, 0.55 * vis))


# ---------------------------------------------------------------- 2. chorus impact

def impact(c, line, t, x, y, size=170, face="gothic_k", color=(1, 1, 1), align="center",
           slam=0.2, overshoot=0.55, tracking=-0.02, vertical=False, hold=0.25, fade_out=0.3,
           outline=False, annot=None, shadow=0.75, marker=None):
    """Heavy type; each character slams in on its sung time."""
    blk = layout(line["text"], face, size, vertical=vertical, tracking=tracking)
    if not vertical:
        if align == "center":
            x = x - blk.width / 2
        elif align == "right":
            x = x - blk.width
    ct = char_times(line)
    vis = _fade_window(line, t, hold=hold, fade_out=fade_out)
    if vis <= 0:
        return
    if marker and not vertical:
        # highlighter swept behind the characters as they are sung
        x_end = None
        for g in blk.glyphs:
            k = clamp01((t - ct[g.index] + LEAD) / 0.12)
            if k > 0:
                x_end = g.x + g.adv * k
        if x_end is not None:
            pad = size * 0.12
            rect = skia.Rect.MakeLTRB(x - pad, y + size * 0.12, x + x_end + pad * 0.5, y + size * 1.02)
            c.save()
            c.skew(-0.08, 0)
            c.translate(size * 0.08 * (y + size * 0.6) * 0.0, 0)
            c.drawRect(rect, paint(marker, 0.92 * vis))
            c.restore()
    for g in blk.glyphs:
        dt = t - ct[g.index] + LEAD
        if dt <= 0:
            continue
        k = dt / slam
        e = expo_out(k)
        sc = 1 + overshoot * (1 - e)
        a = min(1.0, dt / 0.06) * vis
        m = glyph_matrix(g, scale=sc)
        m.postTranslate(x, y)
        if shadow > 0:
            _draw_glyph(c, g, m, paint((0.0, 0.0, 0.02), a * shadow, blur=size * 0.06))
        if outline:
            _draw_glyph(c, g, m, paint(color, a, stroke=size * 0.025))
        else:
            _draw_glyph(c, g, m, paint(color, a))
        # flash: white bloom on the hit
        flash = max(0.0, 1 - k) * vis
        if flash > 0:
            _draw_glyph(c, g, m, paint((1, 1, 1), flash * 0.8, blur=size * 0.12))
    if annot and not vertical:
        k = ease_out((t - line["start"]) / 0.5) * vis
        if k > 0:
            y2 = y + size * 1.08
            c.drawLine(x, y2, x + blk.width * k, y2, paint(color, 0.8 * vis, stroke=1.4))
            ab = layout(annot, "code_jp", max(14, size * 0.11), proportional=False)
            for g in ab.glyphs:
                if g.x > blk.width * k:
                    continue
                m = glyph_matrix(g)
                m.postTranslate(x, y2 + 8)
                _draw_glyph(c, g, m, paint(color, 0.85 * vis))


# ---------------------------------------------------------------- 3. terminal log

def log(c, line, t, x, y, size=24, color=(0.55, 0.85, 1.0), prefix="", cursor=True, face="code_jp",
        hold=1.2, fade_out=0.4):
    """Typed like a console line: '[02:13:44] CORE  <text>' with a block cursor."""
    full = prefix + line["text"]
    blk = layout(full, face, size, proportional=False)
    ct = char_times(line)
    vis = _fade_window(line, t, hold=hold, fade_out=fade_out)
    if vis <= 0:
        return
    n_pre = len(prefix)
    last_x = None
    for g in blk.glyphs:
        if g.index < n_pre:
            on = t >= line["start"] - 0.25
            col = (color[0] * 0.6, color[1] * 0.6, color[2] * 0.6)
        else:
            on = t >= ct[g.index - n_pre] - LEAD
            col = color
        if not on:
            continue
        m = glyph_matrix(g)
        m.postTranslate(x, y)
        _draw_glyph(c, g, m, paint(col, vis))
        last_x = x + g.x + g.adv
    if cursor and last_x is not None and (int(t * 3) % 2 == 0 or t < line["end"]):
        c.drawRect(skia.Rect.MakeXYWH(last_x + 3, y + size * 0.1, size * 0.5, size * 0.9),
                   paint(color, 0.85 * vis))


# ---------------------------------------------------------------- 4. bubbles

def bubbles(c, line, t, x, y, size=46, face="mincho", color=(0.92, 0.97, 1.0), rise=360.0, life=3.2,
            spread=150.0, seed=0):
    """Each character appears at her lips, centred on (x, y), as it is sung and is lifted off in a
    thin soap bubble, wobbles upward and pops."""
    blk = layout(line["text"], face, size, vertical=False)
    ct = char_times(line)
    rnd = np.random.default_rng(seed + len(line["text"]))
    offs = rnd.uniform(-1, 1, (len(line["text"]), 3))
    x0 = x - blk.width / 2
    for g in blk.glyphs:
        hx, hy = x0 + g.cx, y + g.cy
        age = t - ct[g.index]
        if age < 0:
            a = clamp01((age + LEAD) / 0.08)
            if a > 0:
                m = skia.Matrix()
                m.setTranslate(hx - g.cx + g.x, hy - g.cy + g.y)
                m.preScale(g.scale, g.scale)
                _draw_glyph(c, g, m, paint(color, a * 0.9))
            continue
        if age > life:
            continue
        u = age / life
        ox, ph, sp = offs[g.index]
        bx = hx + ox * spread * 0.5 * ease_out(u, 2) + math.sin(age * 2.3 + ph * 6) * 18 * min(1.0, u * 4)
        by = hy - rise * (u ** 0.8) * (0.8 + 0.4 * (sp * 0.5 + 0.5))
        r = size * (0.62 + 0.25 * u)
        a = 1 - ease_in((u - 0.82) / 0.18, 2) if u > 0.82 else 1.0
        pop = clamp01((u - 0.86) / 0.14)
        rr = r * (1 + pop * 0.6)
        c.drawCircle(bx, by, rr, paint(color, a * 0.55 * (1 - pop), stroke=1.4))
        c.drawCircle(bx - rr * 0.35, by - rr * 0.4, rr * 0.12, paint((1, 1, 1), a * 0.5 * (1 - pop)))
        m = skia.Matrix()
        m.setTranslate(bx - g.cx, by - g.cy)
        m.preTranslate(g.cx, g.cy)
        m.preScale(1 - 0.15 * pop, 1 - 0.15 * pop)
        m.preTranslate(-g.cx, -g.cy)
        m.preTranslate(g.x, g.y)
        m.preScale(g.scale, g.scale)
        _draw_glyph(c, g, m, paint(color, a * (1 - pop)))


# ---------------------------------------------------------------- 5. echoes

def echo(c, line, t, x, y, size=64, face="gothic_m", color=(1, 1, 1), copies=7, dx=0.0, dy=None,
         decay=0.72, lag=0.13, align="left", hold=0.6, fade_out=0.5):
    """Each character printed as it is sung, then delayed copies of what has been sung stacking
    downward and fading: voices saturating and echoing. Copies accumulate as the line goes on, so the
    stack only fills once the words are there to repeat."""
    blk = layout(line["text"], face, size, tracking=0.04)
    if align == "center":
        x -= blk.width / 2
    dy = size * 1.32 if dy is None else dy
    ct = char_times(line)
    vis = _fade_window(line, t, fade_in=0.4, hold=hold, fade_out=fade_out)
    if vis <= 0:
        return
    vis *= clamp01((t - line["start"] + 0.4) / 0.3)
    sung = sum(1 for v in ct if v <= t + LEAD) / max(1, len(ct))
    for k in range(copies, -1, -1):
        tt = t - k * lag
        a = vis * (decay ** k)
        if k > 0:
            a *= clamp01(sung * (copies + 1) - k)
            if a <= 0.005:
                continue
        for g in blk.glyphs:
            on = clamp01((tt - ct[g.index] + LEAD) / 0.12)
            ga = a * on
            if ga <= 0.005:
                continue
            m = glyph_matrix(g)
            m.postTranslate(x + k * dx, y + k * dy)
            _draw_glyph(c, g, m, paint(color, ga, blur=k * 0.6))


# ---------------------------------------------------------------- 6. whisper

def whisper(c, line, t, x, y, size=26, face="mincho_r", color=(0.85, 0.88, 0.95), tracking=0.9,
            vertical=False, hold=1.5, fade_out=1.2):
    """Tiny, widely spaced text that fades in slowly: for the empty midnight room."""
    blk = layout(line["text"], face, size, vertical=vertical, tracking=tracking)
    ct = char_times(line)
    vis = _fade_window(line, t, hold=hold, fade_out=fade_out)
    for g in blk.glyphs:
        k = (t - ct[g.index] + LEAD) / 0.6
        if k <= 0:
            continue
        m = glyph_matrix(g)
        m.postTranslate(x, y)
        _draw_glyph(c, g, m, paint(color, ease_out(k, 2) * vis))


# ---------------------------------------------------------------- 7. melt (pixel effect)

def melt_layer(layer, amount, t, seed=3):
    """Drag a premultiplied RGBA layer downward in uneven drips. amount 0..1."""
    if amount <= 0:
        return layer
    h, w = layer.shape[:2]
    rnd = np.random.default_rng(seed)
    cols = np.linspace(0, 1, 48)
    prof = rnd.uniform(0.2, 1.0, 48) ** 3
    prof = np.interp(np.linspace(0, 1, w), cols, prof)
    prof = cv2.GaussianBlur(prof.reshape(1, -1).astype(np.float32), (0, 0), 6).ravel()
    drop = amount * 260.0 * prof
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    wob = np.sin(xx * 0.05 + t * 1.3) * 2.0 * amount
    map_y = yy - drop[None, :] * np.clip((yy / h) * 0.6 + 0.4, 0, 1) - wob
    out = cv2.remap(layer, xx, map_y.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    # stretch streaks: keep the max along the drip
    streak = cv2.blur(out, (1, int(1 + 40 * amount)))
    return np.maximum(out, streak * 0.6)


# ---------------------------------------------------------------- 8. score line (allegro agitato)

def score_line(c, line, t, italic=None, x=200, y=330, size=64, color=(0.96, 0.94, 0.9), hold=0.6, fade_out=0.3):
    """The sung line set above the staff like a score direction; tempo marking in italic serif."""
    vis = _fade_window(line, t, hold=hold, fade_out=fade_out)
    if vis <= 0:
        return
    ct = char_times(line)
    blk = layout(line["text"], "mincho_b", size, tracking=0.08)
    for g in blk.glyphs:
        k = (t - ct[g.index] + LEAD) / 0.1
        if k <= 0:
            continue
        m = glyph_matrix(g, scale=1 + 0.25 * (1 - expo_out(k)))
        m.postTranslate(x, y)
        _draw_glyph(c, g, m, paint(color, min(1.0, k * 2) * vis))
    if italic:
        b2 = layout(italic, "serif_i", 96)
        a = ease_out((t - line["start"] + 0.2) / 0.4) * vis
        for g in b2.glyphs:
            m = glyph_matrix(g)
            m.postTranslate(x, y - 150)
            _draw_glyph(c, g, m, paint((1.0, 0.3, 0.25), a))


# ---------------------------------------------------------------- helpers for tests

def render_lines(fn_calls, w=W, h=H):
    s = surface(w, h)
    c = s.getCanvas()
    for fn, args, kw in fn_calls:
        fn(c, *args, **kw)
    return to_array(s)
