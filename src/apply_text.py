"""Apply translated strings to the game's ScriptableObject text assets.

This is a thin text-only wrapper around `build_patch.build()`.  It used to be a
second, independent implementation, which drifted: it compared the extraction
index's short `kind` (`AutoTalk`/`Title`) against C# class names
(`AutoTalk_Data`/`Title_Data`) and therefore silently dropped 1119 of the 1249
rows while still reporting a success count.  Delegating removes that class of
bug for good.

Usage:
    python src/apply_text.py --column text_zh_Hans --lang-slot 2 \
        --out dist/legacy/X1/FizAndTheRainbowPlanet_Data
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_patch


def run(csv_path: str, column: str, slot: int, out_dir: str,
        locale_code: str = "en", skip_strings: bool = False,
        allow_missing: bool = False) -> dict:
    return build_patch.build(
        out_dir=out_dir,
        translations=csv_path,
        column=column,
        slot=slot,
        locale_code=locale_code,
        skip_fonts=True,          # 只应用文本
        skip_strings=skip_strings,
        allow_missing=allow_missing,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="translation/ALL.csv")
    ap.add_argument("--column", default="text_zh_Hans")
    ap.add_argument("--lang-slot", type=int, default=2,
                    help="Language 枚举槽位：0=ja 1=en_machine 2=en 3=fr 4=es")
    ap.add_argument("--locale", default="en", help="目标 locale 代码")
    ap.add_argument("--out", default="dist/legacy/X1/FizAndTheRainbowPlanet_Data")
    ap.add_argument("--skip-strings", action="store_true",
                    help="不处理 Unity Localization bundle")
    ap.add_argument("--allow-missing", action="store_true")
    args = ap.parse_args()
    print(json.dumps(run(args.csv, args.column, args.lang_slot, args.out,
                         args.locale, args.skip_strings, args.allow_missing),
                     ensure_ascii=False, indent=1))
