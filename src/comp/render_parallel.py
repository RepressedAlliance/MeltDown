"""Composite the film in parallel segments, then join them and add the song.

python render_parallel.py [--workers N] [--preview] [--out PATH] [--redo S23,S24|all]
One segment per shot, so a revised shot re-renders alone: finished segments are reused when
their frame count matches, and --redo forces the listed shots. The join uses the explicit list
of this cut's segments, never whatever happens to lie in the folder.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))

import storyboard  # noqa: E402
import timeline as TL  # noqa: E402

FPS = 24
import paths  # noqa: E402

SONG = paths.song()


def frames_in(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                        "stream=nb_read_packets", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--redo", default="", help="comma list of shot ids to re-render, or 'all'")
    ap.add_argument("--x264-threads", default=None, help="encoder threads per worker (1 when RAM is tight)")
    ap.add_argument("--x264-lookahead", default=None)
    args = ap.parse_args()
    if args.x264_threads:
        os.environ["MV_X264_THREADS"] = args.x264_threads
    if args.x264_lookahead:
        os.environ["MV_X264_LOOKAHEAD"] = args.x264_lookahead
    shots = storyboard.resolved()
    total = int(round(TL.DURATION * FPS))
    starts = [int(round(s["t0"] * FPS)) for s in shots] + [total]
    # a segment's frames all belong to its own shot (render_comp gives each frame to the shot that owns it by
    # the same rounding), so re-rendering a shot never touches the segment after it
    redo = {s.strip() for s in args.redo.split(",") if s.strip()}
    segdir = ROOT / "work" / ("segments_preview" if args.preview else "segments")
    segdir.mkdir(parents=True, exist_ok=True)
    segs, jobs = [], []
    for k, s in enumerate(shots):
        a, b = starts[k], starts[k + 1]
        if b <= a:
            continue
        # named by shot and frame range only, so inserting a shot does not rename (and re-render) the rest
        out = segdir / f"shot_{s['id']}_{a:05d}_{b:05d}.mp4"
        segs.append(out)
        if "all" not in redo and s["id"] not in redo and out.exists() and frames_in(out) == b - a:
            continue
        cmd = [sys.executable, str(HERE / "render_comp.py"), "--from", f"{a / FPS:.6f}", "--to", f"{b / FPS:.6f}",
               "--out", str(out), "--noaudio"] + (["--preview"] if args.preview else [])
        jobs.append((out, cmd, b - a))
    print(f"{len(jobs)} of {len(segs)} shot segments to render", flush=True)
    # longest first so the pool finishes together
    jobs.sort(key=lambda j: -j[2])
    running = []
    t0 = time.time()
    while jobs or running:
        while jobs and len(running) < args.workers:
            out, cmd, n = jobs.pop(0)
            print("start", out.name, n, "frames", flush=True)
            running.append((out, subprocess.Popen(cmd, stdout=subprocess.DEVNULL), n))
        time.sleep(2)
        for item in list(running):
            out, p, n = item
            if p.poll() is not None:
                running.remove(item)
                got = frames_in(out) if out.exists() else -1
                print(f"done {out.name} code={p.returncode} frames={got}/{n} t={time.time() - t0:.0f}s", flush=True)
                if p.returncode != 0 or got != n:
                    for _, q, _ in running:
                        q.wait()
                    raise SystemExit(f"segment failed: {out.name}")
    lst = segdir / "list.txt"
    lst.write_text("".join(f"file '{s.as_posix()}'\n" for s in segs), encoding="utf-8")
    out = Path(args.out or (ROOT / "out" / ("preview.mp4" if args.preview else "roshin_yuukai_mv.mp4")))
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i",
                        str(SONG), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
                        "-movflags", "+faststart", "-shortest", str(out)])
    if r.returncode != 0:
        raise SystemExit("concat failed")
    print("wrote", out, f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
