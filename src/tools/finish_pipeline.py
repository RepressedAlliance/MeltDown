"""Finish the film in one managed job: re-render the listed Blender shots, then composite.

python finish_pipeline.py --shots S24,S26,... [--tails S29,S31] [--pct 80] [--no-comp] [--workers 3]
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
    ap.add_argument("--tails", default="", help="shots that only need their frames past the cut (a dissolve's tail)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--pct", type=int, default=80, help="render resolution percentage for the re-rendered shots")
    ap.add_argument("--no-comp", action="store_true", help="stop after the Blender renders and the black-frame check")
    args = ap.parse_args()
    shots = [s for s in args.shots.split(",") if s]
    tails = [s for s in args.tails.split(",") if s]
    runs = ([["force=1", f"pct={args.pct}", *shots]] if shots else []) + \
           ([["force=1", "tail_only=1", f"pct={args.pct}", *tails]] if tails else [])
    if runs:
        env = dict(os.environ, MV_VOLTILE="16", MV_VOLSAMPLES="32")
        for opts in runs:
            p = subprocess.Popen([PY, str(ROOT / "src" / "blender" / "drive_shots.py"), *opts], env=env,
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
        # guard against silent GPU failures: re-rendered frames must not be pure black. Only this version's frames
        # (as render_comp.render_range): an older, longer version of a shot leaves frames past its end in the folder
        import numpy as np
        from PIL import Image
        sys.path.insert(0, str(ROOT / "src"))
        import storyboard
        span = {s["id"]: (round(s["t0"] * 24), round((max(s["t1"], s.get("render_to", 0.0)) + s.get("tail", 0.0)) * 24) - 1)
                for s in storyboard.resolved()}
        bad = {}
        for sid in shots + tails:
            d = ROOT / "work" / "render" / sid
            lo, hi = span.get(sid, (0, 10 ** 6))
            for f in sorted(d.glob("*.jpg")):
                if not (f.stem.isdigit() and lo <= int(f.stem) <= hi):
                    continue
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
