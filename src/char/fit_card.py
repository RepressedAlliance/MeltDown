"""Stage a replacement pose at its own resolution instead of resampling it (align_pose.py scales the
pixels, which softens a close-up): prints the card height and the shift of its origin that put the
new drawing's eyes exactly where the reference pose's eyes were.

python src/char/fit_card.py <pose> <reference pose> <reference card height (m)>
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from align_pose import eyes  # noqa: E402
from process import OUT  # noqa: E402


def fit(pose, ref, h_ref):
    e_new, _, _ = eyes(pose)
    e_ref, _, _ = eyes(ref)
    w_new, hp_new = json.loads((OUT / pose / "meta.json").read_text(encoding="utf-8"))["size"]
    w_ref, hp_ref = json.loads((OUT / ref / "meta.json").read_text(encoding="utf-8"))["size"]
    m_ref = h_ref / hp_ref                                       # metres per pixel on the reference card
    m_new = m_ref * np.linalg.norm(e_ref[1] - e_ref[0]) / np.linalg.norm(e_new[1] - e_new[0])
    c_new, c_ref = e_new.mean(axis=0), e_ref.mean(axis=0)
    # eye midpoint on each card: x from the card's centre line, z up from its bottom edge (its origin)
    x_new, z_new = (c_new[0] - w_new / 2) * m_new, (hp_new - c_new[1]) * m_new
    x_ref, z_ref = (c_ref[0] - w_ref / 2) * m_ref, (hp_ref - c_ref[1]) * m_ref
    return hp_new * m_new, x_ref - x_new, z_ref - z_new


if __name__ == "__main__":
    h, dx, dz = fit(sys.argv[1], sys.argv[2], float(sys.argv[3]))
    print(f"card h={h:.4f}  shift origin along the card: right {dx:+.4f} m, up {dz:+.4f} m")
