"""Build the complete, file-replacement-only localisation patch.

Nothing here needs a mod loader, a rebuilt Addressables catalog or a patched
DLL: Chinese is written into an *existing* locale slot, so every address and
every bundle name stays exactly as the game shipped it.

Pipeline
  0. translation gate    (src/check_translation.py) - a worksheet with
                         error-level problems aborts before any asset is touched
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
import ntpath
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import UnityPy

from check_translation import SheetError, check_file
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
# Additive (X2) mode: the English `en` slot keeps the original text and Chinese
# goes into the previously vacant `es` (Spanish=4) slot.  That slot's LocFontData
# entry has to point at a CJK face; we repoint it at `k8x12EXL`.
#
# 注意（2026-10-16 审计更正）：`k8x12EXL` 并不是「没有任何 Text 引用」——
# 全量普查显示 49 个场景 Text 以 size 12 用它；而且 additive 构建**不止换它一个
# blob**，`fonts.config.json` 的 `zh_additive` profile 同时把 `k8x12EXS`
# (sharedassets0.assets:14) 换成 fusion-10px-zh_hans、把 `k8x12EXL` 换成
# fusion-8px-zh_hans（已用 sha256 逐字节核实）。后果是**日语/英语模式下**
# 942 个以 size 12 引用 EXS 的 Text 会以 12/10 = 1.2× 的非整数缩放渲染
# （原位图字体是 12px 设计、原本 1:1 锐利），即「追加式不动日英」在字体层不成立。
# 见 work/_additive/AUDIT_BRIEF_v2.md 与子代理 A 的 G-3。
#
# `font_size` 会被直接写进 es 槽的 `size`，必须等于所指字体的设计尺寸
# （见 tools/build_additive_data.py 的断言）。当前方案（2026-10-16 回退定案）：
# **es 槽按该 LocFontData 的 defaultFont 档位镜像**，两个宿主都装 zh_hans blob：
#   size 12 -> sharedassets0.assets:14  k8x12EXS <- fusion-10px-zh_hans
#   size  8 -> sharedassets3.assets:133 k8x12EXL <- fusion-8px-zh_hans
# 插件运行时把中文按原字号量化到 10 / 8 两档（SizeLarge=10 / SizeSmall=8），
# 与这两个宿主的设计尺寸一致 => 中文 1:1 锐利，且**不改变原有排版宽度层级**
# （曾把大档改成 12 试过：中文宽 20%，底栏等紧容器会换行压叠，已回退）。
# 已知代价（用户已接受）：日/英模式下 EXS 被 942 个 Text 以 size 12 使用 =>
# 12/10 = 1.2×；EXL 被 49 个 Text 以 size 12 使用 => 12/8 = 1.5×。
# 不替换 Yoshi5x8_v2.1：它的 advance 只有 0.625em，换 1.0em 方形字体宽 60% 会溢出。
#
# 回退：并非每个 LocFontData 所在文件的外部表里都有 sharedassets3.assets，
# 镜像目标不可解析时回退到 12 档宿主。
ADDITIVE_FONT_FILE = "sharedassets3.assets"
ADDITIVE_FONT_PATH_ID = 133
ADDITIVE_FONTS_BY_SIZE = {8: ("sharedassets3.assets", 133),
                          12: ("sharedassets0.assets", 14)}


def _additive_size_for(default_font):
    """es 槽要镜像的档位：取与 `defaultFont.size` 最接近的受支持档位。"""
    size = 0
    if isinstance(default_font, dict):
        try:
            size = int(default_font.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
    if size <= 0:
        return max(ADDITIVE_FONTS_BY_SIZE)
    return min(ADDITIVE_FONTS_BY_SIZE, key=lambda k: (abs(k - size), -k))


# --------------------------------------------------------------------------
# 0 - translation gate: never build from a worksheet that has error-level
#     problems (placeholders, line breaks, rich-text tags, control markers,
#     empty cells).  Warnings are printed but do not block.
# --------------------------------------------------------------------------
def gate_translations(path: str, column: str) -> None:
    """Run the worksheet checker in front of the build and abort on errors.

    A worksheet whose target column is still completely empty is reported as
    "not started" rather than as one empty row per line, so the pre-translation
    state stays buildable.  A missing worksheet keeps the previous behaviour
    (the build then simply has no translations to apply).
    """
    if not os.path.exists(path):
        print(f"[build] 工作表不存在，跳过译文校验: {path}")
        return
    try:
        report = check_file(path, column=column, verbose=True)
    except SheetError as exc:
        raise SystemExit(f"ABORT: 工作表无法校验: {exc}") from exc
    if report.not_started:
        print(f"[build] {column} 列尚无译文（{report.nonempty}/{report.rows} 行）："
              f"翻译尚未开始，跳过译文校验")
        return
    if report.errors:
        raise SystemExit(
            f"ABORT: 译文校验发现 {len(report.errors)} 个错误级问题"
            f"（另有 {len(report.warnings)} 条警告），已按行号列在上方；"
            f"单独复查: python src/check_translation.py {path}"
            f"；确需跳过请加 --skip-translation-check")


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


# --------------------------------------------------------------------------
# 2b - 修正游戏原版的一处数据错位（暂停菜单「宝藏」页）
# --------------------------------------------------------------------------
TREASURE_DEFAULT = "TreasureText_default"


def _fix_treasure_default(data: dict) -> int:
    """让 `TreasureText_default` 的语言排布与 `TreasureText_stage0N` 对齐。

    游戏代码 `CanvasCamera.UpdateTreasureText` 用**具体宝物**表算出 num::

        num = pausePanel_TreasureTextData[i].textDatas.FindIndex(x => x.language == _lang);
        if (num < 0) num = 0;

    却在「尚未发现」分支里拿同一个 num 去索引**默认宝物**表::

        Title.text = pausePanel_TreasureTextData_default.textDatas[num].strings[0];
        Body.text  = pausePanel_TreasureTextData_default.textDatas[num].strings[1];

    而原版 `TreasureText_default` 的语言序列是 [0, 0, 1, 2, 3, 4]，
    比各 stage 表的 [0, 1, 2, 3, 4] 多一个重复的 language=0 块 ——
    于是默认表整体错开一位。日/英/法恰好都落在非空块上，所以一直没暴露；
    中文写在 Spanish(=4) 槽，stage 表算出 num=4，落到默认表的 index 4 = 空的
    French 块，`strings[0]`/`strings[1]` 都是空串 -> 整页「有图无字」。

    删掉那个重复块即恢复 [0,1,2,3,4] 对齐。被删的块永远选不到
    （`FindIndex(language == 0)` 命中的是 index 0 的正式日文块），
    其它语言命中的下标都由 1..4 归位到 0..3，取到的内容与原来逐字相同。
    """
    blocks = data.get("textDatas") or []
    if len(blocks) < 2:
        return 0
    if blocks[0].get("language") != 0 or blocks[1].get("language") != 0:
        return 0
    del blocks[1]
    return 1


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


def _additive_font_pptr(serialized_file, fname, target):
    """PPtr to `target` = (file, path_id) as seen from the serialized file `fname`.

    `m_FileID` is 0 for a reference inside the same file and otherwise the
    *1-based* position of the target in that file's external table, so the index
    is resolved from the actual table rather than hard-coded.
    """
    target_file, target_path_id = target
    if ntpath.basename(fname) == target_file:
        return {"m_FileID": 0, "m_PathID": target_path_id}
    for index, external in enumerate(getattr(serialized_file, "externals", None) or []):
        if ntpath.basename(str(external.path)) == target_file:
            return {"m_FileID": index + 1, "m_PathID": target_path_id}
    return None


def patch_assets(out_dir, translations, index, slot, font_entries, profile,
                 fusion_dir, font_size, font_map_path="work/font_map.json",
                 additive_font=None):
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
    written_files = set()
    build_started = time.time()
    for fname, work in sorted(by_file.items()):
        src = os.path.join(DATA_DIR, fname)
        env = open_env(src)
        sf = env.files[fname]
        stats = {"file": fname, "text": 0, "fonts": 0, "fonts_skipped": 0,
                 "locfont": 0, "locfont_font": 0, "written": [], "padded": 0,
                 "treasure_fix": 0}

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
            if cls == "LocFontData" and (font_size or additive_font):
                for item in data["fontDatas"]:
                    if item["language"] != slot:
                        continue
                    if additive_font:
                        # 方案甲：es 槽镜像 defaultFont 的档位，字号与字体一起写，
                        # 保证「字号 == 宿主设计尺寸」这一不变量。
                        want_size = _additive_size_for(data.get("defaultFont"))
                        target = additive_font.get(want_size) or additive_font[
                            _additive_size_for(None)]
                        pptr = _additive_font_pptr(sf, fname, target)
                        if pptr is None:
                            # 外部表里没有镜像目标（例如 sharedassets137 没有
                            # sharedassets2.assets）→ 回退到 12 档宿主
                            fallback_size = max(additive_font)
                            fallback = additive_font[fallback_size]
                            pptr = _additive_font_pptr(sf, fname, fallback)
                            if pptr is None:
                                raise SystemExit(
                                    f"ABORT: {fname} has no external entry for "
                                    f"{target[0]} nor {fallback[0]}: cannot "
                                    f"repoint the language {slot} font")
                            print(f"[locfont] {fname}: 无 {target[0]} 外部引用，"
                                  f"es 槽回退到 size {fallback_size} "
                                  f"({fallback[0]}:{fallback[1]})")
                            want_size, target = fallback_size, fallback
                        if item["size"] != want_size:
                            item["size"] = want_size
                            stats["locfont"] += 1
                            touched = True
                        if item["font"] != pptr:
                            item["font"] = pptr
                            stats["locfont_font"] += 1
                            touched = True
                    elif font_size and item["size"] != font_size:
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
                if cls == "TextData" and name == TREASURE_DEFAULT:
                    if _fix_treasure_default(data):
                        stats["treasure_fix"] += 1
                        touched = True
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
            blob_name = pick_blob_name(entry, profile)
            if blob_name is None:
                # the profile explicitly leaves this font untouched
                stats["fonts_skipped"] += 1
                continue
            blob_path = os.path.join(fusion_dir, blob_name)
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

        if (stats["text"] or stats["fonts"] or stats["locfont"]
                or stats["padded"] or stats["locfont_font"] or stats["treasure_fix"]):
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, fname)
            with open(out_path, "wb") as fh:
                fh.write(sf.save())
            written_files.add(fname)
            # .resS / .resource streaming data is never touched: object path ids
            # do not change, so the originals stay valid.
            report.append(stats)

    # 清掉**上一轮**留下的陈旧产物。
    #
    # 曾经踩过：方案甲 v1 构建把 sharedassets137.assets 写进产物（把 es 槽改成
    # k8x12EXL）；后来配置变了，该文件的原版值恰好就等于新目标，于是这一轮
    # 「不需要修改」→ 不写 → 产物里那份**旧文件原封不动地留着**并被分发出去，
    # 数据侧与插件侧因此不一致，而且构建报告里看不到任何异常。
    # 规则：产物目录顶层的序列化数据文件，只要本轮没写过、且原版里存在同名文件，
    # 就删掉 —— 不分发未修改的文件本来就是对的做法。
    removed = []
    if os.path.isdir(out_dir):
        for name in sorted(os.listdir(out_dir)):
            full = os.path.join(out_dir, name)
            if not os.path.isfile(full) or name in written_files:
                continue
            if name.endswith((".resS", ".resource", ".json", ".info")):
                continue
            if not os.path.isfile(os.path.join(DATA_DIR, name)):
                continue          # 不是来自数据目录的东西，不是我们的产物
            # 按 mtime 兜底：本轮构建开始之前就存在的、又不是刚写出来的，就是上一轮的
            # 残留。只靠 written_files 记账曾漏掉过一次（文件被记成"已写"但实际内容
            # 与原版相同、本可不必分发），改成时间戳判定更稳。
            try:
                if os.path.getmtime(full) >= build_started:
                    continue
            except OSError:
                continue
            try:
                os.remove(full)
            except OSError:
                continue
            removed.append(name)
    if removed:
        print(f"[stale] 删除 {len(removed)} 个陈旧产物（原版未改动，不再分发）: "
              f"{removed[:6]}{' …' if len(removed) > 6 else ''}")
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
          skip_fonts=False, skip_strings=False, allow_missing=False,
          skip_translation_check=False, additive=False):
    # The gate runs before anything is loaded or written: a worksheet with
    # error-level problems must never reach the assets.
    if not skip_translation_check:
        gate_translations(translations, column)
    translations = load_translations(translations, column)
    with open(index_path, encoding="utf-8") as fh:
        index = json.load(fh)
    cfg = load_config(config_path)
    font_entries = [e for e in cfg["fonts"] if not e.get("disabled")]

    # Additive mode: Chinese lives in the vacant `es` slot, so that slot's
    # LocFontData must be repointed at the one font blob this mode replaces.
    additive_font = None
    if additive:
        # 方案甲：es 槽按 defaultFont 档位镜像到 EXS(12px 设计) 或 EXL(8px 设计)
        additive_font = dict(ADDITIVE_FONTS_BY_SIZE)

    text_entries = []
    if not skip_fonts:
        text_entries = font_entries
    report = {"mode": {"additive": bool(additive), "slot": slot,
                       "locale": locale_code, "profile": profile,
                       "font_size": font_size,
                       "additive_font": ({str(k): list(v) for k, v in additive_font.items()}
                                        if additive_font else None)}}
    report["assets"] = patch_assets(out_dir, translations, index, slot,
                                    text_entries, profile, fusion_dir,
                                    font_size, additive_font=additive_font)
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
    report["coverage"] = {
        "expected": len(expected),
        "written": len(expected & written),
        "missing": len(missing),
        "missing_sample": missing[:10],
        "unknown_ids": len(unknown),
        "unknown_sample": unknown[:5],
    }
    # Rows whose target-language asset does not exist at all: `expected` never
    # contains them, so they can only be surfaced separately.
    if kind_unroutable:
        report["coverage"]["unroutable"] = sorted(kind_unroutable)[:10]
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
    ap.add_argument("--skip-translation-check", action="store_true",
                    help="跳过译文工作表机械校验门槛（默认有错误级问题即 ABORT）")
    ap.add_argument("--additive", action="store_true",
                    help="X2 追加式：en 槽位保留原版，中文写入 --slot/--locale 指定的"
                         "空置槽位，并把该槽位 LocFontData 的 font/size 按 "
                         "defaultFont 档位镜像到 "
                         + "/".join("size=%d -> %s:%d" % (k, v[0], v[1])
                                    for k, v in sorted(ADDITIVE_FONTS_BY_SIZE.items())))
    a = ap.parse_args()
    out = build(out_dir=a.out, translations=a.translations, column=a.column,
                slot=a.slot, locale_code=a.locale, profile=a.profile,
                font_size=a.font_size, skip_fonts=a.skip_fonts,
                skip_strings=a.skip_strings, allow_missing=a.allow_missing,
                skip_translation_check=a.skip_translation_check,
                additive=a.additive)
    print(json.dumps(out, ensure_ascii=False, indent=1))
