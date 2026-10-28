"""Lead voice only: keep the harmonics of the tracked melody pitch, drop the harmony part.

python melody_mask.py   -> work/stems/vocals_melody.wav (22.05 kHz mono)
The choruses double Rin with a harmony line singing the same words, which blurs the vowels for the
CTC model. With the pYIN pitch (pitch_track.py, same 128-sample hop) every voiced frame keeps only
narrow bands around the lead's harmonics; unvoiced frames (consonants, breaths) pass unchanged.
"""
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "work" / "stems" / "vocals.wav"
DST = ROOT / "work" / "stems" / "vocals_melody.wav"
SR, HOP, NFFT = 22050, 128, 2048


def main():
    y, _ = librosa.load(SRC, sr=SR, mono=True)
    z = np.load(ROOT / "work" / "analysis" / "pitch.npz")
    f0 = librosa.midi_to_hz(z["midi"])                    # nan where unvoiced
    out = np.zeros_like(y)
    freqs = np.fft.rfftfreq(NFFT, 1 / SR)
    block = 30 * SR
    for a in range(0, len(y), block):
        lo, hi = max(0, a - SR), min(len(y), a + block + SR)
        S = librosa.stft(y[lo:hi], n_fft=NFFT, hop_length=HOP)
        fr = lo // HOP + np.arange(S.shape[1])
        f = f0[np.clip(fr, 0, len(f0) - 1)]
        mask = np.ones(S.shape, np.float32)
        for j in np.nonzero(np.isfinite(f))[0]:
            h = np.arange(1, int(8000 / f[j]) + 1) * f[j]
            width = np.maximum(18.0, 0.025 * h)            # Hz: vibrato and the window's spread
            d = np.abs(freqs[:, None] - h[None, :]) / width[None, :]
            mask[:, j] = np.clip(np.exp(-0.5 * d ** 2).max(1), 0.02, 1)
        z_ = librosa.istft(S * mask, hop_length=HOP, length=hi - lo)
        keep0, keep1 = a - lo, min(len(y), a + block) - lo
        out[a:a + keep1 - keep0] = z_[keep0:keep1]
        print(f"{a / SR:6.1f} s", flush=True)
    sf.write(DST, out / (np.abs(out).max() + 1e-9) * 0.9, SR)


if __name__ == "__main__":
    main()
