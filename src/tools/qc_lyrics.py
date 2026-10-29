"""Lyric display check over the whole song, without rendering pictures.

python qc_lyrics.py [--fps 12]
Draws every line on its own small surface at each sampled time, exactly as the compositor would
(style, shot restriction, yielding), and reports:
- late or early lines: first visible later than its first note, or long before it;
- characters that are not fully shown by their note (+1 frame);
- lines cut short: gone less than 0.5 s after their last note while nothing pushed them;
- collisions: two lines visible at once with overlapping boxes;
- reading order: a vertical line shown right of an earlier vertical line still on screen.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import skia

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "src" / "comp")]
import layout2d  # noqa: E402
import render_comp as RC  # noqa: E402
import storyboard  # noqa: E402
import timeline as TL  # noqa: E402
import typo_fx  # noqa: E402

SCALE = 0.25          # draw at quarter size: positions and alpha are what matter


def draw_line(ln, t, shot):
    st = storyboard.LYRIC_STYLES.get(ln["i"])
    if not st or t < ln["start"] - 1.0 or t > ln["end"] + st.get("tail", 4.0):
        return None
    if "shots" in st and shot["id"] not in st["shots"]:
        return None
    w, h = int(RC.W * SCALE), int(RC.H * SCALE)
    surf = skia.Surface(w, h)
    c = surf.getCanvas()
    c.scale(SCALE, SCALE)
    style = st["style"]
    kw = {k: v for k, v in st.items() if k not in ("style", "tail", "melt", "glow", "glow_col", "heat", "shots",
                                                    "at_shot", "apart")}
    kw.update(st.get("at_shot", {}).get(shot["id"], {}))     # as render_comp.py: a line moved for one shot
    ln2, quick = RC._yield_to_next(ln)
    if quick is not None and style in ("tate", "impact", "whisper", "echo", "score_line"):
        kw["fade_out"] = quick
    if style == "telop":
        nxt = TL.LINES[ln["i"] + 1]["start"] if ln["i"] + 1 < len(TL.LINES) else 1e9
        layout2d.telop(c, dict(ln2, next_start=nxt), t, **kw)
    else:
        getattr(typo_fx, style)(c, ln2, t, **kw)
    a = surf.makeImageSnapshot().toarray()[..., 3].astype(np.float32) / 255
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=float, default=12)
    args = ap.parse_args()
    shots = storyboard.resolved()

    def shot_at(t):
        return next((s for s in shots if s["t0"] <= t < s["t1"]), shots[-1])

    times = np.arange(0, TL.DURATION, 1 / args.fps)
    vis = {ln["i"]: [] for ln in TL.LINES}          # (t, alpha mass, bbox)
    for t in times:
        sh = shot_at(t)
        for ln in TL.LINES:
            a = draw_line(ln, t, sh)
            if a is None:
                continue
            m = a > 0.35
            if m.sum() < 6:
                continue
            ys, xs = np.nonzero(m)
            vis[ln["i"]].append((t, float(a.sum()), (xs.min(), ys.min(), xs.max(), ys.max())))
    problems = 0
    for ln in TL.LINES:
        v = vis[ln["i"]]
        i = ln["i"]
        if not v:
            print(f"L{i:02d} never visible  {ln['text']}")
            problems += 1
            continue
        first, last = v[0][0], v[-1][0]
        last_note = max(n["t"] for n in ln["notes"])
        if first > ln["ct"][0] + 0.1:
            print(f"L{i:02d} appears late: {first:.2f} vs first note {ln['ct'][0]:.2f}")
            problems += 1
        nxt = TL.LINES[i + 1]["start"] if i + 1 < len(TL.LINES) else 1e9
        # a line whose section ends in a cut to black goes with that cut (its words must not come up again with
        # the next section): that is not early, as long as its last note was sung before the cut
        cut = next((c for c in RC._section_breaks() if last_note < c <= last + 0.25), None)   # (a 0.12 s fade)
        if last < last_note + 0.5 and last < nxt - 0.3 and cut is None:
            print(f"L{i:02d} gone early: {last:.2f}, last note {last_note:.2f}, next line {nxt:.2f}")
            problems += 1
    # collisions and reading order, frame by frame
    seen = set()
    for t in times:
        on = [(i, b) for i, v in vis.items() for (tt, _, b) in v if abs(tt - t) < 1e-6]
        for a_i, a_b in on:
            for b_i, b_b in on:
                if a_i >= b_i:
                    continue
                ov = not (a_b[2] < b_b[0] or b_b[2] < a_b[0] or a_b[3] < b_b[1] or b_b[3] < a_b[1])
                key = ("overlap", a_i, b_i)
                if ov and key not in seen:
                    seen.add(key)
                    print(f"overlap L{a_i:02d} / L{b_i:02d} at {t:.2f}")
                    problems += 1
                sa, sb = storyboard.LYRIC_STYLES.get(a_i, {}), storyboard.LYRIC_STYLES.get(b_i, {})
                if sa.get("style") == sb.get("style") == "tate" and b_b[0] > a_b[2]:
                    key = ("order", a_i, b_i)
                    if key not in seen:
                        seen.add(key)
                        print(f"reading order: L{b_i:02d} right of earlier L{a_i:02d} at {t:.2f}")
                        problems += 1
    print(f"{problems} problem(s) over {len(TL.LINES)} lines")


if __name__ == "__main__":
    main()
