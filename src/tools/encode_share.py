"""The share version of the film: x264 crf 19 (about half the master's size), audio copied, fast start.

python src/tools/encode_share.py [master] [out]
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out" / "roshin_yuukai_mv.mp4"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name(src.stem + "_share.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-c:v", "libx264", "-preset", "slow", "-crf", "19",
                    "-tune", "film", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(dst)],
                   check=True)
    print("wrote", dst, round(dst.stat().st_size / 1e6), "MB")


if __name__ == "__main__":
    main()
