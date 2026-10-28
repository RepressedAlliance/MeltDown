"""Composite the whole film (or a time range) into a video.

python render_comp.py [--from S] [--to S] [--preview] [--out PATH] [--frames-dir DIR]

Per frame: background (Blender render or 2D generator) -> shot effects ->
lyrics + HUD overlay (with glow) -> cut transitions -> film finishing.
Frames stream straight into ffmpeg; the song is muxed in at the end.
"""
import argparse
import math
import os
import subprocess
import sys
from pathlib import Path

# numpy's OpenBLAS commits a buffer per thread (24 here) on first use; the compositor only
# needs it for tiny colour dot-products
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import cv2  # noqa: E402
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import finish  # noqa: E402
import printlook  # noqa: E402
import hud  # noqa: E402
import layout2d  # noqa: E402
import scenes2d  # noqa: E402
import storyboard  # noqa: E402
import timeline as TL  # noqa: E402
import typo_fx  # noqa: E402
from canvas import H, W, glow, surface, to_array  # noqa: E402
from fastmath import ev, max3, min3  # noqa: E402

ROOT = HERE.parents[1]
FPS = 24
import paths  # noqa: E402

SONG = paths.song()


# ---------------------------------------------------------------- backgrounds

_frame_lists = {}


def _frames(d, ext):
    if d not in _frame_lists:
        _frame_lists[d] = sorted(int(x.stem) for x in d.glob(f"[0-9]*{ext}")) if d.exists() else []
    return _frame_lists[d]


def blender_frame(shot, f, preview):
    sub = "preview" if preview else "render"
    ext = ".png" if preview else ".jpg"
    src = shot.get("frames_from")
    if src:
        # a new cut made from another shot's render: its frames from `at` seconds in, at `speed`
        d = ROOT / "work" / sub / src["id"]
        frames = _frames(d, ext)
        if not frames:
            return None
        f = frames[0] + int(round(src.get("at", 0.0) * FPS + (f - round(shot["t0"] * FPS)) * src.get("speed", 1.0)))
    else:
        d = ROOT / "work" / sub / shot["id"]
    p = d / f"{f:05d}{ext}"
    if not p.exists():
        # previews may be rendered every Nth frame, and a re-timed cut may run a few frames past
        # its render: use the nearest earlier frame, else the first
        frames = _frames(d, ext)
        if not frames:
            return None
        prev = [x for x in frames if x <= f]
        p = d / f"{(prev[-1] if prev else frames[0]):05d}{ext}"
        if not p.exists():
            return None
    im = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if im is None:
        return None
    im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    if im.shape[:2] != (H, W):
        im = cv2.resize(im, (W, H), interpolation=cv2.INTER_CUBIC)
    return im


def placeholder(shot, t):
    img = np.full((H, W, 3), 15, np.uint8)
    cv2.putText(img, f"{shot['id']} {shot['scene']} (not rendered)", (60, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.4,
                (128, 128, 128), 2, cv2.LINE_AA)
    return img.astype(np.float32) / 255


def background(shot, f, t, u, preview):
    bg = shot.get("bg", "blender")
    if bg == "blender":
        im = blender_frame(shot, f, preview)
        return im if im is not None else placeholder(shot, t)
    fn = getattr(scenes2d, bg)
    return np.ascontiguousarray(fn(t, u, **shot.get("bg_args", {})), dtype=np.float32)


# ---------------------------------------------------------------- shot effects

def _val(spec, u):
    """A number or [(u, v), ...] keys (linear)."""
    if not isinstance(spec, (list, tuple)):
        return spec
    if u <= spec[0][0]:
        return spec[0][1]
    for (u0, v0), (u1, v1) in zip(spec, spec[1:]):
        if u <= u1:
            k = (u - u0) / max(1e-6, u1 - u0)
            return v0 + (v1 - v0) * k
    return spec[-1][1]


_noise_cache = {}


def _noise_field(seed, scale):
    key = (seed, scale)
    if key not in _noise_cache:
        rng = np.random.default_rng(seed)
        small = rng.standard_normal((H // scale + 2, W // scale + 2)).astype(np.float32)
        _noise_cache[key] = cv2.resize(small, (W + 2 * scale, H + 2 * scale), interpolation=cv2.INTER_CUBIC)
    return _noise_cache[key]


_cells_cache = {}


def _lights_cells(seed, cell):
    key = (seed, cell)
    if key not in _cells_cache:
        rng = np.random.default_rng(seed)
        small = rng.random((H // cell + 1, W // cell + 1)).astype(np.float32)
        _cells_cache[key] = cv2.resize(small, (W // cell * cell + cell, H // cell * cell + cell),
                                       interpolation=cv2.INTER_NEAREST)[:H, :W]
    return _cells_cache[key]


def apply_fx(img, shot, t, u):
    for fx in shot.get("fx", []):
        kind = fx["type"]
        if kind == "zoom":  # 2D push on a plate
            z = _val(fx["z"], u)
            if abs(z - 1) > 1e-4:
                M = cv2.getRotationMatrix2D((W / 2 + fx.get("cx", 0), H / 2 + fx.get("cy", 0)),
                                            _val(fx.get("rot", 0), u), z)
                img = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        elif kind == "heat":  # heat haze
            a = _val(fx.get("amount", 4.0), u)
            n1 = _noise_field(11, 24)
            n2 = _noise_field(23, 24)
            off = int(t * 60) % 48
            dx = n1[off:off + H, 0:W] * a
            dy = n2[0:H, off:off + W] * a * 0.6
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            img = cv2.remap(img, xx + dx, yy + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        elif kind == "melt":
            a = _val(fx["amount"], u)
            if a > 0:
                rgba = np.dstack([img, np.ones((H, W, 1), np.float32)])
                img = typo_fx.melt_layer(rgba, a, t, seed=fx.get("seed", 3))[..., :3]
        elif kind == "tint":
            img = img * np.array(fx["mul"], np.float32) + np.array(fx.get("add", (0, 0, 0)), np.float32)
        elif kind == "exposure":
            img = img * (2 ** _val(fx["ev"], u))
        elif kind == "duotone":
            lum = img @ np.array([0.3, 0.59, 0.11], np.float32)
            lo, hi = np.array(fx["lo"], np.float32), np.array(fx["hi"], np.float32)
            k = np.clip((lum - fx.get("black", 0.05)) / fx.get("range", 0.8), 0, 1)[..., None]
            img = lo * (1 - k) + hi * k
        elif kind == "strobe":  # brightness kicks on beats
            amt = fx.get("amount", 0.5)
            bt = TL.beat_before(t)
            k = math.exp(-(t - bt) * fx.get("decay", 9.0))
            img = img * (1 + amt * k)
        elif kind == "glitch":
            if _val(fx.get("on", 1.0), u) > 0.5:
                img = glitch(img, t, fx.get("amount", 1.0))
        elif kind == "desat":
            s = _val(fx["sat"], u)
            lum = (img @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
            img = lum + (img - lum) * s
        elif kind == "sparks":
            img = sparks(img, t, fx, u)
        elif kind == "memories":
            img = memories(img, t, u, shot)
        elif kind == "facility_glow":
            img = radial_glow(img, fx["x"], fx["y"], 160, (0.25, 0.6, 1.0), 0.9 + 0.1 * math.sin(t * 3))
        elif kind == "breath":
            k = 0.5 - 0.5 * math.cos(t * 2 * math.pi / 4.2)
            M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, 1.0 + 0.025 * k)
            img = cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
            img = finish.vignette(img, 0.25 + 0.35 * k)
        elif kind == "particles":
            img = particles(img, t, u)
        elif kind == "rgbsplit":  # thermal stress: the red channel slips first
            px = _val(fx["px"], u)
            if px > 0.3:
                img = img.copy()
                img[..., 0] = np.roll(img[..., 0], int(round(px)), axis=1)
                img[..., 2] = np.roll(img[..., 2], -int(round(px * 0.4)), axis=1)
        elif kind == "kick":  # a small push on every kick drum
            ks = [k for k in TL._audio.get("kicks", []) if 0 <= t - k < 0.4]
            if ks:
                z = 1 + fx.get("amount", 0.014) * math.exp(-(t - max(ks)) * 12)
                M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, z)
                img = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        elif kind == "ghost":  # a reflection in glass: screen-blend a character layer
            rgb, al = scenes2d._img(scenes2d.CHAR / fx["pose"] / "color.png")
            sc = fx.get("scale", 1.0) * H / rgb.shape[0]
            cx = fx.get("x", W / 2) + fx.get("drift", 0) * (u - 0.5)
            fg = scenes2d._place(rgb, sc, cx, fx.get("y", H / 2))
            a2 = scenes2d._place(al, sc, cx, fx.get("y", H / 2))[..., None] * fx.get("opacity", 0.35)
            tint = np.array(fx.get("tint", (0.55, 0.65, 0.95)), np.float32)
            g = fg * tint * a2
            img = 1 - (1 - np.clip(img, 0, 1)) * (1 - g)
        elif kind == "tvflicker":
            rng = np.random.default_rng(int(t * 24) * 13)
            img = img * (0.75 + 0.5 * rng.random())
        elif kind == "blur":
            r = _val(fx["sigma"], u)
            if r > 0.3:
                img = cv2.GaussianBlur(img, (0, 0), r)
        elif kind == "lights_out":  # lights switch off cell by cell (about one window each), never back on
            p = _val(fx["progress"], u)
            if p > 0:
                cells = _lights_cells(fx.get("seed", 17), fx.get("cell", 6))
                on = np.clip((cells - p) / 0.02 + 0.5, 0, 1)
                x, y, r = fx.get("keep", (W / 2, H / 2, 0))
                yy, xx = np.ogrid[0:H, 0:W]
                keep = np.clip((r - np.sqrt((xx - x) ** 2 + (yy - y) ** 2)) / 25 + 0.5, 0, 1).astype(np.float32)
                img = img * np.maximum(on, keep)[..., None]
        elif kind == "darken":  # clean-up: hold down a distracting patch with a feathered mask
            x0, y0, x1, y1 = fx["rect"]
            m = np.zeros((H, W), np.float32)
            m[max(0, y0):y1, max(0, x0):x1] = 1.0
            m = cv2.GaussianBlur(m, (0, 0), fx.get("feather", 30))[..., None]
            img = img * (1 - m * fx.get("amount", 0.85))
    return img


def radial_glow(img, x, y, r, col, k=1.0):
    yy, xx = np.ogrid[0:H, 0:W]
    d2 = ((xx - x) ** 2 + (yy - y) ** 2) / (r * r)
    g = (np.exp(-d2) * 0.9 + np.exp(-d2 * 0.08) * 0.25).astype(np.float32)
    return img + g[..., None] * np.array(col, np.float32) * k


def sparks(img, t, fx, u):
    """Flint sparks thrown from the lighter wheel on every snare hit. x/y may be keyed over the shot
    (tracked from the render) so the sparks leave the hood opening as the camera pushes in."""
    import skia
    from canvas import paint
    hits = [h for h in TL._audio.get("snares", []) if 0 <= t - h < 0.6]
    if not hits:
        return img
    s = surface()
    c = s.getCanvas()
    x0, y0 = _val(fx["x"], u), _val(fx["y"], u)
    flash = 0.0
    for h in hits:
        age = t - h
        rng = np.random.default_rng(int(h * 1000))
        n = 26
        ang = rng.uniform(*fx.get("angles", (-2.6, -0.5)), n)
        spd = rng.uniform(250, 900, n)
        for a, v in zip(ang, spd):
            px = x0 + math.cos(a) * v * age
            py = y0 + math.sin(a) * v * age + 900 * age * age
            tail = 0.03
            qx = x0 + math.cos(a) * v * (age - tail)
            qy = y0 + math.sin(a) * v * (age - tail) + 900 * (age - tail) ** 2
            life = max(0.0, 1 - age / rng.uniform(0.25, 0.6))
            c.drawLine(qx, qy, px, py, paint((1.0, 0.85, 0.45), life, stroke=2.2))
        flash = max(flash, math.exp(-age * 18))
    lay = to_array(s)
    img = img * (1 - lay[..., 3:4]) + lay[..., :3] * 1.6
    img = img + glow(lay, sigma=10, strength=1.2) * np.array([1.0, 0.6, 0.25], np.float32)
    return radial_glow(img, x0, y0, 420, (1.0, 0.55, 0.2), 0.5 * flash)


_MEM_SOURCES = ["S05", "S09", "S11", "S17", "S30", "S35", "S16", "S32"]


def memories(img, t, u, shot):
    """Frames from earlier scenes drift through the core and burn away to white."""
    rng = np.random.default_rng(5)
    out = img
    for k, sid in enumerate(_MEM_SOURCES):
        d = ROOT / "work" / ("render" if (ROOT / "work" / "render" / sid).exists() else "preview") / sid
        files = sorted(list(d.glob("[0-9]*.jpg")) + list(d.glob("[0-9]*.png"))) if d.exists() else []
        if not files:
            continue
        src = cv2.imread(str(files[len(files) // 2]))
        if src is None:
            continue
        src = cv2.cvtColor(src, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        wpx = int(rng.uniform(300, 460))
        hpx = int(wpx * 9 / 16)
        src = cv2.resize(src, (wpx, hpx), interpolation=cv2.INTER_AREA)
        cx = (rng.uniform(0.1, 0.9) * W + (u - 0.5) * rng.uniform(-300, 300))
        cy = (rng.uniform(0.15, 0.85) * H - u * rng.uniform(80, 220))
        ang = rng.uniform(-12, 12) + u * rng.uniform(-8, 8)
        M = cv2.getRotationMatrix2D((wpx / 2, hpx / 2), ang, 1.0)
        M[0, 2] += cx - wpx / 2
        M[1, 2] += cy - hpx / 2
        panel = cv2.warpAffine(src, M, (W, H))
        mask = cv2.warpAffine(np.ones((hpx, wpx), np.float32), M, (W, H))
        burn_t = 0.25 + 0.08 * k
        burn = np.clip((u - burn_t) / 0.35, 0, 1)
        nz = _noise_field(31 + k, 16)[:H, :W] * 0.25 + 0.5
        alive = (nz > burn).astype(np.float32) * mask
        edge = ((nz > burn - 0.06) & (nz <= burn)).astype(np.float32) * mask
        out = out * (1 - alive[..., None] * 0.92) + panel * alive[..., None] * 0.92 + edge[..., None] * 2.5
    return out


def particles(img, t, u):
    """Rin coming apart into light: motes rising from the card toward the plasma."""
    import skia
    from canvas import paint
    s = surface()
    c = s.getCanvas()
    rng = np.random.default_rng(9)
    n = 420
    born = rng.uniform(0.2, 1.0, n)
    x0 = rng.normal(980, 120, n)
    y0 = rng.normal(600, 170, n)
    vx = rng.uniform(-260, -60, n)
    vy = rng.uniform(-220, -40, n)
    for i in range(n):
        age = u - born[i]
        if age < 0:
            continue
        a = max(0.0, 1 - age * 1.6)
        x = x0[i] + vx[i] * age * 4 + math.sin(t * 2 + i) * 6
        y = y0[i] + vy[i] * age * 4
        c.drawCircle(x, y, 1.6 + 1.2 * (i % 3), paint((0.75, 0.92, 1.0), a))
    lay = to_array(s)
    return img + lay[..., :3] * 1.4 + glow(lay, sigma=8, strength=1.5) * np.array([0.5, 0.8, 1.0], np.float32)


def glitch(img, t, amount=1.0):
    rng = np.random.default_rng(int(t * 24) * 31)
    out = img.copy()
    for _ in range(int(6 * amount)):
        y = rng.integers(0, H - 40)
        h = rng.integers(6, 60)
        dx = int(rng.integers(-60, 60) * amount)
        out[y:y + h] = np.roll(out[y:y + h], dx, axis=1)
    shift = int(6 * amount)
    out[..., 0] = np.roll(out[..., 0], shift, axis=1)
    out[..., 2] = np.roll(out[..., 2], -shift, axis=1)
    return out


# ---------------------------------------------------------------- lyrics

def _same_slot(a, b):
    if not a or not b or a.get("style") != b.get("style"):
        return False
    return abs(a.get("x", 0) - b.get("x", 0)) < 60 and abs(a.get("y", 0) - b.get("y", 0)) < 60


_BREAKS = None


def _section_breaks():
    """Cuts that open a new section out of black (the bridge, the void): no line lingers past them."""
    global _BREAKS
    if _BREAKS is None:
        _BREAKS = [s["t0"] for s in storyboard.resolved() if s.get("in") == "black" and s["t0"] > 0]
    return _BREAKS


def _yield_to_next(ln):
    """Finish this line (with a quick fade) before a later one would collide with it: the next line
    taking the same slot, any line after heavy impact type, or a vertical line set to the right of a
    vertical one still on screen (columns read right to left, so the old column would read as later)."""
    i = ln["i"]
    st = storyboard.LYRIC_STYLES.get(i)
    if not st:
        return ln, None
    starts = []
    for j in (i + 1, i + 2):
        nst = storyboard.LYRIC_STYLES.get(j)
        if j >= len(TL.LINES) or not nst:
            continue
        clash = j == i + 1 and (_same_slot(st, nst) or st.get("style") == "impact")
        clash |= st.get("style") == "tate" and nst.get("style") == "tate" and nst.get("x", 0) > st.get("x", 0) + 10
        if clash:
            starts.append(TL.LINES[j]["start"])
    last = max(ln["ct"])
    for cut in _section_breaks():
        if ln["start"] < cut < ln["end"] + st.get("hold", 0.7) + 0.5:
            # gone by the cut; if its last word is only sung after it, just long enough to read
            starts.append(cut - 0.02 if last <= cut - 0.15 else last + 0.44)
    if starts:
        return dict(ln, hold_until=min(ln["end"] + 0.6, min(starts) - 0.14)), 0.12
    return ln, None


_STYLE_COLOR = {"tate": (0.95, 0.96, 1.0), "impact": (1, 1, 1), "echo": (1, 1, 1), "bubbles": (0.92, 0.97, 1.0),
                "whisper": (0.85, 0.88, 0.95), "score_line": (0.96, 0.94, 0.9), "log": (0.55, 0.85, 1.0)}


def _adaptive(st):
    """Light type follows the picture behind it; type designed dark (on a marker) keeps its colour."""
    col = st.get("color", _STYLE_COLOR.get(st["style"]))
    return col is not None and 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2] > 0.5


def lyrics_overlay(t, shot):
    """Two premultiplied layers: light lyric type (adapted to the picture later) and everything that
    keeps its colour (dark-on-marker lines, telop, HUD, titles, stamps, print marks)."""
    s = surface()
    c = s.getCanvas()
    sa = surface()
    ca = sa.getCanvas()
    melt_layers = []
    heat_layers = []
    for ln in TL.LINES:
        st = storyboard.LYRIC_STYLES.get(ln["i"])
        if not st or t < ln["start"] - 1.0 or t > ln["end"] + st.get("tail", 4.0):
            continue
        if "shots" in st and shot["id"] not in st["shots"]:
            continue
        style = st["style"]
        kw = {k: v for k, v in st.items() if k not in ("style", "tail", "melt", "glow", "glow_col", "heat", "shots")}
        ln, quick = _yield_to_next(ln)
        if quick is not None and style in ("tate", "impact", "whisper", "echo", "score_line"):
            kw["fade_out"] = quick
        if st.get("heat"):
            s3 = surface()
            getattr(typo_fx, style)(s3.getCanvas(), ln, t, **kw)
            heat_layers.append(to_array(s3))
            continue
        if style == "telop":
            # a caption leaves before the next line is sung
            nxt = TL.LINES[ln["i"] + 1]["start"] if ln["i"] + 1 < len(TL.LINES) else 1e9
            layout2d.telop(c, dict(ln, next_start=nxt), t, **kw)
            continue
        if st.get("melt"):
            s2 = surface()
            getattr(typo_fx, style)(s2.getCanvas(), ln, t, **kw)
            lay = to_array(s2)
            amt = max(0.0, (t - ln["end"] + 0.2) / 1.6) * st["melt"]
            melt_layers.append(typo_fx.melt_layer(lay, min(1.0, amt), t, seed=ln["i"]))
            continue
        getattr(typo_fx, style)(ca if _adaptive(st) else c, ln, t, **kw)
    hud_cfg = shot.get("hud")
    if hud_cfg:
        hud.draw(c, t, **hud_cfg)
    u = (t - shot["t0"]) / max(1e-6, shot["t1"] - shot["t0"])
    if shot.get("title"):
        layout2d.title_card(c, t, u, **shot["title"])
    for st_spec in shot.get("stamps", []):
        layout2d.stamp(c, t, u, **st_spec)
    if shot.get("marks"):
        import printlook
        cfg = printlook.INKSETS.get(shot.get("ink", "night"), {})
        inks = [cfg.get("key", (0.1, 0.1, 0.2))] + [sp[0] for sp in cfg.get("spots", [])]
        layout2d.print_marks(c, t, sheet=f"{shot['id']}   {hud.fmt_clock(hud.clock_at(t))}   SHEET {shot['id'][1:]}",
                             inks=inks)
    lay = to_array(s)
    lay_a = to_array(sa)
    for ml in melt_layers:
        lay_a = lay_a * (1 - ml[..., 3:4]) + ml
    for hl in heat_layers:
        n1 = _noise_field(41, 16)
        off = int(t * 90) % 32
        dy = n1[off:off + H, 0:W] * 3.5
        dx = n1[0:H, off:off + W] * 1.5
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        hl = cv2.remap(hl, xx + dx, yy + dy, cv2.INTER_LINEAR)
        lay_a = lay_a * (1 - hl[..., 3:4]) + hl
    return lay_a, lay


_LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def bright_behind(bg, lo=0.49, hi=0.57):
    """0..1 where the picture is bright, smoothed over a region larger than a glyph. The ramp is
    narrow on purpose: half-flipped type is mid-tone on a mid-tone halo and cannot be read."""
    small = cv2.resize(np.clip(bg, 0, 1), (W // 4, H // 4), interpolation=cv2.INTER_AREA) @ _LUMA
    small = cv2.GaussianBlur(small, (0, 0), 9)
    k = np.clip((small - lo) / (hi - lo), 0, 1)
    k = k * k * (3 - 2 * k)
    return cv2.resize(k, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]


def adapt_type(lay, k, light, dark, mode="flip"):
    """Light type over bright picture: 'flip' prints it in the dark ink (its dark halo turns to paper);
    'plate' keeps it light on a soft dark-ink cloud. Saturated accents keep their colour.
    Returns (premultiplied rgb, alpha, glow source)."""
    rgb, a = lay[..., :3], lay[..., 3:4]
    lt, dk = np.array(light, np.float32), np.array(dark, np.float32)
    if mode == "plate":
        cloud = cv2.GaussianBlur(cv2.dilate(lay[..., 3], np.ones((9, 9), np.uint8)), (0, 0), 9)[..., None]
        p = ev("where(c * k * q > 1, 1, c * k * q)", c=cloud, k=k, q=0.9)
        out = ev("(1 - a) * p * dk + rgb * lt", a=a, p=p, dk=dk, rgb=rgb, lt=lt)
        alpha = ev("a + p * (1 - a)", a=a, p=p)
        return out, alpha, rgb * lt
    lum = ev("wr * r + wg * g + wb * b", r=rgb[..., 0], g=rgb[..., 1], b=rgb[..., 2], wr=0.299, wg=0.587,
             wb=0.114)[..., None]
    mx, mn = max3(rgb)[..., None], min3(rgb)[..., None]
    lc = ev("where(a > e, where(l > a, 1, l / where(a > e, a, e)), 0)", l=lum, a=a, e=1e-4)
    w = ev("k * (1 - where(mx > e, (mx - mn) / where(mx > e, mx, e), 0))", k=k, mx=mx, mn=mn, e=1e-4)
    out = ev("w * (dk * lc + lt * (1 - lc)) * a + (1 - w) * rgb * lt", w=w, dk=dk, lt=lt, lc=lc, a=a, rgb=rgb)
    return out, a, ev("o * (1 - k)", o=out, k=k)


# ---------------------------------------------------------------- transitions

_EMBERS = layout2d.Embers()
EMBER_BY_INK = {"night": (0.22, (1.0, 0.7, 0.35)), "core": (0.6, (0.6, 0.88, 1.0)), "dusk": (0.45, (1.0, 0.6, 0.3)),
                "dream": (0.18, (1.0, 1.0, 1.0)), "white": (0.5, (1.0, 1.0, 1.0)), "void": (0.12, (0.6, 0.7, 1.0)),
                "dawn": (0.4, (1.0, 0.85, 0.5))}


def add_embers(img, t, shot):
    amt, col = EMBER_BY_INK.get(shot.get("ink", "night"), (0.0, (1, 1, 1)))
    amt = shot.get("embers", amt)
    if amt <= 0:
        return img
    f = min(len(TL.env("rms")) - 1, int(t * FPS))
    amt = amt * (0.6 + 0.6 * TL.env("rms")[f])
    s = surface()
    _EMBERS.draw(s.getCanvas(), t, amt, col)
    lay = to_array(s)
    return img + lay[..., :3] + glow(lay, sigma=6, strength=0.8) * np.array(col, np.float32)


_iris_cache = {}


def iris_blend(img, t, shot, prev_shot, preview):
    """The ring motif as a cut: the new shot opens inside a growing circle."""
    d = shot.get("in_dur", 0.45)
    dt = t - shot["t0"]
    if prev_shot is None or dt >= d:
        return img
    key = prev_shot["id"]
    if key not in _iris_cache:
        f_last = int(round(prev_shot["t1"] * FPS)) - 1
        _iris_cache[key] = render_frame([prev_shot], f_last, preview, raw=True)
    old = _iris_cache[key]
    k = dt / d
    k = 1 - (1 - k) ** 3
    r = k * math.hypot(W, H) / 2
    yy, xx = np.ogrid[0:H, 0:W]
    dist = np.sqrt((xx - W / 2) ** 2 + (yy - H / 2) ** 2)
    m = np.clip((r - dist) / 3.0 + 0.5, 0, 1).astype(np.float32)[..., None]
    ring = np.clip(1 - np.abs(dist - r) / 2.5, 0, 1).astype(np.float32)[..., None]
    return old * (1 - m) + img * m + ring * np.array([0.6, 0.9, 1.0], np.float32)


def _zoom_blur(img, spread, steps=6):
    """Copies scaled about the centre from 1 to 1+spread, averaged: a dolly blur through the frame."""
    if spread < 0.004:
        return img
    acc = np.zeros_like(img)
    for k in range(steps):
        m = cv2.getRotationMatrix2D((W / 2, H / 2), 0, 1 + spread * (k + 1) / steps)
        acc += cv2.warpAffine(img, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return acc / steps


def _scaled(img, s):
    if abs(s - 1) < 1e-3:
        return img
    m = cv2.getRotationMatrix2D((W / 2, H / 2), 0, s)
    return cv2.warpAffine(img, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def cross_blend(img, f, t, shot, prev_shot, preview):
    """Soft cuts that keep both shots moving: the outgoing shot is rendered at the same instant (its
    Blender render runs a `tail` past the cut) and mixed in over the first in_dur seconds.
      dissolve  a plain cross-dissolve (in_bloom > 0 lifts the light at its middle, a light leak)
      zoom      a dolly through the cut: the old shot pushes in and blurs away while the new one
                arrives from a slight push, both radially blurred around the midpoint"""
    d = shot.get("in_dur", 0.5)
    dt = t - shot["t0"]
    if prev_shot is None or dt >= d:
        return img
    old = render_frame([prev_shot], f, preview, raw=True)
    k = dt / d
    w = k * k * (3 - 2 * k)
    if shot["in"] == "zoom":
        old = _zoom_blur(_scaled(old, 1 + 0.3 * k), 0.09 * w)
        img = _zoom_blur(_scaled(img, 1 + 0.18 * (1 - k)), 0.09 * (1 - w))
    out = old * (1 - w) + img * w
    b = shot.get("in_bloom", 0.0)
    if b:
        out = out + b * math.sin(math.pi * k) * cv2.GaussianBlur(out, (0, 0), 25)
    return out


def transition(img, t, shot, prev_shot):
    tin = shot.get("in")
    dt = t - shot["t0"]
    if tin == "flash":
        k = math.exp(-dt * 10)
        img = img + k * 1.2
    elif tin == "white":
        d = shot.get("in_dur", 0.5)
        if dt < d:
            img = img * (dt / d) + (1 - dt / d)
    elif tin == "black":
        d = shot.get("in_dur", 0.5)
        if dt < d:
            img = img * (dt / d) ** 1.5
    elif tin == "glitch" and dt < 0.25:
        img = glitch(img, t, 2.0)
    tout = shot.get("out")
    left = shot["t1"] - t
    if tout == "white":
        d = shot.get("out_dur", 0.5)
        if left < d:
            k = 1 - left / d
            img = img * (1 - k) + k
    elif tout == "black":
        d = shot.get("out_dur", 0.5)
        if left < d:
            img = img * (left / d) ** 1.5
    return img


# ---------------------------------------------------------------- main loop

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="t_from", type=float, default=0.0)
    ap.add_argument("--to", dest="t_to", type=float, default=None)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--stills", default=None, help="comma list of seconds: write PNG stills instead of video")
    ap.add_argument("--noaudio", action="store_true", help="video-only segment (for parallel rendering)")
    args = ap.parse_args()
    shots = storyboard.resolved()
    t_end = args.t_to if args.t_to is not None else TL.DURATION
    if args.stills:
        outd = ROOT / "work" / "comp_stills"
        outd.mkdir(parents=True, exist_ok=True)
        for ts in args.stills.split(","):
            t = float(ts)
            img = render_frame(shots, int(round(t * FPS)), args.preview)
            cv2.imwrite(str(outd / f"t{t:07.2f}.png"), cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
            print("still", t)
        return
    out = Path(args.out or (ROOT / "out" / ("preview.mp4" if args.preview else "roshin_yuukai_mv.mp4")))
    out.parent.mkdir(parents=True, exist_ok=True)
    f0, f1 = int(round(args.t_from * FPS)), int(round(t_end * FPS))
    ow, oh = (960, 540) if args.preview else (W, H)
    fps_out = FPS / args.step
    # x264 sizes its frame buffers by thread count (auto = 36 here, ~1 GB at 1080p): cap it so
    # segment workers fit in memory (MV_X264_THREADS=1 MV_X264_LOOKAHEAD=10 when RAM is tight; the
    # compositor runs at ~1 fps, so even one encoder thread keeps up); quality is unchanged
    xt, xl = os.environ.get("MV_X264_THREADS", "4"), os.environ.get("MV_X264_LOOKAHEAD", "20")
    vcodec = (["-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-threads", xt] if args.preview else
              ["-c:v", "libx264", "-preset", "slow", "-crf", "14", "-tune", "film", "-threads", xt,
               "-x264-params", f"aq-mode=3:rc-lookahead={xl}"])
    if args.noaudio:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ow}x{oh}",
               "-r", f"{fps_out}", "-i", "-", *vcodec, "-pix_fmt", "yuv420p", str(out)]
    else:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ow}x{oh}",
               "-r", f"{fps_out}", "-i", "-", "-ss", f"{args.t_from}", "-t", f"{(f1 - f0) / FPS}", "-i", str(SONG),
               "-map", "0:v", "-map", "1:a", *vcodec, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k",
               "-movflags", "+faststart", "-shortest", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(f0, f1, args.step):
        img = render_frame(shots, f, args.preview)
        if (ow, oh) != (W, H):
            img = cv2.resize(img, (ow, oh), interpolation=cv2.INTER_AREA)
        proc.stdin.write((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
        if f % 240 == 0:
            print(f"frame {f} / {f1}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("wrote", out)


def burn_amount(shot, t, u):
    """How far the light burns through the printed page (0 = print, 1 = pure light)."""
    spec = shot.get("burn")
    if spec is None:
        return 0.0
    if isinstance(spec, (int, float)):
        base = float(spec)
    elif isinstance(spec, dict):
        base = _val(spec.get("keys", spec.get("base", 0.3)), u) if "keys" in spec else spec.get("base", 0.3)
        f = min(len(TL.env("rms")) - 1, int(t * FPS))
        base += spec.get("energy", 0.0) * TL.env("rms")[f]
        hits = [h for h in TL._audio.get("snares", []) if 0 <= t - h < 0.5]
        if hits and spec.get("hits", 0) > 0:
            base += spec["hits"] * math.exp(-(t - max(hits)) * 7.0)
    else:
        base = _val(spec, u)
    return float(min(1.0, max(0.0, base)))


SECTION_GLOW = {
    "A1": (0.3, (0.5, 0.62, 0.95)), "A2": (0.3, (0.5, 0.62, 0.95)), "B1": (0.0, (0, 0, 0)),
    "C1": (0.8, (0.35, 0.68, 1.0)), "A3": (0.45, (1.0, 0.5, 0.28)), "A4": (0.45, (1.0, 0.45, 0.25)),
    "B2": (0.4, (0.55, 0.72, 1.0)), "C2": (0.5, (0.85, 0.92, 1.0)), "BR1": (0.25, (0.9, 0.9, 0.9)),
    "BR2": (0.5, (1.0, 0.3, 0.25)), "Q": (0.45, (0.45, 0.6, 1.0)), "C3": (0.75, (1.0, 0.78, 0.45)),
}


def current_section(t):
    sec = None
    for ln in TL.LINES:
        if ln["start"] - 1.0 <= t:
            sec = ln["section"]
        else:
            break
    return sec


def render_frame(shots, f, preview, raw=False):
    t = f / FPS
    idx = next((i for i, s in enumerate(shots) if s["t0"] <= t < s["t1"]), len(shots) - 1)
    shot = shots[idx]
    prev_shot = shots[idx - 1] if idx > 0 else None
    u = (t - shot["t0"]) / max(1e-6, shot["t1"] - shot["t0"])
    img = background(shot, f, t, u, preview)
    img = apply_fx(img, shot, t, u).astype(np.float32, copy=False)
    img = add_embers(img, t, shot)
    inks = shot.get("ink", "night")
    ink_cfg = printlook.INKSETS.get(inks) if inks != "none" else None
    if ink_cfg is not None:
        light = img
        mis = 1.4
        if shot.get("mis_hits"):
            hs = [h for h in TL._audio.get("snares", []) if 0 <= t - h < 0.5]
            if hs:
                mis += shot["mis_hits"] * math.exp(-(t - max(hs)) * 9)
        # print_ev darkens only what goes to the press, so bright renders keep ink (and structure)
        # in their highlights while the burn still reveals the full light
        pe = _val(shot.get("print_ev", 0.0), u)
        src = img * np.float32(2 ** pe) if pe else img
        if shot.get("pre_blur"):
            # merge pinpoint lights into tones the screen can carry, instead of dot noise
            src = cv2.GaussianBlur(src, (0, 0), shot["pre_blur"])
        pr = printlook.riso(src, t, inks=inks, mis=mis)
        pr = printlook.apply_paper(pr, t, amount=0.8)
        b = burn_amount(shot, t, u)
        if b > 0:
            pr = printlook.burn(pr, finish.bloom(light * 1.1, strength=0.6, threshold=0.7), t, b,
                                scorch=shot.get("scorch", (1.0, 0.55, 0.18)))
        img = pr
    lay_a, lay = lyrics_overlay(t, shot)
    lg = _val(shot.get("lyric_glitch", 0.0), u)
    if lg > 0.01:
        # type slips in horizontal bands, re-drawn every frame
        rng = np.random.default_rng(int(t * 24) * 17)
        lay, lay_a = lay.copy(), lay_a.copy()
        for _ in range(int(4 + 10 * lg)):
            y0 = int(rng.integers(0, H - 8))
            h = int(rng.integers(4, 40))
            dx = int(rng.normal(0, 30 * lg))
            for layer in (lay, lay_a):
                layer[y0:y0 + h] = np.roll(layer[y0:y0 + h], dx, axis=1)
    if ink_cfg is not None:
        # type is printed in the ink that reads on this paper: paper tone on dark prints, key ink on dark paper
        dark_paper = ink_cfg.get("invert") or ink_cfg.get("solid")
        tint = np.array(ink_cfg.get("text", ink_cfg["key"] if dark_paper else ink_cfg["paper"]), np.float32) * 1.03
        dark = ink_cfg["paper"] if dark_paper else ink_cfg["key"]
        lay = lay.copy()
        lay[..., :3] *= tint
    else:
        tint, dark = np.ones(3, np.float32), (0.06, 0.06, 0.08)
    a_rgb, a_alpha, a_glow = adapt_type(lay_a, bright_behind(img), tint, dark, shot.get("type_mode", "flip"))
    sec = current_section(t)
    g_str, g_col = SECTION_GLOW.get(sec, (0.4, (0.55, 0.75, 1.0)))
    gcol = np.array(shot.get("glow_col", g_col), np.float32)
    img = img * (1 - lay[..., 3:4]) + lay[..., :3]
    img = ev("i * (1 - a) + c", i=img, a=a_alpha, c=a_rgb)
    gs, gsig = shot.get("glow", g_str), shot.get("glow_sigma", 16)
    img = img + glow(ev("l + g", l=lay[..., :3], g=a_glow), sigma=gsig, strength=gs) * gcol
    if raw:
        return img
    if shot.get("in") == "iris":
        img = iris_blend(img, t, shot, prev_shot, preview)
    elif shot.get("in") in ("dissolve", "zoom"):
        img = cross_blend(img, f, t, shot, prev_shot, preview)
    img = transition(img, t, shot, prev_shot)
    cfg = dict(shot.get("finish", {}))
    if ink_cfg is not None:
        # the print already carries texture and misregistration: keep the film layer light
        cfg.update(grain={"amount": 0.012}, chroma=0.5, halation={"strength": 0.0})
    return finish.finish(img, t, cfg)


if __name__ == "__main__":
    main()
