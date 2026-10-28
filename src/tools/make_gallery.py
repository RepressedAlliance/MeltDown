"""README images from the finished film: a hero mosaic, stills and short silent loops (docs/images/).

python src/tools/make_gallery.py [--video out/roshin_yuukai_mv.mp4]
The moments are chosen in HERO, STILLS and LOOPS below. Loops are silent animated WebP (the song is
not redistributed); stills are JPEG.
"""
import argparse
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "images"

HERO = [21.5, 88.0, 117.6, 190.8, 244.0, 322.9]          # seconds, read left to right, top to bottom
STILLS = [14.6, 43.6, 61.4, 79.0, 104.2, 134.0, 207.8, 262.4, 312.0]
LOOPS = {"loop_opening": (6.4, 2.6), "loop_chorus": (77.6, 2.6), "loop_bridge": (187.6, 2.6)}
BEFORE_AFTER = [(14.0, "bed_sitting"), (43.0, "arm_cut"), (307.0, "bed_lying")]


def frame(video, t, w=1920, h=1080):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    return Image.frombytes("RGB", (w, h), r.stdout[:w * h * 3])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(ROOT / "out" / "roshin_yuukai_mv.mp4"))
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stills").mkdir(exist_ok=True)
    # hero: 3 x 2 frames with a thin paper-coloured gap
    cw, ch, gap = 640, 360, 6
    hero = Image.new("RGB", (3 * cw + 2 * gap, 2 * ch + gap), (232, 226, 212))
    for k, t in enumerate(HERO):
        hero.paste(frame(args.video, t, cw, ch), ((k % 3) * (cw + gap), (k // 3) * (ch + gap)))
    hero.save(OUT / "hero.jpg", quality=90)
    for k, t in enumerate(STILLS, 1):
        frame(args.video, t, 960, 540).save(OUT / "stills" / f"{k:02d}.jpg", quality=88)
    for name, (t, dur) in LOOPS.items():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-t", f"{dur:.3f}", "-i", args.video, "-an",
                        "-vf", "fps=12,scale=640:-2:flags=lanczos", "-c:v", "libwebp_anim", "-q:v", "72",
                        "-loop", "0", str(OUT / f"{name}.webp")], check=True)
    # before / after pairs for the making-of notes: the seventh cut's frame (kept in work/qc/before7)
    # beside the same moment of this film
    (OUT / "making").mkdir(exist_ok=True)
    for t, name in BEFORE_AFTER:
        old = ROOT / "work" / "qc" / "before7" / f"t_{t}.jpg"
        if not old.exists():
            continue
        pair = Image.new("RGB", (2 * 960 + 8, 540), (232, 226, 212))
        pair.paste(Image.open(old).convert("RGB").resize((960, 540), Image.LANCZOS), (0, 0))
        pair.paste(frame(args.video, t, 960, 540), (968, 0))
        pair.save(OUT / "making" / f"{name}.jpg", quality=88)
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            print(p.relative_to(ROOT), round(p.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
