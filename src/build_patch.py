"""Build the complete, file-replacement-only localisation patch.

Nothing here needs a mod loader, a rebuilt Addressables catalog or a patched
DLL: Chinese is written into an *existing* locale slot, so every address and
every bundle name stays exactly as the game shipped it.

Pipeline
  1. tailored worksheet / translations  -> translation/zh_Hans.csv
  2. ScriptableObject text  (TextData / AutoTalk / Title / DamageTalk)
  3. LocFontData            (point the slot at a CJK font, bump the point size)
  4. UnityEngine.Font       (swap the TrueType blob for fusion-pixel-font)
  5. Unity Localization     (rewrite the StringTable values inside their bundle)
"""
from __future__ import annotations

import argparse
import csv
import filecmp
import io
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import UnityPy

from custom_types import DAMAGE_LIST_NAMES, decode, encode, header_end
from font_patch import load_config, pick_blob_name
from loc_common import LANGS, SHARED_TABLE_BUNDLE, STR_TABLE_BUNDLE
from unity_env import BUNDLE_DIR, DATA_DIR, mb_class, mb_name, open_env

TEXT_CLASSES = ("TextData", "AutoTalk_Data", "Title_Data")
DAMAGE_CLASS = "DamageTalk_Data"
# the extraction index uses short kind names, the assets use the C# class names
KIND_TO_CLASS = {"TextData": "TextData", "AutoTalk": "AutoTalk_Data",
                 "Title": "Title_Data", "DamageTalk": "DamageTalk_Data"}
# DamageTalk_Data ships one asset per language; these are their m_Names
DMG_ASSET_LANG = {"DamageTalkData_ja": "ja", "DamageTalkData_enMachine": "en_machine",
                  "DamageTalkData_en": "en", "DamageTalkData_es": "es",
                  "DamageTalkData_fr": "fr"}
TITLE_SUFFIX = {0: "", 1: "_en_machine", 2: "_en", 3: "_fr", 4: "_es"}


def load_translations(path: str, column: str = "zh_Hans") -> dict[str, str]:
    if not os.path.exists(path):
        return {}
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return {r["id"]: r[column] for r in csv.DictReader(fh)
                if (r.get(column) or "").strip()}


# --------------------------------------------------------------------------
# 2/3 - ScriptableObject text + LocFontData, one pass per .assets file
# --------------------------------------------------------------------------
def _shift_text(cls, rid, data, value, slot):
    if cls == "TextData":
        idx = int(rid.rsplit(":", 1)[1])
        block = next((b for b in data["textDatas"] if b["language"] == slot), None)
        if block is None:
            block = {"memo": f"slot{slot}", "language": slot, "strings": []}
            data["textDatas"].append(block)
        while len(block["strings"]) <= idx:
            block["strings"].append("")
        block["strings"][idx] = value
        return True
    if cls == "AutoTalk_Data":
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
    if cls == "Title_Data":
        group = rid.rsplit(":", 1)[1]
        suffix = TITLE_SUFFIX.get(slot)
        if suffix is None:
            return False
        data[group + suffix] = value
        return True
    return False


def _pad_damage(target: dict, source: dict) -> int:
    """Extend `target` so every index present in the ja asset also exists here.

    The per-language DamageTalk assets do not have identical list lengths; 12 of
    the 238 rows have no slot in the English asset, and without this they are
    silently dropped.
    """
    added = 0
    players = target.setdefault("player", [])
    for pi, src_player in enumerate(source.get("player") or []):
        while len(players) <= pi:
            players.append({"charaName": src_player.get("charaName", ""),
                            "defaultCharaSprite": dict(src_player["defaultCharaSprite"]),
                            "defaultWait": src_player.get("defaultWait", 2.0),
                            **{name: [] for name in DAMAGE_LIST_NAMES}})
        tgt_player = players[pi]
        for name in DAMAGE_LIST_NAMES:
            src_list = src_player.get(name) or []
            tgt_list = tgt_player.setdefault(name, [])
            while len(tgt_list) < len(src_list):
                tpl = src_list[len(tgt_list)]
                tgt_list.append({"sensitivity": tpl["sensitivity"],
                                 "charaSprite": dict(tpl["charaSprite"]),
                                 "text": "", "wait": tpl["wait"]})
                added += 1
    return added


def _shift_damage(data, meta, value):
    """DamageTalk ships one asset per language, so the text is a plain write."""
    try:
        player = data["player"][meta["player"]]
        entry = player[meta["source"]][meta["index"]]
    except (KeyError, IndexError):
        return False
    entry["text"] = value
    return True


def patch_assets(out_dir, translations, index, slot, font_entries, profile,
                 fusion_dir, font_size, font_map_path="work/font_map.json"):
    lang_code = LANGS[slot]
    # Which file holds the DamageTalk asset for a given language. Rows that the
    # target language lacks an index for have no `others` entry of that language,
    # so the file has to be resolved once for the whole table instead of per row.
    damage_file = {}
    for meta in index.values():
        if meta.get("kind") != "DamageTalk":
            continue
        for lang, file, _pid in meta.get("others", []):
            damage_file.setdefault(lang, file)

    by_file: dict[str, dict] = {}
    for rid, meta in index.items():
        kind = meta.get("kind")
        if kind not in KIND_TO_CLASS:
            continue
        if kind == "DamageTalk":
            file = damage_file.get(lang_code)
            if file:
                by_file.setdefault(file, {"text": [], "fonts": []})["text"].append(rid)
        elif meta.get("file"):
            by_file.setdefault(meta["file"], {"text": [], "fonts": []})["text"].append(rid)
    for entry in font_entries:
        by_file.setdefault(entry["file"], {"text": [], "fonts": []})["fonts"].append(entry)
    # LocFontData carries no text, so it would never be visited on its own.
    # work/font_map.json records which .assets file each one lives in.
    missing_locfont = []
    if os.path.exists(font_map_path):
        with open(font_map_path, encoding="utf-8") as fh:
            for name, info in json.load(fh).items():
                by_file.setdefault(info["source"], {"text": [], "fonts": []})
    else:
        missing_locfont.append(font_map_path)

    report = []
    for fname, work in sorted(by_file.items()):
        src = os.path.join(DATA_DIR, fname)
        env = open_env(src)
        sf = env.files[fname]
        stats = {"file": fname, "text": 0, "fonts": 0, "locfont": 0,
                 "written": [], "padded": 0}

        # DamageTalk ships one asset per language inside this same file; decode
        # the ja one first so the target language can be padded to match it.
        damage_src = {}
        if any(KIND_TO_CLASS.get(index[r]["kind"]) == DAMAGE_CLASS
               for r in work["text"]):
            for other in sf.objects.values():
                if other.type.name != "MonoBehaviour":
                    continue
                if mb_class(other, sf) != DAMAGE_CLASS:
                    continue
                lang = DMG_ASSET_LANG.get(mb_name(other))
                if lang:
                    damage_src[lang] = decode(other.get_raw_data(), DAMAGE_CLASS)

        wanted = set(work["text"])
        for obj in list(sf.objects.values()):
            if obj.type.name != "MonoBehaviour":
                continue
            cls = mb_class(obj, sf)
            if cls not in KIND_TO_CLASS.values() and cls != "LocFontData":
                continue
            raw = obj.get_raw_data()
            data = decode(raw, cls)
            touched = False
            if cls == "LocFontData" and font_size:
                for item in data["fontDatas"]:
                    if item["language"] == slot and item["size"] != font_size:
                        item["size"] = font_size
                        stats["locfont"] += 1
                        touched = True
            elif cls == DAMAGE_CLASS and DMG_ASSET_LANG.get(mb_name(obj)) == lang_code:
                if "ja" in damage_src:
                    stats["padded"] += _pad_damage(data, damage_src["ja"])
                    touched = True
                for rid in wanted:
                    meta = index[rid]
                    if KIND_TO_CLASS.get(meta["kind"]) != cls:
                        continue
                    value = translations.get(rid)
                    if not value:
                        continue
                    if _shift_damage(data, meta, value):
                        stats["text"] += 1
                        stats["written"].append(rid)
                        touched = True
            elif cls in TEXT_CLASSES:
                name = mb_name(obj)
                for rid in wanted:
                    meta = index[rid]
                    if KIND_TO_CLASS.get(meta["kind"]) != cls                             or meta.get("source") != name:
                        continue
                    value = translations.get(rid)
                    if not value:
                        continue
                    if _shift_text(cls, rid, data, value, slot):
                        stats["text"] += 1
                        stats["written"].append(rid)
                        touched = True
            if touched:
                obj.set_raw_data(raw[:header_end(raw)] + encode(data, cls))

        for entry in work["fonts"]:
            blob_path = os.path.join(fusion_dir, pick_blob_name(entry, profile))
            if not os.path.exists(blob_path):
                report.append({"file": fname, "error": f"missing {blob_path}"})
                continue
            for obj in sf.objects.values():
                if obj.type.name != "Font" or obj.path_id != entry["path_id"]:
                    continue
                d = obj.read()
                d.m_FontData = open(blob_path, "rb").read()
                obj.save_typetree(d)
                stats["fonts"] += 1

        if stats["text"] or stats["fonts"] or stats["locfont"] or stats["padded"]:
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, fname)
            with open(out_path, "wb") as fh:
                fh.write(sf.save())
            # .resS / .resource streaming data is never touched: object path ids
            # do not change, so the originals stay valid.
            report.append(stats)
    return report


# --------------------------------------------------------------------------
# 5 - Unity Localization StringTables inside their Addressables bundle
# --------------------------------------------------------------------------
def _shared_keys(locale_bundle_code=None):
    """id -> key map for every table, read from the SharedTableData bundle."""
    env = open_env(os.path.join(BUNDLE_DIR, SHARED_TABLE_BUNDLE))
    keys = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            cls = obj.read().m_Script.read().m_ClassName
        except Exception:
            continue
        if cls != "SharedTableData":
            continue
        tt = obj.read_typetree()
        keys[tt["m_Name"].replace(" Shared Data", "")] = {
            e["m_Id"]: e["m_Key"] for e in tt["m_Entries"]}
    return keys


def patch_string_tables(out_dir, translations, index, locale_code):
    bundle = STR_TABLE_BUNDLE[locale_code]
    src = os.path.join(BUNDLE_DIR, bundle)
    env = open_env(src)
    shared = _shared_keys()
    stats = {"bundle": bundle, "tables": 0, "entries": 0,
             "written": [], "unmatched": []}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            if obj.read().m_Script.read().m_ClassName != "StringTable":
                continue
        except Exception:
            continue
        tt = obj.read_typetree()
        table = tt["m_Name"].rsplit("_", 1)[0]
        keymap = shared.get(table, {})
        by_key = {key: tid for tid, key in keymap.items()}
        seen = set()
        touched = 0
        for entry in tt.get("m_TableData", []):
            key = keymap.get(entry["m_Id"])
            if not key:
                continue
            rid = f"localization:{table}:{key}"
            seen.add(key)
            value = translations.get(rid)
            if not value:
                continue
            entry["m_Localized"] = value
            stats["written"].append(rid)
            touched += 1
        # A locale's table can be missing keys the source locale has (the English
        # UI Table has 33 of 34). Unity Localization adds such entries at runtime,
        # so doing it here is the same behaviour rather than a cosmetic change.
        for key, value in translations.items():
            prefix = f"localization:{table}:"
            if not key.startswith(prefix) or not value:
                continue
            bare = key[len(prefix):]
            if bare in seen or bare not in by_key:
                continue
            tt.setdefault("m_TableData", []).append({
                "m_Id": by_key[bare], "m_Localized": value,
                "m_Metadata": {"m_Items": []}})
            stats["written"].append(key)
            stats["added"] = stats.get("added", 0) + 1
            touched += 1
        if touched:
            obj.save_typetree(tt)
            stats["tables"] += 1
            stats["entries"] += touched
    if stats["tables"]:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, bundle), "wb") as fh:
            fh.write(env.files[os.path.basename(src)].save(packer="original"))
    return stats


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------
def build(out_dir="dist/FizAndTheRainbowPlanet_Data",
          translations="translation/zh_Hans.csv",
          index_path="work/text_index.json",
          column="zh_Hans", slot=2, locale_code="en",
          profile="zh_hans", font_size=12,
          config_path="fonts.config.json",
          fusion_dir="dist/fonts/source",
          skip_fonts=False, skip_strings=False, allow_missing=False):
    translations = load_translations(translations, column)
    with open(index_path, encoding="utf-8") as fh:
        index = json.load(fh)
    cfg = load_config(config_path)
    font_entries = [e for e in cfg["fonts"] if not e.get("disabled")]

    text_entries = []
    if not skip_fonts:
        text_entries = font_entries
    report = {"assets": patch_assets(out_dir, translations, index, slot,
                                     text_entries, profile, fusion_dir,
                                     font_size)}
    if not skip_strings:
        bundle_out = os.path.join(out_dir, "StreamingAssets", "aa",
                                  "StandaloneWindows64")
        report["string_tables"] = patch_string_tables(
            bundle_out, translations, index, locale_code)

    # ---- coverage accounting: a shortfall must never look like success -----
    written = set()
    for item in report["assets"]:
        written |= set(item.get("written", []))
    written |= set(report.get("string_tables", {}).get("written", []))
    damage_file = {}
    for meta in index.values():
        if meta.get("kind") != "DamageTalk":
            continue
        for lang, file, _pid in meta.get("others", []):
            damage_file.setdefault(lang, file)

    expected, unknown, kind_unroutable = set(), [], set()
    for rid, value in translations.items():
        if not value:
            continue
        if rid not in index:
            unknown.append(rid)
        elif index[rid].get("kind") == "DamageTalk" and                 not damage_file.get(LANGS[slot]):
            kind_unroutable.add(rid)
        elif index[rid].get("kind") in KIND_TO_CLASS or                 index[rid].get("kind") == "localization":
            expected.add(rid)
    missing = sorted(expected - written)
    if kind_unroutable:
        report["coverage"]["unroutable"] = sorted(kind_unroutable)[:10]
    report["coverage"] = {
        "expected": len(expected),
        "written": len(expected & written),
        "missing": len(missing),
        "missing_sample": missing[:10],
        "unknown_ids": len(unknown),
        "unknown_sample": unknown[:5],
    }
    if missing and not allow_missing:
        raise SystemExit(
            f"ABORT: {len(missing)} translated rows were not written "
            f"(e.g. {missing[:5]}). Pass --allow-missing to override.")
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/FizAndTheRainbowPlanet_Data")
    ap.add_argument("--translations", default="translation/zh_Hans.csv")
    ap.add_argument("--column", default="zh_Hans")
    ap.add_argument("--slot", type=int, default=2, help="Language 枚举槽位")
    ap.add_argument("--locale", default="en", help="占用的 locale 代码")
    ap.add_argument("--profile", default="zh_hans")
    ap.add_argument("--font-size", type=int, default=12)
    ap.add_argument("--skip-fonts", action="store_true")
    ap.add_argument("--skip-strings", action="store_true")
    ap.add_argument("--allow-missing", action="store_true",
                    help="只告警不中断（默认缺行即构建失败）")
    a = ap.parse_args()
    out = build(out_dir=a.out, translations=a.translations, column=a.column,
                slot=a.slot, locale_code=a.locale, profile=a.profile,
                font_size=a.font_size, skip_fonts=a.skip_fonts,
                skip_strings=a.skip_strings, allow_missing=a.allow_missing)
    print(json.dumps(out, ensure_ascii=False, indent=1))
