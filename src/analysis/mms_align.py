"""Mora-level forced alignment of the lyrics to the vocal stem, from MMS_FA CTC emissions.

python mms_align.py [margin_s]   -> work/analysis/align_mms.json and a per-line report
Every mora of readings.json is romanized (Hepburn letters, the model's alphabet) and the whole
song is aligned in one Viterbi pass: standard CTC within a line, and between lines a gap state
that can also take any frame at a fixed "garbage" cost, so breaths, backing vocals or effects
that leak into the stem are not forced onto lyric letters. Each line may only move within
margin_s (default 3 s) of its span in the karaoke file, when there is one (see paths.py).
Mora onset = first frame of its first letter; "ー", "っ" and punctuation carry no letters.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
AN = ROOT / "work" / "analysis"
EMDIR = AN / "mms"
READINGS = AN / "readings.json"
OUT = AN / "align_mms.json"
FPS = 50.0
GARBAGE = 2.3          # -log p of a gap frame explained as "not lyrics"

BASE = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "を": "o", "ん": "n", "ゔ": "vu",
    "ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o",
    "ゃ": "ya", "ゅ": "yu", "ょ": "yo", "ゎ": "wa",
}


def romaji(mora):
    if mora in ("ー", "っ"):
        return ""
    if len(mora) == 2 and mora[1] in "ゃゅょ":
        head, v = BASE[mora[0]], BASE[mora[1]][1]
        return head[:-1] + v if head in ("shi", "chi", "ji") else head[:-1] + "y" + v
    if len(mora) == 2 and mora[1] in "ぁぃぅぇぉ":
        return BASE[mora[0]][:-1] + BASE[mora[1]]
    return "".join(BASE[c] for c in mora)


def labels():
    import torchaudio
    return torchaudio.pipelines.MMS_FA.get_dict(star=None)


def load_emissions():
    files = sorted(EMDIR.glob("em_*.npy"))
    return np.concatenate([np.load(f) for f in files])


def build_tokens(readings, lab):
    """Flat letter list; meta[k] = (line, char, mora) of letter k."""
    toks, meta = [], []
    for li, line in enumerate(readings):
        for ci, ch in enumerate(line):
            for mi, mo in enumerate(ch["m"]):
                for letter in romaji(mo):
                    toks.append(lab[letter])
                    meta.append((li, ci, mi))
    return np.array(toks), meta


def viterbi(lp, toks, meta, windows):
    """CTC Viterbi; blank states between lines also accept garbage. windows[line] = (f0, f1)."""
    T, N = len(lp), len(toks)
    S = 2 * N + 1
    lab = np.zeros(S, np.int64)
    lab[1::2] = toks
    line_of = np.empty(S, np.int64)
    tl = np.array([m[0] for m in meta])
    line_of[1::2] = tl
    line_of[0::2] = np.concatenate([[tl[0]], tl])      # blank before token k belongs to its line
    gap = np.zeros(S, bool)
    gap[0] = gap[-1] = True
    gap[2:-1:2] = tl[1:] != tl[:-1]                    # blank between two lines
    line_of[gap] = -1
    lo = np.full(S, 0)
    hi = np.full(S, T - 1)
    for s in range(S):
        if line_of[s] >= 0:
            lo[s], hi[s] = windows[line_of[s]]
    skip = np.zeros(S, bool)
    skip[3::2] = toks[1:] != toks[:-1]
    neg = -1e30
    delta = np.full(S, neg)
    bp = np.zeros((T, S), np.int8)

    def frame_cost(t):
        c = lp[t, lab]
        c[gap] = np.maximum(c[gap], -GARBAGE)
        c[(t < lo) | (t > hi)] = neg
        return c

    c0 = frame_cost(0)
    delta[0], delta[1] = c0[0], c0[1]
    for t in range(1, T):
        a = delta
        b = np.concatenate([[neg], delta[:-1]])
        c = np.concatenate([[neg, neg], delta[:-2]])
        c[~skip] = neg
        stack = np.stack([a, b, c])
        arg = stack.argmax(0)
        delta = stack[arg, np.arange(S)] + frame_cost(t)
        bp[t] = arg
    s = S - 1 if delta[S - 1] >= delta[S - 2] else S - 2
    path = np.empty(T, np.int64)
    for t in range(T - 1, -1, -1):
        path[t] = s
        s -= int(bp[t, s])
    return path


def greedy(lp, f0, f1, inv):
    """Free decoding of frames f0..f1: [(time, letters)] for a quick look at what was sung."""
    am = lp[f0:f1].argmax(1)
    out, prev = [], 0
    for k, a in enumerate(am):
        if a != prev and a != 0:
            out.append((round((f0 + k) / FPS, 2), inv[a]))
        prev = a
    return out


def line_windows(n_lines, margin):
    """Where each line may be sung, in seconds: its karaoke span widened by margin, or anywhere."""
    kp = paths.karaoke()
    if kp is None:
        return [(0.0, 1e9)] * n_lines
    from karaoke_ass import karaoke_line_ends, karaoke_times
    kt, ke = karaoke_times(kp), karaoke_line_ends(kp)
    out = []
    for li in range(n_lines):
        ts = [t for (l2, _, _), t in kt.items() if l2 == li]
        out.append((min(ts) - margin, ke.get(li, max(ts)) + margin) if ts else (0.0, 1e9))
    return out


def main():
    margin = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    lab = labels()
    inv = {v: k for k, v in lab.items()}
    lp = load_emissions()
    readings = json.loads(READINGS.read_text(encoding="utf-8"))
    T = len(lp)
    toks, meta = build_tokens(readings, lab)
    windows = [(max(0, int(a * FPS)), min(T - 1, int(b * FPS))) for a, b in line_windows(len(readings), margin)]
    path = viterbi(lp, toks, meta, windows)
    # first frame on each letter state; frame-level confidence at the letter's best frame
    first = np.full(len(toks), -1)
    best = np.full(len(toks), -1e9)
    for t, s in enumerate(path):
        if s % 2 == 1:
            k = s // 2
            if first[k] < 0:
                first[k] = t
            best[k] = max(best[k], lp[t, toks[k]])
    lines = []
    for li, line in enumerate(readings):
        morae = []
        for ci, ch in enumerate(line):
            for mi, mo in enumerate(ch["m"]):
                ks = [k for k, m in enumerate(meta) if m == (li, ci, mi)]
                if not ks:
                    morae.append({"c": ci, "m": mo, "t": None})
                    continue
                morae.append({"c": ci, "m": mo, "t": round(first[ks[0]] / FPS, 3),
                              "conf": round(float(np.exp(max(best[k] for k in ks))), 3),
                              "frames": [int(first[k]) for k in ks]})
        ts = [m["t"] for m in morae if m["t"] is not None]
        confs = [m["conf"] for m in morae if m["t"] is not None]
        last = max(int(f) for m in morae if m["t"] is not None for f in m["frames"])
        lines.append({"i": li, "text": "".join(c["c"] for c in line), "start": ts[0],
                      "last": round(last / FPS, 3), "conf": round(float(np.median(confs)), 3),
                      "low": int(sum(c < 0.1 for c in confs)), "morae": morae})
    OUT.write_text(json.dumps(lines, ensure_ascii=False, indent=1), encoding="utf-8")
    for ln in lines:
        print(f'{ln["i"]:2d} start {ln["start"]:7.2f}  last {ln["last"]:7.2f}  conf {ln["conf"]:.2f}'
              f'  low {ln["low"]:2d}/{len(ln["morae"])}')
    if len(sys.argv) > 2:
        for span in sys.argv[2:]:
            a, b = (float(x) for x in span.split("-"))
            print(span, " ".join(f"{t}:{s}" for t, s in greedy(lp, int(a * FPS), int(b * FPS), inv)))


if __name__ == "__main__":
    main()
