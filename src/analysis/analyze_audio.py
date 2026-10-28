"""Beat, bar, section and band-energy analysis for the MV timeline.

Writes work/analysis/audio.json (beats, downbeats, per-frame envelopes at the
video frame rate) and work/analysis/overview.png for a quick visual check.
"""
import json
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import paths  # noqa: E402
OUT = ROOT / "work" / "analysis"
FPS = 24


def band_env(S, freqs, lo, hi):
    idx = (freqs >= lo) & (freqs < hi)
    e = S[idx].sum(axis=0)
    e = np.log1p(e / (np.median(e) + 1e-9))
    return e


def resample_env(env, hop_t, n_frames):
    t_src = np.arange(len(env)) * hop_t
    t_dst = np.arange(n_frames) / FPS
    return np.interp(t_dst, t_src, env)


def norm01(x):
    lo, hi = np.percentile(x, 2), np.percentile(x, 99.5)
    return np.clip((x - lo) / (hi - lo + 1e-9), 0, 1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    y, sr = sf.read(paths.song_wav(), dtype="float32")
    y = y.mean(axis=1)
    duration = len(y) / sr
    y22 = librosa.resample(y, orig_sr=sr, target_sr=22050)
    sr = 22050
    hop = 256
    hop_t = hop / sr

    oenv = librosa.onset.onset_strength(y=y22, sr=sr, hop_length=hop, aggregate=np.median)
    tempo_global = librosa.feature.tempo(onset_envelope=oenv, sr=sr, hop_length=hop, max_tempo=240)
    tempo, beats = librosa.beat.beat_track(onset_envelope=oenv, sr=sr, hop_length=hop,
                                           start_bpm=float(tempo_global[0]), tightness=400)
    beat_t = librosa.frames_to_time(beats, sr=sr, hop_length=hop)

    S = np.abs(librosa.stft(y22, n_fft=2048, hop_length=hop)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    low = band_env(S, freqs, 30, 140)
    mid = band_env(S, freqs, 140, 2000)
    high = band_env(S, freqs, 5000, 11000)
    rms = librosa.feature.rms(S=np.sqrt(S), frame_length=2048, hop_length=hop)[0]

    # Downbeat phase: which beat (mod 4) carries the most low-end weight.
    low_at = np.array([low[min(b, len(low) - 1)] for b in beats])
    phase_score = [low_at[p::4].mean() for p in range(4)]
    phase = int(np.argmax(phase_score))
    downbeats = beat_t[phase::4]

    # Section boundaries from a self-similarity novelty curve on beat-synced features.
    chroma = librosa.feature.chroma_cqt(y=y22, sr=sr, hop_length=hop)
    mfcc = librosa.feature.mfcc(y=y22, sr=sr, hop_length=hop, n_mfcc=20)
    feat = np.vstack([librosa.util.normalize(chroma, axis=0), librosa.util.normalize(mfcc, axis=1)])
    sync = librosa.util.sync(feat, beats, aggregate=np.median)
    bounds = librosa.segment.agglomerative(sync, k=18)
    bound_t = librosa.frames_to_time(beats[np.clip(bounds, 0, len(beats) - 1)], sr=sr, hop_length=hop)

    n_frames = int(np.ceil(duration * FPS))
    env = {
        "rms": norm01(resample_env(rms, hop_t, n_frames)),
        "low": norm01(resample_env(low, hop_t, n_frames)),
        "mid": norm01(resample_env(mid, hop_t, n_frames)),
        "high": norm01(resample_env(high, hop_t, n_frames)),
        "onset": norm01(resample_env(oenv, hop_t, n_frames)),
    }

    data = {
        "duration": duration,
        "fps": FPS,
        "n_frames": n_frames,
        "tempo_global": float(tempo_global[0]),
        "tempo_tracked": float(np.atleast_1d(tempo)[0]),
        "beats": [round(float(t), 4) for t in beat_t],
        "downbeat_phase": phase,
        "downbeats": [round(float(t), 4) for t in downbeats],
        "section_bounds": [round(float(t), 3) for t in sorted(set(bound_t))],
        "env": {k: [round(float(v), 4) for v in a] for k, a in env.items()},
    }
    (OUT / "audio.json").write_text(json.dumps(data), encoding="utf-8")

    # Overview image: rows of 30 s each with rms/low/high and beat/downbeat ticks.
    row_s = 30
    rows = int(np.ceil(duration / row_s))
    W, H = 1800, 120
    img = Image.new("RGB", (W, H * rows), (14, 14, 18))
    d = ImageDraw.Draw(img)
    for r in range(rows):
        y0 = r * H
        t0 = r * row_s
        for name, col in (("rms", (230, 230, 230)), ("low", (255, 140, 60)), ("high", (90, 170, 255))):
            a = env[name]
            pts = []
            for x in range(W):
                t = t0 + x / W * row_s
                i = min(int(t * FPS), n_frames - 1)
                pts.append((x, y0 + H - 12 - a[i] * (H - 30)))
            d.line(pts, fill=col, width=1)
        for t in beat_t:
            if t0 <= t < t0 + row_s:
                x = (t - t0) / row_s * W
                d.line([(x, y0 + H - 10), (x, y0 + H - 4)], fill=(120, 120, 120))
        for t in downbeats:
            if t0 <= t < t0 + row_s:
                x = (t - t0) / row_s * W
                d.line([(x, y0 + H - 14), (x, y0 + H - 2)], fill=(255, 255, 0))
        for t in bound_t:
            if t0 <= t < t0 + row_s:
                x = (t - t0) / row_s * W
                d.line([(x, y0), (x, y0 + H)], fill=(255, 60, 90), width=2)
                d.text((x + 3, y0 + 2), f"{t:.1f}", fill=(255, 90, 120))
        for s in range(0, row_s, 5):
            x = s / row_s * W
            d.text((x + 2, y0 + H - 26), f"{t0 + s}s", fill=(90, 90, 90))
        d.line([(0, y0 + H - 1), (W, y0 + H - 1)], fill=(40, 40, 50))
    img.save(OUT / "overview.png")
    print(json.dumps({k: data[k] for k in ("duration", "tempo_global", "tempo_tracked", "downbeat_phase")}))
    print("beats:", len(beat_t), "first beats:", [round(float(t), 3) for t in beat_t[:8]])
    print("sections:", data["section_bounds"])


if __name__ == "__main__":
    sys.exit(main())
