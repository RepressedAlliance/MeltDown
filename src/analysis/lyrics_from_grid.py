"""Lyric timeline for the renderer, from the note-level alignment (grid_align.py).

python lyrics_from_grid.py   -> work/analysis/lyrics_timed.json
Per line, as before: i, text, stanza, section, start, end, ct (one time per character: when the note
of its first mora starts, s). New: ck (the same as 16th-grid indices, beats where ck % 4 == 3) and
notes (every mora's note). "っ" and "・" sit halfway to the next character. A line ends when the
voice lets go of its last note (measured on the vocal stem, at least 0.6 s after the last word),
never after the next line has begun.
The previous timeline stays in lyrics_timed_v1.json; the storyboard still cuts on it, so rendered
shots keep their frames.
"""
import json
from pathlib import Path

import librosa
import numpy as np

from readings import read_lines
from grid_align import OTHER_LINES, PHASE, STEP


ROOT = Path(__file__).resolve().parents[2]
AN = ROOT / "work" / "analysis"
OUT = AN / "lyrics_timed.json"


def voice_off(t_last, t_cap, rms_t, quiet):
    """When the voice lets go after the last note: the start of the first quiet stretch of 0.35 s
    (shorter dips are breaths or consonants inside a held phrase)."""
    i0 = np.searchsorted(rms_t, t_last + 0.12)
    i1 = np.searchsorted(rms_t, t_cap)
    run = 0
    for i in range(i0, i1):
        run = run + 1 if quiet[i] else 0
        if run * (rms_t[1] - rms_t[0]) >= 0.35:
            return float(rms_t[i - run + 1])
    return t_cap


def main():
    meta = read_lines()
    grid = json.loads((AN / "align_grid.json").read_text(encoding="utf-8"))["lines"]
    y, sr = librosa.load(ROOT / "work" / "stems" / "vocals.wav", sr=22050, mono=True)
    hop = 256
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    db = 20 * np.log10(rms + 1e-9)
    db -= np.percentile(db, 99)
    rms_t = np.arange(len(db)) * hop / sr
    quiet = db < -34
    out = []
    for ln, gl in zip(meta, grid):
        assert ln["text"] == gl["text"], (ln["i"], ln["text"], gl["text"])
        n = len(ln["text"])
        first = {}
        for note in gl["notes"]:
            first.setdefault(note["c"], note)
        ct = [first[c]["t"] if c in first else None for c in range(n)]
        ck = [first[c]["k"] if c in first else None for c in range(n)]
        for c in range(n):                      # っ / ・: halfway between their neighbours
            if ct[c] is None:
                prev = next((ct[j] for j in range(c - 1, -1, -1) if ct[j] is not None), None)
                nxt = next((ct[j] for j in range(c + 1, n) if ct[j] is not None), None)
                ct[c] = prev + 0.5 * (nxt - prev) if prev is not None and nxt is not None else (prev or nxt)
                ck[c] = round((ct[c] - PHASE) / STEP, 2)
        out.append(dict(ln, ct=[round(t, 4) for t in ct], ck=ck,
                        notes=[{"c": x["c"], "m": x["m"], "t": x["t"], "k": x["k"]} for x in gl["notes"]]))
    for i, o in enumerate(out):
        last = max(x["t"] for x in o["notes"])
        nxt = out[i + 1]["ct"][0] if i + 1 < len(out) else last + 4.0
        cap = min(nxt - 0.05, last + 4.0)
        end = last + 0.9 if o["i"] in OTHER_LINES else voice_off(last, cap, rms_t, quiet)
        o["start"] = o["ct"][0]
        # at least 0.6 s on the last word: a processed or quiet ending is still read to the end
        o["end"] = round(min(max(end, last + 0.6), cap), 3)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for o in out:
        print(f'{o["i"]:2d} {o["section"]:4s} {o["start"]:7.2f}-{o["end"]:7.2f}  {o["text"]}')


if __name__ == "__main__":
    main()
