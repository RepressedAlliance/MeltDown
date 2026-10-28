"""Write the picture the CRT in the room broadcasts: Rin as the talk-show host (4:3, grey).

python make_tv_picture.py   ->   assets/tv/rin_on_air.png
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
    out = ROOT / "assets" / "tv" / "rin_on_air.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    lum = scenes2d.rin_picture("rin_tv_host", 960, 720)
    cv2.imwrite(str(out), (np.clip(lum, 0, 1) * 255 + 0.5).astype(np.uint8))
    print("wrote", out)


if __name__ == "__main__":
    main()
