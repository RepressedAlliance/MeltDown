"""Where is the film "empty"? The director's word for it was 留白: places where, to the eye, the picture hardly
changes. A cut, a camera move you can see, her moving, lyrics floating across the frame all count as change; a
held picture with only effects on it (a flicker, a strobe, heat haze, the snow on a TV, a light pulsing) or only a
slow drift of the camera does not.

python src/tools/pace_report.py [--video out/roshin_yuukai_mv.mp4] [--min-dur 4.0]
Per shot:
- move: how fast the whole picture moves, in % of the frame's width per second. Features are tracked a quarter
  second apart in the finished film (160 x 90 grey, averaged down and blurred so the halftone screen, which stays
  put on the frame, does not register as a still picture) and
  a similarity transform is fitted to them with RANSAC: a push, a pan or a flight moves them all together, while
  the snow on a TV, a flash or a pulsing light are outliers and do not count;
- acts: her actions, the stop-motion changes of drawing the storyboard declares inside the shot (card `on`
  intervals, the tinnitus `steps`, the TV host's waves, the climb), per second;
- sung: the fraction of the shot sung over (a sung line is on screen as animated type).
A shot of at least --min-dur seconds, not sung, with no action, whose picture moves slower than MOVE, is empty time.
Over a quiet stretch of the song it can be a breath (the near-silent bridge at 3:50, which the director liked);
over a band that keeps playing it needs a reason. Exits 1 if any empty shot lies over the band.
"""
import argparse
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import storyboard  # noqa: E402
import timeline as TL  # noqa: E402

W, H = 160, 90
MOVE = 3.0          # % of the frame's width per second: slower than this the picture reads as standing still
SUNG = 0.3          # a shot sung over more than this fraction has its lyrics moving on screen
BUSY_RMS = 0.3      # the band playing (the near-silent bridge is under 0.2)
BUSY_HITS = 1.5     # drum hits (strength 0.6 and up) per second


def actions(s):
    """Song times inside shot s where the storyboard changes her drawing: card `on` intervals starting in the shot,
    the tinnitus steps, the host's waves (bg_args wave, anim crt_wave), the climb's steps (one a beat)."""
    t0, t1 = s["t0"], s["t1"]
    out = []
    for c in s.get("cards", []):
        out += [a for a, _ in c.get("on", []) if t0 < a < t1]
    ba, an = s.get("bg_args", {}), s.get("anim", {})
    out += [h for _, h in ba.get("steps", []) if t0 < h < t1]
    out += [w for w in ba.get("wave", []) if t0 < w < t1]
    out += [w for w, _ in an.get("crt_wave", []) if t0 < w < t1]
    if an.get("step_beats"):
        out += [b for b in TL.BEATS if t0 < b < t1]
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(ROOT / "out" / "roshin_yuukai_mv.mp4"))
    ap.add_argument("--min-dur", type=float, default=4.0)
    args = ap.parse_args()
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", args.video, "-vf", f"scale={W}:{H}:flags=area", "-f", "rawvideo",
                        "-pix_fmt", "gray", "-"], capture_output=True)
    v = np.frombuffer(r.stdout, np.uint8).reshape(-1, H, W)
    n = len(v)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    step = 6
    corners = np.float32([[0, 0], [W, 0], [W, H], [0, H], [W / 2, H / 2]]).reshape(-1, 1, 2)
    move = np.full(n, np.nan, np.float32)
    for f in range(0, n - step, step):
        a = cv2.GaussianBlur(clahe.apply(v[f]), (0, 0), 1.0)
        b = cv2.GaussianBlur(clahe.apply(v[f + step]), (0, 0), 1.0)
        p0 = cv2.goodFeaturesToTrack(a, maxCorners=300, qualityLevel=0.003, minDistance=4)
        if p0 is None or len(p0) < 12:
            continue
        p1, st, _ = cv2.calcOpticalFlowPyrLK(a, b, p0, None, winSize=(11, 11), maxLevel=3)
        ok = st.ravel() == 1
        if ok.sum() < 12:
            continue
        M, inl = cv2.estimateAffinePartial2D(p0[ok], p1[ok], method=cv2.RANSAC, ransacReprojThreshold=0.6)
        if M is None or inl is None or inl.sum() < 10:
            continue
        moved = cv2.transform(corners, M) - corners
        move[f:f + step] = float(np.hypot(moved[..., 0], moved[..., 1]).mean()) / W * 100 * 24 / step
    rms = np.asarray(TL.env("rms"))
    sung = np.zeros(n, bool)
    for ln in TL.LINES:
        sung[int(ln["start"] * 24):int(ln["end"] * 24) + 1] = True
    busy, breath = [], []
    print(f"{'shot':6} {'start':>7} {'dur':>5} {'move':>5} {'acts':>5} {'sung':>4} {'loud':>5} {'hit/s':>5}")
    for s in storyboard.resolved():
        f0, f1 = round(s["t0"] * 24), min(n, round(s["t1"] * 24))
        if f1 - f0 < 8:
            continue
        dur = (f1 - f0) / 24
        mm = move[f0:f1 - step]
        mv = float(np.nanmedian(mm)) if np.isfinite(mm).any() else float("nan")
        ac = len(actions(s)) / dur
        sg = float(sung[f0:f1].mean())
        loud = float(rms[f0:min(f1, len(rms))].mean())
        hits = sum(1 for h in TL._audio["kicks"] if s["t0"] <= h < s["t1"] and TL.hit_strength(h)[0] >= 0.6) / dur
        empty = dur >= args.min_dur and not mv >= MOVE and ac == 0 and sg <= SUNG
        note = ""
        if empty and loud >= BUSY_RMS and hits >= BUSY_HITS:
            busy.append(s["id"])
            note = "  EMPTY OVER THE BAND"
        elif empty:
            breath.append(s["id"])
            note = "  empty, over a quiet stretch (a breath?)"
        m, sec = divmod(s["t0"], 60)
        print(f"{s['id']:6} {int(m)}:{sec:05.2f} {dur:5.2f} {mv:5.1f} {ac:5.2f} {sg:4.2f} {loud:5.2f} {hits:5.2f}{note}")
    print(f"pace: {len(busy)} empty shot(s) over the band" + (f": {', '.join(busy)}" if busy else "")
          + (f"; over quiet stretches: {', '.join(breath)}" if breath else ""))
    sys.exit(1 if busy else 0)


if __name__ == "__main__":
    main()
