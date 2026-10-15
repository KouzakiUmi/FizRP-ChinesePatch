"""Extract every piece of translatable text from Fiz And The Rainbow Planet.

Three storage mechanisms are used by the game and all three are covered:

* Unity Localization `StringTable` assets living in Addressables bundles
  (UI / Message / Title Contents / SubGames UI / Ending tables).
* Custom ScriptableObjects with a per-language list: `TextData`, `AutoTalk_Data`.
* Custom ScriptableObjects with one field per language: `Title_Data`,
  `DamageTalk_Data`.

Output is (a) a machine readable index used for write-back and (b) CSV sheets
in the column layout the game's own `TextExporter` editor script uses.
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from custom_types import decode
from loc_common import (CSV_COLUMNS, LANGS, SHARED_TABLE_BUNDLE,
                        STR_TABLE_BUNDLE)
from unity_env import BUNDLE_DIR, DATA_DIR, mb_class, mb_name, open_env

CUSTOM_FILES = [
    "sharedassets3.assets", "sharedassets4.assets", "sharedassets7.assets",
    "sharedassets9.assets", "sharedassets14.assets", "sharedassets15.assets",
    "sharedassets16.assets", "sharedassets17.assets", "sharedassets19.assets",
    "sharedassets21.assets", "sharedassets22.assets", "sharedassets23.assets",
    "sharedassets25.assets", "sharedassets26.assets", "sharedassets29.assets",
    "sharedassets30.assets", "sharedassets32.assets", "sharedassets34.assets",
    "sharedassets35.assets", "sharedassets36.assets", "sharedassets37.assets",
    "sharedassets38.assets", "sharedassets39.assets", "sharedassets40.assets",
    "sharedassets41.assets", "sharedassets42.assets", "sharedassets43.assets",
    "sharedassets44.assets", "sharedassets48.assets", "sharedassets49.assets",
    "sharedassets50.assets", "sharedassets51.assets", "sharedassets52.assets",
    "sharedassets54.assets", "sharedassets55.assets", "sharedassets56.assets",
    "sharedassets58.assets", "sharedassets59.assets", "sharedassets62.assets",
    "sharedassets63.assets", "sharedassets64.assets", "sharedassets65.assets",
    "sharedassets66.assets", "sharedassets67.assets", "sharedassets68.assets",
    "sharedassets69.assets", "sharedassets70.assets", "sharedassets71.assets",
    "sharedassets72.assets", "sharedassets73.assets", "sharedassets74.assets",
    "sharedassets75.assets", "sharedassets77.assets", "sharedassets79.assets",
    "sharedassets81.assets", "sharedassets82.assets", "sharedassets83.assets",
    "sharedassets84.assets", "sharedassets85.assets", "sharedassets86.assets",
    "sharedassets87.assets", "sharedassets88.assets", "sharedassets89.assets",
    "sharedassets90.assets", "sharedassets91.assets", "sharedassets92.assets",
    "sharedassets93.assets", "sharedassets96.assets", "sharedassets97.assets",
    "sharedassets98.assets", "sharedassets99.assets", "sharedassets100.assets",
    "sharedassets102.assets", "sharedassets103.assets", "sharedassets105.assets",
    "sharedassets106.assets", "sharedassets107.assets", "sharedassets109.assets",
    "sharedassets111.assets", "sharedassets112.assets", "sharedassets114.assets",
    "sharedassets116.assets", "sharedassets118.assets", "sharedassets119.assets",
    "sharedassets120.assets", "sharedassets121.assets", "sharedassets123.assets",
    "sharedassets124.assets", "sharedassets127.assets", "sharedassets128.assets",
    "sharedassets129.assets", "sharedassets131.assets", "sharedassets135.assets",
    "sharedassets136.assets", "sharedassets137.assets",
    "sharedassets153.assets",
]


def _row(rid, kind, file, path_id, source, index, path, comment, texts):
    row = {"id": rid, "kind": kind, "file": file, "path_id": path_id,
           "source": source, "index": index, "path": path, "comment": comment}
    for lang in LANGS:
        row["text_" + lang] = texts.get(lang, "")
    row["text_zh_Hans"] = ""
    return row


def extract_localization(rows, index):
    """Unity Localization StringTables -> one row per (table, key)."""
    shared, tables = {}, {}
    bundles = [(None, SHARED_TABLE_BUNDLE)] + list(STR_TABLE_BUNDLE.items())
    for code, bundle in bundles:
        env = open_env(os.path.join(BUNDLE_DIR, bundle))
        for obj in env.objects:
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                cls = obj.read().m_Script.read().m_ClassName
            except Exception:
                continue
            tt = obj.read_typetree()
            if cls == "SharedTableData":
                shared[tt["m_Name"].replace(" Shared Data", "")] = {
                    e["m_Id"]: e["m_Key"] for e in tt["m_Entries"]}
            elif cls == "StringTable":
                table = tt["m_Name"].rsplit("_", 1)[0]
                tables.setdefault(table, {})[code] = tt["m_TableData"]
    # every locale uses its own m_Id set, so match on the shared key id first and
    # fall back to positional order when a locale's ids were regenerated.
    for table in sorted(tables):
        keys = shared.get(table, {})
        by_key = {}
        for code, entries in tables[table].items():
            for e in entries:
                by_key.setdefault(e["m_Id"], {})[code] = e["m_Localized"]
            if code == "ja":
                order = [e["m_Id"] for e in entries]
        ids = set(by_key)
        for tid in sorted(ids):
            if tid in keys:
                key = keys[tid]
            else:
                key = f"#{tid}"
            texts = by_key[tid]
            rid = f"localization:{table}:{key}"
            rows.append(_row(rid, "localization", "", "", table, "", key, "", texts))
            index[rid] = {"kind": "localization", "table": table, "key": key,
                          "key_id": tid, "langs": sorted(texts)}


CUSTOM_CLASSES = ("TextData", "AutoTalk_Data", "Title_Data",
                  "DamageTalk_Data", "LocFontData")


def _read_custom(file):
    """Yield (class, path_id, name, decoded_dict) for the game's text assets."""
    env = open_env(os.path.join(DATA_DIR, file))
    sf = env.files[file]
    for obj in sf.objects.values():
        if obj.type.name != "MonoBehaviour":
            continue
        cls = mb_class(obj, sf)
        if cls not in CUSTOM_CLASSES:
            continue
        try:
            data = decode(obj.get_raw_data(), cls)
        except Exception:
            continue
        yield cls, obj.path_id, mb_name(obj), data


def resolve_pptr(sf, ref):
    """Map a PPtr to "<file>:<path_id>", or None when it is a null reference."""
    if not ref or ref.get("m_PathID", 0) == 0:
        return None
    file_id = ref.get("m_FileID", 0)
    if file_id == 0:
        return f"{sf.name}:{ref['m_PathID']}"
    externals = getattr(sf, "externals", None) or []
    if not 0 < file_id <= len(externals):
        return None
    import ntpath
    target = ntpath.basename(str(externals[file_id - 1].path))
    return f"{target}:{ref['m_PathID']}"


def extract_custom(rows, index, font_map):
    for file in CUSTOM_FILES:
        for cls, path_id, name, data in _read_custom(file):
            if cls == "TextData":
                _text_data(rows, index, file, path_id, name, data)
            elif cls == "AutoTalk_Data":
                _auto_talk(rows, index, file, path_id, name, data)
            elif cls == "Title_Data":
                _title_data(rows, index, file, path_id, name, data)
            elif cls == "DamageTalk_Data":
                _damage_talk(index, file, path_id, name, data)
            elif cls == "LocFontData":
                _loc_font(file, path_id, name, data, font_map)


def _loc_font(file, path_id, name, data, font_map):
    env = open_env(os.path.join(DATA_DIR, file))
    sf = env.files[file]
    entry = {"source": file, "path_id": path_id,
             "default": _font_entry(sf, data["defaultFont"]),
             "perLanguage": {}}
    for item in data["fontDatas"]:
        entry["perLanguage"][LANGS[item["language"]]] = _font_entry(sf, item)
    font_map[name] = entry


def _font_entry(sf, item):
    return {"language": item["language"], "font": resolve_pptr(sf, item["font"]),
            "size": item["size"], "lineSpacing": item["lineSpacing"],
            "memo": item["memo"]}


def _text_data(rows, index, file, path_id, name, data):
    blocks = {b["language"]: b["strings"] for b in data["textDatas"]}
    count = max((len(v) for v in blocks.values()), default=0)
    ja = blocks.get(0, [])
    for i in range(count):
        texts = {}
        for lang_idx, lang in enumerate(LANGS):
            arr = blocks.get(lang_idx)
            if arr and i < len(arr):
                texts[lang] = arr[i]
        rid = f"TextData:{name}:{i}"
        rows.append(_row(rid, "TextData", file, path_id, name, i, f"textDatas[{i}]",
                         ja[i] if i < len(ja) else "", texts))
        index[rid] = {"kind": "TextData", "file": file, "path_id": path_id,
                      "source": name, "index": i}


def _auto_talk(rows, index, file, path_id, name, data):
    base = data.get("talkDatas") or []
    loc = {e["language"]: (e.get("talkDatas") or [])
           for e in (data.get("locTalkDatas") or [])}
    count = max([len(base)] + [len(v) for v in loc.values()])
    for i in range(count):
        texts = {}
        if i < len(base):
            texts["ja"] = base[i].get("text", "")
        for lang_idx, lang in enumerate(LANGS):
            if lang == "ja":
                continue
            arr = loc.get(lang_idx)
            if arr and i < len(arr):
                texts[lang] = arr[i].get("text", "")
        comment = ""
        if i < len(base):
            speaker = base[i].get("chara")
            comment = f"wait={base[i].get('wait', 0.0):.2f} speaker={speaker}"
        rid = f"AutoTalk:{name}:{i}"
        rows.append(_row(rid, "AutoTalk", file, path_id, name, i, f"talkDatas[{i}]",
                         comment, texts))
        index[rid] = {"kind": "AutoTalk", "file": file, "path_id": path_id,
                      "source": name, "index": i,
                      "hasLoc": sorted(loc)}


TITLE_GROUPS = ["label", "info", "infoDisable"]
TITLE_SUFFIX = {"ja": "", "en_machine": "_en_machine", "en": "_en",
                "fr": "_fr", "es": "_es"}


def _title_data(rows, index, file, path_id, name, data):
    for group in TITLE_GROUPS:
        texts = {lang: (data.get(group + suffix) or "")
                 for lang, suffix in TITLE_SUFFIX.items()}
        rid = f"Title:{name}:{group}"
        rows.append(_row(rid, "Title", file, path_id, name, "", group, "", texts))
        index[rid] = {"kind": "Title", "file": file, "path_id": path_id,
                      "source": name, "group": group}


from custom_types import DAMAGE_LIST_NAMES as DMG_LISTS

DMG_ASSET_LANG = {"DamageTalkData_ja": "ja", "DamageTalkData_enMachine": "en_machine",
                  "DamageTalkData_en": "en", "DamageTalkData_es": "es",
                  "DamageTalkData_fr": "fr"}


def _damage_talk(index, file, path_id, name, data):
    """DamageTalk ships one asset per language; merge them into shared rows."""
    lang = DMG_ASSET_LANG.get(name)
    if lang is None:
        return
    for pi, player in enumerate(data.get("player") or []):
        for lst in DMG_LISTS:
            for ti, entry in enumerate(player.get(lst) or []):
                rid = f"DamageTalk:{lst}:{pi}:{ti}"
                meta = index.setdefault(rid, {"kind": "DamageTalk",
                                              "source": lst, "player": pi,
                                              "index": ti})
                meta.setdefault("texts", {})[lang] = entry.get("text", "")
                meta.setdefault("others", []).append((lang, file, path_id))


def damage_rows(rows, index):
    for rid, meta in index.items():
        if meta.get("kind") != "DamageTalk":
            continue
        rows.append(_row(rid, "DamageTalk", meta["others"][0][1] if meta["others"] else "",
                         "", meta["source"], meta["index"],
                         f"player[{meta['player']}].{meta['source']}[{meta['index']}]",
                         ";".join(f"{l}={f}:{p}" for l, f, p in meta["others"]),
                         meta.get("texts", {})))


def main(out_dir="translation", index_path="work/text_index.json",
         font_map_path="work/font_map.json"):
    rows, index, font_map = [], {}, {}
    extract_localization(rows, index)
    extract_custom(rows, index, font_map)
    damage_rows(rows, index)
    rows.sort(key=lambda r: (r["kind"], r["source"], r["path"], str(r["id"])))

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)
    with open(font_map_path, "w", encoding="utf-8") as fh:
        json.dump(font_map, fh, ensure_ascii=False, indent=1)

    by_kind = {}
    for row in rows:
        by_kind.setdefault(row["kind"], []).append(row)
    for kind, group in by_kind.items():
        with open(os.path.join(out_dir, f"{kind}.csv"), "w",
                  encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(group)
    with open(os.path.join(out_dir, "ALL.csv"), "w",
              encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({k: len(v) for k, v in sorted(by_kind.items())},
                     ensure_ascii=False, indent=1))
    print("total rows:", len(rows))
    return rows


if __name__ == "__main__":
    main()
