"""Melody pitch of the vocal stem (pYIN), cached for the lyric aligner.

python pitch_track.py              -> work/analysis/pitch.npz: t (s), midi (nan where unvoiced), vprob
python pitch_track.py --other a-b  -> work/analysis/pitch_other.npz: the same on vocals+other, only
                                      inside a..b s (the processed chorus line Demucs put in "other")
Hop 128 at 22.05 kHz (5.8 ms); 30 s blocks with overlap keep memory small.
"""
import sys
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
VOCALS = ROOT / "work" / "stems" / "vocals.wav"
OUT = ROOT / "work" / "analysis" / "pitch.npz"
SR, HOP, FRAME = 22050, 128, 1024


def main():
    src, out, span = VOCALS, OUT, None
    if "--other" in sys.argv:
        src, out = ROOT / "work" / "stems" / "vocals_other.wav", ROOT / "work" / "analysis" / "pitch_other.npz"
        span = [float(x) for x in sys.argv[sys.argv.index("--other") + 1].split("-")]
    y, _ = librosa.load(src, sr=SR, mono=True)
    n = 1 + len(y) // HOP
    f0 = np.full(n, np.nan, np.float32)
    vp = np.zeros(n, np.float32)
    block, pad = 30 * SR, SR
    starts = range(0, len(y), block)
    if span:
        block = int((span[1] - span[0]) * SR)
        starts = [int(span[0] * SR)]
    for a in starts:
        lo, hi = max(0, a - pad), min(len(y), a + block + pad)
        f, _, p = librosa.pyin(y[lo:hi], sr=SR, fmin=130, fmax=1400, frame_length=FRAME, hop_length=HOP)
        i0 = (a - lo) // HOP
        i1 = i0 + min(block, len(y) - a) // HOP + 1
        dst = a // HOP
        m = min(i1 - i0, n - dst, len(f) - i0)
        f0[dst:dst + m] = f[i0:i0 + m]
        vp[dst:dst + m] = p[i0:i0 + m]
        print(f"{a / SR:6.1f} s", flush=True)
    t = np.arange(n) * HOP / SR
    np.savez_compressed(out, t=t, midi=librosa.hz_to_midi(f0).astype(np.float32), vprob=vp)


if __name__ == "__main__":
    main()
