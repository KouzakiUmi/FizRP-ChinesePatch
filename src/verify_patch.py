"""Re-open a built patch and prove every layer really carries the translation."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import UnityPy

from custom_types import decode
from unity_env import BUNDLE_DIR, mb_class, mb_name, open_env

MARK = "【译】"


def check_assets(patched_dir, slot=2):
    facts = {"TextData": 0, "AutoTalk_Data": 0, "Title_Data": 0,
             "DamageTalk_Data": 0, "LocFontData": 0}
    bad = []
    for fname in sorted(os.listdir(patched_dir)):
        if not fname.endswith(".assets"):
            continue
        env = open_env(os.path.join(patched_dir, fname))
        sf = env.files[fname]
        for obj in sf.objects.values():
            if obj.type.name != "MonoBehaviour":
                continue
            cls = mb_class(obj, sf)
            if cls not in facts:
                continue
            try:
                data = decode(obj.get_raw_data(), cls)
            except Exception as exc:  # noqa: BLE001
                bad.append(f"{fname}:{obj.path_id} {cls} decode failed: {exc}")
                continue
            blob = repr(data)
            if cls == "LocFontData":
                for item in data["fontDatas"]:
                    if item["language"] == slot:
                        facts[cls] += 1
                        if item["size"] != 12:
                            bad.append(f"LocFontData size={item['size']}")
                continue
            if MARK in blob:
                facts[cls] += 1
            else:
                bad.append(f"{fname}:{obj.path_id} {cls} has no translation")
    return facts, bad


def check_strings(patched_bundle_dir, locale_bundle, slot_lang="en"):
    src = os.path.join(patched_bundle_dir, locale_bundle)
    env = open_env(src)
    total = marked = 0
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            if obj.read().m_Script.read().m_ClassName != "StringTable":
                continue
        except Exception:
            continue
        tt = obj.read_typetree()
        for entry in tt.get("m_TableData", []):
            total += 1
            if MARK in entry["m_Localized"]:
                marked += 1
    header = open(src, "rb").read(8)
    return {"total": total, "translated": marked, "signature": header[:7].decode()}


def check_fonts(patched_dir):
    out = []
    for fname in sorted(os.listdir(patched_dir)):
        if not fname.endswith(".assets"):
            continue
        env = UnityPy.load(os.path.join(patched_dir, fname))
        sf = list(env.files.values())[0]
        for obj in sf.objects.values():
            if obj.type.name != "Font":
                continue
            from fonts import read_name_table
            blob = bytes(obj.read().m_FontData)
            family = read_name_table(blob).get("family", "")
            if "Fusion" in family:
                out.append((fname, obj.path_id, family))
    return out


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "work/_smoke2"
    facts, bad = check_assets(d)
    print("assets layer:", facts)
    print("problems:", bad[:10] if bad else "none")
    print("fonts:", check_fonts(d))
    b = os.path.join(d, "..", "aa_bundles")
    for cand in (b, os.path.join(d, "aa_bundles")):
        if os.path.isdir(cand):
            print("strings:", check_strings(
                cand, "localization-string-tables-english(en)_assets_all.bundle"))
