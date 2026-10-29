"""Backgrounds for shots made entirely in 2D (no Blender render).

Each generator returns an RGB float32 frame (1080x1920x3, linear-ish 0..1) for
song time t and shot-relative time u (0..1).
"""
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import skia

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typo.glyphs import glyph_matrix, layout  # noqa: E402

from canvas import H, W, paint, surface, to_array  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[2]
CHAR = ROOT / "assets" / "char"


@lru_cache(maxsize=8)
def _img(path):
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im is None:
        raise FileNotFoundError(path)
    if im.shape[2] == 4:
        rgb = cv2.cvtColor(im[..., :3], cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        a = im[..., 3].astype(np.float32) / 255
        return rgb, a
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(np.float32) / 255, None


def _place(src, scale, cx, cy, angle=0.0, out_w=W, out_h=H, border=cv2.BORDER_CONSTANT):
    """Affine-place an image so that its centre lands at (cx, cy) with scale/rotation."""
    h, w = src.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    M[0, 2] += cx - w / 2
    M[1, 2] += cy - h / 2
    return cv2.warpAffine(src, M, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=border)


def black(t, u, **kw):
    return np.zeros((H, W, 3), np.float32)


def white(t, u, level=1.0, tint=(1.0, 0.98, 0.95), **kw):
    return np.ones((H, W, 3), np.float32) * np.array(tint, np.float32) * level


def ring(t, u, radius=210.0, draw=1.0, color=(0.45, 0.85, 1.0), breathe=True, grow=False, **kw):
    """A thin glowing ring: the first image of the film. grow: it draws itself over the shot."""
    s = surface()
    c = s.getCanvas()
    r = radius * (1 + (0.015 * math.sin(t * 2.2) if breathe else 0))
    sweep = 360.0 * max(0.0, min(1.0, draw if not grow else u / 0.75))
    rect = skia.Rect.MakeXYWH(W / 2 - r, H / 2 - r, 2 * r, 2 * r)
    p = paint(color, 1.0, stroke=2.2)
    p.setStrokeCap(skia.Paint.kRound_Cap)
    path = skia.Path()
    path.addArc(rect, -90, sweep)
    c.drawPath(path, p)
    c.drawPath(path, paint(color, 0.6, stroke=6, blur=8))
    lay = to_array(s)
    return lay[..., :3]


def eye(t, u, city_plate=None, zoom=(1.0, 1.18), drift=(0, -12), reflect=0.55, tear=0.0, light=1.0,
        pose="rin_eye_macro", **kw):
    """Rin's eye with the city reflected in the iris (`pose`: an alternate drawing of the same eye,
    e.g. swollen from crying, aligned to the original so the iris ellipse still applies)."""
    rgb, _ = _img(CHAR / pose / "color.png")
    info = json.loads((CHAR / "rin_eye_macro" / "iris.json").read_text())
    (icx, icy), (ew, eh), ang = info["ellipse"]
    h, w = rgb.shape[:2]
    if light != 1.0:
        # night: cool, dim, with a little warm city spill from below
        yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
        tint = np.array([0.55, 0.65, 0.95], np.float32) * light + yy * np.array([0.25, 0.12, 0.02]) * light
        base = rgb * tint
    else:
        base = rgb.copy()
    if city_plate:
        plate, _ = _img(Path(city_plate))
        # fisheye-squash the plate into the iris ellipse
        ph, pw = plate.shape[:2]
        size = int(max(ew, eh) * 1.1)
        yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
        nx, ny = (xx - size / 2) / (size / 2), (yy - size / 2) / (size / 2)
        rr = np.sqrt(nx * nx + ny * ny) + 1e-6
        k = np.arctan(rr * 1.6) / (rr * math.atan(1.6))
        sx = (nx * k * 0.5 + 0.5) * (pw - 1)
        sy = (ny * k * 0.42 + 0.5) * (ph - 1)
        refl = cv2.remap(plate, sx.astype(np.float32), sy.astype(np.float32), cv2.INTER_LINEAR)
        refl = cv2.flip(refl, 1)
        mask = np.zeros((h, w), np.float32)
        cv2.ellipse(mask, ((icx, icy), (ew * 0.92, eh * 0.92), ang), 1.0, -1)
        mask = cv2.GaussianBlur(mask, (0, 0), 6)
        canvas = np.zeros_like(base)
        x0, y0 = int(icx - size / 2), int(icy - size / 2)
        xs0, ys0 = max(0, x0), max(0, y0)
        xs1, ys1 = min(w, x0 + size), min(h, y0 + size)
        canvas[ys0:ys1, xs0:xs1] = refl[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0]
        lum = canvas.max(axis=2, keepdims=True)
        base = base + canvas * mask[..., None] * reflect * (0.4 + lum)
    if tear > 0:
        # a wet line along the lower lid
        t_mask = np.zeros((h, w), np.float32)
        cv2.ellipse(t_mask, ((icx, icy + eh * 0.36), (ew * 1.25, eh * 0.18), 0), 1.0, 3)
        t_mask = cv2.GaussianBlur(t_mask, (0, 0), 3)
        base = base + t_mask[..., None] * tear * 0.9
    z = zoom[0] + (zoom[1] - zoom[0]) * (u * u * (3 - 2 * u))
    scale = max(W / w, H / h) * z
    cx = W / 2 - (icx - w / 2) * scale + drift[0] * u
    cy = H / 2 - (icy - h / 2) * scale * 0.35 + drift[1] * u
    return _place(base, scale, cx, cy, border=cv2.BORDER_REFLECT)


def card(t, u, pose, bg=(0, 0, 0), scale=1.0, cx=W / 2, cy=H / 2, duotone=None, angle=0.0, **kw):
    """A character layer placed flat in frame, optionally duotone (for graphic sections)."""
    rgb, a = _img(CHAR / pose / "color.png")
    if duotone:
        lum = rgb @ np.array([0.3, 0.59, 0.11], np.float32)
        lo, hi = np.array(duotone[0], np.float32), np.array(duotone[1], np.float32)
        lum = np.clip((lum - 0.15) / 0.7, 0, 1)[..., None]
        rgb = lo * (1 - lum) + hi * lum
    s = scale * H / rgb.shape[0]
    fg = _place(rgb, s, cx, cy, angle)
    al = _place(a, s, cx, cy, angle)[..., None]
    out = np.ones((H, W, 3), np.float32) * np.array(bg, np.float32)
    return out * (1 - al) + fg * al


# ---------------------------------------------------------------- schematic city map (interlude)

@lru_cache(maxsize=1)
def _map_layer():
    """City footprints, highway and the facility ring drawn as a cyan schematic (cached)."""
    import citygen
    boxes = citygen._buildings(11)
    hw = citygen._highway_path(11)
    s = surface(2400, 2400)
    c = s.getCanvas()
    sc, ox, oy = 0.55, 1200, 1200 + 380 * 0.55

    def P(x, y):
        return ox + x * sc, oy - y * sc
    for (x, y, w, h, z) in boxes:
        x0, y0 = P(x - w / 2, y + h / 2)
        a = min(1.0, 0.25 + z / 260)
        c.drawRect(skia.Rect.MakeXYWH(x0, y0, w * sc, h * sc), paint((0.4, 0.8, 1.0), a * 0.55, stroke=1.0))
    path = skia.Path()
    for k, (x, y, _) in enumerate(hw):
        px, py = P(x, y)
        path.moveTo(px, py) if k == 0 else path.lineTo(px, py)
    c.drawPath(path, paint((1.0, 0.6, 0.25), 0.8, stroke=3.0))
    # shoreline
    x0, y0 = P(-1700, -232)
    x1, _ = P(1700, -232)
    c.drawLine(x0, y0, x1, y0, paint((0.4, 0.8, 1.0), 0.8, stroke=1.5))
    rx, ry = P(citygen.REACTOR_POS[0], citygen.REACTOR_POS[1])
    for rr, a in ((citygen.REACTOR_R * sc, 0.95), (citygen.REACTOR_R * sc * 0.8, 0.5)):
        c.drawCircle(rx, ry, rr, paint((0.5, 0.9, 1.0), a, stroke=2.5))
    return to_array(s), (rx, ry)


def hudmap(t, u, **kw):
    """Interlude: the city as a scanned schematic, zooming toward the reactor ring."""
    lay, (rx, ry) = _map_layer()
    k = u * u * (3 - 2 * u)
    z = 0.5 + 1.6 * k ** 2
    cx = 1200 + (rx - 1200) * k
    cy = 1150 + (ry - 1150) * k
    M = np.float32([[z, 0, W / 2 - cx * z], [0, z, H / 2 - cy * z]])
    img = cv2.warpAffine(lay, M, (W, H), flags=cv2.INTER_LINEAR)
    rgb = img[..., :3]
    # scan line sweeping down, plus faint grid
    scan_y = (t * 420) % (H + 200) - 100
    yy = np.arange(H, dtype=np.float32)[:, None]
    scan = (np.exp(-((yy - scan_y) / 18.0) ** 2) * 0.35)[..., None]
    out = rgb * (1.5 + scan * 2.0) + scan * np.array([0.1, 0.3, 0.45], np.float32)
    grid = np.zeros((H, W), np.float32)
    grid[::60, :] = 0.06
    grid[:, ::60] = 0.06
    out = out + grid[..., None] * np.array([0.3, 0.6, 0.8], np.float32)
    # pulse ring at the reactor
    pr = 40 + (t * 160) % 260
    ring = surface()
    rc = ring.getCanvas()
    sx, sy = W / 2 + (rx - cx) * z, H / 2 + (ry - cy) * z
    rc.drawCircle(sx, sy, pr, paint((0.6, 0.95, 1.0), max(0.0, 1 - pr / 300), stroke=2))
    out = out + to_array(ring)[..., :3]
    return out.astype(np.float32)


# ---------------------------------------------------------------- TV static (bridge)

# what the TVs broadcast: Rin. Source crop (x0, y0, x1, y1) of each pose, framed 4:3 like a TV shot
TV_CROPS = {
    "rin_tv_host": (-181, 0, 1206, 1040),      # the talk-show host, a presenter's medium shot: mic, wave, smile
    "rin_laugh": (0, 60, 1024, 828),
    "rin_laugh_clap": (0, 120, 1024, 888),
    "rin_face_close": (0, 40, 1024, 808),
    "rin_ears_covered": (0, 0, 1024, 768),
    "rin_profile_close": (280, 0, 1232, 714),
    "rin_eye_macro": (240, 120, 1360, 960),
    "rin_sit_knees": (60, 120, 1254, 1015),
    "rin_back_stand": (152, 0, 872, 540),
    "rin_float": (40, 160, 1000, 880),
    "rin_sleep": (0, 0, 1365, 1024),
}


@lru_cache(maxsize=24)
def rin_picture(pose="rin_face_close", w=960, h=720, flip=False):
    """Rin as a TV picture: the pose cropped 4:3 over a studio backdrop (soft key spot behind her),
    returned as luminance 0..1 (h, w) float32."""
    rgb, a = _img(CHAR / pose / "color.png")
    x0, y0, x1, y1 = TV_CROPS.get(pose, (0, 0, rgb.shape[1], rgb.shape[0]))
    # a crop may reach past the drawing (a wider shot): pad with transparent studio
    pl, pt = max(0, -x0), max(0, -y0)
    pr, pb = max(0, x1 - rgb.shape[1]), max(0, y1 - rgb.shape[0])
    if pl or pt or pr or pb:
        rgb = np.pad(rgb, ((pt, pb), (pl, pr), (0, 0)))
        a = np.pad(a, ((pt, pb), (pl, pr)))
        x0, x1, y0, y1 = x0 + pl, x1 + pl, y0 + pt, y1 + pt
    rgb, a = rgb[y0:y1, x0:x1], a[y0:y1, x0:x1]
    rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
    a = cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA)[..., None]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    spot = np.exp(-(((xx - w * 0.5) / (w * 0.42)) ** 2 + ((yy - h * 0.38) / (h * 0.5)) ** 2))
    back = (0.16 + 0.22 * spot - 0.06 * (yy / h))[..., None]
    pic = rgb * a + back * (1 - a)
    lum = pic @ np.array([0.3, 0.59, 0.11], np.float32)
    lum = np.clip((lum - 0.04) * 1.08, 0, 1).astype(np.float32)
    return np.ascontiguousarray(lum[:, ::-1] if flip else lum)


def _signal(t, k=0, base=0.62):
    """Reception strength 0..1 of channel k: drifts, and drops out for a few frames now and then."""
    s = base + 0.28 * math.sin(t * (1.1 + 0.17 * k) + k * 1.9) + 0.12 * math.sin(t * 3.7 + k)
    rng = np.random.default_rng(int(t * 24) * 131 + k)
    if rng.random() < 0.07:
        s *= 0.25
    return float(np.clip(s, 0.0, 1.0))


def static(t, u, **kw):
    """Full-screen TV: snow, scanlines and a rolling bar; through it, Rin comes and goes with the signal."""
    rng = np.random.default_rng(int(t * 24))
    small = rng.random((H // 3, W // 3), dtype=np.float32)
    n = cv2.resize(small, (W, H), interpolation=cv2.INTER_NEAREST)
    yy = np.arange(H, dtype=np.float32)[:, None]
    scan = 0.75 + 0.25 * np.sin(yy * 1.4)
    roll = ((yy / H + t * 0.3) % 1.0)
    bar = 1.0 + 0.5 * np.exp(-((roll - 0.5) / 0.06) ** 2)
    g = _signal(t, base=kw.get("signal", 0.55))
    # snow above and beside the picture keeps the host's bow and waving hand inside the frame; the bust's
    # bottom edge stays on the frame's bottom edge (inside the frame it would show as a straight cut)
    pw, ph = 1300, 975
    pic = rin_picture(kw.get("pose", "rin_tv_host"), pw, ph)
    full = np.zeros((H, W), np.float32)
    x0, y0 = (W - pw) // 2, H - ph
    full[y0:y0 + ph, x0:x0 + pw] = pic
    # weak signal: the picture tears sideways in bands
    if g < 0.6:
        for _ in range(int((0.6 - g) * 20)):
            y0 = int(rng.integers(0, H - 40))
            hh = int(rng.integers(8, 70))
            full[y0:y0 + hh] = np.roll(full[y0:y0 + hh], int(rng.normal(0, 60 * (0.7 - g))), axis=1)
    img = (n * (1 - 0.8 * g) * 0.6 + full * g * 0.95) * scan * bar
    return np.repeat(img[..., None], 3, axis=2) * np.array([0.92, 0.96, 1.0], np.float32)


# ---------------------------------------------------------------- score (allegro agitato)

STAFF_Y = 470
STAFF_GAP = 26


def score(t, u, mode="calm", **kw):
    s = surface()
    c = s.getCanvas()
    wild = mode == "wild"
    col = (0.95, 0.93, 0.9)
    for k in range(5):
        y = STAFF_Y + k * STAFF_GAP
        if wild:
            path = skia.Path()
            for x in range(0, W + 20, 20):
                yy = y + math.sin(x * 0.02 + t * 9 + k) * (6 + 30 * u) * math.sin(t * 3 + x * 0.003)
                path.moveTo(x, yy) if x == 0 else path.lineTo(x, yy)
            c.drawPath(path, paint(col, 0.85, stroke=1.6))
        else:
            c.drawLine(0, y, W, y, paint(col, 0.85, stroke=1.6))
    # notes rushing right-to-left, one per sixteenth of the song's grid (each enters on its sixteenth)
    import timeline as TL
    rng = np.random.default_rng(7)
    pitches = rng.integers(-4, 12, 400)
    speed = 520 if not wild else 980
    k0 = int((186.0 - TL.PHASE) / TL.STEP)
    for k in range(400):
        tn = TL.PHASE + (k0 + k) * TL.STEP
        x = W - (t - tn) * speed
        if -60 < x < W + 60:
            y = STAFF_Y + 4 * STAFF_GAP - pitches[k] * STAFF_GAP / 2
            c.save()
            c.translate(x, y)
            c.rotate(-20)
            c.drawOval(skia.Rect.MakeXYWH(-13, -9, 26, 18), paint(col, 0.95))
            c.restore()
            c.drawLine(x + 12, y, x + 12, y - 80, paint(col, 0.9, stroke=2))
    # tempo mark and a crescendo hairpin that keeps opening
    for txt, face, size, dx, dy in (("♩", "dela", 50, 0, 6), ("= 165", "serif_i", 54, 46, 0)):
        blk = layout(txt, face, size)
        for g in blk.glyphs:
            m = glyph_matrix(g)
            m.postTranslate(W - 380 + dx, STAFF_Y - 210 + dy)
            pth = skia.Path(g.path)
            pth.transform(m)
            c.drawPath(pth, paint(col, 0.9))
    hx0, hy = 260, STAFF_Y + 5 * STAFF_GAP + 70
    hx1 = hx0 + 300 + 1200 * u
    spread = 6 + 46 * u
    c.drawLine(hx0, hy, hx1, hy - spread, paint((1.0, 0.25, 0.2), 0.9, stroke=3))
    c.drawLine(hx0, hy, hx1, hy + spread, paint((1.0, 0.25, 0.2), 0.9, stroke=3))
    # metronome needle at the left, at the end of its swing on every beat
    ph = math.cos(math.pi * (((t - TL.BEATS[0]) / TL.BEAT) % 2))
    c.drawLine(150, 900, 150 + 140 * ph, 900 - 260, paint((1.0, 0.25, 0.2), 0.9, stroke=4))
    c.drawCircle(150, 900, 10, paint((1.0, 0.25, 0.2), 0.9))
    lay = to_array(s)
    bg = np.ones((H, W, 3), np.float32) * np.array([0.04, 0.035, 0.035], np.float32)
    return bg * (1 - lay[..., 3:4]) + lay[..., :3]


# ---------------------------------------------------------------- tinnitus

def tinnitus(t, u, pose="rin_ears_covered", close=False, **kw):
    # sized so her bow and elbows stay inside the frame
    scale, cx, cy = (1.15, W * 0.68, H * 0.64) if not close else (1.45, W * 0.6, H * 0.8)
    base = card(t, u, pose, bg=(0.02, 0.0, 0.0), scale=scale, cx=cx, cy=cy,
                duotone=((0.03, 0.0, 0.01), (1.0, 0.16, 0.12)))
    s = surface()
    c = s.getCanvas()
    amp = 8 + 120 * u ** 2
    freq = 0.02 + 0.1 * u
    path = skia.Path()
    for x in range(0, W + 4, 4):
        y = H / 2 + math.sin(x * freq + t * 40) * amp * (0.6 + 0.4 * math.sin(x * 0.003 + t))
        path.moveTo(x, y) if x == 0 else path.lineTo(x, y)
    c.drawPath(path, paint((1, 1, 1), 0.95, stroke=2.2))
    c.drawPath(path, paint((1, 0.6, 0.6), 0.6, stroke=10, blur=10))
    lay = to_array(s)
    # the ringing runs behind her: drawn over her it crossed her face and hair like a second outline
    _rgb, a = _img(CHAR / pose / "color.png")
    lay = lay * (1 - _place(a, scale * H / a.shape[0], cx, cy)[..., None])
    return base * (1 - lay[..., 3:4]) + lay[..., :3]


# ---------------------------------------------------------------- end card

def endcard(t, u, **kw):
    s = surface()
    c = s.getCanvas()
    a = min(1.0, u * 4) * (1 - max(0.0, (u - 0.8) / 0.2))
    blk = layout("炉心融解", "mincho_b", 120, vertical=True, tracking=0.12)
    for g in blk.glyphs:
        m = glyph_matrix(g)
        m.postTranslate(W / 2 + 60, H / 2 - blk.height / 2 - 70)
        p = skia.Path(g.path)
        p.transform(m)
        c.drawPath(p, paint((0.95, 0.96, 1.0), a))
    for txt, face, size, y in (("iroha(sasaki)  feat.  Kagamine Rin", "code_jp", 34, H / 2 + 300),
                               ("MELTDOWN — fan music video", "mono", 22, H / 2 + 360)):
        b2 = layout(txt, face, size, proportional=False)
        for g in b2.glyphs:
            m = glyph_matrix(g)
            m.postTranslate(W / 2 - 260 - b2.width / 2 + 120, y)
            p = skia.Path(g.path)
            p.transform(m)
            c.drawPath(p, paint((0.7, 0.85, 1.0), a * 0.85))
    c.drawCircle(W / 2 - 330, H / 2 - 10, 120, paint((0.45, 0.85, 1.0), a * 0.8, stroke=1.6))
    lay = to_array(s)
    return lay[..., :3]


# ---------------------------------------------------------------- the reactor in her chest

def chest_core(t, u, pose="rin_float", chest=(0.5, 0.36), scale=0.86, cx=W * 0.42, cy=H * 0.52, mode="calm", **kw):
    """Rin as a technical silhouette with a pulsing reactor ring where her heart is. Sized so the whole
    outline, bow to feet, stays inside the frame through the shot's push-in."""
    import timeline as TL
    rgb, a = _img(CHAR / pose / "color.png")
    edge = cv2.imread(str(CHAR / pose / "edge.png"), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
    h, w = a.shape
    s = scale * H / h
    al = _place(a, s, cx, cy)
    ed = _place(edge, s, cx, cy)
    out = np.ones((H, W, 3), np.float32) * np.array([0.05, 0.06, 0.14], np.float32)
    body = np.array([0.02, 0.025, 0.06], np.float32)
    out = out * (1 - al[..., None]) + body * al[..., None]
    out = out + (ed > 0.55).astype(np.float32)[..., None] * np.array([0.75, 0.8, 0.85], np.float32) * 0.8
    # the ring at the chest, beating with the kick drum
    px = cx + (chest[0] - 0.5) * w * s
    py = cy + (chest[1] - 0.5) * h * s
    kicks = [k for k in TL._audio.get("kicks", []) if 0 <= t - k < 0.4]
    beat = math.exp(-(t - max(kicks)) * 9) if kicks else 0.0
    srf = surface()
    c = srf.getCanvas()
    if mode == "tight":
        # the ring in her chest constricting: shrinking, thicker, red, with a pressure band closing in
        r = 70 - 38 * u + 6 * beat
        col, col2 = (1.0, 0.3, 0.2), (1.0, 0.75, 0.6)
        c.drawCircle(px, py, r, paint(col, 1.0, stroke=6 + 10 * u))
        c.drawCircle(px, py, r * 0.45, paint(col2, 0.9, stroke=2))
        for k in range(3):
            rr = r * (2.6 - 0.5 * k) - 60 * u
            c.drawCircle(px, py, max(r * 1.15, rr), paint(col, 0.25 + 0.2 * k, stroke=1.4))
    else:
        # sized with the figure (0.86 is the whole outline in frame)
        r = (46 + 10 * beat + 20 * u) * scale / 0.86
        c.drawCircle(px, py, r, paint((1.0, 0.75, 0.3), 1.0, stroke=6))
        c.drawCircle(px, py, r * 0.55, paint((1.0, 0.9, 0.6), 0.9, stroke=2))
        c.drawCircle(px, py, r * 1.6, paint((1.0, 0.6, 0.25), 0.35 + 0.5 * beat, stroke=1.2))
    # callouts
    lab = paint((0.85, 0.9, 1.0), 0.85, stroke=1.4)
    # all callouts to her right: the lyric column runs down the left of the frame
    for (dx, dy, label) in ((260, -170, "炉心 / CORE"), (300, 40, "温度 / TEMP"), (240, 190, "鼓動 / PULSE")):
        ex, ey = px + dx, py + dy
        c.drawLine(px + np.sign(dx) * r * 1.1, py, ex - np.sign(dx) * 10, ey, lab)
        c.drawLine(ex, ey, ex + np.sign(dx) * 170, ey, lab)
        blk = layout(label, "code_jp", 22, proportional=False)
        bx = ex + (10 if dx > 0 else -170)
        for g in blk.glyphs:
            m = glyph_matrix(g)
            m.postTranslate(bx, ey - 32)
            pth = skia.Path(g.path)
            pth.transform(m)
            c.drawPath(pth, paint((0.85, 0.9, 1.0), 0.9))
    lay = to_array(srf)
    out = out * (1 - lay[..., 3:4]) + lay[..., :3]
    g = cv2.GaussianBlur(lay[..., :3], (0, 0), 18)
    return out + g * (1.2 + 1.5 * beat)


# ---------------------------------------------------------------- wall of TVs (laughter of someone unseen)

# the line about laughter filling the air: the channels are mostly Rin laughing, among the host and a few
# quieter moments of the film, so the wall reads as one laugh multiplied
WALL_POSES = ["rin_laugh", "rin_laugh_clap", "rin_tv_host", "rin_laugh", "rin_laugh_clap", "rin_face_close",
              "rin_laugh", "rin_tv_host", "rin_laugh_clap", "rin_eye_macro"]


def tv_wall(t, u, cols=5, rows=4, **kw):
    """A wall of small CRTs, every channel showing Rin (a different moment of the film on each), each
    with its own reception, rolling bar and scanlines; the whole wall flares on the snares like a
    laugh track."""
    import timeline as TL
    out = np.zeros((H, W, 3), np.float32)
    gw, gh = W / cols, H / rows
    pad = 14
    rng = np.random.default_rng(int(t * 24))
    hits = [s for s in TL._audio.get("snares", []) if 0 <= t - s < 0.4]
    laugh = 0.35 * math.exp(-(t - max(hits)) * 9) if hits else 0.0
    for r in range(rows):
        for c in range(cols):
            k = r * cols + c
            x0, y0 = int(c * gw + pad), int(r * gh + pad)
            x1, y1 = int((c + 1) * gw - pad), int((r + 1) * gh - pad)
            w, h = x1 - x0, y1 - y0
            noise = rng.random((h // 3 + 1, w // 3 + 1), dtype=np.float32)
            snow = cv2.resize(noise, (w, h), interpolation=cv2.INTER_NEAREST) * 0.55
            g = _signal(t, k, base=0.7)
            pic = rin_picture(WALL_POSES[(k * 3 + r) % len(WALL_POSES)], w, h, flip=(k % 3 == 1))
            scr = snow * (1 - 0.85 * g) + pic * g
            phase = (t * (0.6 + 0.13 * k) + k * 0.37) % 1.0
            yy = np.arange(h, dtype=np.float32)[:, None] / h
            bar = 1 + 0.6 * np.exp(-((yy - phase) / 0.06) ** 2)
            scan = 0.8 + 0.2 * np.sin(np.arange(h, dtype=np.float32)[:, None] * 1.3)
            scr = scr * bar * scan * (1 + laugh)
            out[y0:y1, x0:x1] = scr[..., None] * np.array([0.9, 0.95, 1.0], np.float32)
            cv2.rectangle(out, (x0 - 3, y0 - 3), (x1 + 2, y1 + 2), (0.1, 0.1, 0.11), 3)
    z = 1.0 + 0.25 * u
    M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, z)
    return cv2.warpAffine(out, M, (W, H), flags=cv2.INTER_LINEAR)
