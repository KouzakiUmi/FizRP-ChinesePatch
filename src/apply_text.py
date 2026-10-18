"""Apply translated strings to the game's ScriptableObject text assets.

This is a thin text-only wrapper around `build_patch.build()`.  It used to be a
second, independent implementation, which drifted: it compared the extraction
index's short `kind` (`AutoTalk`/`Title`) against C# class names
(`AutoTalk_Data`/`Title_Data`) and therefore silently dropped 1119 of the 1249
rows while still reporting a success count.  Delegating removes that class of
bug for good.

Usage:
    python src/apply_text.py --column zh_Hans \
        --out dist-additive/FizAndTheRainbowPlanet_Data
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_patch


def run(csv_path: str, column: str, out_dir: str,
        skip_strings: bool = False,
        allow_missing: bool = False) -> dict:
    return build_patch.build(
        out_dir=out_dir,
        translations=csv_path,
        column=column,
        skip_fonts=True,          # 只应用文本
        skip_strings=skip_strings,
        allow_missing=allow_missing,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="translation/zh_Hans.csv")
    ap.add_argument("--column", default="zh_Hans")
    ap.add_argument("--out", default="dist-additive/FizAndTheRainbowPlanet_Data")
    ap.add_argument("--skip-strings", action="store_true",
                    help="不处理 Unity Localization bundle")
    ap.add_argument("--allow-missing", action="store_true")
    args = ap.parse_args()
    print(json.dumps(run(args.csv, args.column, args.out,
                         args.skip_strings, args.allow_missing),
                     ensure_ascii=False, indent=1))
