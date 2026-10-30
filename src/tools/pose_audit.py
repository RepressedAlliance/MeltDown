"""Which character drawings each shot shows, and where the same drawing comes back.

python src/tools/pose_audit.py
Lists every shot with the drawings in it (cards, 2D scenes and their default drawings, effects, re-cut
frames), then each drawing with the shots it appears in and how close together. A drawing seen twice
should be a choice (a bookend, one continuous scene), not a shortcut: give the other shot its own pose.
Last, the stop-motion check: where a shot's cards take turns (`on` intervals: one figure, unless the cards say
which with `figure`), exactly one of them must be on at every frame the shot renders: a gap is a figure that
vanishes, an overlap two drawings at once. Exits 1 if it finds either.
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


# ---------------------------------------------------------------- stop motion: one drawing at every frame
FPS = 24
bad = 0
for s in storyboard.resolved():
    groups = collections.defaultdict(list)
    for c in s.get("cards") or []:
        if isinstance(c, dict) and c.get("on") is not None:
            groups[c.get("figure", "Rin")].append(c)
    f0 = round(s["t0"] * FPS)
    f1 = round((max(s["t1"], s.get("render_to", 0.0)) + s.get("tail", 0.0)) * FPS) - 1
    for fig, cards in groups.items():
        if len(cards) < 2 and all(c["on"] and c["on"][0][0] <= s["t0"] and c["on"][-1][1] >= s["t1"] for c in cards):
            continue
        # a frame f shows a drawing whose interval holds its time (the change falls in the gap between frames)
        count = [sum(any(a <= f / FPS < b for a, b in c["on"]) for c in cards) for f in range(f0, f1 + 1)]
        holes = [f for f, n in zip(range(f0, f1 + 1), count) if n == 0]
        twice = [f for f, n in zip(range(f0, f1 + 1), count) if n > 1]
        for name, fs in (("no drawing", holes), ("two drawings", twice)):
            if fs:
                bad += 1
                print(f"PROBLEM {s['id']} ({fig}): {name} on {len(fs)} frames, "
                      f"{fs[0] / FPS:.3f}-{fs[-1] / FPS:.3f}s ({', '.join(c.get('pose', '?') for c in cards)})")
print(f"stop motion: {bad} problem(s)")
sys.exit(1 if bad else 0)
