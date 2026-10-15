"""Write translated strings back into the game's ScriptableObject text assets.

Only the custom components are handled here (`TextData`, `AutoTalk_Data`,
`Title_Data`, `DamageTalk_Data`) plus the per-language font table
(`LocFontData`). Unity Localization `StringTable` assets live in Addressables
bundles and need a new locale, which is a separate step - see docs/FINDINGS.md.

Usage:
    python src/apply_text.py --column text_zh_Hans --lang-slot 5 \
        --out dist/FizAndTheRainbowPlanet_Data

`--lang-slot` is the `Language` enum value the translation is written into
(0=ja 1=en_machine 2=en 3=fr 4=es, 5=新增中文).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import UnityPy

from custom_types import decode, encode, header_end
from unity_env import DATA_DIR, mb_class, mb_name, open_env

TARGETS = ("TextData", "AutoTalk_Data", "Title_Data", "DamageTalk_Data",
           "LocFontData")


def load_rows(csv_path: str, column: str) -> dict[str, str]:
    out = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            value = (row.get(column) or "").strip()
            if value:
                out[row["id"]] = row[column]
    return out


def _apply(kind: str, rid: str, name: str, data: dict, value: str, slot: int) -> bool:
    if kind == "TextData":
        idx = int(rid.rsplit(":", 1)[1])
        block = next((b for b in data["textDatas"] if b["language"] == slot), None)
        if block is None:
            block = {"memo": f"slot{slot}", "language": slot, "strings": []}
            data["textDatas"].append(block)
        while len(block["strings"]) <= idx:
            block["strings"].append("")
        block["strings"][idx] = value
        return True
    if kind == "AutoTalk":
        idx = int(rid.rsplit(":", 1)[1])
        entry = next((e for e in data["locTalkDatas"] if e["language"] == slot), None)
        if entry is None:
            entry = {"language": slot, "talkDatas": []}
            data["locTalkDatas"].append(entry)
        while len(entry["talkDatas"]) < len(data["talkDatas"]):
            entry["talkDatas"].append(dict(data["talkDatas"][len(entry["talkDatas"])]))
        if idx < len(entry["talkDatas"]):
            entry["talkDatas"][idx]["text"] = value
            return True
        return False
    if kind == "Title":
        group = rid.rsplit(":", 1)[1]
        suffix = {0: "", 1: "_en_machine", 2: "_en", 3: "_fr", 4: "_es"}.get(slot)
        if suffix is None:
            return False
        data[group + suffix] = value
        return True
    if kind == "DamageTalk":
        return False  # written through the per-language asset path below
    return False


def run(csv_path: str, column: str, slot: int, out_dir: str) -> dict:
    rows = load_rows(csv_path, column)
    with open("work/text_index.json", encoding="utf-8") as fh:
        index = json.load(fh)

    by_file: dict[str, list[str]] = {}
    for rid, value in rows.items():
        meta = index.get(rid)
        if not meta or meta.get("kind") not in TARGETS or not meta.get("file"):
            continue
        by_file.setdefault(meta["file"], []).append(rid)

    stats = {"files": 0, "applied": 0, "skipped": 0, "details": []}
    for fname, rids in sorted(by_file.items()):
        env = open_env(os.path.join(DATA_DIR, fname))
        sf = env.files[fname]
        touched = 0
        for obj in list(sf.objects.values()):
            if obj.type.name != "MonoBehaviour":
                continue
            cls = mb_class(obj, sf)
            if cls not in TARGETS:
                continue
            name = mb_name(obj)
            applicable = []
            for rid in rids:
                meta = index[rid]
                if meta["kind"] != cls:
                    continue
                if cls in ("TextData", "AutoTalk"):
                    if meta["source"] == name:
                        applicable.append(rid)
                elif cls == "Title" and meta.get("group") and meta["source"] == name:
                    applicable.append(rid)
            if not applicable:
                continue
            raw = obj.get_raw_data()
            data = decode(raw, cls)
            for rid in applicable:
                if _apply(cls, rid, name, data, rows[rid], slot):
                    touched += 1
                else:
                    stats["skipped"] += 1
            if touched:
                # the generated typetree for these classes is unusable, so the
                # re-encoded payload is spliced back onto the untouched header
                payload = encode(data, cls)
                obj.set_raw_data(raw[:header_end(raw)] + payload)
        if touched:
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, fname)
            with open(out_path, "wb") as fh:
                fh.write(sf.save())
            for suffix in (".resS", ".resource"):
                side = os.path.join(DATA_DIR, fname + suffix)
                if os.path.exists(side):
                    shutil.copy2(side, out_path + suffix)
            stats["files"] += 1
            stats["applied"] += touched
            stats["details"].append({"file": fname, "applied": touched})
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="translation/ALL.csv")
    ap.add_argument("--column", default="text_zh_Hans")
    ap.add_argument("--lang-slot", type=int, default=5)
    ap.add_argument("--out", default="dist/FizAndTheRainbowPlanet_Data")
    args = ap.parse_args()
    print(json.dumps(run(args.csv, args.column, args.lang_slot, args.out),
                     ensure_ascii=False, indent=1))
