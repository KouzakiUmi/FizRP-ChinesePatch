"""Verify a built patch by reading every translated value back from disk.

This replaces an earlier version that only asked "does the marker string appear
somewhere in this object".  That passed even when 12 of 238 DamageTalk rows were
never written, or when a value landed at the wrong index, so it is not a
verification at all.  Here every expected row is looked up at its exact
location: file -> object -> language slot -> index/path.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import UnityPy

from build_patch import DMG_ASSET_LANG, KIND_TO_CLASS, TITLE_SUFFIX
from custom_types import decode
from fonts import read_name_table
from loc_common import LANGS
from unity_env import BUNDLE_DIR, DATA_DIR, mb_class, mb_name, open_env


def load_expected(csv_path: str, column: str) -> dict[str, str]:
    with io.open(csv_path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if rows and column not in rows[0]:
        column = next((c for c in rows[0] if c.startswith("zh")), column)
    return {r["id"]: r[column] for r in rows if (r.get(column) or "").strip()}


def value_at(cls: str, data: dict, meta: dict, rid: str, slot: int):
    """Read back exactly the cell a row is supposed to occupy."""
    if cls == "TextData":
        i = int(rid.rsplit(":", 1)[1])
        for b in data["textDatas"]:
            if b["language"] == slot:
                return b["strings"][i] if i < len(b["strings"]) else None
        return None
    if cls == "AutoTalk_Data":
        i = int(rid.rsplit(":", 1)[1])
        for e in data["locTalkDatas"]:
            if e["language"] == slot:
                return e["talkDatas"][i]["text"] if i < len(e["talkDatas"]) else None
        return None
    if cls == "Title_Data":
        suffix = TITLE_SUFFIX.get(slot)
        return data.get(rid.rsplit(":", 1)[1] + suffix) if suffix is not None else None
    if cls == "DamageTalk_Data":
        try:
            return data["player"][meta["player"]][meta["source"]][meta["index"]]["text"]
        except (KeyError, IndexError, TypeError):
            return None
    return None


def check_objects(patched_dir, expected, index, slot):
    lang_code = LANGS[slot]
    damage_file = {}
    for meta in index.values():
        if meta.get("kind") == "DamageTalk":
            for lang, file, _pid in meta.get("others", []):
                damage_file.setdefault(lang, file)

    # group the rows by the file/object that should hold them
    todo: dict[tuple, list[str]] = {}
    for rid, value in expected.items():
        meta = index.get(rid)
        if not meta or meta.get("kind") not in KIND_TO_CLASS:
            continue
        kind = meta["kind"]
        cls = KIND_TO_CLASS[kind]
        if kind == "DamageTalk":
            fname, want_name = damage_file.get(lang_code), None
        else:
            fname, want_name = meta.get("file"), meta.get("source")
        if not fname:
            continue
        todo.setdefault((fname, cls, want_name), []).append(rid)

    ok, bad = 0, []
    envs: dict[str, object] = {}
    for (fname, cls, want_name), rids in todo.items():
        if fname not in envs:
            envs[fname] = open_env(os.path.join(patched_dir, fname))
        sf = envs[fname].files[fname]
        target = None
        for obj in sf.objects.values():
            if obj.type.name != "MonoBehaviour" or mb_class(obj, sf) != cls:
                continue
            name = mb_name(obj)
            if cls == "DamageTalk_Data":
                if DMG_ASSET_LANG.get(name) == lang_code:
                    target = obj
                    break
            elif name == want_name:
                target = obj
                break
        if target is None:
            bad.append((f"{fname}:{want_name}", "object not found"))
            continue
        data = decode(target.get_raw_data(), cls)
        for rid in rids:
            got = value_at(cls, data, index[rid], rid, slot)
            if got == expected[rid]:
                ok += 1
            else:
                bad.append((rid, f"expected {expected[rid][:30]!r} got {str(got)[:30]!r}"))
    return ok, bad


def check_strings(patched_dir, expected, index, locale_code):
    import build_patch
    bundle = build_patch.STR_TABLE_BUNDLE[locale_code]
    path = os.path.join(patched_dir, "StreamingAssets", "aa",
                        "StandaloneWindows64", bundle)
    if not os.path.exists(path):
        return 0, [(bundle, "missing")]
    env = open_env(path)
    shared = build_patch._shared_keys()
    found = {}
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
        for entry in tt.get("m_TableData", []):
            key = keymap.get(entry["m_Id"])
            if key:
                found[f"localization:{table}:{key}"] = entry["m_Localized"]
    ok, bad = 0, []
    for rid, value in expected.items():
        meta = index.get(rid)
        if not meta or meta.get("kind") != "localization":
            continue
        if found.get(rid) == value:
            ok += 1
        else:
            bad.append((rid, f"got {str(found.get(rid))[:30]!r}"))
    return ok, bad


def check_fonts(patched_dir):
    seen = []
    for fname in sorted(os.listdir(patched_dir)):
        if not fname.endswith(".assets"):
            continue
        env = UnityPy.load(os.path.join(patched_dir, fname))
        sf = list(env.files.values())[0]
        for obj in sf.objects.values():
            if obj.type.name != "Font":
                continue
            blob = bytes(obj.read().m_FontData)
            family = read_name_table(blob).get("family", "")
            if blob[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf"):
                seen.append((fname, obj.path_id, "NOT A FONT"))
            elif "Fusion" in family:
                seen.append((fname, obj.path_id, family))
    return seen


def check_structure(patched_dir, names):
    problems = []
    for f in sorted(names):
        if not f.endswith(".assets"):
            continue
        a, b = os.path.join(DATA_DIR, f), os.path.join(patched_dir, f)
        if not (os.path.exists(a) and os.path.exists(b)):
            continue
        sa = list(UnityPy.load(a).files.values())[0]
        sb = list(UnityPy.load(b).files.values())[0]
        if len(sa.objects) != len(sb.objects):
            problems.append((f, f"object count {len(sa.objects)} -> {len(sb.objects)}"))
            continue
        if set(sa.objects) != set(sb.objects):
            problems.append((f, "path id set changed"))
            continue
        for pid in sa.objects:
            if sa.objects[pid].class_id != sb.objects[pid].class_id:
                problems.append((f"{f}:{pid}", "class id changed"))
        if list(sa.externals or []) != list(sb.externals or []):
            problems.append((f, "externals changed"))
    return problems


def main(patched_dir, csv_path, column, slot):
    with open("work/text_index.json", encoding="utf-8") as fh:
        index = json.load(fh)
    expected = load_expected(csv_path, column)
    routable = {r: v for r, v in expected.items()
                if r in index and (index[r].get("kind") in KIND_TO_CLASS
                                   or index[r].get("kind") == "localization")}
    ok_obj, bad_obj = check_objects(patched_dir, routable, index, slot)
    ok_str, bad_str = check_strings(patched_dir, routable, index, LANGS[slot])
    files = {m["file"] for m in index.values() if m.get("file")}
    if os.path.exists("work/font_map.json"):
        with io.open("work/font_map.json", encoding="utf-8") as fh:
            files |= {v["source"] for v in json.load(fh).values()}
    prob = check_structure(patched_dir, files)
    fonts = check_fonts(patched_dir)
    print("expected translated rows : %d" % len(routable))
    print("  scripting objects ok   : %d" % ok_obj)
    print("  localization table ok  : %d" % ok_str)
    print("  verified total         : %d" % (ok_obj + ok_str))
    print("  wrong / missing        : %d" % (len(bad_obj) + len(bad_str)))
    for b in (bad_obj + bad_str)[:10]:
        print("     ", b)
    print("fonts replaced           : %d" % len(fonts))
    for f in fonts:
        print("     ", f)
    print("structural problems      : %d" % len(prob))
    for item in prob[:6]:
        print("     ", item)
    return 0 if not (bad_obj or bad_str or prob) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("patched_dir", nargs="?",
                    default="dist-additive/FizAndTheRainbowPlanet_Data")
    ap.add_argument("--csv", default="translation/zh_Hans.csv")
    ap.add_argument("--column", default="zh_Hans")
    ap.add_argument("--slot", type=int, choices=[4], default=4)
    args = ap.parse_args()
    raise SystemExit(main(args.patched_dir, args.csv, args.column, args.slot))
