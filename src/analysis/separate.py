"""Split the song into stems with Demucs (htdemucs) on CPU.

Runs each ~30 s chunk in its own short process so a random CPU crash only
costs one chunk; finished chunks are kept and skipped on re-run. Stems land in
work/stems/{drums,bass,other,vocals}.wav.
"""
import os
import subprocess
import sys
from pathlib import Path

# OpenBLAS reserves a buffer per thread at import; on 24 threads that alone
# overruns the task's 1 GiB commit budget.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "3")
os.environ.setdefault("MKL_NUM_THREADS", "3")

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import paths  # noqa: E402

SONG = paths.song_wav()
WORK = ROOT / "work" / "stems"
CHUNK = 12.0
OVERLAP = 2.0
SOURCES = ["drums", "bass", "other", "vocals"]


def worker(idx, start, end):
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    import torch

    assert not torch.cuda.is_available()
    torch.set_num_threads(3)
    # oneDNN grabs large scratch buffers that fail under the job's commit cap.
    torch.backends.mkldnn.enabled = False
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    model = get_model("htdemucs")
    model.eval()
    assert list(model.sources) == SOURCES, model.sources
    info = sf.info(SONG)
    sr = info.samplerate
    a, b = int(start * sr), int(min(end * sr, info.frames))
    wav, _ = sf.read(SONG, start=a, stop=b, dtype="float32", always_2d=True)
    x = torch.from_numpy(wav.T.copy())
    ref = x.mean(0)
    mean, std = ref.mean(), ref.std()
    x = (x - mean) / (std + 1e-8)
    with torch.no_grad():
        out = apply_model(model, x[None], device="cpu", shifts=1, split=True, overlap=0.25,
                          segment=4.0, progress=False)[0]
    out = (out * std + mean).numpy().astype(np.float32)
    tmp = WORK / f"chunk_{idx:03d}.tmp.npy"
    np.save(tmp, out)
    os.replace(tmp, WORK / f"chunk_{idx:03d}.npy")
    print("chunk done", idx, flush=True)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    info = sf.info(SONG)
    sr, total = info.samplerate, info.frames
    dur = total / sr
    chunks = []
    s = 0.0
    while s < dur - 0.5:
        chunks.append((len(chunks), s, min(s + CHUNK, dur)))
        s += CHUNK - OVERLAP
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="-1")
    for i, s, e in chunks:
        f = WORK / f"chunk_{i:03d}.npy"
        if f.exists():
            continue
        for attempt in range(3):
            r = subprocess.run([sys.executable, __file__, "worker", str(i), str(s), str(e)], env=env)
            if r.returncode == 0 and f.exists():
                break
            print(f"chunk {i} attempt {attempt + 1} failed (code {r.returncode})", flush=True)
        else:
            raise SystemExit(f"chunk {i} failed 3 times")

    acc = np.zeros((4, 2, total), np.float32)
    wsum = np.zeros(total, np.float32)
    ramp = int(OVERLAP * sr)
    for i, s, e in chunks:
        out = np.load(WORK / f"chunk_{i:03d}.npy")
        a = int(s * sr)
        n = out.shape[-1]
        w = np.ones(n, np.float32)
        if i > 0:
            w[:ramp] = np.linspace(0, 1, ramp, dtype=np.float32)
        if i < len(chunks) - 1:
            w[-ramp:] = np.minimum(w[-ramp:], np.linspace(1, 0, ramp, dtype=np.float32))
        n = min(n, total - a)
        acc[:, :, a:a + n] += out[:, :, :n] * w[:n]
        wsum[a:a + n] += w[:n]
    acc /= np.maximum(wsum, 1e-6)
    for k, name in enumerate(SOURCES):
        sf.write(WORK / f"{name}.wav", np.clip(acc[k].T, -1, 1), sr, subtype="PCM_16")
    for i, _, _ in chunks:
        (WORK / f"chunk_{i:03d}.npy").unlink()
    print("stems written:", [str(WORK / f"{n}.wav") for n in SOURCES], flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker(int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]))
    else:
        main()
