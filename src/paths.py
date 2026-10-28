"""Where the inputs you bring yourself live. Nothing here is in the repository: the song, its lyrics and
any timing references belong to their authors.

  input/song.m4a      the song (any format ffmpeg reads; the first input/song.* is used)
  input/lyrics.txt    the lyrics, one sung line per line, a blank line between stanzas
  input/karaoke.ass   optional: a karaoke file timed by ear ({\\k} syllables), the main timing reference
  input/lrc/          optional: LRC files (or lrclib / NetEase JSON) to cross-check line starts

The working copy this film was made in kept the song and lyrics at the repository root and the
references under work/analysis/; those places are still searched.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "input"
WORK = ROOT / "work"
AN = WORK / "analysis"


def _first(*patterns):
    for folder, pattern in patterns:
        hits = sorted(folder.glob(pattern)) if folder.exists() else []
        if hits:
            return hits[0]
    return None


def song():
    p = _first((INPUT, "song.*"), (ROOT, "*.m4a"), (ROOT, "*.mp3"), (ROOT, "*.flac"))
    if p is None:
        raise SystemExit("no song: put it in input/ (for example input/song.m4a)")
    return p


def song_wav():
    """The song as 44.1 kHz stereo 16-bit WAV for the analysis (made once with ffmpeg)."""
    out = WORK / "song.wav"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(song()), "-ar", "44100", "-ac", "2",
                        "-c:a", "pcm_s16le", str(out)], check=True)
    return out


def lyrics():
    p = _first((INPUT, "lyrics.txt"), (ROOT, "炉心融解.txt"))
    if p is None:
        raise SystemExit("no lyrics: put them in input/lyrics.txt (one sung line per line)")
    return p


def karaoke():
    """The karaoke reference, or None (the alignment then falls back to its acoustic line windows)."""
    return _first((INPUT, "karaoke.ass"), (AN / "karaoke", "*.ass"))


def lrc_dir():
    return _first((INPUT, "lrc"), (AN, "lrc"))
