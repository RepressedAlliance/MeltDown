"""Rebuild work/analysis/lyrics_timed.json from the timing that ships with the repository
(data/lyrics_timing.json: when every character and note of the song is sung, without the words) and
the lyrics you bring yourself (input/lyrics.txt), so the film renders without running the alignment.

python src/analysis/apply_timing.py
Stops at the first line whose length differs from the timed one (a different lyric version).
For another song, run the alignment instead (docs: 制作流程.md, "歌词逐字对齐").
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readings import FIX, char_readings, morae, read_lines  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "lyrics_timing.json"
OUT = ROOT / "work" / "analysis" / "lyrics_timed.json"


def main():
    timed = json.loads(DATA.read_text(encoding="utf-8"))["lines"]
    lines = read_lines()
    if len(lines) != len(timed):
        raise SystemExit(f"the lyrics have {len(lines)} sung lines, the timing {len(timed)}")
    out = []
    for ln, tm in zip(lines, timed):
        text = ln["text"]
        if len(text) != tm["n"]:
            raise SystemExit(f"line {ln['i'] + 1}: {len(text)} characters, the timing expects {tm['n']}: {text}")
        rds = char_readings(text)
        for k, r in FIX.get(ln["i"], {}).items():
            rds[k] = r
        mor = [morae(r) if r else [] for r in rds]
        out.append({"i": ln["i"], "text": text, "stanza": ln["stanza"], "section": ln["section"],
                    "ct": tm["ct"], "ck": tm["ck"],
                    "notes": [{"c": c, "m": mor[c][j], "t": t, "k": k} for c, j, t, k in tm["notes"]],
                    "start": tm["start"], "end": tm["end"]})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", OUT, len(out), "lines")


if __name__ == "__main__":
    main()
