"""Replace the game's embedded TrueType fonts with fusion-pixel-font builds.

The game ships every font as a *dynamic* UnityEngine.Font asset whose whole
TrueType file lives in `m_FontData`, so swapping that blob is enough for the
renderer (legacy uGUI `Text`) to pick up the new typeface.

Only the `.assets` files are rewritten; the companion `.resS` / `.resource`
streaming files are copied through untouched because object path ids do not
change.
"""
from __future__ import annotations

import argparse
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


def pick_blob_name(entry: dict, profile: str) -> str | None:
    """`fusion` is either a plain filename or a {profile: filename} mapping.

    A *missing* profile key falls back to `default`; an explicit ``null`` does
    not - it means "this profile leaves the font alone" and is returned as None
    so the caller skips the object instead of swapping in the default blob.
    """
    fusion = entry["fusion"]
    if isinstance(fusion, dict):
        if profile in fusion:
            return fusion[profile]
        return fusion.get("default")
    return fusion


def _clone_object(sf, template, mutate):
    """Serialize a copy of `template` (with `mutate` applied) as a new object.

    Returns the new path id.  UnityPy can only add objects by writing their
    bytes, so the copy is produced from the template's typetree.
    """
    from UnityPy.files.ObjectReader import ObjectReader
    from UnityPy.helpers import TypeTreeHelper
    from UnityPy.helpers.TypeTreeHelper import EndianBinaryWriter

    tree = template.read_typetree()
    mutate(tree)
    node = template._get_typetree_node()
    writer = EndianBinaryWriter(endian=template.reader.endian)
    TypeTreeHelper.write_typetree(tree, node, writer, sf)
    data = writer.bytes

    path_id = max(o.path_id for o in sf.objects.values()) + 1
    reader = ObjectReader(
        assets_file=sf,
        reader=template.reader,
        path_id=path_id,
        type_id=template.type_id,
        serialized_type=template.serialized_type,
        class_id=template.class_id,
        type=template.type,
        byte_start=0,
        byte_size=len(data),
        is_destroyed=0,
        is_stripped=0,
        data=data,
    )
    sf.objects[path_id] = reader
    return path_id


def add_font_host(sf, name: str, blob: bytes) -> int:
    """Add a new Font object holding `blob` and return its path id.

    Every font slot the game still uses is taken, so the 12px face used by the
    two big titles is added as an extra object.  It is written into
    sharedassets0.assets, a file the payload already ships and every scene
    loads, so the object is instantiated at runtime like the game's own fonts.

    The face gets its **own** "Font Material" and 0x0 "Font Texture", like
    each of the game's own fonts: a dynamic font rasterizes its glyphs into
    its own texture at runtime, so two fonts sharing one texture would mix
    the 10px and 12px designs of the same codepoints and render the wrong
    glyph.  The Font class typetree itself is file-global, so the new object
    copies an existing Font's type information and swaps name, data, material
    and texture.
    """
    template = None
    for obj in list(sf.objects.values()):
        if obj.type.name == "Font":
            template = obj
            break
    if template is None:
        raise SystemExit("ABORT: no Font object to copy the type information from")

    font_tree = template.read_typetree()
    mat_ref = font_tree.get("m_DefaultMaterial") or {}
    tex_ref = font_tree.get("m_Texture") or {}
    mat_path = mat_ref.get("m_PathID", 0)
    tex_path = tex_ref.get("m_PathID", 0)
    mat_template = sf.objects.get(mat_path) if mat_path else None
    tex_template = sf.objects.get(tex_path) if tex_path else None
    if mat_template is None or tex_template is None:
        raise SystemExit("ABORT: the template font has no font material/texture to clone")

    new_tex = _clone_object(sf, tex_template, lambda t: t.update({"m_Name": "Font Texture"}))
    new_mat = _clone_object(sf, mat_template, lambda t: t.update(
        {"m_Name": "Font Material",
         "m_SavedProperties": _retarget_texture(t.get("m_SavedProperties"), new_tex)}))
    path_id = _clone_object(sf, template, lambda t: t.update({
        "m_Name": name,
        "m_FontData": blob,
        "m_FontNames": [name],
        "m_DefaultMaterial": {"m_FileID": 0, "m_PathID": new_mat},
        "m_Texture": {"m_FileID": 0, "m_PathID": new_tex},
    }))
    return path_id


def _retarget_texture(saved_properties, new_texture_path):
    """Point a material's _MainTex at the freshly cloned font texture.

    `m_TexEnvs` entries are (name, value) pairs in this Unity version; a plain
    dict is accepted too so the code does not depend on the exact shape.
    """
    if not isinstance(saved_properties, dict):
        return saved_properties
    saved = dict(saved_properties)
    textures = []
    for entry in saved.get("m_TexEnvs") or []:
        if isinstance(entry, tuple) and len(entry) == 2:
            name, value = entry
            if isinstance(value, dict):
                value = dict(value)
                inner = value.get("m_Texture")
                if isinstance(inner, dict):
                    value["m_Texture"] = {"m_FileID": 0, "m_PathID": new_texture_path}
            textures.append((name, value))
            continue
        if isinstance(entry, dict):
            item = dict(entry)
            if isinstance(item.get("_MainTex"), dict):
                main = dict(item["_MainTex"])
                main["m_Texture"] = {"m_FileID": 0, "m_PathID": new_texture_path}
                item["_MainTex"] = main
            textures.append(item)
            continue
        textures.append(entry)
    saved["m_TexEnvs"] = textures
    return saved


def build(config: dict, out_dir: str, fusion_dir: str = "dist/fonts/source",
          dry_run: bool = False, profile: str = "zh_additive") -> list[dict]:
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
            if blob_name is None:
                # profile explicitly asks for this font to be left alone
                continue
            blob_path = os.path.join(fusion_dir, blob_name)
            if not os.path.exists(blob_path):
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
    ap = argparse.ArgumentParser(description="构建 X2 双档字体（zh_additive）")
    ap.add_argument("out", nargs="?", default="dist-additive/FizAndTheRainbowPlanet_Data")
    args = ap.parse_args()
    cfg = load_config()
    rep = build(cfg, args.out)
    problems = verify(args.out, rep)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    print("verify problems:", problems or "none")
