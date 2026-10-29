"""How fast the picture pushes forward, frame by frame: the expansion rate of the image (optical-flow
divergence), so a forward move that should feel even can be checked and tuned against numbers.

python src/tools/push_speed.py 0 34 [--video out/roshin_yuukai_mv.mp4] [--chart work/qc/push_0_34.png]
Prints the rate per shot (percent of scale per second: 10 means the picture grows 10 % a second) and writes
a chart of the rate over time with the cuts marked. The halftone screen is blurred away before measuring,
since its fixed dots would read as no motion.
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

FPS = 24
CW, CH = 480, 270


def frames(video, t0, t1):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", str(video), "-vf",
           f"scale={CW}:{CH}", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (CW * CH)
    return np.frombuffer(raw[:n * CW * CH], np.uint8).reshape(n, CH, CW)


def _picture_mask(h, w):
    """Where the picture is, not the overlays that stay put on screen: the print marks along the edges, the
    readout panel low on the left and the lyric columns at the sides."""
    m = np.zeros((h, w), np.uint8)
    m[int(h * 0.08):int(h * 0.92), int(w * 0.12):int(w * 0.85)] = 255
    m[int(h * 0.72):, :int(w * 0.3)] = 0
    return m


def expansion(a, b, mask=None):
    """The relative growth of the picture from a to b: corners tracked from one frame to the next, and the
    scale of the similarity transform that best maps them (RANSAC keeps the dominant motion)."""
    a = cv2.GaussianBlur(a, (0, 0), 2.5)
    b = cv2.GaussianBlur(b, (0, 0), 2.5)
    p0 = cv2.goodFeaturesToTrack(a, 400, 0.01, 8, mask=mask)
    if p0 is None or len(p0) < 12:
        return np.nan
    p1, st, _ = cv2.calcOpticalFlowPyrLK(a, b, p0, None, winSize=(21, 21), maxLevel=3)
    ok = st.ravel() == 1
    if ok.sum() < 12:
        return np.nan
    m, inl = cv2.estimateAffinePartial2D(p0[ok], p1[ok], method=cv2.RANSAC, ransacReprojThreshold=1.5)
    if m is None:
        return np.nan
    return float(np.hypot(m[0, 0], m[1, 0])) - 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("t0", type=float)
    ap.add_argument("t1", type=float)
    ap.add_argument("--video", default=str(ROOT / "out" / "roshin_yuukai_mv.mp4"))
    ap.add_argument("--chart", default=None)
    args = ap.parse_args()
    fr = frames(args.video, args.t0, args.t1)
    mask = _picture_mask(CH, CW)
    rate = np.array([expansion(fr[k], fr[k + 1], mask) for k in range(len(fr) - 1)]) * FPS * 100
    rate = np.where(np.isnan(rate), 0.0, rate)
    ts = args.t0 + (np.arange(len(rate)) + 0.5) / FPS
    shots = [s for s in storyboard.resolved() if s["t1"] > args.t0 and s["t0"] < args.t1]
    for s in shots:
        sel = (ts >= s["t0"]) & (ts < s["t1"])
        if sel.any():
            r = rate[sel]
            print(f"{s['id']:5} {s['t0']:6.2f}-{s['t1']:6.2f}  mean {r.mean():6.1f} %/s  "
                  f"start {r[:6].mean():6.1f}  end {r[-6:].mean():6.1f}  min {r.min():6.1f}  max {r.max():6.1f}")
    out = Path(args.chart or ROOT / "work" / "qc" / f"push_{args.t0:05.1f}_{args.t1:05.1f}.png")
    W, H, pad = 1600, 500, 40
    img = np.full((H, W, 3), 250, np.uint8)
    lo, hi = min(-10.0, float(np.percentile(rate, 1))), max(60.0, float(np.percentile(rate, 99)))

    def px(t, v):
        return (int(pad + (t - args.t0) / (args.t1 - args.t0) * (W - 2 * pad)),
                int(H - pad - (v - lo) / (hi - lo) * (H - 2 * pad)))
    for v in range(0, int(hi) + 1, 10):
        cv2.line(img, px(args.t0, v), px(args.t1, v), (225, 225, 225), 1)
        cv2.putText(img, str(v), (4, px(args.t0, v)[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (120, 120, 120), 1)
    for s in shots:
        x = px(max(s["t0"], args.t0), 0)[0]
        cv2.line(img, (x, pad // 2), (x, H - pad), (180, 200, 255), 1)
        cv2.putText(img, s["id"], (x + 3, pad // 2 + 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 100, 200), 1)
    pts = np.array([px(t, v) for t, v in zip(ts, rate)], np.int32)
    cv2.polylines(img, [pts], False, (40, 40, 40), 2)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)
    print("chart", out)


if __name__ == "__main__":
    main()
