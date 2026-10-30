"""Write the picture the CRT in the room broadcasts: Rin as the talk-show host (4:3, grey).

python make_tv_picture.py   ->   assets/tv/rin_on_air.png, rin_on_air_wave.png
Uses the same framing as the 2D TVs (scenes2d.rin_picture), so every screen in the film shows her
the same way.
"""
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "comp"))
sys.path.insert(0, str(ROOT / "src"))
import scenes2d  # noqa: E402


def main():
    # the host, and the same picture with her hand at the other end of the wave (swapped on the beat)
    for pose, name in (("rin_tv_host", "rin_on_air.png"), ("rin_tv_host_wave", "rin_on_air_wave.png")):
        out = ROOT / "assets" / "tv" / name
        out.parent.mkdir(parents=True, exist_ok=True)
        lum = scenes2d.rin_picture(pose, 960, 720)
        cv2.imwrite(str(out), (np.clip(lum, 0, 1) * 255 + 0.5).astype(np.uint8))
        print("wrote", out)


if __name__ == "__main__":
    main()
