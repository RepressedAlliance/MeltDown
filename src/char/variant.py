"""A second drawing of a pose for stop-motion on the beat: the base pose with one part moved (a thumb striking a
lighter, a lowered arm, swinging feet, a waving hand), identical to the base everywhere else.

python variant.py <base_pose> <new_pose> "cx,cy,rx,ry,deg;..." [ref]   (expects assets/char/raw/<new_pose>_v1.png;
ref: the line-scale reference size the base was processed with, if its canvas was widened by extend_canvas.py)
The new raw image is an image model's edit of the base's raw image with only that part changed, but the model
redraws every line a little and may change the canvas size. So the edit is aligned to the base raw (affine ECC,
measured only outside the named ellipses, where nothing should have moved), and taken only inside the ellipses
(base raw pixels: where the part was and where it went), colour and alpha both, since the silhouette changes.
That patched raw (<new_pose>_v2.png) is processed like any pose (process.py, same line scale as the base), and
then every layer outside the ellipses is copied back from the base, so the two cards are pixel-identical there
and can swap mid-shot without the figure shimmering. The base's hair sway weights and closed-eye layer follow.
"""
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process import OUT, RAW, load_rgba, process, save_rgba  # noqa: E402


def _ellipses(shape, ellipses):
    keep = np.zeros(shape, np.uint8)
    for cx, cy, rx, ry, deg in ellipses:
        cv2.ellipse(keep, (int(cx), int(cy)), (int(rx), int(ry)), deg, 0, 360, 1, -1)
    return keep


def _blend_layer(outside, inside, m, target=None):
    """target (default: `inside`) = `outside` beyond the mask m, `inside` within it."""
    a = cv2.imread(str(outside), cv2.IMREAD_UNCHANGED)
    b = cv2.imread(str(inside), cv2.IMREAD_UNCHANGED)
    if a is None or b is None or a.shape != b.shape:
        return
    mm = m if a.ndim == 2 else m[..., None]
    out = a.astype(np.float32) * (1 - mm) + b.astype(np.float32) * mm
    cv2.imwrite(str(target or inside), np.clip(out + 0.5, 0, 255).astype(a.dtype))


def main(base_pose, new_pose, ellipses, ref=None):
    meta_b = json.loads((OUT / base_pose / "meta.json").read_text(encoding="utf-8"))
    base_rgb, base_a = load_rgba(RAW / meta_b["source"])
    h, w = base_a.shape
    rgb, a = load_rgba(RAW / f"{new_pose}_v1.png")
    if rgb.shape[:2] != (h, w):
        rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_CUBIC)
        a = cv2.resize(a, (w, h), interpolation=cv2.INTER_CUBIC)
    keep = _ellipses((h, w), ellipses)
    # align on what should not have moved: everything solid outside the (dilated) ellipses
    calm = ((cv2.dilate(keep, np.ones((41, 41), np.uint8)) == 0) & (base_a > 0.5)).astype(np.uint8)
    g0 = cv2.cvtColor((base_rgb * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255 * base_a
    g1 = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255 * a
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(g0, g1, warp, cv2.MOTION_AFFINE,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-7), calm, 5)
    except cv2.error as e:
        print("ECC failed, using identity:", e)
    flags = cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP
    rgb_al = cv2.warpAffine(rgb, warp, (w, h), flags=flags)
    a_al = cv2.warpAffine(a, warp, (w, h), flags=flags)
    # the silhouette changes run past any ellipse drawn by eye (a sneaker's toe, a cuff): just around the
    # ellipses, take every pixel the edit added or removed too, or a sliver of the old limb stays behind
    near = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (161, 161)))
    moved = ((np.abs(base_a - a_al) > 0.5) & (near > 0)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(moved)
    touch = cv2.dilate(keep, np.ones((5, 5), np.uint8))
    for i in range(1, n):
        if (touch[lab == i] > 0).any():        # only changes that join the named part, not stray noise
            keep[lab == i] = 1
    keep = cv2.dilate(keep, np.ones((7, 7), np.uint8))
    m = cv2.GaussianBlur(keep.astype(np.float32), (0, 0), 3)
    out_a = base_a * (1 - m) + a_al * m
    # straight alpha: where the part moved into empty space, its colour comes from the edit alone
    wa, wb = base_a * (1 - m), a_al * m
    out_rgb = (base_rgb * wa[..., None] + rgb_al * wb[..., None]) / np.maximum(wa + wb, 1e-4)[..., None]
    save_rgba(RAW / f"{new_pose}_v2.png", out_rgb, out_a)
    # process at the base's line scale (a widened canvas keeps its original size as the reference)
    ref = ref or meta_b.get("ref") or max(h, w)
    process(new_pose, "v2", ref=ref)
    dst, src = OUT / new_pose, OUT / base_pose
    mm = cv2.GaussianBlur(cv2.dilate(keep, np.ones((9, 9), np.uint8)).astype(np.float32), (0, 0), 3)
    for name in ("color.png", "normal.png", "edge.png", "hair.png", "skin.png", "cloth.png"):
        _blend_layer(src / name, dst / name, mm)
    if (src / "hair_soft.png").exists():
        shutil.copy2(src / "hair_soft.png", dst / "hair_soft.png")
    if (src / "color_blink.png").exists():
        # its closed eyes are the base's: the moved part comes from this pose's own colour
        _blend_layer(src / "color_blink.png", dst / "color.png", mm, target=dst / "color_blink.png")
    meta = json.loads((dst / "meta.json").read_text(encoding="utf-8"))
    meta.update(variant_of=base_pose, regions=[list(e) for e in ellipses], ref=ref)
    (dst / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("variant written", new_pose, "from", base_pose, "warp", np.round(warp, 4).tolist())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], [tuple(float(v) for v in e.split(",")) for e in sys.argv[3].split(";")],
         int(sys.argv[4]) if len(sys.argv) > 4 else None)
