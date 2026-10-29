"""Frames on both sides of every cut in a time range, one row per cut, to judge transitions.

python cut_sheet.py 0 34 [--video out/roshin_yuukai_mv.mp4] [--offsets -0.25,-0.08,0,0.08,0.25] [--comp]
Writes work/qc/cuts_<a>_<b>.png: each row is a cut (shot ids and time on the left), frames at the
given offsets from the cut. --comp composites those frames directly (render_comp.py --stills), so the
cuts can be judged while the film itself is still being composited.
"""
import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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
    ap.add_argument("--comp", action="store_true", help="composite the frames instead of reading the video")
    args = ap.parse_args()
    offs = [float(x) for x in args.offsets.split(",")]
    shots = storyboard.resolved()
    cuts = [(a, b) for a, b in zip(shots, shots[1:]) if args.t0 <= b["t0"] <= args.t1]
    if args.comp:
        times = sorted({round(b["t0"] + o, 2) for _, b in cuts for o in offs})
        for i in range(0, len(times), 60):
            subprocess.run([sys.executable, str(ROOT / "src" / "comp" / "render_comp.py"), "--stills",
                            ",".join(f"{t:.2f}" for t in times[i:i + 60])], check=True, stdout=subprocess.DEVNULL)

    def grab(t):
        if args.comp:
            return Image.open(ROOT / "work" / "comp_stills" / f"t{round(t, 2):07.2f}.png").convert("RGB").resize((CW, CH))
        return frame_at(args.video, t)
    W = 110 + len(offs) * (CW + 4)
    sheet = Image.new("RGB", (W, len(cuts) * (CH + 4)), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = None
    for r, (a, b) in enumerate(cuts):
        y = r * (CH + 4)
        mm, ss = divmod(b["t0"], 60)
        d.text((6, y + 6), f"{a['id']}>{b['id']}\n{int(mm)}:{ss:05.2f}\n{b.get('in') or 'cut'}", fill=(240, 220, 120),
               font=font)
        for k, o in enumerate(offs):
            sheet.paste(grab(b["t0"] + o), (110 + k * (CW + 4), y))
    out = ROOT / "work" / "qc" / f"cuts_{args.t0:05.1f}_{args.t1:05.1f}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print("sheet", out)


if __name__ == "__main__":
    main()
