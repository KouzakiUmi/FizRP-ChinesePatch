# -*- coding: utf-8 -*-
"""打包「追加式 X2」发布目录与 zip（当前安装包路线）。

用法（在项目根执行）::

    python tools/package_additive.py                 # 生成 dist/FizRP-X2-v<版本>/ + zip + sha256
    python tools/package_additive.py --check         # 只核验现有 zip 与清单，不写文件
    python tools/package_additive.py --force         # 存在旧产物时先删除再重建

输入（全部只读）：

    dist-additive/manifest-additive.json   权威清单（版本、文件表、哈希）
    dist-additive/payload/                 载荷（由 build_additive_payload.py 生成）
    tools/patch_tool.py                    无头安装核心
    docs/release/README-X2.txt             发布说明源（{{VERSION}} 占位）
    docs/release/KNOWN-ISSUES-X2.txt       实机待验项源（{{VERSION}} 占位）
    dist/fonts/source/OFL.txt              字体授权（SIL OFL-1.1）

输出：

    dist/FizRP-X2-v<版本>/                 发布目录
    dist/FizRP-X2-v<版本>.zip              压缩包（根目录为 FizRP-X2-v<版本>/）
    dist/FizRP-X2-v<版本>.zip.sha256       校验和

退出码：0 成功；1 校验失败；2 用法错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MANIFEST = os.path.join(ROOT, "dist-additive", "manifest-additive.json")
PAYLOAD = os.path.join(ROOT, "dist-additive", "payload")
PATCH_TOOL = os.path.join(HERE, "patch_tool.py")
README_SRC = os.path.join(ROOT, "docs", "release", "README-X2.txt")
KNOWN_SRC = os.path.join(ROOT, "docs", "release", "KNOWN-ISSUES-X2.txt")
OFL_SRC = os.path.join(ROOT, "dist", "fonts", "source", "OFL.txt")
LICENSE_SRC = os.path.join(ROOT, "LICENSE")
NOTICES_SRC = os.path.join(ROOT, "THIRD-PARTY-NOTICES.txt")
DIST = os.path.join(ROOT, "dist")

INSTALL_BAT = """@echo off
chcp 65001 >nul
cd /d "%~dp0"
python patch_tool.py install --additive --yes
pause
"""
UNINSTALL_BAT = """@echo off
chcp 65001 >nul
cd /d "%~dp0"
python patch_tool.py uninstall --additive --yes
pause
"""


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest():
    with open(MANIFEST, encoding="utf-8") as handle:
        return json.load(handle)


def render(template, version):
    with open(template, encoding="utf-8") as handle:
        text = handle.read()
    if "{{VERSION}}" not in text:
        raise SystemExit("模板缺少 {{VERSION}} 占位：%s" % template)
    return text.replace("{{VERSION}}", version)


def verify_payload(payload_dir, manifest):
    problems = []
    seen = set()
    for entry in manifest["files"]:
        rel = entry["path"]
        path = os.path.join(payload_dir, *rel.split("/"))
        if not os.path.isfile(path):
            problems.append("missing: " + rel)
            continue
        seen.add(rel.replace("/", os.sep))
        actual = sha256(path)
        if actual != entry["sha256"]:
            problems.append("hash: %s" % rel)
        if os.path.getsize(path) != entry["size"]:
            problems.append("size: %s" % rel)
    for dirpath, _dirnames, filenames in os.walk(payload_dir):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, payload_dir)
            if rel not in seen:
                problems.append("extra: " + rel.replace(os.sep, "/"))
    return problems


def write_release(out_dir, version, manifest):
    if os.path.isdir(out_dir):
        raise SystemExit("输出目录已存在（加 --force 覆盖）：%s" % out_dir)
    os.makedirs(out_dir)
    shutil.copytree(PAYLOAD, os.path.join(out_dir, "payload"))
    shutil.copy2(PATCH_TOOL, os.path.join(out_dir, "patch_tool.py"))
    shutil.copy2(MANIFEST, os.path.join(out_dir, "manifest-additive.json"))
    shutil.copy2(OFL_SRC, os.path.join(out_dir, "LICENSE-fusion-pixel-font.txt"))
    shutil.copy2(LICENSE_SRC, os.path.join(out_dir, "LICENSE"))
    shutil.copy2(NOTICES_SRC, os.path.join(out_dir, "THIRD-PARTY-NOTICES.txt"))
    for name, text in (("README.txt", render(README_SRC, version)),
                       ("KNOWN-ISSUES.txt", render(KNOWN_SRC, version)),
                       ("install.bat", INSTALL_BAT),
                       ("uninstall.bat", UNINSTALL_BAT)):
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    problems = verify_payload(os.path.join(out_dir, "payload"), manifest)
    if problems:
        raise SystemExit("发布目录校验失败：\n  " + "\n  ".join(problems[:20]))


def write_zip(out_dir, zip_path):
    if os.path.exists(zip_path):
        os.remove(zip_path)
    prefix = os.path.basename(out_dir) + "/"
    # 固定时间戳，保证相同输入产出相同 zip（载荷/说明内容变化时哈希仍会改变）。
    fixed_ts = (2026, 10, 18, 0, 0, 0)
    with zipfile.ZipFile(zip_path, "w") as archive:
        for dirpath, dirnames, filenames in os.walk(out_dir):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, out_dir).replace(os.sep, "/")
                info = zipfile.ZipInfo(prefix + rel, date_time=fixed_ts)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                with open(full, "rb") as handle:
                    archive.writestr(info, handle.read(),
                                     compress_type=zipfile.ZIP_DEFLATED,
                                     compresslevel=9)
    digest = sha256(zip_path)
    checksum_path = zip_path + ".sha256"
    with open(checksum_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("%s  %s\n" % (digest, os.path.basename(zip_path)))
    return digest


def verify_zip(zip_path, manifest):
    if not os.path.isfile(zip_path):
        raise SystemExit("找不到 zip：%s" % zip_path)
    problems = []
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        prefix = os.path.basename(zip_path)[:-4] + "/"
        if prefix + "manifest-additive.json" not in names:
            problems.append("missing manifest-additive.json")
        for entry in manifest["files"]:
            name = prefix + "payload/" + entry["path"]
            if name not in names:
                problems.append("missing: " + entry["path"])
                continue
            digest = hashlib.sha256(archive.read(name)).hexdigest()
            if digest != entry["sha256"]:
                problems.append("hash: " + entry["path"])
        for required in ("README.txt", "KNOWN-ISSUES.txt", "patch_tool.py",
                         "LICENSE", "THIRD-PARTY-NOTICES.txt",
                         "LICENSE-fusion-pixel-font.txt", "install.bat", "uninstall.bat"):
            if prefix + required not in names:
                problems.append("missing: " + required)
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="打包 X2 追加式发布目录与 zip")
    parser.add_argument("--check", action="store_true", help="只核验现有 zip")
    parser.add_argument("--force", action="store_true", help="覆盖已有产物")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    version = manifest["version"]
    out_dir = os.path.join(DIST, "FizRP-X2-v" + version)
    zip_path = out_dir + ".zip"

    if args.check:
        problems = verify_zip(zip_path, manifest) + verify_payload(PAYLOAD, manifest)
        if problems:
            print("CHECK FAILED")
            for item in problems[:30]:
                print("  " + item)
            return 1
        print("CHECK OK: %s（%d 个载荷文件）" % (os.path.basename(zip_path), len(manifest["files"])))
        return 0

    if args.force:
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        for path in (zip_path, zip_path + ".sha256"):
            if os.path.exists(path):
                os.remove(path)

    write_release(out_dir, version, manifest)
    digest = write_zip(out_dir, zip_path)
    problems = verify_zip(zip_path, manifest)
    if problems:
        print("ZIP 校验失败：")
        for item in problems[:30]:
            print("  " + item)
        return 1
    print("已生成：%s" % out_dir)
    print("已生成：%s" % zip_path)
    print("sha256：%s" % digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
