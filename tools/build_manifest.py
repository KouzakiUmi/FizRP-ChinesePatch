# -*- coding: utf-8 -*-
"""从 X2 载荷与独立游戏基线生成 manifest-additive.json，不依赖本机归档。

python tools/build_manifest.py [--payload-dir PATH] [--out PATH] [--version VERSION]
只读载荷与 config/game-reference.json；只写目标清单，不构建或安装。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys

from patch_tool import REFERENCE_FILES, validate_manifest

NAME = "Fiz 与彩虹星球 简体中文补丁"
GAME = "Fiz and the Rainbow Planet"
VERSION = "1.2.13"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAYLOAD_DIR = os.path.join(PROJECT_ROOT, "dist-additive", "payload")
MANIFEST_PATH = os.path.join(PROJECT_ROOT, "dist-additive", "manifest-additive.json")
REFERENCE_PATH = os.path.join(PROJECT_ROOT, "config", "game-reference.json")
SKIP_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_payload(payload_dir=None):
    root = PAYLOAD_DIR if payload_dir is None else payload_dir
    if not os.path.isdir(root):
        raise RuntimeError("载荷目录不存在: %s" % root)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if name in SKIP_NAMES:
                raise RuntimeError("载荷目录出现非常规文件: %s" % name)
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            found.append((rel, full, os.path.getsize(full)))
    return iter(sorted(found))


def build_manifest(payload_dir=None, reference_path=None, version=VERSION):
    reference_path = REFERENCE_PATH if reference_path is None else reference_path
    with open(reference_path, encoding="utf-8") as handle:
        reference = json.load(handle)
    refs = reference.get("reference_hashes")
    if not isinstance(refs, dict) or set(refs) != set(REFERENCE_FILES):
        raise RuntimeError("游戏基线必须包含 %s" % ", ".join(REFERENCE_FILES))
    files = [{"path": rel, "sha256": sha256(full), "size": size}
             for rel, full, size in iter_payload(payload_dir)]
    try:
        reference_source = os.path.relpath(reference_path, PROJECT_ROOT).replace(os.sep, "/")
    except ValueError:  # Windows 的测试/输入目录可能位于另一个盘符。
        reference_source = os.path.basename(reference_path)
    manifest = {
        "name": NAME, "game": GAME, "version": version,
        "built": datetime.date.today().isoformat(),
        "payload_files": len(files), "payload_bytes": sum(e["size"] for e in files),
        "patch_info": {"reference_hashes": refs, "payload_files": len(files),
                       "mode": "additive",
                       "patch_info_source": reference_source},
        "files": files, "mode": "additive",
    }
    return validate_manifest(manifest)


def write_manifest(manifest, path=None):
    path = MANIFEST_PATH if path is None else path
    validate_manifest(manifest)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成 X2 权威清单（独立游戏版本基线）")
    parser.add_argument("--payload-dir", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--additive", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        manifest = build_manifest(args.payload_dir, version=args.version)
        out = write_manifest(manifest, args.out)
    except (OSError, ValueError, RuntimeError) as exc:
        print("manifest: FAILED - %s" % exc, file=sys.stderr)
        return 1
    print("manifest: %s -> %d files, %d bytes" %
          (out, manifest["payload_files"], manifest["payload_bytes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
