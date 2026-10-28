"""Thin skia/numpy helpers shared by the 2D compositor."""
import cv2
import numpy as np
import skia

W, H = 1920, 1080


def surface(w=W, h=H):
    info = skia.ImageInfo.Make(w, h, skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType)
    s = skia.Surface.MakeRaster(info)
    s.getCanvas().clear(skia.ColorTRANSPARENT)
    return s


def to_array(surf):
    """Premultiplied RGBA float32 0..1."""
    a = surf.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kPremul_AlphaType)
    return a.astype(np.float32) / 255.0


def paint(color=(1, 1, 1), alpha=1.0, stroke=None, blur=0.0, aa=True):
    p = skia.Paint(AntiAlias=aa)
    p.setColor4f(skia.Color4f(float(color[0]), float(color[1]), float(color[2]), float(alpha)))
    if stroke:
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(float(stroke))
    if blur > 0:
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, float(blur)))
    return p


def over(dst, src):
    """Premultiplied src over dst (both HxWx4 or dst HxWx3 opaque)."""
    a = src[..., 3:4]
    if dst.shape[-1] == 3:
        return dst * (1 - a) + src[..., :3]
    return dst * (1 - a) + src


def add(dst, src_rgb, k=1.0):
    return dst + src_rgb * k


def glow(layer, sigma=12.0, strength=1.0, scale=0.25):
    """Cheap bloom of a premultiplied layer: blur at reduced resolution."""
    h, w = layer.shape[:2]
    small = cv2.resize(layer[..., :3], (max(1, int(w * scale)), max(1, int(h * scale))),
                       interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigma * scale)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR) * strength


def screen(dst, src_rgb):
    return 1 - (1 - dst) * (1 - np.clip(src_rgb, 0, 1))
