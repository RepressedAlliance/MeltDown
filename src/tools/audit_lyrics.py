"""Whole-song audit of the lyric timing against the vocals, for the kinds of error a listener notices.

python audit_lyrics.py [--lrc work/analysis/lrc]
Per line it flags:
- HELD   a character placed inside a held note: the voice is sustained on one pitch and nothing
         starts there (later words pushed early when the singer holds or pauses mid-line);
- ONSET  a clear new syllable in the vocals (pitch step or consonant break, or a phrase starting
         after silence) with no character near it;
- TAIL   the line is gone while the voice (vocal stem or the processed voice in "other") goes on;
- LRC    the line starts more than 0.6 s away from the LRC files (work/analysis/lrc/*.json, lrclib
         format; only lines that start an LRC entry).
"""
import argparse
import glob
import json
import re
import sys
from pathlib import Path

import librosa
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
AN = ROOT / "work" / "analysis"
sys.path.insert(0, str(ROOT / "src"))
import timeline as TL  # noqa: E402

STEP, PHASE = TL.STEP, TL.PHASE


def load_features():
    pz = np.load(AN / "pitch.npz")
    t, midi, vp = pz["t"], pz["midi"], pz["vprob"]
    y, sr = librosa.load(ROOT / "work" / "stems" / "vocals.wav", sr=22050, mono=True)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=128)[0]
    db = 20 * np.log10(rms + 1e-9)
    db -= np.percentile(db, 99)
    n = min(len(db), len(t))
    vo = np.concatenate([np.load(f) for f in sorted((AN / "mms_vocals_other").glob("em_*.npy"))])
    spk_vo = 1 - np.exp(vo[:, 0])
    return t[:n], midi[:n], vp[:n], db[:n], spk_vo


def grid_flags(t, midi, vp, db):
    """Per 16th: is a note starting here (onset), is the voice holding one note through it (held)?"""
    rate = 1 / (t[1] - t[0])
    K = int((t[-1] - PHASE) / STEP)
    g = PHASE + np.arange(K) * STEP

    def win(arr, a, b, fn):
        i0 = np.clip(((g + a) * rate).astype(int), 0, len(arr) - 1)
        i1 = np.clip(((g + b) * rate).astype(int), 0, len(arr) - 1)
        out = np.empty(K)
        for k in range(K):
            seg = arr[i0[k]:i1[k] + 1]
            seg = seg[np.isfinite(seg)]
            out[k] = fn(seg) if len(seg) else np.nan
        return out

    before = win(midi, -0.08, -0.015, np.median)
    after = win(midi, 0.015, 0.08, np.median)
    step = np.abs(after - before)
    dip = win(vp, -0.09, 0.0, np.min)
    vp_after = win(vp, 0.01, 0.07, np.mean)
    loud_before = win(db, -0.35, -0.08, np.max)
    loud_after = win(db, 0.0, 0.1, np.max)
    voiced_around = win(vp, -0.1, 0.1, np.min)
    onset = (np.nan_to_num(step) >= 1.0) | ((np.nan_to_num(dip, nan=1) < 0.2) & (np.nan_to_num(vp_after) > 0.65)) \
        | ((loud_after - loud_before) > 15)
    held = (np.nan_to_num(voiced_around) > 0.6) & (np.nan_to_num(step, nan=9) < 0.4) & ~onset
    return g, onset, held, loud_after


def lrc_starts(lrc_dir, lines):
    """{our line: [(LRC start, slack before, slack after)]} for lines that open an LRC entry; a file
    with only whole seconds says "somewhere in that second"."""
    norm = lambda s: re.sub(r"[\s・、。!?！？「」()（）]", "", s).replace("奇麗", "綺麗")
    out = {}
    for f in sorted(glob.glob(str(lrc_dir / "*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        rows = []
        for l in (d.get("syncedLyrics") or "").splitlines():
            m = re.match(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)", l)
            if m and norm(m.group(3)):
                rows.append((int(m.group(1)) * 60 + float(m.group(2)), norm(m.group(3))))
        whole = all(abs(t - round(t)) < 1e-6 for t, _ in rows)
        slack = (0.6, 1.6) if whole else (0.6, 0.6)
        i = 0
        for t, txt in rows:
            acc, first = "", None
            while i < len(lines) and txt.startswith(acc + norm(lines[i]["text"])):
                acc += norm(lines[i]["text"])
                first = i if first is None else first
                i += 1
            if first is not None:
                out.setdefault(first, []).append((t, *slack))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lrc", default=str(AN / "lrc"))
    args = ap.parse_args()
    lines = json.loads((AN / "lyrics_timed.json").read_text(encoding="utf-8"))
    t, midi, vp, db, spk_vo = load_features()
    g, onset, held, loud = grid_flags(t, midi, vp, db)
    lrc = lrc_starts(Path(args.lrc), lines)
    char_k = sorted({n["k"] for l in lines for n in l["notes"]} | {round((ct - PHASE) / STEP) for l in lines for ct in l["ct"]})
    total = {"HELD": 0, "ONSET": 0, "TAIL": 0, "LRC": 0}
    for li, l in enumerate(lines):
        flags = []
        for n in l["notes"]:
            if n["m"] in ("ー",) or n.get("opt"):
                continue
            k = n["k"]
            if 0 <= k < len(held) and held[k] and not onset[max(0, k - 1):k + 2].any():
                flags.append(("HELD", f"{n['m']}@{n['t']:.2f}"))
        nxt = lines[li + 1]["start"] if li + 1 < len(lines) else l["end"] + 3
        k0, k1 = round((l["start"] - PHASE) / STEP), round((min(nxt, l["end"] + 2.0) - PHASE) / STEP)
        for k in range(k0 + 1, min(k1, len(onset))):
            if onset[k] and loud[k] > -30 and not any(abs(k - c) <= 1 for c in char_k[np.searchsorted(char_k, k - 2):
                                                                                        np.searchsorted(char_k, k + 3)]):
                flags.append(("ONSET", f"{PHASE + k * STEP:.2f}"))
        # voice after the line is gone and before the next one starts
        a, b = l["end"] + 0.7, nxt - 0.1
        if b - a > 0.3:
            seg = (t >= a) & (t < b)
            vstem = (db[seg] > -30).mean() if seg.any() else 0
            fr = slice(int(a * 50), int(b * 50))
            vproc = (spk_vo[fr] > 0.5).mean() if b > a else 0
            if vstem > 0.25 or vproc > 0.08:
                flags.append(("TAIL", f"{a:.2f}-{b:.2f} vocal {vstem:.0%} processed {vproc:.0%}"))
        for lt, before, after in lrc.get(li, []):
            if not (lt - before <= l["start"] <= lt + after):
                flags.append(("LRC", f"ours {l['start']:.2f} vs {lt:.2f}"))
        for f, _ in flags:
            total[f] += 1
        if flags:
            print(f"L{li:02d} {l['start']:7.2f} " + "  ".join(f"{f}:{d}" for f, d in flags))
    print("totals", total)


if __name__ == "__main__":
    main()
