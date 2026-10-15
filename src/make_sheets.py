"""Build the translator-facing worksheet from the extraction index.

Japanese is the source of truth (it is the language the game was written in),
English is carried alongside as a reference/机器翻译校核用的第二依据.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

COLUMNS = ["id", "kind", "source", "path", "comment",
           "ja_source", "en_reference", "zh_Hans"]
KIND_NOTE = {
    "localization": "Unity Localization 表（UI/菜单/结局字幕）",
    "AutoTalk": "剧情对话",
    "TextData": "短文本 / 提示 / 名单",
    "Title": "标题菜单条目",
    "DamageTalk": "战斗受击台词",
}


def main(src="translation/ALL.csv", dst="translation/zh_Hans.csv"):
    with io.open(src, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    with io.open(dst, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            comment = r["comment"] or ""
            note = KIND_NOTE.get(r["kind"], r["kind"])
            w.writerow({
                "id": r["id"],
                "kind": r["kind"],
                "source": r["source"],
                "path": r["path"],
                "comment": (note + (" | " + comment if comment else "")),
                "ja_source": r["text_ja"],
                "en_reference": r["text_en"] or r["text_en_machine"],
                "zh_Hans": "",
            })
    print(f"wrote {dst}: {len(rows)} rows, columns={COLUMNS}")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
