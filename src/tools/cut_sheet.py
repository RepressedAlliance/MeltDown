"""Frames on both sides of every cut in a time range, one row per cut, to judge transitions.

python cut_sheet.py 0 34 [--video out/roshin_yuukai_mv.mp4] [--offsets -0.25,-0.08,0,0.08,0.25]
Writes work/qc/cuts_<a>_<b>.png: each row is a cut (shot ids and time on the left), frames at the
given offsets from the cut.
"""
import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import storyboard  # noqa: E402

FPS = 24
CW, CH = 320, 180


def frame_at(video, t):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={CW}:{CH}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    if len(r.stdout) < CW * CH * 3:
        return Image.new("RGB", (CW, CH))
    return Image.frombytes("RGB", (CW, CH), r.stdout[:CW * CH * 3])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("t0", type=float)
    ap.add_argument("t1", type=float)
    ap.add_argument("--video", default=str(ROOT / "out" / "roshin_yuukai_mv.mp4"))
    ap.add_argument("--offsets", default="-0.25,-0.08,0,0.08,0.25")
    args = ap.parse_args()
    offs = [float(x) for x in args.offsets.split(",")]
    shots = storyboard.resolved()
    cuts = [(a, b) for a, b in zip(shots, shots[1:]) if args.t0 <= b["t0"] <= args.t1]
    W = 110 + len(offs) * (CW + 4)
    sheet = Image.new("RGB", (W, len(cuts) * (CH + 4)), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for r, (a, b) in enumerate(cuts):
        y = r * (CH + 4)
        d.text((6, y + 6), f"{a['id']}>{b['id']}\n{b['t0']:.2f}s\n{b.get('in', '')}", fill=(240, 220, 120))
        for k, o in enumerate(offs):
            sheet.paste(frame_at(args.video, b["t0"] + o), (110 + k * (CW + 4), y))
    out = ROOT / "work" / "qc" / f"cuts_{args.t0:05.1f}_{args.t1:05.1f}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print("sheet", out)


if __name__ == "__main__":
    main()
