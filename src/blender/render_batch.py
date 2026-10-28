"""Render many storyboard shots in one Blender session (resumable).

blender -b --factory-startup -P render_batch.py -- [preview=1] [step=N] [pct=P] [samples=S] <shot_id|all> ...
Existing frames are skipped, so a crash or power loss only costs the frame in flight.
"""
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import common  # noqa: E402
import render_shot  # noqa: E402

def peak_commit_mib():
    import ctypes
    import ctypes.wintypes as wt

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = wt.HANDLE
    k32.K32GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
    p = PMC()
    p.cb = ctypes.sizeof(PMC)
    k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(p), p.cb)
    return p.PeakPagefileUsage / 2 ** 20


argv = sys.argv[sys.argv.index("--") + 1:]
opts = dict(a.split("=", 1) for a in argv if "=" in a)
ids = [a for a in argv if "=" not in a]
preview = opts.get("preview", "0") == "1"
step = int(opts.get("step", 1))
if ids == ["all"]:
    import storyboard
    ids = [s["id"] for s in storyboard.resolved() if s.get("scene")]
t_all = time.time()
for sid in ids:
    try:
        t = time.time()
        sc, shot, f0, f1 = render_shot.prepare(sid, preview=preview, pct=opts.get("pct"), samples=opts.get("samples"))
        out = common.ROOT / "work" / ("preview" if preview else "render") / sid
        # align preview steps to the global frame grid so shots share sample phases
        a = f0 + (-f0) % step
        common.render_frames(sc, out, a, f1, step=step, skip_existing=opts.get("force", "0") != "1")
        n = len(range(a, f1 + 1, step))
        print(f"BATCH_SHOT_OK {sid} frames={n} {time.time() - t:.1f}s peak_commit={peak_commit_mib():.0f}MiB",
              flush=True)
    except Exception:
        print(f"BATCH_SHOT_FAIL {sid}", flush=True)
        traceback.print_exc()
print(f"BATCH_DONE {time.time() - t_all:.1f}s", flush=True)
