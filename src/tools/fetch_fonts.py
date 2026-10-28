"""Download the OFL fonts used by the MV from the google/fonts repository."""
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "assets" / "fonts"
FAMILIES = [
    "shipporiminchob1",
    "zenoldmincho",
    "delagothicone",
    "zenkakugothicnew",
    "mplus1code",
    "jetbrainsmono",
    "bigshouldersdisplay",
    "bigshoulders",
    "instrumentserif",
]


def main():
    s = requests.Session()
    s.headers["User-Agent"] = "roshin-yuukai-mv-font-fetch"
    for fam in FAMILIES:
        r = s.get(f"https://api.github.com/repos/google/fonts/contents/ofl/{fam}", timeout=30)
        if r.status_code != 200:
            print("skip", fam, r.status_code)
            continue
        out = DEST / fam
        out.mkdir(parents=True, exist_ok=True)
        for item in r.json():
            name = item["name"]
            if not (name.endswith(".ttf") or name.endswith(".otf") or name == "OFL.txt"):
                continue
            target = out / name
            if target.exists() and target.stat().st_size == item["size"]:
                continue
            data = s.get(item["download_url"], timeout=120).content
            target.write_bytes(data)
            print("got", fam, name, len(data))


if __name__ == "__main__":
    sys.exit(main())
