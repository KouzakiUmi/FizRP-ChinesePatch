"""Build the 12px design-size Chinese font host used by the two big titles.

Why a *new* host instead of reusing an existing font slot
---------------------------------------------------------
The stage-select world name and the central stage title are the only texts that
are rendered large.  They need a design size that can actually draw dense CJK
strokes: at 8px the glyphs for 糖/浆/饼 have no counters left, so any integer
upscale just magnifies a solid block (verified against the v1.2.10 screenshot).
10px is usable but the stage-select box is only 32 canvas units tall, so a 1:1
render of it is smaller than the original 14px title; 12px keeps the size
comparable to the original while staying 1:1 (stage select) or 2x (movie title).

Every font slot the game still uses is taken, so the 12px face is added as a
*new* Font object in sharedassets0.assets - a file that is already part of the
payload and that every scene loads.  The face is subset to the characters the
translation actually uses (plus ASCII), which keeps it at a few hundred KB
instead of the 7 MB full zh_hans face.
"""
from __future__ import annotations

import io
import os
import zipfile

from fontTools import subset
from fontTools.ttLib import TTFont

# The 12px face carries no TrueType hinting (checked: no fpgm/prep/cvt, no
# per-glyph instructions), so subsetting keeps the outlines bit-exact and the
# pixel grid intact - the design grid comes from the outline coordinates only.
ASCII = "".join(chr(c) for c in range(0x20, 0x7F))
EXTRA = "　、。，！？：；「」『』（）《》·…—～“”‘’"


def chars_from_translation(rows) -> set:
    """Every character the Chinese text can show, plus ASCII and CJK punctuation."""
    chars: set = set()
    for row in rows:
        chars.update(row.get("zh_Hans") or "")
    chars.update(ASCII)
    chars.update(EXTRA)
    chars.discard("\n")
    chars.discard("\r")
    return chars


def extract_member(zip_path: str, member: str) -> bytes:
    with zipfile.ZipFile(zip_path) as zf:
        return zf.read(member)


def build_subset(source_ttf: bytes, chars: set, out_path: str) -> str:
    """Write a subset of `source_ttf` holding only `chars`."""
    options = subset.Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    options.recalc_bounds = True
    font = subset.load_font(io.BytesIO(source_ttf), options)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text="".join(sorted(chars)))
    subsetter.subset(font)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    subset.save_font(font, out_path, options)
    check = TTFont(out_path)
    cmap = check.getBestCmap()
    missing = [c for c in chars if ord(c) not in cmap]
    if missing:
        raise SystemExit(
            "ABORT: 12px font subset is missing %d characters (e.g. %s)"
            % (len(missing), "".join(sorted(missing)[:20])))
    return out_path
