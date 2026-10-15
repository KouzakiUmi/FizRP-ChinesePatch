"""Replace the game's embedded TrueType fonts with fusion-pixel-font builds.

The game ships every font as a *dynamic* UnityEngine.Font asset whose whole
TrueType file lives in `m_FontData`, so swapping that blob is enough for the
renderer (legacy uGUI `Text`) to pick up the new typeface.

Only the `.assets` files are rewritten; the companion `.resS` / `.resource`
streaming files are copied through untouched because object path ids do not
change.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import UnityPy

from unity_env import DATA_DIR, GAME_ROOT

DEFAULT_CONFIG = "fonts.config.json"
# companions that must be copied next to a rewritten .assets file
SIDECAR_SUFFIXES = (".resS", ".resource", ".assets.split0")


def load_config(path: str = DEFAULT_CONFIG) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _find_font(sf, path_id):
    for obj in sf.objects.values():
        if obj.type.name == "Font" and obj.path_id == path_id:
            return obj
    return None


def pick_blob_name(entry: dict, profile: str) -> str:
    """`fusion` is either a plain filename or a {profile: filename} mapping."""
    fusion = entry["fusion"]
    if isinstance(fusion, dict):
        return fusion.get(profile) or fusion.get("default")
    return fusion


def build(config: dict, out_dir: str, fusion_dir: str = "dist/fonts/source",
          dry_run: bool = False, profile: str = "default") -> list[dict]:
    """Write patched copies of every touched .assets file into `out_dir`."""
    report = []
    by_file: dict[str, list[dict]] = {}
    for entry in config["fonts"]:
        if entry.get("disabled"):
            continue
        by_file.setdefault(entry["file"], []).append(entry)

    for fname, entries in sorted(by_file.items()):
        src = os.path.join(DATA_DIR, fname)
        if not os.path.exists(src):
            report.append({"file": fname, "error": "missing source"})
            continue
        env = UnityPy.load(src)
        sf = env.files[fname] if fname in env.files else list(env.files.values())[0]
        changed = []
        for entry in entries:
            blob_name = pick_blob_name(entry, profile)
            blob_path = os.path.join(fusion_dir, blob_name)
            if not blob_path or not os.path.exists(blob_path):
                report.append({"file": fname, "path_id": entry["path_id"],
                               "error": f"missing font {blob_name}"})
                continue
            blob = open(blob_path, "rb").read()
            obj = _find_font(sf, entry["path_id"])
            if obj is None:
                report.append({"file": fname, "path_id": entry["path_id"],
                               "error": "font object not found"})
                continue
            data = obj.read()
            before = len(bytes(data.m_FontData))
            data.m_FontData = blob
            obj.save_typetree(data)
            changed.append({"path_id": entry["path_id"], "name": data.m_Name,
                            "fusion": blob_name, "old_bytes": before,
                            "new_bytes": len(blob)})
        if dry_run or not changed:
            report.extend(changed)
            continue
        raw = sf.save()
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, fname)
        with open(out_path, "wb") as fh:
            fh.write(raw)
        for suffix in SIDECAR_SUFFIXES:
            side = src + suffix
            if os.path.exists(side):
                shutil.copy2(side, out_path + suffix)
        for item in changed:
            report.append({"file": fname, **item,
                           "out_size": os.path.getsize(out_path)})
    return report


def verify(patched_dir: str, report: list[dict]) -> list[str]:
    """Re-open each patched file and confirm the new font blob is in place."""
    problems = []
    for item in report:
        if "error" in item or "fusion" not in item:
            continue
        path = os.path.join(patched_dir, item["file"])
        env = UnityPy.load(path)
        sf = env.files[item["file"]] if item["file"] in env.files \
            else list(env.files.values())[0]
        obj = _find_font(sf, item["path_id"])
        if obj is None:
            problems.append(f"{item['file']}:{item['path_id']} missing after patch")
            continue
        data = obj.read()
        got = bytes(data.m_FontData)
        want = open(os.path.join("dist/fonts/source", item["fusion"]), "rb").read()
        if got != want:
            problems.append(f"{item['file']}:{item['path_id']} blob mismatch")
    return problems


if __name__ == "__main__":
    cfg = load_config()
    args = [a for a in sys.argv[1:]]
    profile = "default"
    if "--profile" in args:
        i = args.index("--profile")
        profile = args[i + 1]
        del args[i:i + 2]
    out = args[0] if args else "dist/FizAndTheRainbowPlanet_Data"
    rep = build(cfg, out, profile=profile)
    problems = verify(out, rep)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print("verify problems:", problems or "none")
