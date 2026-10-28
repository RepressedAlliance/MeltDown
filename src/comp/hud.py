"""Reactor-console HUD: core temperature, story clock, frame marks, alarms.

The temperature is the film's quiet spine: it starts at 36.5 °C, climbs to the
"100 million degrees" of fusion plasma, overflows, and settles back to 36.5 °C
in the last shot, when Rin is finally asleep.
"""
import math
import sys
from pathlib import Path

import numpy as np
import skia

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typo.glyphs import glyph_matrix, layout  # noqa: E402

from canvas import paint  # noqa: E402

CYAN = (0.55, 0.88, 1.0)
RED = (1.0, 0.18, 0.12)
AMBER = (1.0, 0.72, 0.25)

# (song seconds, value °C); interpolated in log space. None = no signal.
TEMP_KEYS = [
    (0.0, 36.5), (7.4, 36.5), (22.0, 36.9), (52.0, 37.9), (62.0, 39.6), (66.2, 42.0),
    (68.0, 1.5e7), (93.0, 4.0e7), (101.0, 4.2e7),
    (102.5, 5.5e3), (126.0, 9.0e3), (138.0, 1.2e4),
    (140.0, 1.0e8), (164.0, 1.1e8), (199.0, 1.6e8), (230.0, 3.0e8),
    (231.0, None), (259.0, None),
    (259.8, 2.0e8), (271.2, 9.9e9),
    (273.1, 1.0e8), (300.0, 6.0e3), (309.6, 300.0), (315.5, 36.5), (330.0, 36.5),
]

STATUS = [
    (0.0, "正常 NORMAL"), (52.0, "上昇 RISING"), (62.0, "警告 WARNING"), (66.2, "臨界 CRITICAL"),
    (68.0, "点火 IGNITION"), (102.5, "減衰 DECAY"), (140.0, "臨界 CRITICAL"), (164.7, "不安定 UNSTABLE"),
    (231.0, "信号なし NO SIGNAL"), (259.8, "暴走 RUNAWAY"), (271.2, "溢出 OVERFLOW"),
    (273.1, "冷却 COOLING"), (315.5, "正常 NORMAL"),
]

# story clock: (song seconds, story seconds since midnight)
CLOCK_KEYS = [(0.0, 2 * 3600), (66.0, 2 * 3600 + 3 * 60 + 12), (102.5, 18 * 3600 + 24 * 60),
              (139.0, 19 * 3600 + 3 * 60), (164.7, 3 * 3600 + 33 * 60), (231.0, 4 * 3600 + 44 * 60),
              (259.8, 5 * 3600 + 30 * 60), (318.0, 5 * 3600 + 49 * 60), (330.0, 6 * 3600)]


def temp_at(t):
    for (t0, v0), (t1, v1) in zip(TEMP_KEYS, TEMP_KEYS[1:]):
        if t0 <= t < t1:
            if v0 is None or v1 is None:
                return v0 if v1 is None else None
            u = (t - t0) / (t1 - t0)
            return math.exp(math.log(v0) * (1 - u) + math.log(v1) * u)
    return TEMP_KEYS[-1][1]


def status_at(t):
    s = STATUS[0][1]
    for t0, name in STATUS:
        if t >= t0:
            s = name
    return s


def clock_at(t):
    for (t0, c0), (t1, c1) in zip(CLOCK_KEYS, CLOCK_KEYS[1:]):
        if t0 <= t < t1:
            # the story clock runs at real speed inside a section; jumps between sections
            return c0 + (t - t0)
    return CLOCK_KEYS[-1][1]


def fmt_temp(v, t):
    if v is None:
        return "--.-"
    if v >= 1e9 and int(t * 12) % 2 == 0:
        return "#########"
    if v < 100:
        return f"{v:4.1f}"
    return f"{int(v):,}"


def fmt_clock(sec):
    sec = int(sec) % 86400
    return f"{sec // 3600:02d}:{(sec // 60) % 60:02d}:{sec % 60:02d}"


def _text(c, s, face, size, x, y, col, a=1.0, tracking=0.0, proportional=False):
    blk = layout(s, face, size, tracking=tracking, proportional=proportional)
    for g in blk.glyphs:
        m = glyph_matrix(g)
        m.postTranslate(x, y)
        path = skia.Path(g.path)
        path.transform(m)
        # dark halo so the readout survives on light paper as well as on dark ink
        c.drawPath(path, paint((0.02, 0.03, 0.08), a * 0.7, stroke=max(2.0, size * 0.1), blur=size * 0.02))
        c.drawPath(path, paint(col, a))
    return blk.width


def brackets(c, x0, y0, x1, y1, col=CYAN, a=0.6, L=26, w=1.5):
    p = paint(col, a, stroke=w)
    for (x, y, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        c.drawLine(x, y, x + dx * L, y, p)
        c.drawLine(x, y, x, y + dy * L, p)


def draw(c, t, level=1, col=None, alarm=False, alpha=1.0, corner="bl"):
    """level 1: compact readout in a corner; level 2: full console frame."""
    if level <= 0 or alpha <= 0:
        return
    col = col or (RED if alarm and int(t * 4) % 2 == 0 else CYAN)
    v = temp_at(t)
    W, H = 1920, 1080
    if level >= 2:
        brackets(c, 60, 60, W - 60, H - 60, col, 0.5 * alpha)
        _text(c, "REACTOR 01 / 炉心監視系", "code_jp", 18, 92, 78, col, 0.7 * alpha)
        _text(c, fmt_clock(clock_at(t)), "mono", 18, W - 92 - 100, 78, col, 0.7 * alpha)
        # ticks along the bottom edge, moving with time
        p = paint(col, 0.35 * alpha, stroke=1)
        off = (t * 40) % 24
        for k in range(70):
            x = 120 + k * 24 - off
            c.drawLine(x, H - 92, x, H - 92 + (10 if k % 5 == 0 else 5), p)
    x0, y0 = (92, H - 200) if corner == "bl" else (W - 520, H - 200)
    _text(c, "炉心温度  CORE TEMP", "code_jp", 17, x0, y0, col, 0.75 * alpha)
    _text(c, fmt_temp(v, t), "shoulders", 64, x0, y0 + 26, col, 0.95 * alpha)
    _text(c, "℃", "code_jp", 28, x0 + 16 + 34 * len(fmt_temp(v, t)), y0 + 54, col, 0.8 * alpha)
    _text(c, status_at(t), "code_jp", 17, x0, y0 + 108, col, 0.75 * alpha)
    # sparkline of the last 20 s (log scale)
    path = skia.Path()
    for k in range(80):
        tt = t - 20 + k * 0.25
        vv = temp_at(max(0, tt))
        yv = 0 if vv is None else min(1.0, math.log10(max(vv, 1)) / 10.0)
        px, py = x0 + 260 + k * 2.6, y0 + 96 - yv * 70
        path.moveTo(px, py) if k == 0 else path.lineTo(px, py)
    c.drawPath(path, paint(col, 0.6 * alpha, stroke=1.3))
    if alarm:
        a = (0.5 + 0.5 * math.sin(t * 12)) * alpha
        c.drawRect(skia.Rect.MakeXYWH(0, 140, W, 46), paint(RED, 0.18 * a))
        msg = "警告  WARNING  炉心温度上昇  CORE TEMPERATURE RISING  " * 3
        off = (t * 220) % 900
        _text(c, msg, "code_jp", 22, -off, 150, RED, 0.85 * a)
