"""Extract the game's embedded TrueType fonts and identify them."""
from __future__ import annotations

import os
import struct

import UnityPy

from unity_env import DATA_DIR

_TRUE_MAGIC = (b"\x00\x01\x00\x00", b"OTTO", b"true")


def sniff(blob: bytes) -> str | None:
    head = blob[:4]
    if head == b"\x00\x01\x00\x00" or head == b"true":
        return "ttf"
    if head == b"OTTO":
        return "otf"
    if head == b"ttcf":
        return "ttc"
    if head == b"wOFF":
        return "woff"
    return None


def iter_font_objects():
    """Yield (source_file, path_id, name, blob) for every UnityEngine.Font."""
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith(".assets"):
            continue
        env = UnityPy.load(os.path.join(DATA_DIR, fname))
        for obj in env.objects:
            if obj.type.name != "Font":
                continue
            data = obj.read()
            yield fname, obj.path_id, data.m_Name, bytes(data.m_FontData)


def read_name_table(blob: bytes) -> dict[str, str]:
    """Pull family/subfamily/full/postscript names from the OpenType `name` table."""
    if sniff(blob) == "ttc":
        offset = struct.unpack(">I", blob[12:16])[0]
        blob = blob[offset:]
    if blob[:4] not in _TRUE_MAGIC:
        return {}
    num_tables = struct.unpack(">H", blob[4:6])[0]
    name_off = None
    for i in range(num_tables):
        rec = 12 + i * 16
        if blob[rec:rec + 4] == b"name":
            name_off = struct.unpack(">I", blob[rec + 8:rec + 12])[0]
            break
    if name_off is None:
        return {}
    count, str_off = struct.unpack(">HH", blob[name_off + 2:name_off + 6])
    storage = name_off + str_off
    want = {1: "family", 2: "subfamily", 4: "full", 6: "postscript"}
    best: dict[str, tuple[int, str]] = {}
    for i in range(count):
        rec = name_off + 6 + i * 12
        pid, eid, _lid, nid, length, off = struct.unpack(">HHHHHH", blob[rec:rec + 12])
        if nid not in want:
            continue
        raw = blob[storage + off:storage + off + length]
        try:
            if pid == 3:
                text, rank = raw.decode("utf-16-be"), 2
            elif pid == 0:
                text, rank = raw.decode("utf-16-be"), 1
            elif pid == 1 and eid == 0:
                text, rank = raw.decode("mac-roman"), 0
            else:
                continue
        except UnicodeDecodeError:
            continue
        key = want[nid]
        if key not in best or rank > best[key][0]:
            best[key] = (rank, text)
    return {k: v[1] for k, v in best.items()}


def extract_all(dest: str) -> list[dict]:
    os.makedirs(dest, exist_ok=True)
    out = []
    for fname, path_id, name, blob in iter_font_objects():
        safe = name.replace("/", "_").replace("\\", "_")
        ext = sniff(blob) or "bin"
        path = os.path.join(dest, f"{safe}.{ext}")
        with open(path, "wb") as fh:
            fh.write(blob)
        out.append({
            "source": fname, "path_id": path_id, "name": name,
            "file": os.path.basename(path), "bytes": len(blob),
            "format": sniff(blob), **read_name_table(blob),
        })
    return out


if __name__ == "__main__":
    import json
    import sys

    dest = sys.argv[1] if len(sys.argv) > 1 else "work/fonts/original"
    info = extract_all(dest)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as fh:
            json.dump(info, fh, ensure_ascii=False, indent=1)
    else:
        print(json.dumps(info, ensure_ascii=False, indent=1))
