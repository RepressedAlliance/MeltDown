"""Finish the film in one managed job: re-render the listed Blender shots, then composite.

python finish_pipeline.py --shots S24,S26,... [--workers 3]
Stage 1 runs drive_shots.py (force) at reduced resolution with coarser volumetrics
(MV_VOLTILE=16) so the volumetric core shots stay under the job's memory cap even as Eevee's
per-frame peak creeps up (the comp upscales them; the halftone print hides the difference);
stage 2 runs render_parallel.py. Stops if any shot fails.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default="")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--pct", type=int, default=80, help="render resolution percentage for the re-rendered shots")
    ap.add_argument("--no-comp", action="store_true", help="stop after the Blender renders and the black-frame check")
    args = ap.parse_args()
    shots = [s for s in args.shots.split(",") if s]
    if shots:
        env = dict(os.environ, MV_VOLTILE="16", MV_VOLSAMPLES="32")
        p = subprocess.Popen([PY, str(ROOT / "src" / "blender" / "drive_shots.py"), "force=1", f"pct={args.pct}", *shots],
                             env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                             errors="replace")
        out = []
        for line in p.stdout:
            out.append(line)
            if line.startswith(("BATCH_SHOT", "SHOT_RETRY", "DRIVE_DONE")):
                print(line.rstrip()[:200], flush=True)
        p.wait()
        m = re.search(r"DRIVE_DONE \d+s failed=\[(.*?)\]", "".join(out))
        if not m or m.group(1).strip():
            print("STAGE1_FAILED", m.group(1) if m else "no DRIVE_DONE", flush=True)
            return 2
        # guard against silent GPU failures: re-rendered frames must not be pure black
        import numpy as np
        from PIL import Image
        bad = {}
        for sid in shots:
            d = ROOT / "work" / "render" / sid
            for f in sorted(d.glob("*.jpg")):
                if np.asarray(Image.open(f).convert("L").reduce(16)).mean() < 0.5 and sid not in ("S54",):
                    bad.setdefault(sid, []).append(f.stem)
        if bad:
            print("STAGE1_BLACK", {k: (len(v), v[:3]) for k, v in bad.items()}, flush=True)
            return 3
        print("STAGE1_OK", flush=True)
    if args.no_comp:
        return 0
    r = subprocess.run([PY, str(ROOT / "src" / "comp" / "render_parallel.py"), "--workers", str(args.workers)])
    print("STAGE2_DONE", r.returncode, flush=True)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
