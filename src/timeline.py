"""Song time helpers shared by the storyboard, Blender and the compositor (pure Python).

Two timelines live side by side:
- the song's real grid: 165 BPM, constant (fitted on the drum stem, see src/analysis/grid_align.py);
  BEATS / DOWNBEATS / beat_before serve every rhythm effect, LINES the lyric display (note-level);
- the cut timeline the edit was made on, frozen in data/cut_timeline.json: L() / Le() are the line
  times of the first alignment pass and beat_near() snaps to the first-pass beat tracker (110 BPM), so
  refining the lyric timing never moves a cut (cuts then land on the 165 BPM grid, see on_grid).
"""
import bisect
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FPS = 24
_AN = ROOT / "work" / "analysis"
_audio = json.loads((_AN / "audio.json").read_text(encoding="utf-8"))
DURATION = _audio["duration"]

BPM, PHASE = 165.0, 0.07          # 16th-note grid: PHASE + k * STEP
STEP = 60.0 / BPM / 4
BEAT = 4 * STEP
BEATS = [PHASE + k * STEP for k in range(3, int((DURATION - PHASE) / STEP), 4)]   # kick on 1 and 3: k % 4 == 3
DOWNBEATS = BEATS[::4]            # bar phase of the intro (the second chorus enters half a bar later)
_CUT = json.loads((ROOT / "data" / "cut_timeline.json").read_text(encoding="utf-8"))
CUT_BEATS = _CUT["beats"]         # first-pass tracker: what the storyboard's cuts were snapped to


def _load(name):
    p = _AN / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


LINES = _load("lyrics_timed.json")
CUT_LINES = _CUT["lines"]


def L(i):
    """Start of lyric line i on the cut timeline (0-based over non-empty lines)."""
    return CUT_LINES[i][0]


def Le(i):
    return CUT_LINES[i][1]


def Ln(i):
    """Start of lyric line i as sung (its first note)."""
    return LINES[i]["ct"][0]


def greet(i, eighths=1):
    """A cut that greets line i: on the eighth-note grid, `eighths` eighths before its first note
    (a note on an off sixteenth is greeted by the eighth just before it)."""
    k = round((Ln(i) - PHASE) / STEP)
    k = k - 2 if k % 2 == 1 else k - 1
    return PHASE + (k - 2 * (eighths - 1)) * STEP


def on_grid(t):
    """The frame nearest the song's eighth note nearest t: where a cut lands on the beat grid."""
    e8 = 2 * STEP
    g = PHASE + STEP + round((t - PHASE - STEP) / e8) * e8
    return round(g * FPS) / FPS


def beat_near(t):
    """Nearest beat of the cut timeline (storyboard snapping)."""
    j = bisect.bisect_left(CUT_BEATS, t)
    cands = [CUT_BEATS[k] for k in (j - 1, j) if 0 <= k < len(CUT_BEATS)]
    return min(cands, key=lambda b: abs(b - t)) if cands else t


def beat_before(t):
    j = bisect.bisect_right(BEATS, t) - 1
    return BEATS[j] if j >= 0 else t


def beats_between(t0, t1):
    return [b for b in BEATS if t0 <= b < t1]


def accents(t0, t1, thr=0.45, gap=0.3):
    """The audible hits between t0 and t1 (song seconds): peaks of the onset envelope at or above thr, at least
    gap seconds apart (of two closer ones the stronger is kept). This song's accents are often off the beat (on
    the "and" of 1 or of 3), so an action meant to land with what is heard follows these, not the beat grid."""
    on = _audio["env"]["onset"]
    fps = _audio["fps"]
    peaks = [(f / fps, on[f]) for f in range(max(1, int(t0 * fps)), min(len(on) - 1, int(t1 * fps) + 1))
             if on[f] >= thr and on[f] >= on[f - 1] and on[f] >= on[f + 1] and t0 <= f / fps < t1]
    kept = []
    for t, v in sorted(peaks, key=lambda p: -p[1]):
        if all(abs(t - k) >= gap for k, _ in kept):
            kept.append((t, v))
    return sorted(t for t, _ in kept)


def frame(t):
    return int(round(t * FPS))


def env(name):
    return _audio["env"][name]
