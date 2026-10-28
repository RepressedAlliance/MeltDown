"""Which composited segments are older than what they are made of: prints the --redo list for
render_parallel.py.

python src/tools/stale_segments.py [--also S65c]
A segment is stale when any frame it reads changed after it was written: its own Blender frames, the
frames it re-cuts from another shot (frames_from), the outgoing shot it dissolves or zooms from
(iris / dissolve / zoom transitions render that shot under the cut), or the earlier shots whose frames
drift through it (the "memories" effect).
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import storyboard  # noqa: E402

FPS = 24
# the shots whose frames the "memories" effect floats through the picture (src/comp/render_comp.py)
MEMORY_SOURCES = ["S05", "S09", "S11", "S17", "S30", "S35", "S16", "S32"]


def newest(shot_id):
    d = ROOT / "work" / "render" / shot_id
    if not d.exists():
        return 0.0
    return max((p.stat().st_mtime for p in d.glob("*.jpg")), default=0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--also", default="", help="shots to add regardless (e.g. a comp-only change)")
    args = ap.parse_args()
    shots = storyboard.resolved()
    total = int(round(storyboard.DURATION * FPS))
    starts = [int(round(s["t0"] * FPS)) for s in shots] + [total]
    stale = []
    for k, s in enumerate(shots):
        # the segment render_parallel.py would join for this cut (same name rule)
        seg = ROOT / "work" / "segments" / f"shot_{s['id']}_{starts[k]:05d}_{starts[k + 1]:05d}.mp4"
        if not seg.exists():
            stale.append(s["id"])
            continue
        t_seg = seg.stat().st_mtime
        srcs = [s["id"]]
        if s.get("frames_from"):
            srcs.append(s["frames_from"]["id"])
        if any(fx.get("type") == "memories" for fx in s.get("fx", [])):
            srcs += MEMORY_SOURCES
        if s.get("in") in ("iris", "dissolve", "zoom") and k > 0:
            prev = shots[k - 1]
            srcs.append(prev["id"])
            if prev.get("frames_from"):
                srcs.append(prev["frames_from"]["id"])
        if any(newest(x) > t_seg for x in srcs):
            stale.append(s["id"])
    stale += [x for x in args.also.split(",") if x and x not in stale]
    print(",".join(stale))
    print(len(stale), "of", len(shots), "segments to redo", file=sys.stderr)


if __name__ == "__main__":
    main()
