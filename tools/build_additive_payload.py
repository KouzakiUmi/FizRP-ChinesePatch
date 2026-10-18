# -*- coding: utf-8 -*-
"""组装「追加式中文（X2）」安装器载荷：``dist-additive/payload/``。

用法（在项目根执行）::

    python tools/build_additive_payload.py                 # 组装 + 生成 manifest-additive.json
    python tools/build_additive_payload.py --check         # 只核验现有载荷（不写任何文件）
    python tools/build_additive_payload.py --no-manifest   # 只组装，不生成清单

载荷是**一个平铺目录**，安装器按「相对路径首段」把条目分别投放到两个目标根：

    payload/*.assets                     -> <游戏根>/FizAndTheRainbowPlanet_Data/*.assets
    payload/StreamingAssets/**           -> <游戏根>/FizAndTheRainbowPlanet_Data/StreamingAssets/**
    payload/winhttp.dll                  -> <游戏根>/winhttp.dll
    payload/doorstop_config.ini          -> <游戏根>/doorstop_config.ini
    payload/.doorstop_version            -> <游戏根>/.doorstop_version
    payload/changelog.txt                -> <游戏根>/changelog.txt
    payload/BepInEx/**                   -> <游戏根>/BepInEx/**

> **投放位置说明（与「镜像 Data 目录」描述的偏差，故意为之）**：BepInEx 5 的
> Doorstop 代理 ``winhttp.dll`` 必须位于**游戏可执行文件所在目录**（Windows 的
> DLL 搜索顺序从 exe 目录开始，``*_Data`` 不在搜索路径里），``doorstop_config.ini``
> 与 ``BepInEx/`` 也必须与它同级；放进 ``*_Data`` 安装后不会生效。因此载荷保持
> 平铺，由安装器（``patch_tool.py`` 的 ``ADDITIVE_GAME_ROOT_NAMES`` /
> ``ADDITIVE_GAME_ROOT_PREFIXES``）把 loader 条目路由到游戏根，其余条目路由到
> Data 目录。两侧共用同一组常量，本脚本会校验载荷里没有第三条路由。

载荷文件数构成（全部现场核对，不猜）::

    102 数据文件   dist-additive/FizAndTheRainbowPlanet_Data/
                   （98 .assets + 3 个 bundle + catalog.json）
     23 游戏根     winhttp.dll、doorstop_config.ini、.doorstop_version、changelog.txt
                   （4 个）+ BepInEx/ 19 个（core 18 + plugins/FizRPLangMenu.dll）
    ---
    125

catalog.json 的生成：``work/_crc/catalog.original.json`` 复制进临时工作目录后，
用 ``tools/catalog_sync.py --bundle-dir <payload 的 StandaloneWindows64> \
--bundle localization-string-tables-spanish(es)_assets_all.bundle --crc 0 --write``
就地改写（``--crc 0`` 是**设计上的占位值**，实机首跑后从 Player.log 的 calculated
行回填），再 ``--verify`` 要求 rc=0。临时目录用完即删，因此 ``.bak`` 不会进载荷。

退出码：0 成功；1 核验失败或运行期错误；2 用法错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DIST_DATA_DIR = os.path.join(ROOT, "dist-additive", "FizAndTheRainbowPlanet_Data")
BEPINEX_RUNTIME_DIR = os.path.join(ROOT, "work", "_additive", "bepinex", "runtime")
PLUGIN_DLL = os.path.join(ROOT, "work", "_additive", "plugin", "FizRPLangMenu.dll")
PLUGIN_REL = "BepInEx/plugins/FizRPLangMenu.dll"
CATALOG_SOURCE = os.path.join(ROOT, "work", "_crc", "catalog.original.json")
CATALOG_REL = "StreamingAssets/aa/catalog.json"
CATALOG_TOOL = os.path.join(HERE, "catalog_sync.py")
TMP_DIR = os.path.join(ROOT, "work", "_additive", "_g4_tmp")
OUT_DIR = os.path.join(ROOT, "dist-additive", "payload")
MANIFEST_OUT = os.path.join(ROOT, "dist-additive", "manifest-additive.json")
INVENTORY_OUT = os.path.join(ROOT, "work", "_additive", "G4_payload_inventory.json")

ES_BUNDLE_NAME = "localization-string-tables-spanish(es)_assets_all.bundle"
ES_BUNDLE_REL = "StreamingAssets/aa/StandaloneWindows64/" + ES_BUNDLE_NAME
ES_BUNDLE_BYTES = None   # 已废弃：译文修订会改变尺寸，不再做固定值校验（保留常量避免旧引用报错）
# 数据文件数不是固定值：被修改的 .assets 数量随构建配置变化
# （单中文字体宿主 = 96 .assets + 1 es bundle = 97；双字号宿主多改 sharedassets0.assets = 98）。
# 故只校验下限，精确集合由 --check 的关键文件检查与构建报告保证。
DATA_FILE_COUNT_MIN = 96        # 至少 96 个 .assets 数据文件
RUNTIME_FILE_COUNT = 22         # work/_additive/bepinex/runtime 下文件数

# 与 patch_tool.py 一致的 loader 条目集合（首段名 / 首段前缀）
GAME_ROOT_NAMES = ("winhttp.dll", "doorstop_config.ini", ".doorstop_version",
                   "changelog.txt")
GAME_ROOT_PREFIXES = ("BepInEx/",)

def _expected_total(data_count, catalog_in_data=0):
    """载荷总文件数 = 数据 + loader + 1 插件 + 1 catalog（数据数动态传入）。

    ``catalog_in_data=1`` 表示 ``data_count`` 已经包含数据目录里的
    ``StreamingAssets/aa/catalog.json``（assemble 的 copy_into 会连它一起复制），
    此时不再额外 +1，避免把 catalog 数两遍（126 vs 125 的误报）。
    """
    return data_count + RUNTIME_FILE_COUNT + 1 + (0 if catalog_in_data else 1)
_CHUNK = 1 << 20


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def walk_files(root):
    """返回 [(相对路径(posix), 绝对路径)]，按相对路径排序。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            out.append((rel, full))
    out.sort(key=lambda item: item[0])
    return out


def route_of(rel):
    """载荷相对路径 -> 投放目标根（"game_root" 或 "data"）。第三条路由即错误。"""
    rel = str(rel).replace("\\", "/")
    head = rel.split("/", 1)[0]
    if head in GAME_ROOT_NAMES or rel.startswith(GAME_ROOT_PREFIXES):
        return "game_root"
    if head.endswith(".assets") or head == "StreamingAssets":
        return "data"
    raise ValueError("载荷条目 %s 不属于任何已知投放路由（loader / Data）" % rel)


def copy_into(src_root, dst_root, expect, prune=False):
    """把 src_root 下的文件平铺复制进 dst_root；返回复制条数（与 expect 不符即报错）。

    复制前会删掉 dst_root 里**源目录已经没有**的旧文件。否则上一版载荷留下的
    陈旧文件会一直跟着分发 —— 踩过：某版把 sharedassets2.assets 的字体 blob 换成
    中文，后来方案变更不再修改它，但陈旧副本留在载荷里，安装器照样把它写进游戏，
    而数据侧/清单/日志三方都看不出问题。
    """
    if not os.path.isdir(src_root):
        raise RuntimeError("源目录不存在: %s" % src_root)
    wanted = set(rel for rel, _full in walk_files(src_root))
    # prune 只在「数据目录 -> 载荷」那一次开启：copy_into 也被用于 loader 目录，
    # 若在第二次调用时按 loader 的文件集去删，会把刚复制好的数据文件全删掉（踩过）。
    if prune and os.path.isdir(dst_root):
        for rel, full in list(walk_files(dst_root)):
            if rel in wanted:
                continue
            if rel in (CATALOG_REL, ES_BUNDLE_REL):
                continue            # 这两个由后续步骤单独放置/校验
            if rel == PLUGIN_REL or rel.startswith("BepInEx/") or rel in (
                    "winhttp.dll", "doorstop_config.ini", "changelog.txt"):
                continue            # loader 侧不归数据目录管
            try:
                os.remove(full)
            except OSError:
                pass
    count = 0
    for rel, full in walk_files(src_root):
        dst = os.path.join(dst_root, rel.replace("/", os.sep))
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.copy2(full, dst)
        count += 1
    if expect is not None and count < expect:
        raise RuntimeError("从 %s 只复制了 %d 个文件，少于下限 %d"
                           % (src_root, count, expect))
    return count


def fresh_dir(path, expected_path):
    """清空并重建 path；删前用绝对路径自证，绝不误删其它目录。"""
    full = os.path.abspath(path)
    if full != os.path.abspath(expected_path):
        raise RuntimeError("拒绝删除非预期路径: %s (期望 %s)" % (full, expected_path))
    if os.path.isdir(full):
        shutil.rmtree(full)
    os.makedirs(full, exist_ok=True)
    return full


def run_catalog_tool(args):
    """调用 catalog_sync.py，返回 (rc, stdout, stderr)。

    子进程强制 UTF-8 输出（PYTHONIOENCODING）：默认会被 Windows 控制台代码页
    （GBK/CP936）接管，管道里就会变成不可逆的乱码。
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run([sys.executable, CATALOG_TOOL] + list(args),
                          cwd=ROOT, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    if out:
        print(out.rstrip())
    if err:
        print(err.rstrip(), file=sys.stderr)
    return proc.returncode, out, err


def generate_catalog(out_dir):
    """用 catalog_sync 生成 payload 内的 catalog.json；返回核验输出。"""
    for path in (CATALOG_SOURCE, CATALOG_TOOL):
        if not os.path.isfile(path):
            raise RuntimeError("缺少输入文件: %s" % path)
    bundle_dir = os.path.join(out_dir, "StreamingAssets", "aa",
                              "StandaloneWindows64")
    bundle_file = os.path.join(bundle_dir, ES_BUNDLE_NAME)
    if not os.path.isfile(bundle_file):
        raise RuntimeError("payload 内找不到 es 串表 bundle: %s" % bundle_file)
    size = os.path.getsize(bundle_file)
    if size <= 0:
        raise RuntimeError("es 串表 bundle 为空: %s" % bundle_file)
    # 刻意不校验固定尺寸：译文修订会改变 bundle 大小，而 catalog_sync 是按实际文件
    # 写入 m_BundleSize 的，硬编码期望值只会造成误报（曾因此中断组装并产出残缺载荷）。

    # 在临时目录里改写：catalog_sync 落盘前会写同名 .bak，不能让它落进载荷。
    tmp = fresh_dir(TMP_DIR, TMP_DIR)
    work_catalog = os.path.join(tmp, "catalog.json")
    shutil.copy2(CATALOG_SOURCE, work_catalog)
    print("== catalog_sync: %s -> %s" % (CATALOG_SOURCE, work_catalog))

    # 同步载荷里**所有** bundle，而不只是 es 串表：
    # 图像本地化会额外带 localization-assets-{shared,japanese(ja)}，
    # 只同步 es 会让那两个 bundle 的 m_BundleSize/m_Crc 保持原版值，
    # Addressables 校验不过 -> 贴图不加载（踩过：游戏里图片没换）。
    payload_bundles = sorted(f for f in os.listdir(bundle_dir) if f.endswith(".bundle"))
    bundle_args = []
    for name in payload_bundles:
        bundle_args += ["--bundle", name]
    rc, _out, _err = run_catalog_tool([
        work_catalog, "--bundle-dir", bundle_dir, *bundle_args,
        "--crc", "0", "--write"])
    if rc != 0:
        raise RuntimeError("catalog_sync --write 退出码 %d（拒绝产出占位 catalog）" % rc)

    rc, verify_out, _err = run_catalog_tool([work_catalog, "--verify"])
    if rc != 0:
        raise RuntimeError("catalog_sync --verify 退出码 %d（生成结果不自洽）" % rc)

    dst = os.path.join(out_dir, CATALOG_REL.replace("/", os.sep))
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    shutil.copy2(work_catalog, dst)
    shutil.rmtree(tmp, ignore_errors=True)
    return {"verify_rc": rc, "verify_tail": verify_out.strip().splitlines()[-3:],
            "bytes": os.path.getsize(dst), "sha256": sha256(dst)}


def assemble():
    """组装载荷目录，返回统计信息。"""
    out = fresh_dir(OUT_DIR, OUT_DIR)
    print("载荷输出目录: %s" % out)

    print("== 1/4 数据文件: %s" % DIST_DATA_DIR)
    data_count = copy_into(DIST_DATA_DIR, out, DATA_FILE_COUNT_MIN, prune=True)

    print("== 2/4 loader 运行时: %s" % BEPINEX_RUNTIME_DIR)
    runtime_count = copy_into(BEPINEX_RUNTIME_DIR, out, RUNTIME_FILE_COUNT)

    print("== 3/4 插件 DLL: %s -> %s" % (PLUGIN_DLL, PLUGIN_REL))
    if not os.path.isfile(PLUGIN_DLL):
        raise RuntimeError("插件 DLL 不存在: %s" % PLUGIN_DLL)
    plugin_dst = os.path.join(out, PLUGIN_REL.replace("/", os.sep))
    os.makedirs(os.path.dirname(plugin_dst), exist_ok=True)
    shutil.copy2(PLUGIN_DLL, plugin_dst)

    print("== 4/4 catalog.json（原版 catalog + payload es bundle，--crc 0 占位）")
    catalog_info = generate_catalog(out)

    files = walk_files(out)
    routes = {"data": 0, "game_root": 0}
    for rel, _full in files:
        routes[route_of(rel)] += 1
    expected_total = _expected_total(data_count, catalog_in_data=1)
    if len(files) != expected_total:
        raise RuntimeError("载荷文件数 %d != 期望 %d（%d 数据 + %d loader + 1 插件 + 1 catalog）"
                           % (len(files), expected_total, data_count, RUNTIME_FILE_COUNT))
    return {"out_dir": out, "files": files, "data_count": data_count,
            "runtime_count": runtime_count, "routes": routes,
            "catalog": catalog_info}


def check_payload(out_dir=None):
    """只读核验现有载荷（存在性、计数、路由、catalog 自洽）。返回 (ok, 明细列表)。"""
    out_dir = os.path.abspath(out_dir or OUT_DIR)
    lines = []
    problems = []
    lines.append("载荷目录: %s" % out_dir)
    if not os.path.isdir(out_dir):
        return False, lines + ["载荷目录不存在。"]
    files = walk_files(out_dir)
    data_files = sum(1 for rel, _f in files if "/" not in rel.replace("\\", "/")
                     and rel.endswith(".assets"))
    # bundle 不再只有 es 串表：图像本地化会再加 ja / shared 两个 bundle。
    # 按实际数量计，否则一加 bundle 就误报「文件数异常」。
    bundle_files = sum(1 for rel, _f in files if rel.endswith(".bundle"))
    expect_total = _expected_total(data_files + bundle_files)
    lines.append("载荷文件数: %d（按 %d .assets + %d bundle + %d loader + 插件 + catalog 推算期望 %d）"
                 % (len(files), data_files, bundle_files, RUNTIME_FILE_COUNT, expect_total))
    if len(files) != expect_total:
        problems.append("文件数 %d != %d" % (len(files), expect_total))
    rels = set(rel for rel, _full in files)
    routes = {"data": 0, "game_root": 0}
    for rel in sorted(rels):
        try:
            routes[route_of(rel)] += 1
        except ValueError as exc:
            problems.append(str(exc))
    lines.append("投放路由: Data=%d, 游戏根=%d" % (routes["data"], routes["game_root"]))
    for rel in (ES_BUNDLE_REL, CATALOG_REL, PLUGIN_REL, "winhttp.dll",
                "doorstop_config.ini", "BepInEx/core/BepInEx.Preloader.dll"):
        if rel in rels:
            lines.append("  存在: %s (%d B)"
                         % (rel, os.path.getsize(os.path.join(out_dir, rel.replace("/", os.sep)))))
        else:
            problems.append("缺少关键文件: %s" % rel)
    es = os.path.join(out_dir, ES_BUNDLE_REL.replace("/", os.sep))
    if os.path.isfile(es) and os.path.getsize(es) <= 0:
        problems.append("es 串表 bundle 为空: %s" % ES_BUNDLE_REL)
    # 尺寸是否与 catalog 记录一致由下面的 catalog_sync --verify 判定（自洽性检查），
    # 不在这里比对任何硬编码期望值。
    catalog = os.path.join(out_dir, CATALOG_REL.replace("/", os.sep))
    if os.path.isfile(catalog):
        rc, _out, _err = run_catalog_tool([catalog, "--verify"])
        lines.append("catalog_sync --verify: rc=%d" % rc)
        if rc != 0:
            problems.append("catalog_sync --verify 退出码 %d" % rc)
    else:
        problems.append("缺少 %s" % CATALOG_REL)
    if "catalog.json.bak" in " ".join(sorted(rels)) or any(
            rel.endswith(".bak") for rel in rels):
        problems.append("载荷内出现 .bak 残留")

    # 交叉断言：投放 Data 的条目必须与「数据侧产物目录」逐字节一致。
    # 这条由子代理 A 的 G-6 触发 —— 载荷里的 es 串表 bundle 曾与 data 目录不同步
    # （8936 vs 8905 字节），而本函数原先只做自洽性检查（catalog 与载荷内部一致），
    # 发现不了「载荷整体滞后于数据侧」；照 payload 分发/重装会把译文回退一轮。
    # 修法：先跑 tools/build_additive_data.py，再重建载荷。
    drift = []
    compared = 0
    for rel in sorted(rels):
        if route_of(rel) != "data":
            continue
        src = os.path.join(DIST_DATA_DIR, rel.replace("/", os.sep))
        dst = os.path.join(out_dir, rel.replace("/", os.sep))
        if not os.path.isfile(src) or not os.path.isfile(dst):
            continue
        if os.path.getsize(src) != os.path.getsize(dst):
            drift.append((rel, os.path.getsize(src), os.path.getsize(dst)))
            continue
        compared += 1
        with open(src, "rb") as fh:
            a = hashlib.sha256(fh.read()).digest()
        with open(dst, "rb") as fh:
            b = hashlib.sha256(fh.read()).digest()
        if a != b:
            drift.append((rel, os.path.getsize(src), os.path.getsize(dst)))
    # 防线：载荷里不该出现「与原版完全相同」的数据文件。
    # 出现过：某版把 sharedassets2.assets 的字体 blob 换成中文，方案变更后不再修改它，
    # 但陈旧副本留在载荷里被照常安装 —— 游戏里就一直留着上一版改过的字体，
    # 而数据侧、清单、安装日志三方都看不出问题。
    staging = os.path.join(ROOT, "work", "_additive", "staging",
                           "FizAndTheRainbowPlanet_Data")
    stale_same = []
    if os.path.isdir(staging):
        for rel in sorted(rels):
            if route_of(rel) != "data" or not rel.endswith(".assets"):
                continue
            orig = os.path.join(staging, rel.replace("/", os.sep))
            cur = os.path.join(out_dir, rel.replace("/", os.sep))
            if not os.path.isfile(orig) or not os.path.isfile(cur):
                continue
            if os.path.getsize(orig) != os.path.getsize(cur):
                continue
            with open(orig, "rb") as fh:
                a = hashlib.sha256(fh.read()).digest()
            with open(cur, "rb") as fh:
                b = hashlib.sha256(fh.read()).digest()
            if a == b:
                stale_same.append(rel)
    if stale_same:
        problems.append("载荷含 %d 个与原版完全相同的数据文件（陈旧残留，"
                        "应清掉；可能之前版本改过、现在已不必分发）: %s"
                        % (len(stale_same), ", ".join(stale_same[:5])))
    else:
        lines.append("陈旧残留检查: 载荷数据文件均与原版不同 OK")
    lines.append("与数据目录交叉核对: 逐字节比对 %d 个文件，不一致 %d 个"
                 % (compared, len(drift)))
    for rel, sa, sb in drift[:10]:
        problems.append("载荷与数据目录不同步: %s（data %d B / payload %d B）"
                        " —— 先跑 tools/build_additive_data.py 再重建载荷" % (rel, sa, sb))
    if len(drift) > 10:
        problems.append("…另有 %d 个不同步文件未逐条列出" % (len(drift) - 10))
    for problem in problems:
        lines.append("问题: %s" % problem)
    ok = not problems
    lines.append("Payload: %s (%d)" % ("OK" if ok else "异常", len(files)))
    return ok, lines


def write_inventory(info, check_lines=None):
    payload_dir = info["out_dir"]
    entries = []
    for rel, full in info["files"]:
        entries.append({"path": rel, "route": route_of(rel),
                        "size": os.path.getsize(full), "sha256": sha256(full)})
    doc = {
        "generated_by": "tools/build_additive_payload.py",
        "payload_dir": payload_dir,
        "file_count": len(entries),
        "file_count_breakdown": {"data": info["data_count"],
                                 "loader_runtime": info["runtime_count"],
                                 "plugin": 1, "catalog": 1},
        "routes": info["routes"],
        "catalog": info["catalog"],
        "selfcheck": check_lines,
        "files": entries,
    }
    os.makedirs(os.path.dirname(INVENTORY_OUT), exist_ok=True)
    with open(INVENTORY_OUT, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    print("清单候选（未签名）: %s" % INVENTORY_OUT)
    return doc


def build_manifest(out_dir):
    """调用 build_manifest.py 的 additive 分支生成 dist-additive/manifest-additive.json。"""
    sys.path.insert(0, HERE)
    import build_manifest  # noqa: E402  （同目录模块，组装末段才需要）

    manifest = build_manifest.build_manifest(payload_dir=out_dir)
    build_manifest.write_manifest(manifest, MANIFEST_OUT)
    print("manifest: %s（%d files, %d bytes）"
          % (MANIFEST_OUT, manifest["payload_files"], manifest["payload_bytes"]))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="build_additive_payload.py",
        description="组装追加式中文（X2）安装器载荷 dist-additive/payload/",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="只核验现有载荷，不写任何文件")
    parser.add_argument("--no-manifest", action="store_true",
                        help="只组装载荷，不生成 manifest-additive.json")
    args = parser.parse_args(argv)

    try:
        if args.check:
            ok, lines = check_payload()
            for line in lines:
                print(line)
            return 0 if ok else 1

        info = assemble()
        ok, lines = check_payload(info["out_dir"])
        for line in lines:
            print(line)
        if not ok:
            raise RuntimeError("组装后自检未通过")
        write_inventory(info, lines)
        if not args.no_manifest:
            build_manifest(info["out_dir"])
    except Exception as exc:
        print("build_additive_payload: FAILED - %s" % exc, file=sys.stderr)
        return 1
    print("build_additive_payload: OK（载荷 %d 文件，Data %d / 游戏根 %d）"
          % (len(info["files"]), info["routes"]["data"], info["routes"]["game_root"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
