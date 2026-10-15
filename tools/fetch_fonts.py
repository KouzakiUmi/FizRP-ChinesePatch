"""Download and unpack the fusion-pixel-font release used by this project."""
from __future__ import annotations

import os
import urllib.request
import zipfile

TAG = os.environ.get("FUSION_PIXEL_TAG", "2026.09.25")
BASE = "https://github.com/TakWolf/fusion-pixel-font/releases/download"
VARIANTS = ["12px-proportional", "10px-proportional", "8px-proportional"]
RAW = "work/fonts/source"
OUT = "dist/fonts/source"


def fetch():
    os.makedirs(RAW, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    for variant in VARIANTS:
        name = f"fusion-pixel-font-{variant}-ttf-v{TAG}.zip"
        dest = os.path.join(RAW, name)
        if not (os.path.exists(dest) and os.path.getsize(dest) > 1000):
            print("downloading", name)
            urllib.request.urlretrieve(f"{BASE}/{TAG}/{name}", dest)
        with zipfile.ZipFile(dest) as zf:
            for entry in zf.namelist():
                base = os.path.basename(entry)
                if entry.endswith(".ttf"):
                    open(os.path.join(OUT, base), "wb").write(zf.read(entry))
                elif base == "OFL.txt":
                    open(os.path.join(OUT, "OFL.txt"), "wb").write(zf.read(entry))
    print("fonts in", OUT)
    for f in sorted(os.listdir(OUT)):
        print("  ", f, f"{os.path.getsize(os.path.join(OUT, f)):,}")


if __name__ == "__main__":
    fetch()
