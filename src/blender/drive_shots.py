"""Render storyboard shots one Blender process at a time (fresh memory per shot).

python drive_shots.py [preview=1 step=3 pct=40 samples=6] <shot_id ...|all>
A shot whose Blender process crashes is retried once; finished frames are kept.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
# set the BLENDER environment variable when Blender 5.2 is installed somewhere else
BLENDER = os.environ.get("BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def main():
    args = sys.argv[1:]
    opts = [a for a in args if "=" in a]
    ids = [a for a in args if "=" not in a]
    if ids == ["all"]:
        import storyboard
        ids = [s["id"] for s in storyboard.resolved() if s.get("scene")]
    t_all = time.time()
    failed = []
    for sid in ids:
        ok = False
        for attempt in range(2):
            t = time.time()
            r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", str(HERE / "render_batch.py"), "--",
                                *opts, sid], capture_output=True, text=True, encoding="utf-8", errors="replace")
            line = next((l for l in r.stdout.splitlines() if l.startswith("BATCH_SHOT")), "")
            if line.startswith("BATCH_SHOT_OK") and r.returncode == 0:
                print(f"{line}  ({time.time() - t:.1f}s wall)", flush=True)
                ok = True
                break
            tail = "\n".join((r.stdout + r.stderr).splitlines()[-6:])
            print(f"SHOT_RETRY {sid} attempt {attempt + 1} code {r.returncode}\n{tail}", flush=True)
        if not ok:
            failed.append(sid)
    print(f"DRIVE_DONE {time.time() - t_all:.0f}s failed={failed}", flush=True)


if __name__ == "__main__":
    main()
