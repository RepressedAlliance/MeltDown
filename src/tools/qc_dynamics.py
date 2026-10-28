"""How the picture moves against the music: motion, brightness, cuts, beats and lyrics on one timeline.

python qc_dynamics.py [--video out/roshin_yuukai_mv.mp4] [--out work/qc]
Writes dynamics.png (one row per 60 s) and prints per-section numbers: loudness, picture motion,
cuts per minute, and stretches where the music pushes but the picture stands still (or the reverse).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import storyboard  # noqa: E402
import timeline as TL  # noqa: E402

FPS = 24
VW, VH = 192, 108


def picture(video):
    """Per-frame motion (mean abs difference to the previous frame), brightness and cut score."""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-an", "-vf", f"scale={VW}:{VH}",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    motion, bright, cut = [], [], []
    prev = None
    while True:
        buf = p.stdout.read(VW * VH)
        if len(buf) < VW * VH:
            break
        f = np.frombuffer(buf, np.uint8).astype(np.float32) / 255.0
        bright.append(f.mean())
        if prev is None:
            motion.append(0.0)
            cut.append(0.0)
        else:
            motion.append(np.abs(f - prev).mean())
            h0 = np.histogram(prev, 32, (0, 1))[0] / f.size
            h1 = np.histogram(f, 32, (0, 1))[0] / f.size
            cut.append(0.5 * np.abs(h1 - h0).sum())
        prev = f
    p.wait()
    return np.array(motion), np.array(bright), np.array(cut)


def smooth(x, n):
    k = np.ones(n) / n
    return np.convolve(x, k, mode="same")


def norm(x):
    lo, hi = np.percentile(x, 2), np.percentile(x, 98)
    return np.clip((x - lo) / max(hi - lo, 1e-6), 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(ROOT / "out" / "roshin_yuukai_mv.mp4"))
    ap.add_argument("--out", default=str(ROOT / "work" / "qc"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    audio = json.loads((ROOT / "work" / "analysis" / "audio.json").read_text(encoding="utf-8"))
    env = audio["env"]
    motion, bright, cutscore = picture(args.video)
    n = min(len(motion), len(env["rms"]))
    motion, bright, cutscore = motion[:n], bright[:n], cutscore[:n]
    rms = np.array(env["rms"][:n])
    onset = np.array(env["onset"][:n])
    m_s, r_s = norm(smooth(motion, 12)), norm(smooth(rms, 12))
    shots = storyboard.resolved()
    lines = TL.LINES
    cuts = [s["t0"] for s in shots[1:]]
    detected = [i / FPS for i in np.nonzero(cutscore > 0.25)[0]]

    # numbers per section
    bounds = [0.0] + audio["section_bounds"][1:] + [n / FPS]
    print("section          dur   loud  motion  cuts/min  corr")
    for a, b in zip(bounds, bounds[1:]):
        i0, i1 = int(a * FPS), int(b * FPS)
        if i1 - i0 < FPS:
            continue
        c = sum(a <= t < b for t in cuts) / ((b - a) / 60)
        corr = np.corrcoef(m_s[i0:i1], r_s[i0:i1])[0, 1] if i1 - i0 > 2 * FPS else float("nan")
        print(f"{a:7.2f}-{b:7.2f} {b - a:6.1f} {r_s[i0:i1].mean():6.2f} {m_s[i0:i1].mean():7.2f} {c:9.1f} {corr:6.2f}")
    print(f"whole film corr(motion, loudness) = {np.corrcoef(m_s, r_s)[0, 1]:.2f}")
    print("cut offset to nearest beat (frames):",
          sorted(round((t - TL.beat_near(t)) * FPS) for t in cuts if abs(t - TL.beat_near(t)) * FPS >= 1))
    # two-second windows where loud music meets a still picture, or the reverse
    w = 2 * FPS
    for i in range(0, n - w, FPS):
        r, m = r_s[i:i + w].mean(), m_s[i:i + w].mean()
        if r > 0.6 and m < 0.12:
            print(f"still on loud  {i / FPS:7.2f}s  loud {r:.2f} motion {m:.2f}")
        elif r < 0.2 and m > 0.6:
            print(f"busy on quiet  {i / FPS:7.2f}s  loud {r:.2f} motion {m:.2f}")

    # timeline chart, one row per minute
    px, rowh, top = 30, 230, 6
    rows = int(np.ceil(n / FPS / 60))
    im = Image.new("RGB", (60 * px + 60, rows * rowh), (24, 24, 28))
    d = ImageDraw.Draw(im)
    for r in range(rows):
        y0 = r * rowh
        x = lambda t: 50 + (t - r * 60) * px  # noqa: E731
        d.text((4, y0 + 4), f"{r}:00", fill=(200, 200, 200))
        base = y0 + rowh - 40
        for i in range(r * 60 * FPS, min(n, (r + 1) * 60 * FPS)):
            t = i / FPS
            d.line([(x(t), base), (x(t), base - 150 * r_s[i])], fill=(70, 70, 82))
            d.point((x(t), base - 150 * min(onset[i] / (onset.max() + 1e-6) * 2, 1)), fill=(120, 120, 140))
        pts = [(x(i / FPS), base - 150 * m_s[i]) for i in range(r * 60 * FPS, min(n, (r + 1) * 60 * FPS))]
        if len(pts) > 1:
            d.line(pts, fill=(255, 190, 40), width=2)
        pts = [(x(i / FPS), base - 150 * bright[i]) for i in range(r * 60 * FPS, min(n, (r + 1) * 60 * FPS))]
        if len(pts) > 1:
            d.line(pts, fill=(90, 200, 255), width=1)
        for b in TL.BEATS:
            if r * 60 <= b < (r + 1) * 60:
                big = any(abs(b - db) < 0.01 for db in TL.DOWNBEATS)
                d.line([(x(b), base + 2), (x(b), base + (10 if big else 5))], fill=(150, 150, 150))
        for s in shots:
            if r * 60 <= s["t0"] < (r + 1) * 60:
                d.line([(x(s["t0"]), y0 + top + 12), (x(s["t0"]), base)], fill=(230, 60, 60))
                d.text((x(s["t0"]) + 2, y0 + top), s["id"], fill=(240, 120, 120))
        for t in detected:
            if r * 60 <= t < (r + 1) * 60:
                d.line([(x(t), base - 6), (x(t), base + 12)], fill=(255, 255, 255))
        for ln in lines:
            if ln["end"] > r * 60 and ln["start"] < (r + 1) * 60:
                a, b = max(ln["start"], r * 60), min(ln["end"], (r + 1) * 60)
                d.rectangle([x(a), base + 16, x(b), base + 24], fill=(120, 220, 140))
                d.text((x(a), base + 26), f"L{ln['i']}", fill=(160, 230, 170))
    im.save(out / "dynamics.png")
    print("chart", out / "dynamics.png")


if __name__ == "__main__":
    main()
