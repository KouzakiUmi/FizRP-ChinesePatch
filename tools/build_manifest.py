# -*- coding: utf-8 -*-
"""从载荷目录重新生成 manifest.json（替换式）或 manifest-additive.json（追加式 X2）。

用法（在项目根执行）：

    python tools/build_manifest.py                    # 替换式：dist/FizRP-Chinese-Patch/files -> manifest.json
    python tools/build_manifest.py --additive         # 追加式：dist-additive/payload        -> dist-additive/manifest-additive.json

输入（替换式）：``dist/FizRP-Chinese-Patch/files/``（打包后交付目录里的载荷；平铺镜像
``FizAndTheRainbowPlanet_Data`` 结构，含 ``StreamingAssets/...`` 子目录）。
输入（追加式）：``dist-additive/payload/``（平铺载荷：Data 侧数据文件 + 游戏根侧的
BepInEx loader 条目；路由规则见 ``tools/build_additive_payload.py``）。
输出字段与「阶段 F 冻结契约 v1」§4 一致：

    {"name","game","version","built","payload_files","payload_bytes",
     "patch_info","files":[{"path","sha256","size"}, ...]}

``path`` 为 **posix 相对路径**，``files`` 顺序为 path 排序（稳定可复现）。
追加式清单多带 ``"mode":"additive"``，其 ``patch_info`` 复用替换式
``patch-info.json`` 的 ``reference_hashes``（同一游戏 build 的门禁基线），
``payload_files`` 按 additive 载荷重算 —— 因此 additive 安装器**只依赖
manifest-additive.json 一个文件**即可完成自检与版本门禁。

注意：本脚本只读载荷、只写清单文件，不触碰 ``dist/`` 既有内容，
也不做任何 PyInstaller 构建。默认（无参数）行为与历史版本逐字一致。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
from typing import Iterator, List, Optional, Tuple

# ---- 冻结常量（与契约 §4 一致 -----------------------------------------------------------------

NAME = "Fiz 与彩虹星球 简体中文补丁"
GAME = "Fiz and the Rainbow Planet"
VERSION = "1.2.0"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_DIR = os.path.join(PROJECT_ROOT, "dist", "FizRP-Chinese-Patch")
PAYLOAD_DIR = os.path.join(PACKAGE_DIR, "files")
PATCH_INFO_PATH = os.path.join(PACKAGE_DIR, "patch-info.json")
MANIFEST_PATH = os.path.join(PROJECT_ROOT, "manifest.json")
# 追加式（X2）载荷与清单：清单与载荷同树，便于整棵 dist-additive/ 一起分发。
ADDITIVE_PAYLOAD_DIR = os.path.join(PROJECT_ROOT, "dist-additive", "payload")
ADDITIVE_MANIFEST_PATH = os.path.join(PROJECT_ROOT, "dist-additive",
                                      "manifest-additive.json")

# 载荷目录里的非载荷残留物（正常不会出现；出现即视为错误，不静默跳过）
SKIP_NAMES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})

_CHUNK = 1024 * 1024


def sha256(path: str) -> str:
    """分块计算 SHA-256（载荷约 65 MB，避免整文件读入内存）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def iter_payload(payload_dir: Optional[str] = None) -> Iterator[Tuple[str, str, int]]:
    """遍历载荷目录，产出 ``(rel_posix, abs_path, size)``，按 rel_posix 排序。"""
    root = PAYLOAD_DIR if payload_dir is None else payload_dir
    found: List[Tuple[str, str, int]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for filename in sorted(filenames):
            if filename in SKIP_NAMES:
                raise RuntimeError(
                    "载荷目录出现非常规文件，请先人工确认: %s" % filename)
            abs_path = os.path.join(dirpath, filename)
            rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
            found.append((rel, abs_path, os.path.getsize(abs_path)))
    found.sort(key=lambda item: item[0])
    return iter(found)


def load_patch_info(path: Optional[str] = None) -> dict:
    """读取 ``patch-info.json``；缺失或损坏返回 ``{}``（与 patch_tool.load_patch_info 同语义）。"""
    path = PATCH_INFO_PATH if path is None else path
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_manifest(payload_dir: Optional[str] = None,
                   patch_info_path: Optional[str] = None,
                   check_declared: bool = True) -> dict:
    """替换式清单（默认参数下与历史行为逐字一致）。

    ``check_declared=False`` 供 additive 复用：追加式载荷与替换式
    ``patch-info.json`` 的 ``payload_files`` 必然不同（103 vs 121），
    此时由 ``build_additive_manifest`` 自行重算该字段。
    """
    payload_dir = PAYLOAD_DIR if payload_dir is None else payload_dir
    if not os.path.isdir(payload_dir):
        raise RuntimeError("载荷目录不存在: %s" % payload_dir)

    files: List[dict] = []
    total_bytes = 0
    payload_files = 0
    for rel, abs_path, size in iter_payload(payload_dir):
        files.append({"path": rel, "sha256": sha256(abs_path), "size": size})
        total_bytes += size
        payload_files += 1

    patch_info = load_patch_info(patch_info_path)
    declared = patch_info.get("payload_files")
    if check_declared and declared is not None and declared != payload_files:
        raise RuntimeError(
            "patch-info.json 声明 payload_files=%r，实际载荷 %d 个，拒绝生成清单"
            % (declared, payload_files))

    return {
        "name": NAME,
        "game": GAME,
        "version": VERSION,
        "built": datetime.date.today().strftime("%Y-%m-%d"),
        "payload_files": payload_files,
        "payload_bytes": total_bytes,
        "patch_info": patch_info,
        "files": files,
    }


def build_additive_manifest(payload_dir: Optional[str] = None,
                            patch_info_path: Optional[str] = None) -> dict:
    """追加式（X2）清单：字段与替换式一致，另带 ``mode`` 与自洽的 ``patch_info``。

    ``patch_info`` 复用替换式 ``patch-info.json`` 的 ``reference_hashes``（同一游戏
    build 的版本门禁基线），但 ``payload_files`` 按 additive 载荷重算，避免让
    additive 安装器去读一个条目数不同的替换式 patch-info。
    """
    payload_dir = ADDITIVE_PAYLOAD_DIR if payload_dir is None else payload_dir
    manifest = build_manifest(payload_dir, patch_info_path=patch_info_path,
                              check_declared=False)
    base = load_patch_info(patch_info_path)
    info = {key: value for key, value in base.items() if key != "payload_files"}
    info["payload_files"] = manifest["payload_files"]
    info["mode"] = "additive"
    info["patch_info_source"] = (
        "%s（reference_hashes 复用；payload_files 按 additive 载荷重算）"
        % os.path.relpath(patch_info_path or PATCH_INFO_PATH,
                          PROJECT_ROOT).replace(os.sep, "/"))
    manifest["mode"] = "additive"
    manifest["patch_info"] = info
    return manifest


def write_manifest(manifest: dict, path: Optional[str] = None) -> str:
    """写出清单（UTF-8、LF、indent=1，与既有 manifest.json 同风格）。"""
    path = MANIFEST_PATH if path is None else path
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_manifest.py",
        description="从载荷目录生成 manifest.json（默认）或 manifest-additive.json（--additive）")
    parser.add_argument("--additive", action="store_true",
                        help="对 dist-additive/payload 生成 dist-additive/manifest-additive.json")
    parser.add_argument("--payload-dir", default=None, help="覆盖载荷目录")
    parser.add_argument("--out", default=None, help="覆盖清单输出路径")
    args = parser.parse_args(argv)

    payload_dir = args.payload_dir
    out = args.out
    try:
        if args.additive:
            manifest = build_additive_manifest(payload_dir)
            out = out or ADDITIVE_MANIFEST_PATH
        else:
            manifest = build_manifest(payload_dir)
            out = out or MANIFEST_PATH
    except Exception as exc:  # 失败必须可见且非 0 退出
        print("manifest: FAILED - %s" % exc, file=sys.stderr)
        return 1

    write_manifest(manifest, out)
    if args.additive:
        print("manifest: %s -> %d files, %d bytes"
              % (out, manifest["payload_files"], manifest["payload_bytes"]))
    else:
        # 替换式路径保持历史输出格式逐字不变（契约 §4 的自检依据）
        print("manifest: %d files, %d bytes"
              % (manifest["payload_files"], manifest["payload_bytes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

