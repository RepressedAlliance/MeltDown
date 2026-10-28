"""Quality check of the finished film: stream info, black/frozen intervals and review sheets.

python qc_video.py [--video out/roshin_yuukai_mv.mp4] [--out work/qc]
python qc_video.py --strip 61.0 63.0 [--step 2]     consecutive frames around a cut or a move
Sheets show the in / middle / out frame of every shot and a frame just after each lyric line
starts, so framing, cuts and lyric sync can be reviewed without scrubbing the video.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import storyboard  # noqa: E402
import timeline as TL  # noqa: E402

FPS = 24
CW, CH = 480, 270


def grab(video, times, batch=60):
    """Decode the frames at the given times, `batch` frames per ffmpeg pass (a longer select
    expression makes ffmpeg fail silently); returns {frame index: image}."""
    ns = sorted({int(round(t * FPS)) for t in times})
    size = CW * CH * 3
    out = {}
    for b in range(0, len(ns), batch):
        part = ns[b:b + batch]
        expr = "+".join(f"eq(n\\,{n})" for n in part)
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-an", "-vf",
                            f"select={expr},scale={CW}:{CH}", "-vsync", "0", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-"], capture_output=True)
        out.update({n: Image.frombytes("RGB", (CW, CH), r.stdout[k * size:(k + 1) * size])
                    for k, n in enumerate(part) if (k + 1) * size <= len(r.stdout)})
    return out


def cell(frames, t):
    return frames.get(int(round(t * FPS)), Image.new("RGB", (CW, CH), (255, 0, 255)))


def sheet(path, cells, cols):
    lab = 18
    rows = (len(cells) + cols - 1) // cols
    im = Image.new("RGB", (cols * (CW + 4) - 4, rows * (CH + lab + 4)), (40, 40, 44))
    d = ImageDraw.Draw(im)
    for i, (label, img) in enumerate(cells):
        x, y = (i % cols) * (CW + 4), (i // cols) * (CH + lab + 4)
        im.paste(img, (x, y + lab))
        d.text((x + 4, y + 3), label, fill=(235, 235, 235))
    im.save(path)
    print("sheet", path)


def probe(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration,bit_rate:stream=codec_name,width,height,r_frame_rate,nb_frames,sample_rate,"
                        "channels", "-of", "json", str(video)], capture_output=True, text=True)
    return json.loads(r.stdout)


def detect(video):
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-an", "-vf",
                        "blackdetect=d=0.2:pix_th=0.08,freezedetect=n=0.002:d=1.0", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    black = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)]
    fs = map(float, re.findall(r"freeze_start: ([\d.]+)", r.stderr))
    fe = map(float, re.findall(r"freeze_end: ([\d.]+)", r.stderr))
    return black, list(zip(fs, fe))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(ROOT / "out" / "roshin_yuukai_mv.mp4"))
    ap.add_argument("--out", default=str(ROOT / "work" / "qc"))
    ap.add_argument("--strip", nargs=2, type=float, default=None)
    ap.add_argument("--step", type=int, default=2)
    args = ap.parse_args()
    video, out = Path(args.video), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    shots = storyboard.resolved()

    def shot_at(t):
        return next((s["id"] for s in shots if s["t0"] <= t < s["t1"]), "?")

    if args.strip:
        a, b = args.strip
        ts = [n / FPS for n in range(int(round(a * FPS)), int(round(b * FPS)) + 1, args.step)]
        frames = grab(video, ts)
        sheet(out / f"strip_{a:07.2f}_{b:07.2f}.png", [(f"{shot_at(t)} {t:.3f}s", cell(frames, t)) for t in ts], 4)
        return

    info = probe(video)
    print(json.dumps(info, ensure_ascii=False))
    dur = float(info["format"]["duration"])
    print(f"duration {dur:.3f}s  song {TL.DURATION:.3f}s  diff {dur - TL.DURATION:+.3f}s")
    black, frozen = detect(video)
    for a, b in black:
        print(f"black  {a:7.2f}-{b:7.2f}  {shot_at(a)}")
    for a, b in frozen:
        print(f"freeze {a:7.2f}-{b:7.2f}  {shot_at(a)}")

    shot_ts = []
    for s in shots:
        a, b = s["t0"], min(s["t1"], dur)
        e = min(0.15, (b - a) / 4)
        shot_ts.append((s["id"], [a + e, (a + b) / 2, b - e]))
    lyr = json.loads((ROOT / "work" / "analysis" / "lyrics_timed.json").read_text(encoding="utf-8"))
    lyr_ts = [(f"L{x['i']:02d}", x["start"] + 0.25) for x in lyr]
    frames = grab(video, [t for _, ts in shot_ts for t in ts] + [t for _, t in lyr_ts])

    cells = [(f"{sid} {t:.2f}s", cell(frames, t)) for sid, ts in shot_ts for t in ts]
    for k in range(0, len(cells), 18):
        sheet(out / f"shots_{k // 18:02d}.png", cells[k:k + 18], 3)
    cells = [(f"{name} {t:.2f}s {shot_at(t)}", cell(frames, t)) for name, t in lyr_ts]
    for k in range(0, len(cells), 16):
        sheet(out / f"lyrics_{k // 16:02d}.png", cells[k:k + 16], 4)


if __name__ == "__main__":
    main()
