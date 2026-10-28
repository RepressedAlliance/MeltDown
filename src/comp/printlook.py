"""The film's unifying "printed page" look, and the chorus burn-through.

Every frame is treated like a small-run print on warm paper: a key ink laid
down as an AM halftone in the shadows, one or two spot inks (Rin's yellow is
always one of them), slight misregistration between inks and a paper grain that
"boils" every few frames. In the choruses the reactor light burns through the
page: bright areas punch out of the print into pure light, with a scorched rim.
"""
import math
from functools import lru_cache

import cv2
import numpy as np

from fastmath import clip01, ev, max3

H, W = 1080, 1920
_LUM = dict(wr=0.299, wg=0.587, wb=0.114)


@lru_cache(maxsize=16)
def _screen(angle_deg, cell):
    a = math.radians(angle_deg)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    u = xx * math.cos(a) + yy * math.sin(a)
    v = -xx * math.sin(a) + yy * math.cos(a)
    fu = (u / cell) % 1.0 - 0.5
    fv = (v / cell) % 1.0 - 0.5
    return np.sqrt(fu * fu + fv * fv).astype(np.float32)


def halftone(density, angle=22.5, cell=6.0):
    """AM halftone coverage (0..1) for a density field (0..1)."""
    d = _screen(angle, cell)
    # dot radius sqrt(density / pi) * 1.13 against the screen distance, anti-aliased over 0.9 / cell
    v = ev("(sqrt(where(x < 0, 0, where(x > 1, 1, x))) * k - d) * ia + h", x=density, d=d,
           k=1.13 / math.sqrt(math.pi), ia=cell / 0.9, h=0.5)
    return clip01(v, out=v)


@lru_cache(maxsize=4)
def _paper(seed=3):
    rng = np.random.default_rng(seed)
    big = cv2.resize(rng.standard_normal((H // 40, W // 40)).astype(np.float32), (W + 64, H + 64),
                     interpolation=cv2.INTER_CUBIC)
    mid = cv2.resize(rng.standard_normal((H // 6, W // 6)).astype(np.float32), (W + 64, H + 64),
                     interpolation=cv2.INTER_CUBIC)
    fine = rng.standard_normal((H + 64, W + 64)).astype(np.float32)
    fib = cv2.GaussianBlur(rng.standard_normal((H + 64, W + 64)).astype(np.float32), (0, 0), sigmaX=6, sigmaY=0.6)
    tex = big * 0.014 + mid * 0.012 + fine * 0.012 + fib * 0.04
    return tex


def paper_grain(t, boil_every=3):
    k = int(t * 24) // boil_every
    rng = np.random.default_rng(k)
    ox, oy = rng.integers(0, 64, 2)
    return _paper()[oy:oy + H, ox:ox + W]


def _shift(a, dx, dy):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(a, M, (W, H), borderMode=cv2.BORDER_REPLICATE)


# Rin's yellow ink also takes the shaded strands of her hair, which render warmer (hue 30-40) than its band:
# without them the shading printed in the key ink alone, a grey copy of her hair under the yellow one ("two
# layers of hair"). (lowest hue, saturation floor there): her skin (hue 18-28, saturation up to 0.3) stays out
HAIR_SHADE = (28, 0.38)

INKSETS = {
    # paper, key ink, [(spot ink, hue lo, hue hi, sat min)], key curve (lo, hi luminance), inverted paper
    "night": dict(paper=(0.93, 0.9, 0.83), key=(0.1, 0.13, 0.3), keytop=0.9,
                  spots=[((1.0, 0.83, 0.0), 38, 72, 0.3), ((1.0, 0.45, 0.16), 8, 38, 0.35),
                         ((0.0, 0.66, 0.74), 165, 215, 0.25)]),
    "graphic": dict(paper=(0.07, 0.09, 0.2), key=(0.93, 0.9, 0.83), solid=True,
                    spots=[((0.2, 0.82, 0.9), 165, 215, 0.2), ((1.0, 0.55, 0.2), 10, 40, 0.3),
                           ((1.0, 0.83, 0.0), 40, 66, 0.3)]),
    # Rin's hair washes out in the overexposed dream room: a low saturation floor keeps it yellow
    "dream": dict(paper=(0.97, 0.95, 0.91), key=(0.36, 0.33, 0.34), keyamp=1.0, keytop=0.95,
                  spots=[((1.0, 0.83, 0.0), 40, 72, 0.12, HAIR_SHADE), ((0.0, 0.66, 0.74), 165, 215, 0.25),
                         ((1.0, 0.55, 0.62), 330, 360, 0.2)]),
    "core": dict(paper=(0.9, 0.93, 0.95), key=(0.03, 0.14, 0.5),
                 spots=[((0.15, 0.78, 1.0), 170, 230, 0.15), ((1.0, 0.83, 0.0), 40, 72, 0.3, HAIR_SHADE),
                        ((0.55, 0.4, 1.0), 240, 300, 0.2)]),
    "dusk": dict(paper=(0.96, 0.88, 0.8), key=(0.33, 0.05, 0.16),
                 spots=[((1.0, 0.22, 0.14), 0, 22, 0.35), ((1.0, 0.6, 0.22), 22, 45, 0.35),
                        ((1.0, 0.83, 0.0), 45, 66, 0.3), ((0.1, 0.62, 0.9), 180, 230, 0.25)]),
    "white": dict(paper=(0.95, 0.96, 0.97), key=(0.24, 0.3, 0.38), keyamp=0.8,
                  spots=[((0.25, 0.8, 1.0), 170, 230, 0.12), ((1.0, 0.83, 0.0), 40, 72, 0.3, HAIR_SHADE)]),
    "mono": dict(paper=(0.9, 0.89, 0.86), key=(0.07, 0.07, 0.07), cell=7.5,
                 spots=[((0.9, 0.12, 0.1), 340, 360, 0.4), ((0.9, 0.12, 0.1), 0, 10, 0.4)]),
    "agitato": dict(paper=(0.07, 0.03, 0.03), key=(1.0, 0.2, 0.15), invert=True, spots=[]),
    "score": dict(paper=(0.05, 0.045, 0.045), key=(0.95, 0.92, 0.85), invert=True, cell=4.5,
                  spots=[((1.0, 0.25, 0.2), 340, 360, 0.3), ((1.0, 0.25, 0.2), 0, 15, 0.3)]),
    "void": dict(paper=(0.035, 0.04, 0.07), key=(0.6, 0.72, 1.0), invert=True,
                 spots=[((1.0, 0.83, 0.0), 40, 72, 0.3, HAIR_SHADE)]),
    "dawn": dict(paper=(0.97, 0.92, 0.82), key=(0.35, 0.22, 0.14),
                 spots=[((1.0, 0.72, 0.1), 28, 60, 0.25), ((0.45, 0.72, 1.0), 180, 235, 0.15),
                        ((1.0, 0.45, 0.35), 0, 28, 0.3)]),
    # her crying eye at dusk: warm paper and wine key like the dusk section, but the iris keeps its aqua so
    # the red sun reflected in it (and the flushed lid) read against their complement
    "dusk_eye": dict(paper=(0.97, 0.9, 0.82), key=(0.3, 0.06, 0.12), keytop=0.85,
                     spots=[((0.0, 0.64, 0.7), 150, 215, 0.12), ((1.0, 0.22, 0.14), 0, 20, 0.25),
                            ((1.0, 0.58, 0.2), 20, 45, 0.3), ((1.0, 0.83, 0.0), 45, 66, 0.3)]),
    # the last close-up: dawn paper, but her eyes keep their aqua (warm light pulls the iris toward
    # green, so the band is wide and the saturation floor low)
    "morning": dict(paper=(0.97, 0.93, 0.85), key=(0.3, 0.2, 0.14),
                    spots=[((1.0, 0.76, 0.12), 30, 62, 0.25), ((0.05, 0.68, 0.72), 140, 215, 0.1),
                           ((1.0, 0.52, 0.42), 0, 24, 0.28)]),
}


def solid(img, cfg, mis=1.0):
    """Screen-print style for line graphics: flat inks, no halftone, so hairlines survive."""
    lum = img @ np.array([0.299, 0.587, 0.114], np.float32)
    k = np.clip((lum - 0.04) / 0.4, 0, 1)
    paper = np.array(cfg["paper"], np.float32)
    ink = np.array(cfg["key"], np.float32)
    out = paper * (1 - k[..., None]) + ink * k[..., None]
    hsv = cv2.cvtColor(np.clip(img, 0, 1), cv2.COLOR_RGB2HSV)
    for col, h0, h1, smin in cfg["spots"]:
        m = ((hsv[..., 0] >= h0) & (hsv[..., 0] <= h1)).astype(np.float32) * np.clip(
            (hsv[..., 1] - smin) / 0.4, 0, 1) * k
        m = _shift(m, -mis, mis * 0.6)
        out = out * (1 - m[..., None]) + np.array(col, np.float32) * m[..., None]
    return out


def riso(img, t, inks="night", cell=None, mis=1.4, contrast=1.15):
    """Separate the frame into paper + key ink + spot inks, each an AM halftone, slightly misregistered.
    Inverted ink sets print light ink on dark paper (key density follows brightness)."""
    cfg = INKSETS[inks] if isinstance(inks, str) else inks
    if cfg.get("solid"):
        return solid(img, cfg)
    cell = cell or cfg.get("cell", 5.5)
    lum = ev("(wr * r + wg * g + wb * b - h) * c + h", r=img[..., 0], g=img[..., 1], b=img[..., 2], h=0.5,
             c=contrast, **_LUM)
    lum = clip01(lum, out=lum)
    hsv = cv2.cvtColor(clip01(img), cv2.COLOR_RGB2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    out = np.empty((H, W, 3), np.float32)
    out[:] = np.array(cfg["paper"], np.float32)
    key = np.array(cfg["key"], np.float32)
    amp = cfg.get("keyamp", 1.0)
    if cfg.get("invert"):
        kd = ev("where(l > a, 1, l / a) ** p * m", l=lum, a=0.85, p=0.9, m=amp)
        kc = _shift(halftone(kd, 22.5, cell), mis, -mis * 0.6)
        out = ev("o * (1 - k) + key * k", o=out, k=kc[..., None], key=key, out=out)
    else:
        top = cfg.get("keytop", 0.8)
        kd = ev("where(l > tp, 0, (tp - l) / tp) ** p * m", l=lum, tp=top, p=1.1, m=amp)
        kc = _shift(halftone(kd, 22.5, cell), mis, -mis * 0.6)
        out = ev("o * (1 - k * (1 - key))", o=out, k=kc[..., None], key=key, out=out)
    angles = (67.5, 7.5, 52.5, 37.5)
    vs = ev("where(v * s > 1, 1, v * s)", v=val, s=1.25)
    for k, spot in enumerate(cfg["spots"]):
        col, h0, h1, smin = spot[:4]
        # an optional (lower hue, saturation floor) extends the band down to warmer, more saturated colours
        lo, sm_lo = spot[4] if len(spot) > 4 else (h0, smin)
        band = ev("where((h >= a) & (h <= b), one, zero)", h=hue, a=lo, b=h1, one=1.0, zero=0.0)
        band = cv2.GaussianBlur(band, (0, 0), 1.0)
        sm = ev("where(h < a, s1, s0)", h=hue, a=h0, s1=sm_lo, s0=smin) if lo < h0 else smin
        sd = ev("bd * where(st < sm, 0, where((st - sm) * iq > 1, 1, (st - sm) * iq)) * vs",
                bd=band, st=sat, sm=sm, iq=1 / 0.45, vs=vs)
        sc = _shift(halftone(sd, angles[k % 4], cell * 0.9), -mis * 0.7 * (k + 1) / 2, mis * 0.5)
        col = np.array(col, np.float32)
        if cfg.get("invert"):
            out = ev("o * (1 - s) + c * s", o=out, s=sc[..., None], c=col, out=out)
        else:
            out = ev("o * (1 - s * (1 - c))", o=out, s=sc[..., None], c=col, out=out)
    return out


def printed(img, t, ink=(0.08, 0.1, 0.22), strength=0.55, cell=5.0, mis=1.2, shadow_from=0.42, paper_tint=(1.0, 0.97, 0.9)):
    """B: keep the image's colour, lay a halftone key ink in the shadows, add paper and misregistration."""
    lum = img @ np.array([0.299, 0.587, 0.114], np.float32)
    dens = np.clip((shadow_from - lum) / shadow_from, 0, 1)
    cov = halftone(dens * strength * 1.4, 22.5, cell)
    base = img.copy()
    # print darks with dots instead of smooth gradients: lift smooth shadows, add dots
    lift = np.clip(shadow_from - lum, 0, None)[..., None] * strength * 0.9
    base = base + lift * np.array(paper_tint, np.float32) * 0.35
    base = base * (1 - cov[..., None] * strength * (1 - np.array(ink, np.float32)))
    # slight misregistration of the warm channel
    base[..., 0] = _shift(base[..., 0], mis, -mis * 0.5)
    base[..., 2] = _shift(base[..., 2], -mis * 0.6, mis * 0.4)
    return base


def apply_paper(img, t, amount=1.0, tint=(1.0, 0.985, 0.95)):
    g = paper_grain(t)
    return ev("i * (1 + g * a) * tn", i=img, g=g[..., None], a=amount, tn=np.array(tint, np.float32))


@lru_cache(maxsize=1)
def _burn_noise(seed=7):
    """Smooth blotches (no fine grain) so the burnt hole has an organic, clean outline."""
    rng = np.random.default_rng(seed)
    big = cv2.resize(rng.standard_normal((H // 48 + 2, W // 48 + 2)).astype(np.float32), (W + 96, H + 96),
                     interpolation=cv2.INTER_CUBIC)
    mid = cv2.resize(rng.standard_normal((H // 12 + 2, W // 12 + 2)).astype(np.float32), (W + 96, H + 96),
                     interpolation=cv2.INTER_CUBIC)
    return big * 0.06 + mid * 0.025


def burn(printed_img, glow_img, t, amount, scorch=(1.0, 0.55, 0.18), noise_scale=24):
    """Chorus: bright areas of the light-render punch through the print with a thin scorched rim."""
    if amount <= 0:
        return printed_img
    lum = max3(glow_img)
    # the outline boils every two frames, like hand-cut film
    rng = np.random.default_rng(int(t * 24) // 2 + 991)
    ox, oy = rng.integers(0, 96, 2)
    f = ev("lm + n - th", lm=lum, n=_burn_noise()[oy:oy + H, ox:ox + W], th=1.0 - amount)
    m = ev("where(f < 0, 0, where(f * a > 1, 1, f * a))", f=f, a=1 / 0.03)
    # rim = a 2 px line just outside the hole, plus a soft hot glow
    rim = cv2.dilate(m, np.ones((5, 5), np.uint8)) - m
    halo = cv2.GaussianBlur(rim, (0, 0), 3.0)
    return ev("p * (1 - m) + gl * m + (r * o + h * q) * sc", p=printed_img, m=m[..., None], gl=glow_img,
              r=rim[..., None], h=halo[..., None], o=0.9, q=0.9, sc=np.array(scorch, np.float32))
