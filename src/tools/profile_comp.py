"""Profile the compositor on a few frames: wall time per frame and the top functions.

python profile_comp.py 72.3 150.2 250.0 [--top 30]
"""
import cProfile
import pstats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "comp"))
sys.path.insert(0, str(ROOT / "src"))
import render_comp  # noqa: E402
import storyboard  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 30
    times = [float(a) for a in args if a.replace(".", "", 1).isdigit()]
    shots = storyboard.resolved()
    for t in times:  # warm caches first so the profile shows steady-state cost
        render_comp.render_frame(shots, int(round(t * 24)), False)
    pr = cProfile.Profile()
    for t in times:
        f = int(round(t * 24)) + 1
        t0 = time.perf_counter()
        pr.enable()
        render_comp.render_frame(shots, f, False)
        pr.disable()
        sid = next(s["id"] for s in shots if s["t0"] <= f / 24 < s["t1"])
        print(f"frame t={f / 24:.2f} {sid}: {time.perf_counter() - t0:.2f}s", flush=True)
    st = pstats.Stats(pr)
    st.sort_stats("tottime").print_stats(top)


if __name__ == "__main__":
    main()
