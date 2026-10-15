"""Which Font assets does the game actually render text with?

UnityEngine.UI.Text keeps its font in `m_FontData.m_Font`, so the typetrees are
walked recursively looking for PPtr fields whose name mentions "font".
"""
from __future__ import annotations

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unity_env import DATA_DIR, mb_class, open_env

INTEREST = {"Text", "TextMeshProUGUI", "LocalizedText", "TMP_Text", "InlineImage",
            "TextData", "AutoTalk_Data", "Title_Data"}


def walk(node, found, prefix=""):
    if isinstance(node, dict):
        for key, value in node.items():
            if "font" in key.lower() and isinstance(value, dict) \
                    and "m_PathID" in value and value["m_PathID"]:
                found.append((prefix + key, value))
            walk(value, found, prefix + key + ".")
    elif isinstance(node, list):
        for item in node:
            walk(item, found, prefix)


def run():
    usage = collections.Counter()
    owners = collections.defaultdict(collections.Counter)
    errors = collections.Counter()
    for fname in sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".assets")):
        env = open_env(os.path.join(DATA_DIR, fname))
        sf = env.files[fname]
        externals = sf.externals or []
        for obj in sf.objects.values():
            if obj.type.name != "MonoBehaviour":
                continue
            cls = mb_class(obj, sf)
            if cls not in INTEREST:
                continue
            try:
                tt = obj.read_typetree(check_read=False)
            except Exception as exc:  # noqa: BLE001
                errors[f"{cls}: {type(exc).__name__}"] += 1
                continue
            found = []
            walk(tt, found)
            for key, ref in found:
                fid = ref.get("m_FileID", 0)
                if fid == 0:
                    target = fname
                elif 0 < fid <= len(externals):
                    target = os.path.basename(str(externals[fid - 1].path))
                else:
                    target = f"?file{fid}"
                full = f"{target}:{ref['m_PathID']}"
                usage[full] += 1
                owners[full][f"{cls}.{key}"] += 1
    return usage, owners, errors


if __name__ == "__main__":
    usage, owners, errors = run()
    print(f"{'font reference':32s} {'count':>6s}  where")
    for ref, count in usage.most_common():
        where = dict(owners[ref])
        print(f"{ref:32s} {count:>6d}  {where}")
    print("\nread problems:", dict(errors))
