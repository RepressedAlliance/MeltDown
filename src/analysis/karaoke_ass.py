"""Syllable timing from a karaoke .ass (\\k tags), mapped onto our lyric morae.

python karaoke_ass.py [file.ass]   -> work/analysis/karaoke/syllables.json and a comparison report
A karaoke line is "{\\k15}ma{\\k55}chi ..." from its start time: each syllable starts where the
previous one's duration (centiseconds) ends. Syllables are romaji (sometimes several morae, e.g.
"kyuu", "nai", or English spellings such as "ETHER" for a katakana loanword), so they are matched to our
morae by aligning the romaji strings; a mora inside a longer syllable gets its share of it.
"""
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
from mms_align import romaji  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
AN = ROOT / "work" / "analysis"
DEFAULT = paths.karaoke()
OUT = AN / "karaoke" / "syllables.json"
KTAG = re.compile(r"\{\\[kK][fo]?(\d+)\}([^{]*)")
LINE = re.compile(r"(?:Comment|Dialogue): \d+,(\d+):(\d+):(\d+\.\d+),(\d+):(\d+):(\d+\.\d+),"
                  r"[^,]*,[^,]*,\d+,\d+,\d+,karaoke,(.*)")


def parse(path):
    rows = []
    for raw in Path(path).read_text(encoding="utf-8-sig").splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        for k, s in KTAG.findall(m.group(7)):
            if s.strip():
                rows.append((round(t, 3), int(k) / 100, s.strip().lower()))
            t += int(k) / 100
    return rows


def our_morae(with_times=True):
    """Every mora of our lyrics in order: (line, char, mora index, kana, romaji, our note time)."""
    readings = json.loads((AN / "readings.json").read_text(encoding="utf-8"))
    lines = json.loads((AN / "lyrics_timed.json").read_text(encoding="utf-8")) if with_times else None
    out = []
    for li, rd in enumerate(readings):
        notes = {(n["c"], n["m"]): n["t"] for n in lines[li]["notes"]} if lines else {}
        for ci, ch in enumerate(rd):
            for mi, mo in enumerate(ch["m"]):
                r = romaji(mo) or ("-" if mo == "ー" else "")
                if not r:
                    continue
                out.append((li, ci, mi, mo, r, notes.get((ci, mo))))
    return out


def karaoke_times(path=DEFAULT):
    """{(line, char, mora): karaoke start time} for every mora the karaoke file covers."""
    morae = our_morae(with_times=False)
    kt, _ = match(parse(path), morae)
    return {(m[0], m[1], m[2]): t for m, t in zip(morae, kt) if t is not None}


def karaoke_line_ends(path=DEFAULT):
    """{line: when the karaoke's last syllable of that line ends} (its start + \\k duration)."""
    morae = our_morae(with_times=False)
    _, ke = match(parse(path), morae)
    out = {}
    for m, e in zip(morae, ke):
        if e is not None:
            out[m[0]] = max(out.get(m[0], 0.0), e)
    return out


def match(syl, morae):
    """Start and syllable-end time for each of our morae from the karaoke syllables, aligning the
    two romaji strings."""
    a = "".join(m[4] for m in morae)
    b, bt, be = "", [], []
    for t, d, s in syl:
        s = re.sub(r"[^a-z]", "", s.replace("ー", "-"))
        for i, ch in enumerate(s):
            b += ch
            bt.append(t + d * i / max(1, len(s)))
            be.append(t + d)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    amap, emap = {}, {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "replace"):
            for k in range(i2 - i1):
                j = min(j1 + k, j2 - 1) if tag == "replace" else j1 + k
                amap[i1 + k], emap[i1 + k] = bt[j], be[j]
    starts, ends, pos = [], [], 0
    for m in morae:
        starts.append(amap.get(pos))
        ends.append(emap.get(pos + len(m[4]) - 1))
        pos += len(m[4])
    return starts, ends


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    syl = parse(path)
    morae = our_morae()
    kt, _ = match(syl, morae)
    rows = [dict(line=m[0], char=m[1], mora=m[2], kana=m[3], ours=m[5], karaoke=t) for m, t in zip(morae, kt)]
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
    d = [r["ours"] - r["karaoke"] for r in rows if r["ours"] is not None and r["karaoke"] is not None]
    import numpy as np
    d = np.array(d)
    print(f"{len(syl)} karaoke syllables, {len(rows)} of our morae, {len(d)} compared")
    print("ours - karaoke (s): median %.3f, |diff| pct50 %.2f pct80 %.2f pct95 %.2f" %
          (np.median(d), *np.percentile(np.abs(d), [50, 80, 95])))
    print("within 0.10 s: %.0f%%   0.25 s: %.0f%%   0.50 s: %.0f%%" %
          tuple(100 * (np.abs(d) <= x).mean() for x in (0.1, 0.25, 0.5)))


if __name__ == "__main__":
    main()
