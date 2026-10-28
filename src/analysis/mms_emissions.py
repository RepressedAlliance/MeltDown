"""CTC emissions of the vocal stem from the MMS forced-alignment model (torchaudio MMS_FA, CPU).

python mms_emissions.py              compute every missing chunk, a few per child process (retried)
python mms_emissions.py --chunks 3,4 compute just those chunks in this process
python mms_emissions.py --src NAME   same on work/stems/NAME.wav into work/analysis/mms_NAME/
                                     (vocals_other: vocals + other, for lines Demucs put in "other")
Chunks are 20 s with 2 s of context on both sides and land in work/analysis/mms/em_###.npy:
20 ms frames (50 per second, frame k of the song starts at k * 0.02 s), log-probabilities over
the model's blank + 27 letters (no star). Long CPU inference on this machine crashes at random,
so the work is cut into short child processes and finished chunks are never redone.
"""
import os
import subprocess
import sys
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[2]
VOCALS = ROOT / "work" / "stems" / "vocals.wav"
OUTDIR = ROOT / "work" / "analysis" / "mms"
SR = 16000
HOP = 320                      # samples per emission frame
CHUNK = 1000                   # frames per chunk (20 s)
CTX = 100                      # context frames on each side (2 s)
PER_PROCESS = 4
SRC_ARGS = []
if "--src" in sys.argv:
    i = sys.argv.index("--src")
    SRC_ARGS = sys.argv[i:i + 2]
    del sys.argv[i:i + 2]
    VOCALS = ROOT / "work" / "stems" / f"{SRC_ARGS[1]}.wav"
    OUTDIR = ROOT / "work" / "analysis" / f"mms_{SRC_ARGS[1]}"


def load_vocals():
    import soundfile as sf
    import torch
    import torchaudio

    y, sr = sf.read(VOCALS, dtype="float32", always_2d=True)
    y = torch.from_numpy(y.mean(axis=1))
    return torchaudio.functional.resample(y, sr, SR)


def n_chunks(n_samples):
    return -(-(n_samples // HOP) // CHUNK)


def chunk_path(k):
    return OUTDIR / f"em_{k:03d}.npy"


def compute(chunks):
    import numpy as np
    import torch
    import torchaudio

    assert not torch.cuda.is_available()
    torch.set_num_threads(8)
    wav = load_vocals()
    model = torchaudio.pipelines.MMS_FA.get_model(with_star=False).eval()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for k in chunks:
        f0, f1 = k * CHUNK, (k + 1) * CHUNK
        a = max(0, (f0 - CTX) * HOP)
        b = min(len(wav), (f1 + CTX) * HOP + 400)
        with torch.inference_mode():
            em, _ = model(wav[a:b].unsqueeze(0))
        em = em[0].numpy()
        lead = f0 - a // HOP
        keep = em[lead:lead + (f1 - f0)]
        np.save(chunk_path(k), keep.astype(np.float32))
        print(f"chunk {k}: frames {f0}-{f0 + len(keep)}", flush=True)


def drive():
    import soundfile as sf

    info = sf.info(VOCALS)
    total = n_chunks(int(info.frames * SR / info.samplerate))
    for attempt in range(8):
        missing = [k for k in range(total) if not chunk_path(k).exists()]
        if not missing:
            print(f"all {total} chunks present")
            return
        batch = missing[:PER_PROCESS]
        r = subprocess.run([sys.executable, __file__, "--chunks", ",".join(map(str, batch))] + SRC_ARGS)
        if r.returncode:
            print(f"child exited {r.returncode} on {batch} (attempt {attempt}); retrying", flush=True)
    raise SystemExit("chunks still missing after retries")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--chunks":
        compute([int(x) for x in sys.argv[2].split(",")])
    else:
        drive()
