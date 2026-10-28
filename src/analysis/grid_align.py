"""Place every sung mora on the song's 16th-note grid (165 BPM, constant: a DAW-made Vocaloid track).

python grid_align.py   -> work/analysis/align_grid.json (+ per-line report)

Vocaloid notes start on the grid and their consonants lead by 10-60 ms, so each mora picks a grid
index in one dynamic programme over the whole song instead of trusting frame-level CTC, which is
weak in the layered choruses. Evidence per (mora, grid point):
- MMS_FA letter posteriors of the mora's first letter and vowel around the point, from the vocal
  stem, from the lead alone (harmony masked, melody_mask.py) and from vocals+other (Demucs put the
  processed last line of chorus 1 into "other");
- onset strength, "something is being sung" (1 - blank) and loudness of the line's stem;
- the melody (pYIN, pitch_track.py): a pitch step or a voicing dip (unvoiced consonant) at the point.
Inside a line, gaps between notes carry a rhythm prior (8ths most common) and silent gaps cost extra
(a line is one phrase). Lines move only inside a window: the karaoke span when a karaoke file is
given (the main reference, see below), else around the frame-level MMS alignment; WINDOWS can pin a
line's span by hand when there is no karaoke file.
Lines that repeat word for word (the chorus hook ...) share one rhythm: after the first pass their
evidence is summed, the common rhythm is solved once, each copy is re-anchored, and the whole song is
solved again around them. "ー" takes its own note without letter evidence; "っ" and punctuation
get no note.
"""
import json
import sys
import warnings
from pathlib import Path

import librosa
import numpy as np

from mms_align import labels, romaji

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
AN = ROOT / "work" / "analysis"
STEMS = ROOT / "work" / "stems"
OUT = AN / "align_grid.json"
BPM, PHASE = 165.0, 0.07          # fitted on the drum stem: residual within +-6 ms all song
STEP = 60.0 / BPM / 4
BEAT_K = 3                        # grid index k is a beat when k % 4 == 3 (kick on 1 and 3 of the intro)
FPS = 50.0
W_CTC, W_ON, W_SPK, W_V, W_N, W_8TH, W_REST, W_START = 1.0, 1.6, 0.6, 1.5, 1.6, 0.25, 0.35, 2.5
VO_HANDICAP = 0.3                 # letters heard only in vocals+other count slightly less
MELODY_HANDICAP = 0.15            # ... or only in the lead with the harmony masked out (melody_mask.py)
NEG = -1e9
MAXD = 40                         # longest gap between two notes of one line, in 16ths

# lines whose voice Demucs put (mostly) into "other": their loudness/onsets come from vocals+other
OTHER_LINES = {17}
# A karaoke timing made by ear (karaoke_ass.py: \k syllables) is the main reference: it agrees with
# the audio evidence to ~30 ms wherever both are clear, and it knows how the singer phrases the
# held and processed passages the stems blur. Each mora is pulled to its karaoke time; the audio
# then puts it on the exact 16th. Lines move only inside the karaoke line span (+-0.6 s).
KARAOKE = paths.karaoke()
W_KAR, SIG_KAR = 8.0, 0.05
# Hand constraints, only for passages no reference covers: spans (s) and note times (s) per line
# (None: left to the search). With the karaoke file present there are none.
WINDOWS = {}
PINS = {}
REPEATS = [(12, 15, 30, 33, 48), (13, 31), (8, 26), (40, 42), (41, 43)]    # used only without karaoke


def rhythm_prior(d):
    table = {1: -1.2, 2: 0.0, 3: -0.8, 4: -0.5, 5: -2.0, 6: -1.0, 7: -2.4, 8: -1.0}
    return table.get(d, -2.4 - 0.04 * (d - 8))


def stem_features(path):
    y, sr = librosa.load(path, sr=22050, mono=True)
    hop = 128
    S = librosa.feature.melspectrogram(y=y, sr=sr, n_fft=2048, hop_length=hop, n_mels=128, fmax=8000)
    on = librosa.onset.onset_strength(S=librosa.power_to_db(S), sr=sr, hop_length=hop, lag=2, max_size=3)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    # onset strength relative to its local loudness (+-4 s), so quiet sections still count
    win = int(4 / (hop / sr))
    loc = np.array([np.percentile(on[max(0, i - win):i + win:8], 95) + 1e-6 for i in range(0, len(on), 64)])
    loc = np.interp(np.arange(len(on)), np.arange(0, len(on), 64), loc)
    db = 20 * np.log10(rms + 1e-9)
    return {"rate": sr / hop, "on": np.clip(on / loc, 0, 1.5), "db": db - np.percentile(db, 99)}


def reduce_win(arr, rate, g, a, b, fn, offset=0.0):
    """fn over arr[t in g+a .. g+b] for every grid time g (arr sampled at rate, t = i / rate + offset)."""
    i0 = np.clip(np.floor((g + a - offset) * rate).astype(int), 0, len(arr) - 1)
    i1 = np.clip(np.ceil((g + b - offset) * rate).astype(int), 0, len(arr) - 1)
    n = int((i1 - i0).max()) + 1
    idx = np.clip(i0[:, None] + np.arange(n)[None, :], 0, len(arr) - 1)
    v = arr[idx].astype(np.float64)
    v[idx > i1[:, None]] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return fn(v, axis=1)


LONG = {("o", "u"), ("u", "u"), ("e", "i"), ("i", "i"), ("a", "a"), ("e", "e"), ("o", "o")}


def unit_list(readings):
    """One unit per mora that starts a note: (line, char, mora, kana, letters, optional).
    A long-vowel continuation (ゆう = yū, ごう = gō, けい = kē) has no consonant to find, so it is
    timed by the melody alone, like "ー". Inside a character it is optional: Vocaloid parts often
    give it a note of its own (a pitch step), but when nothing marks one it merges into the previous
    mora (only a character's first mora is shown). "っ" has no note."""
    units = []
    for li, line in enumerate(readings):
        prev_v = None
        for ci, ch in enumerate(line):
            for mi, mo in enumerate(ch["m"]):
                if mo == "っ":
                    continue
                lets = romaji(mo)
                cont = mo == "ー" or (prev_v is not None and len(lets) == 1 and (prev_v, lets) in LONG)
                units.append((li, ci, mi, mo, "" if cont else lets, cont and mi > 0))
                if lets and not cont:
                    prev_v = lets[-1]
    return units


def build_evidence(units, lab, g):
    def em(d):
        return np.concatenate([np.load(f) for f in sorted((AN / d).glob("em_*.npy"))])

    lp_v, lp_o, lp_m = em("mms"), em("mms_vocals_other"), em("mms_vocals_melody")
    lp = np.maximum(np.maximum(lp_v, lp_o - VO_HANDICAP), lp_m - MELODY_HANDICAP)
    spk = np.maximum.reduce([1 - np.exp(lp_v[:, 0]), 0.8 * (1 - np.exp(lp_o[:, 0])), 0.9 * (1 - np.exp(lp_m[:, 0]))])
    fv, fo = stem_features(STEMS / "vocals.wav"), stem_features(STEMS / "vocals_other.wav")
    pz = np.load(AN / "pitch.npz")
    rate_p = 1.0 / (pz["t"][1] - pz["t"][0])

    def melody(z):
        """A note starts here: the pitch steps, or voicing comes back after a dip (a consonant)."""
        step = np.abs(reduce_win(z["midi"], rate_p, g, 0.015, 0.07, np.nanmedian)
                      - reduce_win(z["midi"], rate_p, g, -0.07, -0.015, np.nanmedian))
        dip = (reduce_win(z["vprob"], rate_p, g, 0.01, 0.06, np.nanmean)
               - reduce_win(z["vprob"], rate_p, g, -0.09, 0.0, np.nanmin))
        return np.maximum(np.nan_to_num(np.clip(step, 0, 1)), np.nan_to_num(np.clip(dip, 0, 1)))

    E_n = melody(pz)
    po = AN / "pitch_other.npz"
    E_n_o = melody(np.load(po)) if po.exists() else E_n
    E_spk = np.log(reduce_win(spk, FPS, g, -0.09, 0.02, np.nanmax, 0.01) + 0.02)
    eighth = np.where(np.arange(len(g)) % 2 == 1, W_8TH, 0.0)
    per_src = {}
    for name, f, en in (("v", fv, E_n), ("o", fo, E_n_o)):
        E_on = reduce_win(f["on"], f["rate"], g, -0.07, 0.03, np.nanmax)
        loud = reduce_win(f["db"], f["rate"], g, 0.0, 0.09, np.nanmax)
        E_v = np.clip((loud + 32) / 12, -2.5, 0)
        # a phrase starts here: quiet just before, singing right after (first note of a line)
        before = reduce_win(f["db"], f["rate"], g, -0.35, -0.08, np.nanmax)
        start = np.clip((loud - before) / 18.0, 0, 1)
        per_src[name] = dict(start=W_START * start,
                             base=W_ON * E_on + W_SPK * E_spk + W_V * E_v + W_N * en + eighth,
                             hold=W_V * E_v + W_N * en + eighth,
                             silent=(loud < -36) & (reduce_win(pz["vprob"], rate_p, g, 0.0, STEP, np.nanmax) < 0.3)
                             if name == "v" else np.zeros(len(g), bool))
    cache = {}

    def letter(ch, a, b):
        if (ch, a, b) not in cache:
            cache[ch, a, b] = np.clip(reduce_win(lp[:, lab[ch]], FPS, g, a, b, np.nanmax, 0.01), -9, 0)
        return cache[ch, a, b]

    ev = np.empty((len(units), len(g)), np.float32)
    for u, (li, _, _, _, lets, _) in enumerate(units):
        src = per_src["o" if li in OTHER_LINES else "v"]
        if not lets:                   # "ー": a held vowel on a new note, no letter evidence
            ev[u] = src["hold"]
            continue
        if len(lets) == 1:
            e = letter(lets[0], -0.08, 0.06)
        else:
            e = 0.5 * (letter(lets[0], -0.09, 0.03) + letter(lets[-1], -0.04, 0.09))
        ev[u] = W_CTC * e + src["base"]
        if u == 0 or units[u - 1][0] != li:
            ev[u] += src["start"]
    return ev, per_src["v"]["silent"]


def rest_cost(C, K, d):
    """Cost of a gap of d steps ending at every k: silent grid points strictly inside the gap."""
    out = np.zeros(K, np.float32)
    if d > 2:
        inside = C[d:K] - C[1:K - d + 1]          # points k-d+1 .. k-1 for k = d .. K-1
        out[d:] = W_REST * np.maximum(0, inside - 1)
    return out


def solve(units, ev, win, fixed, C):
    """Global DP: unit u on grid index k. fixed[u] = k pins a unit."""
    U, K = ev.shape
    ks = np.arange(K)
    prior = np.array([rhythm_prior(d) for d in range(1, MAXD + 1)], np.float32)
    rests = [rest_cost(C, K, d) for d in range(1, MAXD + 1)]
    D = np.full((U, K), NEG, np.float32)
    bp = np.zeros((U, K), np.int32)
    for u, (li, *_rest) in enumerate(units):
        lo, hi = win[li]
        e = np.where((ks >= lo) & (ks <= hi), ev[u], NEG).astype(np.float32)
        if u in fixed:
            e = np.where(ks == fixed[u], 0.0, NEG).astype(np.float32)
        if u == 0:
            D[u], bp[u] = e, -1
            continue
        prev = D[u - 1]
        if units[u - 1][0] != li:              # new line: any earlier end
            best = np.maximum.accumulate(np.concatenate([[NEG], prev[:-1]]).astype(np.float32))
            arg = _argrun(prev)
        else:
            best = np.full(K, NEG, np.float32)
            arg = np.zeros(K, np.int64)
            for d in range(1, MAXD + 1):
                cand = np.concatenate([np.full(d, NEG, np.float32), prev[:-d]]) + prior[d - 1] - rests[d - 1]
                better = cand > best
                best = np.where(better, cand, best)
                arg = np.where(better, ks - d, arg)
        D[u] = e + best
        bp[u] = arg
        if units[u][5] and u not in fixed:     # optional: merge into the previous note
            merge = prev > D[u]
            D[u] = np.where(merge, prev, D[u])
            bp[u] = np.where(merge, ks, bp[u])
    k = int(D[-1].argmax())
    pos = np.empty(U, np.int64)
    for u in range(U - 1, -1, -1):
        pos[u] = k
        k = bp[u, k]
    return pos


def _argrun(prev):
    """For each k: index of the maximum of prev[0 .. k-1]."""
    K = len(prev)
    out = np.zeros(K, np.int64)
    run = 0
    for k in range(1, K):
        if prev[k - 1] >= prev[run]:
            run = k - 1
        out[k] = run
    return out


def line_dp(S, sil, first_max=0, weight=1.0, opt=None):
    """Rhythm of one line from evidence S[m, r]; the first note sits at r <= first_max. weight scales
    the rhythm prior and rest cost (= number of copies when S sums several). Returns (offsets, score)."""
    n, R = S.shape
    prior = weight * np.array([rhythm_prior(d) for d in range(1, MAXD + 1)])
    C = np.concatenate([[0.0], np.cumsum(sil)])
    D = np.full((n, R), NEG)
    bp = np.zeros((n, R), np.int64)
    D[0, :first_max + 1] = S[0, :first_max + 1]
    for m in range(1, n):
        for r in range(1, R):
            best, arg = NEG, 0
            for d in range(1, min(MAXD, r) + 1):
                inside = C[r] - C[r - d + 1] if d > 2 else 0
                v = D[m - 1, r - d] + prior[d - 1] - weight * W_REST * max(0, inside - 1)
                if v > best:
                    best, arg = v, r - d
            D[m, r] = S[m, r] + best
            bp[m, r] = arg
            if opt is not None and opt[m] and D[m - 1, r] > D[m, r]:
                D[m, r], bp[m, r] = D[m - 1, r], r
    r = int(D[-1].argmax())
    score = float(D[-1, r])
    rel = [0] * n
    for m in range(n - 1, -1, -1):
        rel[m] = r
        r = bp[m, r]
    return rel, score


def tie_repeats(units, ev, pos, silent, by_line, win):
    """Shared rhythm for word-for-word repeats; returns {unit: k} pins.
    Each copy first gets its own best rhythm near its first-pass start; the copy with the strongest
    evidence is the template, the others are re-anchored to it, and the summed evidence is solved
    again. A copy whose own evidence clearly disagrees with the shared rhythm is left free."""
    K = ev.shape[1]
    R, SLACK = 84, 6
    groups = []

    def window(us, a):
        """Evidence of one copy from grid index a on; outside the line's window nothing fits."""
        seg = np.full((len(us), R), NEG / 100)
        wlo, whi = win[units[us[0]][0]]
        lo, hi = max(0, a, wlo), min(K, a + R, whi + 1)
        if hi > lo:
            seg[:, lo - a:hi - a] = ev[us, lo:hi]
        sil = np.zeros(R)
        sil[lo - a:hi - a] = silent[lo:hi]
        return seg, sil

    def fit(us, rel, a0):
        best = None
        wlo, whi = win[units[us[0]][0]]
        for c in range(a0 - 8, a0 + 9):
            if c < wlo or c + rel[-1] > whi:
                continue
            sc = float(sum(ev[u, c + r] for u, r in zip(us, rel)))
            if best is None or sc > best[0]:
                best = (sc, c)
        return best

    for group in REPEATS:
        inst = [by_line[li] for li in group]
        assert len({len(us) for us in inst}) == 1, group
        own = []
        for us in inst:
            a = int(pos[us[0]]) - SLACK
            rel, sc = line_dp(*window(us, a), first_max=2 * SLACK, opt=[units[u][5] for u in us])
            own.append((sc, a + rel[0], [r - rel[0] for r in rel]))
        tmpl = max(range(len(inst)), key=lambda i: own[i][0] / len(inst[i]))
        rel = own[tmpl][2]
        anchors = [(fit(us, rel, o[1]) or (0, o[1]))[1] for us, o in zip(inst, own)]
        for _ in range(2):
            S = np.zeros((len(rel), R))
            sil = np.zeros(R)
            for us, a in zip(inst, anchors):
                seg, sl = window(us, a)
                S += seg
                sil += sl
            rel, _ = line_dp(S, sil, weight=len(inst), opt=[units[u][5] for u in inst[0]])
            anchors = [(fit(us, rel, a) or (0, a))[1] for us, a in zip(inst, anchors)]
        kept, pins = [], {}
        for li, us, a, o in zip(group, inst, anchors, own):
            f = fit(us, rel, a)
            if f is None or f[0] < o[0] - 1.5:
                continue
            kept.append(li)
            for u, r in zip(us, rel):
                pins[u] = a + r
        print("tied", group, "own", [round(o[0], 1) for o in own], "shared", [round((fit(us, rel, a) or (NEG, 0))[0], 1) for us, a in zip(inst, anchors)])
        print("tied", group, "kept", kept, "rhythm", " ".join(str(b - a) for a, b in zip(rel, rel[1:])),
              "starts", " ".join(f"{PHASE + a * STEP:.2f}" for a in anchors))
        groups.append((group, pins))
    return groups


def main():
    lab = labels()
    readings = json.loads((AN / "readings.json").read_text(encoding="utf-8"))
    mms = json.loads((AN / "align_mms.json").read_text(encoding="utf-8"))
    n_frames = sum(np.load(f, mmap_mode="r").shape[0] for f in (AN / "mms").glob("em_*.npy"))
    K = int((n_frames / FPS - PHASE) / STEP)
    g = PHASE + np.arange(K) * STEP
    units = unit_list(readings)
    by_line = {}
    for u, un in enumerate(units):
        by_line.setdefault(un[0], []).append(u)
    ev, silent = build_evidence(units, lab, g)
    C = np.concatenate([[0], np.cumsum(silent)]).astype(np.float32)
    kar = {}
    if KARAOKE:
        from karaoke_ass import karaoke_times
        kar = karaoke_times(KARAOKE)
        for u, (li, ci, mi, *_rest) in enumerate(units):
            if (li, ci, mi) in kar:
                ev[u] += W_KAR * np.exp(-0.5 * ((g - kar[li, ci, mi]) / SIG_KAR) ** 2).astype(np.float32)
        print(f"karaoke reference: {sum((un[0], un[1], un[2]) in kar for un in units)} of {len(units)} morae")
    win = []
    for li, m in enumerate(mms):
        kt = [t for (l2, _, _), t in kar.items() if l2 == li]
        if li in WINDOWS:
            a, b = WINDOWS[li]
        elif kt:
            a, b = min(kt) - 0.6, max(kt) + 0.6
        else:
            a, b = m["start"] - 1.5, m["last"] + 1.5
        win.append((max(0, int(np.ceil((a - PHASE) / STEP))), min(K - 1, int((b - PHASE) / STEP))))
    pins = {}
    for li, times in PINS.items():
        req = [u for u in by_line[li] if not units[u][5]]
        assert len(req) == len(times), (li, len(req), len(times))
        for u, t in zip(req, times):
            if t is not None:
                pins[u] = int(round((t - PHASE) / STEP))
    pos = solve(units, ev, win, pins, C)
    for group, gp in ([] if kar else tie_repeats(units, ev, pos, silent, by_line, win)):
        trial = {**pins, **gp}
        tied = solve(units, ev, win, trial, C)
        d = np.diff(tied)
        opt = np.array([un[5] for un in units[1:]])
        if np.all((d > 0) | (opt & (d == 0))) and all(tied[u] == k for u, k in trial.items()):
            pins, pos = trial, tied
        else:
            print("could not keep the shared rhythm of", group)
    out = []
    for li, line in enumerate(readings):
        us = by_line[li]
        out.append({"i": li, "text": "".join(c["c"] for c in line),
                    "notes": [{"c": units[u][1], "m": units[u][3], "k": int(pos[u]), "t": round(float(g[pos[u]]), 4),
                               "ev": round(float(ev[u, pos[u]]), 2)} for u in us]})
    OUT.write_text(json.dumps({"bpm": BPM, "phase": PHASE, "beat_k": BEAT_K, "lines": out}, ensure_ascii=False,
                              indent=1), encoding="utf-8")
    for o, m in zip(out, mms):
        t0 = o["notes"][0]["t"]
        steps = [b["k"] - a["k"] for a, b in zip(o["notes"], o["notes"][1:])]
        print(f'{o["i"]:2d} start {t0:7.2f}  mms {m["start"]:7.2f}  '
              f'ev {np.mean([n["ev"] for n in o["notes"]]):5.2f}  rhythm {" ".join(map(str, steps))}')


if __name__ == "__main__":
    main()
