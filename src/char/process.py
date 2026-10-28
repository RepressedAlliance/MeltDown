"""Turn a generated character image into relightable, animatable layers.

For each raw RGBA image this writes assets/char/<name>/:
  color.png   cleaned, stylised colour with straight alpha
  normal.png  pseudo normal map (silhouette-inflated + shading cues) for relighting
  hair.png    hair mask (for sway), skin.png, cloth.png (white hoodie)
  meta.json   size and bounding box

Stylising pulls the image towards cel animation: edge-preserving smoothing,
palette consolidation in Lab space, and a unified warm-dark line colour, which
removes most of the soft "AI" gradients and texture noise.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "assets" / "char" / "raw"
OUT = ROOT / "assets" / "char"


def load_rgba(path):
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im.shape[2] == 3:
        a = np.full(im.shape[:2] + (1,), 255, np.uint8)
        im = np.concatenate([im, a], 2)
    rgb = cv2.cvtColor(im[..., :3], cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    a = im[..., 3].astype(np.float32) / 255
    return rgb, a


def clean_alpha(a):
    # generated alpha tops out just below 1 inside the figure
    hi = np.percentile(a[a > 0.5], 50) if (a > 0.5).any() else 1.0
    a = np.clip(a / max(hi, 1e-3), 0, 1)
    a[a < 0.02] = 0
    return a


def decontaminate(rgb, a, iters=12):
    """Push opaque colours outward so semi-transparent edges carry no black fringe."""
    solid = (a > 0.85).astype(np.float32)
    col = rgb * solid[..., None]
    w = solid.copy()
    k = np.ones((3, 3), np.float32)
    for _ in range(iters):
        col_b = cv2.filter2D(col, -1, k)
        w_b = cv2.filter2D(w, -1, k)
        grow = (w == 0) & (w_b > 0)
        col[grow] = col_b[grow] / w_b[grow][:, None]
        w[grow] = 1
    out = np.where(solid[..., None] > 0, rgb, col)
    return out


def stylise(rgb, a, n_colors=28, line_color=(0.16, 0.09, 0.08)):
    img8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    smooth = cv2.bilateralFilter(img8, 7, 28, 5)
    smooth = cv2.edgePreservingFilter(smooth, flags=cv2.RECURS_FILTER, sigma_s=12, sigma_r=0.12)
    lab = cv2.cvtColor(smooth, cv2.COLOR_RGB2LAB).astype(np.float32)
    mask = a > 0.5
    data = lab[mask]
    if len(data) > 200000:
        idx = np.random.default_rng(0).choice(len(data), 200000, replace=False)
        sample = data[idx]
    else:
        sample = data
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5)
    _, _, centers = cv2.kmeans(sample, n_colors, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    # assign every pixel, then blend 70% toward its palette colour (keeps soft shading alive)
    flat = lab.reshape(-1, 3)
    d = ((flat[:, None, :] - centers[None, :, :]) ** 2).sum(-1)
    q = centers[d.argmin(1)].reshape(lab.shape)
    mixed = lab * 0.3 + q * 0.7
    out = cv2.cvtColor(np.clip(mixed, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32) / 255
    # line art: dark, thin structures -> one consistent warm dark tone
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    line = np.clip((blackhat - 0.06) * 6.0, 0, 1)
    line = cv2.GaussianBlur(line, (0, 0), 0.6)
    lc = np.array(line_color, np.float32)
    out = out * (1 - line[..., None] * 0.85) + lc * line[..., None] * 0.85
    return np.clip(out, 0, 1), line


def pseudo_normal(rgb, a, strength=1.0):
    """Height = blurred silhouette only (a rounded body); line detail would emboss."""
    h = np.zeros_like(a)
    for s, w in ((60, 0.55), (24, 0.3), (8, 0.15)):
        h += cv2.GaussianBlur(a, (0, 0), s) * w
    gx = cv2.Sobel(h, cv2.CV_32F, 1, 0, ksize=5)
    gy = cv2.Sobel(h, cv2.CV_32F, 0, 1, ksize=5)
    scale = 18.0 * strength
    nx, ny = -gx * scale, gy * scale  # image y down -> normal y up
    nz = np.ones_like(nx)
    n = np.stack([nx, ny, nz], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n


def region_masks(rgb, a):
    hsv = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    h, s, v = hsv[..., 0] * 2, hsv[..., 1] / 255, hsv[..., 2] / 255
    solid = a > 0.5
    # Rin: honey-blonde hair (yellow hue, saturated); the tie is yellow too, so keep
    # only components that touch the top third of the figure
    hair = (h > 36) & (h < 62) & (s > 0.42) & (v > 0.5) & solid
    hair = cv2.morphologyEx(hair.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(hair)
    keep = np.zeros_like(hair)
    ys = np.nonzero(solid)[0]
    top = ys.min() + (ys.max() - ys.min()) * 0.4 if len(ys) else 0
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] > 0.002 * a.size and stats[i, cv2.CC_STAT_TOP] < top:
            keep[lab == i] = 1
    skin = (h < 40) & (s > 0.06) & (s < 0.45) & (v > 0.7) & solid
    cloth = (s < 0.1) & (v > 0.68) & solid
    return keep.astype(np.float32), skin.astype(np.float32), cloth.astype(np.float32)


def save_rgba(path, rgb, a):
    im = np.dstack([np.clip(rgb, 0, 1), np.clip(a, 0, 1)])
    im = (im * 255 + 0.5).astype(np.uint8)
    cv2.imwrite(str(path), cv2.cvtColor(im, cv2.COLOR_RGBA2BGRA))


def save_gray(path, m):
    cv2.imwrite(str(path), (np.clip(m, 0, 1) * 255).astype(np.uint8))


def process(name, version="v1", opaque=False, ref=None):
    """ref: the image size the line and edge widths are measured against (default: this image's own
    size). A canvas widened by extend_canvas.py keeps its original size here, so it processes alike."""
    from celify import celify
    src = RAW / f"{name}_{version}.png"
    rgb, a = load_rgba(src)
    if opaque:
        a = np.ones_like(a)
    a = clean_alpha(a)
    rgb = decontaminate(rgb, a)
    ref = ref or max(a.shape)
    scale = ref / 1200.0
    sty, a, info = celify(rgb, a, scale=scale)
    n = pseudo_normal(sty, a)
    hair, skin, cloth = region_masks(sty, a)
    od = OUT / name
    od.mkdir(parents=True, exist_ok=True)
    save_rgba(od / "color.png", sty, a)
    nm = (n * 0.5 + 0.5)
    cv2.imwrite(str(od / "normal.png"), cv2.cvtColor((nm * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    # narrow inner edge band for rim light (about 1.1% of the image size)
    dist = cv2.distanceTransform((a > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    band = np.clip(1 - dist / (0.011 * ref), 0, 1) ** 1.5 * (a > 0.5)
    save_gray(od / "edge.png", cv2.GaussianBlur(band.astype(np.float32), (0, 0), 1.0))
    save_gray(od / "hair.png", hair)
    save_gray(od / "skin.png", skin)
    save_gray(od / "cloth.png", cloth)
    ys, xs = np.nonzero(a > 0.5)
    meta = {"name": name, "source": src.name, "size": [int(a.shape[1]), int(a.shape[0])],
            "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]}
    (od / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("processed", name, meta["size"], meta["bbox"])


if __name__ == "__main__":
    names = sys.argv[1:]
    for nm in names:
        process(nm, opaque=(nm == "eye_macro"))
