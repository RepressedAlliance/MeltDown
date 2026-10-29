"""A new pose that is an existing one with another expression: every layer copied from the base pose, and the
edited face patched into its colour only where the expression changed, inside the face box.

python expression.py <base_pose> <new_pose> "cx,cy,rx,ry,deg;..."   (expects assets/char/raw/<new_pose>_v1.png)
The edit is an image model's redraw of the base pose's raw image with only the eyes and mouth changed, but it
redraws every line a little: patched whole, the figure would shimmer against the base under a dissolve. So the
edit is aligned to the processed base (affine ECC, as blink.py does) and taken only inside the given ellipses
(base-image pixels: each eye with its brow, the mouth), feathered. A difference threshold, as blink.py uses,
misses a change of gaze (an iris moved a few pixels), so the regions are named. The base's other layers
(alpha, edges, normals, hair and cloth masks, its closed-eye color_blink.png) stay as they are, so both poses
line up exactly and can swap mid-shot.
"""
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from celify import celify  # noqa: E402
from process import OUT, RAW, clean_alpha, decontaminate, load_rgba  # noqa: E402


def main(base_pose, new_pose, ellipses):
    src, dst = OUT / base_pose, OUT / new_pose
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file():
            shutil.copy2(f, dst / f.name)
    if not (src / "color_blink.png").exists():
        # a base without its own closed-eye layer is the resting face: the new pose swaps back to it (blink 1)
        shutil.copy2(src / "color.png", dst / "color_blink.png")
    base = cv2.imread(str(src / "color.png"), cv2.IMREAD_UNCHANGED)
    base_rgb = cv2.cvtColor(base[..., :3], cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    base_a = base[..., 3].astype(np.float32) / 255
    rgb, a = load_rgba(RAW / f"{new_pose}_v1.png")
    if rgb.shape[:2] != base_rgb.shape[:2]:
        rgb = cv2.resize(rgb, (base_rgb.shape[1], base_rgb.shape[0]), interpolation=cv2.INTER_CUBIC)
        a = cv2.resize(a, (base_rgb.shape[1], base_rgb.shape[0]), interpolation=cv2.INTER_CUBIC)
    a = clean_alpha(a)
    rgb = decontaminate(rgb, a)
    sty, a, _ = celify(rgb, a, scale=max(a.shape) / 1200.0)
    g0 = cv2.cvtColor((base_rgb * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    g1 = cv2.cvtColor((sty * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(g0 * base_a, g1 * a, warp, cv2.MOTION_AFFINE,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5)
    except cv2.error as e:
        print("ECC failed, using identity:", e)
    h, w = g0.shape
    sty_al = cv2.warpAffine(sty, warp, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    keep = np.zeros((h, w), np.uint8)
    for cx, cy, rx, ry, deg in ellipses:
        cv2.ellipse(keep, (int(cx), int(cy)), (int(rx), int(ry)), deg, 0, 360, 1, -1)
    keep = keep * (base_a > 0.5)
    mask = cv2.GaussianBlur(keep.astype(np.float32), (0, 0), 4)[..., None]
    out = base_rgb * (1 - mask) + sty_al * mask
    rgba = np.dstack([out, base_a])
    rgba = (np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8)
    cv2.imwrite(str(dst / "color.png"), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    meta.update(name=new_pose, source=f"{new_pose}_v1.png", expression_of=base_pose,
                face_regions=[list(e) for e in ellipses])
    (dst / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("expression written", new_pose, "from", base_pose, "patched px:", int(keep.sum()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], [tuple(float(v) for v in e.split(",")) for e in sys.argv[3].split(";")])
