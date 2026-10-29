"""Every cut of the film with the numbers that make a transition feel abrupt.

python src/tools/cut_report.py [--video out/roshin_yuukai_mv.mp4]
For each cut: the transition type, the jump in brightness and colour across it (frames 2 before and
2 after), how far it is from the eighth-note grid, and whether a lyric line is being sung through it.
A big jump with a plain cut in a quiet passage, or a cut in the middle of a sung line, is a candidate.
"""
import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import storyboard  # noqa: E402
import timeline as TL  # noqa: E402

FPS = 24
CW, CH = 160, 90


def frame(video, f):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{f / FPS:.4f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={CW}:{CH}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    return np.frombuffer(r.stdout[:CW * CH * 3], np.uint8).reshape(CH, CW, 3).astype(np.float32) / 255


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(ROOT / "out" / "roshin_yuukai_mv.mp4"))
    args = ap.parse_args()
    shots = storyboard.resolved()
    eighth = 60.0 / 165 / 2
    grid0 = TL.BEATS[0] if TL.BEATS else 0.0
    print(f"{'cut':14s} {'time':>8s} {'in':9s} {'dY':>6s} {'dRGB':>6s} {'grid ms':>8s}  sung through")
    for a, b in zip(shots, shots[1:]):
        t = b["t0"]
        f = int(round(t * FPS))
        x, y = frame(args.video, f - 2), frame(args.video, f + 2)
        dy = abs(float(x.mean() - y.mean()))
        drgb = float(np.abs(x.mean(axis=(0, 1)) - y.mean(axis=(0, 1))).sum())
        g = (t - grid0) / eighth
        off = (g - round(g)) * eighth * 1000
        sung = [ln["i"] for ln in TL.LINES if ln["start"] + 0.15 < t < ln["end"] - 0.15]
        mm, ss = divmod(t, 60)
        print(f"{a['id']:>5s}>{b['id']:<7s} {int(mm)}:{ss:05.2f} {b.get('in', 'cut'):9s} {dy:6.3f} {drgb:6.3f} "
              f"{off:+8.0f}  {sung if sung else ''}")


if __name__ == "__main__":
    main()
