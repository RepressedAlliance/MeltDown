"""Which character drawings each shot shows, and where the same drawing comes back.

python src/tools/pose_audit.py
Lists every shot with the drawings in it (cards, 2D scenes and their default drawings, effects, re-cut
frames), then each drawing with the shots it appears in and how close together. A drawing seen twice
should be a choice (a bookend, one continuous scene), not a shortcut: give the other shot its own pose.
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storyboard  # noqa: E402

DEFAULT = {"eye": "rin_eye_macro", "tinnitus": "rin_ears_covered", "chest_core": "rin_float"}
WALL = {"tv_wall": "rin_laugh+rin_laugh_clap+rin_tv_host+rin_face_close+rin_eye_macro"}


def strings(o, out):
    if isinstance(o, str):
        if o.startswith("rin_"):
            out.add(o)
    elif isinstance(o, dict):
        for k, v in o.items():
            if k in ("color_blink",):
                continue
            strings(v, out)
    elif isinstance(o, (list, tuple)):
        for v in o:
            strings(v, out)


rows = []
for s in storyboard.resolved():
    ps = set()
    strings({k: v for k, v in s.items() if k not in ("cam",)}, ps)
    bg = s.get("bg")
    if bg in DEFAULT and not (s.get("bg_args") or {}).get("pose"):
        ps.add(DEFAULT[bg])
    if bg in WALL:
        ps.add(WALL[bg])
    src = s.get("frames_from")
    rows.append((s["t0"], s["t1"], s["id"], s.get("scene") or ("2d:" + str(bg)), sorted(ps), src))

use = collections.defaultdict(list)
for t0, t1, sid, sc, ps, src in rows:
    m, sec = divmod(t0, 60)
    tag = f"  <- frames of {src}" if src else ""
    print(f"{int(m)}:{sec:05.2f}  {t1 - t0:5.2f}s  {sid:6} {sc:14} {', '.join(ps)}{tag}")
    for p in ps:
        use[p].append((t0, sid))
print()
for p, lst in sorted(use.items(), key=lambda kv: -len(kv[1])):
    gaps = [b[0] - a[0] for a, b in zip(lst, lst[1:])]
    print(f"{p:22} x{len(lst):2}  " + "  ".join(f"{sid}@{int(t // 60)}:{t % 60:04.1f}" for t, sid in lst)
          + (f"   (closest {min(gaps):.0f}s apart)" if gaps else ""))
