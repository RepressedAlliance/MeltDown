"""Kana reading of every displayed lyric character, split into morae, for mora-level alignment.

python readings.py            write work/analysis/readings.json (automatic, then FIX below applies)
Each line becomes [{"c": char, "m": [mora, ...]}]: kanji carry their reading, kana themselves,
"ー" lengthens the previous vowel, "っ" is its own (silent) mora, punctuation carries no mora.
pykakasi reads words; compounds are split per kanji where the single-kanji readings add up,
otherwise by mora count. FIX holds hand corrections (particles sung as わ/え, compound splits,
song-specific readings): {line index: {character index: reading}}.
"""
import json
import re
import sys
from pathlib import Path

import pykakasi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "work" / "analysis" / "readings.json"
# stanza labels, in order (a blank line in the lyrics starts the next stanza)
SECTIONS = ["A1", "A2", "B1", "C1", "A3", "A4", "B2", "C2", "BR1", "BR2", "Q", "C3"]
SMALL = set("ゃゅょぁぃぅぇぉゎ")
PUNCT = set("、。・ 　,.!?！？「」")
KAKASI = pykakasi.kakasi()

# hand corrections, by line and character index: the readings the automatic reader gets wrong for this
# song (particles sung as わ, the sung reading of a kanji, how a compound splits between its kanji)
FIX = {
    1: {4: "ま", 5: "すい"},
    2: {4: "ご", 5: "ぜん"},
    8: {0: "きみ"},
    10: {0: "きみ", 2: "ほそ"},
    23: {9: "ひ"},
    25: {9: "せ", 10: "かい"},
    26: {0: "きみ"},
    29: {5: "わ"},
    36: {0: "と", 1: "けい"},
    37: {4: "し", 5: "かい"},
    39: {2: "ごえ"},
    41: {8: "や"},
    43: {8: "や"},
    45: {0: "ま", 1: "よ", 2: "なか"},
    51: {6: "わ"},
    53: {3: "は", 4: "ぐるま"},
    54: {6: "せ", 7: "かい"},
}


def read_lines():
    """The lyrics as [{i, text, stanza, section}], one entry per sung line."""
    stanzas, cur = [], []
    for raw in paths.lyrics().read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s:
            if cur:
                stanzas.append(cur)
                cur = []
            continue
        cur.append(s)
    if cur:
        stanzas.append(cur)
    lines = []
    for si, st in enumerate(stanzas):
        for text in st:
            lines.append({"i": len(lines), "text": text, "stanza": si,
                          "section": SECTIONS[si] if si < len(SECTIONS) else f"S{si}"})
    return lines


def hira(s):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def is_kana(c):
    return "ぁ" <= c <= "ゖ" or "ァ" <= c <= "ヺ" or c in "ーゝゞヽヾ"


def morae(reading):
    out = []
    for c in reading:
        if c in SMALL and out:
            out[-1] += c
        else:
            out.append(c)
    return out


def split_compound(chars, reading):
    """Give each kanji of a compound its share of the reading."""
    singles = [hira(KAKASI.convert(c)[0]["hira"]) if KAKASI.convert(c) else "" for c in chars]
    if "".join(singles) == reading and all(singles):
        return singles
    m = morae(reading)
    n = len(chars)
    base, extra = divmod(len(m), n)
    out, k = [], 0
    for i in range(n):
        take = base + (1 if i < extra else 0)
        take = max(1, take) if k < len(m) else 0
        out.append("".join(m[k:k + take]))
        k += take
    if k < len(m):
        out[-1] += "".join(m[k:])
    return out


def char_readings(text):
    res = []
    for seg in KAKASI.convert(text):
        orig, rd = seg["orig"], hira(seg["hira"])
        if all(is_kana(c) or c in PUNCT for c in orig):
            res += [("" if c in PUNCT else hira(c)) for c in orig]
            continue
        # kanji runs as capture groups, kana runs as literals
        runs = re.findall(r"[^ぁ-ゖァ-ヺー]+|[ぁ-ゖァ-ヺー]+", orig)
        pat = "".join("(.+?)" if not is_kana(r[0]) else re.escape(hira(r)) for r in runs) + "$"
        mt = re.match(pat, rd)
        if not mt:
            res += split_compound(list(orig), rd)
            continue
        g = iter(mt.groups())
        for r in runs:
            if is_kana(r[0]):
                res += [hira(c) for c in r]
            else:
                res += split_compound(list(r), next(g))
    return res


def main():
    lines = read_lines()
    out = []
    for ln in lines:
        text = ln["text"]
        rds = char_readings(text)
        for k, r in FIX.get(ln["i"], {}).items():
            rds[k] = r
        if len(rds) != len(text):
            raise SystemExit(f"line {ln['i']}: {len(rds)} readings for {len(text)} characters")
        out.append([{"c": c, "m": (morae(r) if r else [])} for c, r in zip(text, rds)])
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    for i, ln in enumerate(out):
        print(i, " ".join(f"{d['c']}={''.join(d['m']) or '-'}" for d in ln))


if __name__ == "__main__":
    main()
