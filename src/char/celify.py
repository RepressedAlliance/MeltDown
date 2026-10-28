"""Cel flattening for generated character art.

Keeps the source line art's shape (the new model-sheet style prompts already give
clean lines) but rebuilds everything that reads as "AI":
  * soft gradients and texture noise in fills -> snapped to a small palette
    with majority-smoothed region edges (flat cel colour + one hard shadow)
  * line colour -> one consistent colour-traced tone (darkened fill underneath)
Eyes are protected so irises keep their drawn gradient and catchlights.
"""
import cv2
import numpy as np


def _remove_small(mask, min_area):
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[lab]


def celify(rgb, a, scale=1.0, k=30, chroma_weight=2.6, snap=0.75, line_thresh=0.06, line_dark=0.25,
           smooth_sigma=1.4, line_mix=0.5):
    """rgb float32 HxWx3 (0..1 straight), a float32 HxW. scale ~ image size / 1200."""
    s = scale
    solid = a > 0.5
    img8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    gray = cv2.cvtColor(img8, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    hsv = cv2.cvtColor(img8, cv2.COLOR_RGB2HSV).astype(np.float32)
    hue, sat, val = hsv[..., 0] * 2, hsv[..., 1] / 255, hsv[..., 2] / 255

    # ---- line mask (soft, keeps the source anti-aliasing) without thick dark shapes
    ks = max(3, int(round(7 * s)) | 1)
    bh = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ks, ks)))
    line_soft = np.clip((bh - line_thresh * 0.5) / (line_thresh * 1.5), 0, 1) * solid
    hard = line_soft > 0.5

    # ---- fill flattening
    base = cv2.bilateralFilter(img8, int(5 * s) | 1, 30, 4 * s)
    inpaint_mask = (cv2.dilate(hard.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0).astype(np.uint8)
    base_noline = cv2.inpaint(base, inpaint_mask, max(2, int(3 * s)), cv2.INPAINT_TELEA)
    lab = cv2.cvtColor(base_noline, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 1:] = (lab[..., 1:] - 128) * chroma_weight + 128
    pts = lab[solid]
    rng = np.random.default_rng(0)
    sample = pts[rng.choice(len(pts), min(len(pts), 160000), replace=False)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.3)
    _, _, centers = cv2.kmeans(sample, k, None, crit, 4, cv2.KMEANS_PP_CENTERS)
    flat = lab.reshape(-1, 3)
    labels = np.empty(len(flat), np.int32)
    for i in range(0, len(flat), 400000):
        d = ((flat[i:i + 400000, None, :] - centers[None]) ** 2).sum(-1)
        labels[i:i + 400000] = d.argmin(1)
    labels = labels.reshape(a.shape)
    best = np.full(a.shape, -1.0, np.float32)
    lab_s = np.zeros(a.shape, np.int32)
    for c in range(k):
        m = cv2.GaussianBlur((labels == c).astype(np.float32), (0, 0), smooth_sigma * s)
        upd = m > best
        best[upd] = m[upd]
        lab_s[upd] = c
    centers = centers.copy()
    centers[:, 1:] = (centers[:, 1:] - 128) / chroma_weight + 128
    pal = cv2.cvtColor(np.clip(centers, 0, 255).astype(np.uint8)[None], cv2.COLOR_LAB2RGB)[0]
    quant = pal[lab_s].astype(np.float32) / 255

    # protect eyes: aqua irises plus their surroundings keep the drawn detail
    aqua = (hue > 150) & (hue < 205) & (sat > 0.28) & solid
    aqua = _remove_small(aqua, int(40 * s * s))
    eye = cv2.dilate(aqua.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                                                      (int(30 * s) | 1, int(30 * s) | 1)))
    eye = cv2.GaussianBlur(eye.astype(np.float32), (0, 0), 4 * s)
    w = (snap * (1 - eye) * (1 - line_soft))[..., None]
    fill = base.astype(np.float32) / 255 * (1 - w) + quant * w

    # ---- colour-traced lines
    local = cv2.GaussianBlur(quant, (0, 0), 3.0 * s)
    lc = local * line_dark + np.array([0.12, 0.07, 0.06], np.float32) * (1 - line_dark)
    lc = np.minimum(lc, local * 0.5)
    # inside the eye zone keep the original dark strokes (lashes, pupils)
    orig = img8.astype(np.float32) / 255
    lc = lc * (1 - eye[..., None]) + orig * eye[..., None]
    # keep the drawn stroke shapes; only pull their colour halfway to the traced tone
    lc = orig * (1 - line_mix) + lc * line_mix
    la = line_soft[..., None]
    out = fill * (1 - la) + lc * la
    alpha = np.clip(a, 0, 1)
    return np.clip(out, 0, 1), alpha, {"line": line_soft, "labels": lab_s, "palette": pal, "eye": eye}
