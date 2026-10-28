"""Review sheets of the finished film for a second reviewer: every shot as one row of three frames
(start, middle, end), a few shots per sheet, written to work/qc/film_review/sheet_##.jpg.

python src/tools/film_review.py [--video out/roshin_yuukai_mv.mp4] [--per 6] [--shots S05,S14]
Then: src/tools/codex_review.ps1 -Images <sheets> -PromptFile work/qc/codex/prompt_film.md -OutFile ...
"""
import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import storyboard  # noqa: E402

CW, CH = 640, 360


def frame_at(video, t):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={CW}:{CH}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    if len(r.stdout) < CW * CH * 3:
        return Image.new("RGB", (CW, CH))
    return Image.frombytes("RGB", (CW, CH), r.stdout[:CW * CH * 3])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(ROOT / "out" / "roshin_yuukai_mv.mp4"))
    ap.add_argument("--per", type=int, default=6)
    ap.add_argument("--shots", default=None)
    args = ap.parse_args()
    shots = storyboard.resolved()
    if args.shots:
        want = set(args.shots.split(","))
        shots = [s for s in shots if s["id"] in want]
    out = ROOT / "work" / "qc" / "film_review"
    out.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = None
    paths = []
    for k in range(0, len(shots), args.per):
        group = shots[k:k + args.per]
        sheet = Image.new("RGB", (3 * CW + 4, len(group) * (CH + 26)), (14, 14, 16))
        d = ImageDraw.Draw(sheet)
        for r, s in enumerate(group):
            y = r * (CH + 26)
            d.text((6, y + 3), f"{s['id']}  {s['t0']:.2f}-{s['t1']:.2f}s", fill=(255, 220, 0), font=font)
            dur = s["t1"] - s["t0"]
            for c, u in enumerate((0.12, 0.5, 0.88)):
                sheet.paste(frame_at(args.video, s["t0"] + u * dur), (c * (CW + 2), y + 26))
        p = out / f"sheet_{k // args.per:02d}.jpg"
        sheet.save(p, quality=88)
        paths.append(p)
        print(p)


if __name__ == "__main__":
    main()
