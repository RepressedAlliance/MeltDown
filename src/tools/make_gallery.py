"""README images of the film: a hero mosaic, stills, short silent loops and before/after pairs (docs/images/).

python src/tools/make_gallery.py
Every image is composited from the renders with the lyric layer left out, so the repository shows the
pictures without carrying the song's words (the HUD and titles stay). The moments are chosen in HERO,
STILLS and LOOPS below; loops are silent animated WebP at 12 fps, stills are JPEG.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "comp"))
OUT = ROOT / "docs" / "images"
FPS = 24

HERO = [21.5, 88.0, 117.6, 194.8, 233.5, 322.9]          # seconds, read left to right, top to bottom
STILLS = [17.2, 43.6, 52.6, 79.0, 104.2, 134.0, 207.8, 262.4, 312.0]
LOOPS = {"loop_opening": (6.4, 2.6), "loop_chorus": (77.6, 2.6), "loop_bridge": (192.6, 2.1)}
# before / after pairs for the making-of notes: the seventh cut's frame (kept in work/qc/before7) beside
# the same shot of this film (at t_after, after any dissolve into it), both cropped to the part the note
# is about (x, y, w, h at 1920 x 1080) and clear of the old frame's lyrics
BEFORE_AFTER = [(14.0, "bed_sitting", (0, 0, 1920, 1080), 15.2), (43.0, "arm_cut", (180, 280, 1340, 800), 43.0),
                (307.0, "bed_lying", (200, 0, 1400, 1080), 307.0)]

_shots = None


def frame(t, w=1920, h=1080):
    """The finished frame at t seconds, without the lyrics."""
    global _shots
    import render_comp
    import storyboard
    if _shots is None:
        storyboard.LYRIC_STYLES.clear()
        storyboard.EXTRA_LINES.clear()       # sung words off the lyric sheet are lyrics too
        _shots = storyboard.resolved()
    img = np.clip(render_comp.render_frame(_shots, int(round(t * FPS)), False), 0, 1)
    im = Image.fromarray((img * 255 + 0.5).astype(np.uint8))
    return im if (w, h) == im.size else im.resize((w, h), Image.LANCZOS)


def loop(name, t0, dur, w=640, h=360, fps=12):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-c:v", "libwebp_anim", "-q:v", "72", "-loop", "0",
                          str(OUT / f"{name}.webp")], stdin=subprocess.PIPE)
    for k in range(int(round(dur * fps))):
        p.stdin.write(frame(t0 + k / fps, w, h).tobytes())
    p.stdin.close()
    if p.wait():
        raise SystemExit(f"loop {name} failed")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stills").mkdir(exist_ok=True)
    (OUT / "making").mkdir(exist_ok=True)
    # hero: 3 x 2 frames with a thin paper-coloured gap
    cw, ch, gap = 640, 360, 6
    hero = Image.new("RGB", (3 * cw + 2 * gap, 2 * ch + gap), (232, 226, 212))
    for k, t in enumerate(HERO):
        hero.paste(frame(t, cw, ch), ((k % 3) * (cw + gap), (k // 3) * (ch + gap)))
    hero.save(OUT / "hero.jpg", quality=90)
    for k, t in enumerate(STILLS, 1):
        frame(t, 960, 540).save(OUT / "stills" / f"{k:02d}.jpg", quality=88)
    for name, (t, dur) in LOOPS.items():
        loop(name, t, dur)
    for t, name, (x, y, w, h), t_after in BEFORE_AFTER:
        old = ROOT / "work" / "qc" / "before7" / f"t_{t}.jpg"
        if not old.exists():
            continue
        a = Image.open(old).convert("RGB").resize((1920, 1080), Image.LANCZOS).crop((x, y, x + w, y + h))
        b = frame(t_after).crop((x, y, x + w, y + h))
        s = 900 / w
        a, b = (im.resize((900, int(round(h * s))), Image.LANCZOS) for im in (a, b))
        pair = Image.new("RGB", (2 * 900 + 8, a.height), (232, 226, 212))
        pair.paste(a, (0, 0))
        pair.paste(b, (908, 0))
        pair.save(OUT / "making" / f"{name}.jpg", quality=88)
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            print(p.relative_to(ROOT), round(p.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
