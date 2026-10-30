"""Does every cut land on a hit you can hear? (cut_report.py checks the 8th-note grid; this checks the drums.)

python src/tools/cut_hits.py [--all]
On the grid is not on the music: this song's hits are mostly syncopated (the "and" of a beat), and cuts placed
an eighth before the singing from an older alignment of the lyrics landed between the hits (the director: "没对上
音乐 也没对上节奏"). For every cut this lists the drum hits within 0.35 s (timeline's drum onsets), each scored by
its attack (the onset envelope) and its weight (the low band), and says whether the cut is ON a hit (within a
frame, 0.6 or more: timeline.on_a_hit), MISSES a strong one (0.75) nearby, or sits where the drums are quiet. Transitions (dissolves, fades)
are listed with their kind: a fade's start and end can carry it. Exits 1 if any plain cut misses a strong hit.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import storyboard  # noqa: E402
import timeline as TL  # noqa: E402

FPS = 24
WINDOW = 0.35
STRONG = 0.75


strength = TL.hit_strength


def beat_pos(t):
    k = round((t - TL.PHASE) / TL.STEP)
    return ((k - 3) % 16) / 4 + 1


def main():
    show_all = "--all" in sys.argv
    hits = sorted(TL._audio.get("kicks", []))
    shots = storyboard.resolved()
    misses = 0
    for a, b in zip(shots, shots[1:]):
        c = round(b["t0"] * FPS) / FPS                       # the cut, at the frame the new shot owns
        kind = b.get("in") or "cut"
        near = [(h, *strength(h)) for h in hits if abs(h - c) <= WINDOW]
        best = max(near, key=lambda x: x[1]) if near else None
        if not near:
            verdict = "quiet"
        elif TL.on_a_hit(c):
            verdict = "on"
        elif best[1] >= STRONG:
            verdict = "MISSES"
        else:
            verdict = "between"
        bad = verdict == "MISSES" and kind in ("cut", None)
        misses += bad
        if show_all or verdict in ("MISSES", "between"):
            m, s = divmod(c, 60)
            desc = "  ".join(f"{h - c:+.3f}s b{beat_pos(h):.2f} {st:.2f}" for h, st, _, _ in near)
            print(f"{a['id']:>5}>{b['id']:<5} {int(m)}:{s:05.2f} b{beat_pos(c):.2f} {kind:8s} {verdict:7s}"
                  + (f"  best {best[0] - c:+.3f}s ({best[1]:.2f})" if best else "") + f"   [{desc}]")
    print(f"cut hits: {misses} plain cut(s) miss a clearly stronger hit")
    sys.exit(1 if misses else 0)


if __name__ == "__main__":
    main()
