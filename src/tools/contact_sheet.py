"""Tile images (RGBA composited over grey) into one preview sheet."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def main():
    out = Path(sys.argv[1])
    files = [Path(p) for p in sys.argv[2:]]
    cell = 512
    cols = min(4, len(files))
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 20)), (60, 60, 66))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGBA")
        im.thumbnail((cell, cell))
        bg = Image.new("RGBA", im.size, (110, 110, 118, 255))
        bg.alpha_composite(im)
        x, y = (i % cols) * cell, (i // cols) * (cell + 20)
        sheet.paste(bg.convert("RGB"), (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        d.text((x + 4, y + cell + 4), f.stem, fill=(230, 230, 230))
    sheet.save(out)


if __name__ == "__main__":
    main()
