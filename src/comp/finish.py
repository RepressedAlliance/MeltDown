"""Film finishing applied to every frame: grade, halation, lens, vignette, grain."""
from functools import lru_cache

import cv2
import numpy as np

from fastmath import clip01, ev

H, W = 1080, 1920
_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
_cx, _cy = (W - 1) / 2, (H - 1) / 2
_r2 = ((_xx - _cx) / _cx) ** 2 + ((_yy - _cy) / _cy) ** 2


def grade(img, lift=(0, 0, 0), gamma=(1, 1, 1), gain=(1, 1, 1), sat=1.0, contrast=1.0, pivot=0.4):
    out = ev("i * gn + lf * (1 - i)", i=img, gn=np.array(gain, np.float32), lf=np.array(lift, np.float32))
    out = ev("where(o > 0, o, 0)", o=out, out=out)
    g = np.array(gamma, np.float32)
    if np.any(g != 1):
        out = np.power(np.maximum(out, 1e-6), 1.0 / g)
    if contrast != 1.0:
        out = ev("(o - p) * c + p", o=out, p=pivot, c=contrast, out=out)
    if sat != 1.0:
        lum = ev("wr * r + wg * g + wb * b", r=out[..., 0], g=out[..., 1], b=out[..., 2],
                 wr=0.2126, wg=0.7152, wb=0.0722)[..., None]
        out = ev("l + (o - l) * s", l=lum, o=out, s=sat, out=out)
    return ev("where(o > 0, o, 0)", o=out, out=out)


def halation(img, strength=0.25, threshold=0.7, color=(1.0, 0.45, 0.25), sigma=18):
    """Film halation: bright areas bleed a warm glow."""
    if strength <= 0:
        return img
    small = cv2.resize(img, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    hi = np.clip(small - threshold, 0, None)
    hi = hi.max(axis=2, keepdims=True) * np.array(color, np.float32)
    hi = cv2.GaussianBlur(hi, (0, 0), sigma / 4)
    hi = cv2.resize(hi, (W, H), interpolation=cv2.INTER_LINEAR)
    return img + hi * strength


def bloom(img, strength=0.2, threshold=0.85, sigma=40):
    if strength <= 0:
        return img
    small = cv2.resize(img, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    hi = np.clip(small - threshold, 0, None)
    b = cv2.GaussianBlur(hi, (0, 0), sigma / 4) + cv2.GaussianBlur(hi, (0, 0), sigma / 12) * 0.5
    return img + cv2.resize(b, (W, H), interpolation=cv2.INTER_LINEAR) * strength


@lru_cache(maxsize=2)
def _chroma_maps(amount):
    k = amount / max(_cx, _cy)
    r = np.sqrt(_r2)
    maps = []
    for sgn in (1.0, -1.0):
        s = 1 + sgn * k * r * 0.5
        maps.append((_cx + (_xx - _cx) * s, _cy + (_yy - _cy) * s))
    return maps


def chroma(img, amount=1.5):
    """Radial chromatic aberration (px at the frame corner)."""
    if amount <= 0:
        return img
    out = img.copy()
    for ch, (mx, my) in zip((0, 2), _chroma_maps(float(amount))):
        out[..., ch] = cv2.remap(img[..., ch], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return out


@lru_cache(maxsize=2)
def _vignette_shape(roundness):
    return (np.clip(_r2 * 0.5 * roundness, 0, 1) ** 1.5)[..., None]


def vignette(img, amount=0.35, roundness=1.0):
    if amount <= 0:
        return img
    return ev("i * (1 - a * v)", i=img, a=amount, v=_vignette_shape(float(roundness)))


def grain(img, t, amount=0.035, size=1.0, seed=0):
    rng = np.random.default_rng(int(t * 24) * 7919 + seed)
    if size != 1.0:
        h2, w2 = int(H / size), int(W / size)
        n = rng.standard_normal((h2, w2), dtype=np.float32)
        n = cv2.resize(n, (W, H), interpolation=cv2.INTER_LINEAR)
    else:
        n = rng.standard_normal((H, W), dtype=np.float32)
    lum = ev("(r + g + b) * th", r=img[..., 0], g=img[..., 1], b=img[..., 2], th=1 / 3)[..., None]
    # more grain in the mids, less in deep blacks and highlights
    return ev("i + n * a * (4 * l * (1 - where(l < 0, 0, where(l > 1, 1, l))) + q)", i=img, n=n[..., None],
              a=amount, l=lum, q=0.25)


def tonemap(img):
    """Soft shoulder so overlays/glows never clip harshly."""
    return ev("i / (1 + where(i > p, i - p, 0) * k)", i=img, p=0.8, k=1.2)


def finish(img, t, cfg):
    img = grade(img, **cfg.get("grade", {}))
    img = bloom(img, **cfg.get("bloom", {"strength": 0.0}))
    img = halation(img, **cfg.get("halation", {"strength": 0.18}))
    img = chroma(img, cfg.get("chroma", 1.2))
    img = vignette(img, cfg.get("vignette", 0.3))
    img = tonemap(img)
    img = grain(img, t, **cfg.get("grain", {"amount": 0.03}))
    return clip01(img, out=img)
