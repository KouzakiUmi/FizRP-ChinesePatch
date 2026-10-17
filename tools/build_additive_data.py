# -*- coding: utf-8 -*-
"""生成「追加式中文（X2）」的数据侧产物：``dist-additive/FizAndTheRainbowPlanet_Data/``。

用法（在项目根执行）::

    python tools/build_additive_data.py            # 读取 work/_additive/staging 的原版资产
    python tools/build_additive_data.py --check    # 只核对产物，不写文件

数据侧与载荷侧分开：

    tools/build_additive_data.py     原版资产  ->  dist-additive/FizAndTheRainbowPlanet_Data/
    tools/build_additive_payload.py  上一步产物 ->  dist-additive/payload/ + manifest-additive.json

`build_additive_payload.py` 只做组装，**不会**重新跑文本注入，所以改了
`src/build_patch.py` 或 `translation/zh_Hans.csv` 之后必须先跑本脚本，否则载荷里
还是上一版数据。这个坑踩过一次：载荷清单的时间戳没变、安装「成功」，但文本没更新。

参数与原 G1 构建一致：中文写入原先空置的 `es`（Language.Spanish = 4）槽位，
profile = `zh_additive`，只替换一个字体 blob（k8x12EXL）。默认还会把
`work/image_tickets_opt/deliverables-opt` 的 16 张 v2.4 贴图回灌进数据目录
（`--no-images` 可跳过，仅调试用），并在末尾同步 catalog。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

STAGING_ROOT = os.path.join(ROOT, "work", "_additive", "staging")
OUT_DIR = os.path.join(ROOT, "dist-additive", "FizAndTheRainbowPlanet_Data")

# 与原构建一致；改动这些等于改变交付形态，需同步 docs。
SLOT = 4                 # Language.Spanish
LOCALE = "es"
PROFILE = "zh_additive"
COLUMN = "zh_Hans"

# `font_size` 会被 `build_patch` **直接写进 es 槽的 `size`**（src/build_patch.py 的
# LocFontData 分支），所以它必须等于 es 槽所指字体的**设计尺寸**，否则字号与字形网格
# 不 1:1 —— 8px 设计配 size 10/12 分别是 1.25×/1.5× 的整数倍缩放，像素字会糊。
#
# 方案甲（2026-10-16 定案）：es 槽**按该 LocFontData 的 defaultFont 档位镜像**，
# 两个宿主都装 zh_hans blob，且宿主设计尺寸 == 它被使用的字号：
#     size 12 -> sharedassets0.assets:14   k8x12EXS  <- fusion-12px-zh_hans
#     size  8 -> sharedassets3.assets:133  k8x12EXL  <- fusion-8px-zh_hans
# 与插件常量 `Font10Name="k8x12EXS"/SizeLarge=12`、`Font8Name="k8x12EXL"/SizeSmall=8`
# 一一对应，所以数据侧与运行时完全一致，没有瞬时失配。
#
# 这条不变量被静默破坏过一次（构建默认参数 font_size=12 覆盖了原先的 10，
# 谁都没注意到），所以现在由 build_patch 的 `_additive_size_for` 统一决定，
# 并在 --check 里逐槽断言。
SLOT_FONT_BY_SIZE = {8: ("sharedassets3.assets", 133),
                     12: ("sharedassets0.assets", 14)}
# 回退：sharedassets137.assets 的外部表里没有 sharedassets2.assets，
# 它的 es 槽会回退到 12 档宿主（见 build_patch 的 fallback 分支）。
SLOT_FALLBACK_SIZE = 12
ES_BUNDLE_NAME = "localization-string-tables-spanish(es)_assets_all.bundle"

# 文本构建先落到临时目录，再用 tools/build_image_patch.py 把 16 张 v2.4 贴图
# 回灌到最终数据目录。缺了这一步，data 会“文本/字体正确、贴图回退成原版”，
# 而 verify_patch 只核对文本，看不出来（本次踩过）。
TEXT_STAGE = os.path.join(ROOT, "work", "_additive", "_stage_text",
                          "FizAndTheRainbowPlanet_Data")
IMAGE_STAGE = os.path.join(ROOT, "work", "_additive", "_stage_images",
                           "FizAndTheRainbowPlanet_Data")
IMAGES_DIR = os.path.join(ROOT, "work", "image_tickets_opt", "deliverables-opt")
IMAGE_TOOL = os.path.join(ROOT, "tools", "build_image_patch.py")


def _fresh_dir(path):
    """清空并重建构建目录；先自证路径落在 work/ 或 dist-additive/ 下。"""
    full = os.path.abspath(path)
    allowed = (os.path.abspath(os.path.join(ROOT, "work")),
               os.path.abspath(os.path.join(ROOT, "dist-additive")))
    if not any(full == base or full.startswith(base + os.sep) for base in allowed):
        raise RuntimeError("拒绝清理非构建目录: %s" % full)
    if os.path.isdir(full):
        shutil.rmtree(full)
    os.makedirs(full)


def _copy_missing(src_root, dst_root):
    """把 src_root 中目标不存在的文件补进 dst_root（不覆盖已构建的 es bundle）。"""
    for rel in _walk_rel(src_root):
        src = os.path.join(src_root, rel)
        dst = os.path.join(dst_root, rel)
        if os.path.exists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def _walk_rel(root):
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            yield os.path.relpath(os.path.join(dirpath, name), root)


def _changed_files(text_stage, staging_data):
    """TEXT_STAGE 相对 staging 有差异的文件（即文本/字体实际改写的文件集）。"""
    changed = []
    for rel in _walk_rel(text_stage):
        src = os.path.join(text_stage, rel)
        base = os.path.join(staging_data, rel)
        if os.path.isfile(base):
            with open(src, "rb") as a, open(base, "rb") as b:
                if hashlib.sha256(a.read()).hexdigest() == hashlib.sha256(b.read()).hexdigest():
                    continue
        changed.append(rel)
    return changed


def _sync_catalog(out_dir):
    """让数据目录自己的 catalog 与 es bundle 尺寸一致（中间产物也自洽）。

    仍**不要**直接分发本目录：正式载荷由 build_additive_payload.py 重新生成
    catalog（CRC 占位 0），本步骤只是避免 data 目录出现「catalog 说 8905、
    bundle 实际 8904」这种中间态误导。
    """
    catalog = os.path.join(out_dir, "StreamingAssets", "aa", "catalog.json")
    bundle_dir = os.path.join(out_dir, "StreamingAssets", "aa", "StandaloneWindows64")
    tool = os.path.join(ROOT, "tools", "catalog_sync.py")
    if not os.path.isfile(catalog):
        print("跳过 catalog 同步：找不到 %s" % catalog)
        return 0
    bundles = sorted(name for name in os.listdir(bundle_dir) if name.endswith(".bundle"))
    bundle_args = []
    for name in bundles:
        bundle_args += ["--bundle", name]
    for extra in (["--crc", "0", "--write"], ["--verify"]):
        rc = subprocess.call([sys.executable, tool, catalog,
                              "--bundle-dir", bundle_dir, *bundle_args] + extra)
        if rc != 0:
            return rc
    bak = catalog + ".bak"
    if os.path.exists(bak):
        os.remove(bak)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成追加式中文补丁的数据侧产物")
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--staging", default=STAGING_ROOT,
                    help="原版资产根目录（含 FizAndTheRainbowPlanet_Data）")
    ap.add_argument("--translations", default=os.path.join(ROOT, "translation", "zh_Hans.csv"))
    ap.add_argument("--images", default=IMAGES_DIR,
                    help="贴图交付目录（默认 v2.4 deliverables-opt）")
    ap.add_argument("--no-images", action="store_true",
                    help="跳过贴图回灌（仅调试；正式构建不要用）")
    ap.add_argument("--check", action="store_true", help="只核验现有产物，不写文件")
    args = ap.parse_args(argv)

    if not os.path.isdir(os.path.join(args.staging, "FizAndTheRainbowPlanet_Data")):
        print("找不到原版资产: %s" % args.staging)
        return 2
    os.environ["FIZRP_ROOT"] = args.staging   # build_patch 通过它定位原版 DATA_DIR

    import build_patch  # noqa: E402  (必须在设置 FIZRP_ROOT 之后导入)

    if args.check:
        return _check(args.out, args.staging)

    build_kwargs = dict(
        translations=args.translations,
        column=COLUMN,
        slot=SLOT,
        locale_code=LOCALE,
        profile=PROFILE,
        additive=True,
    )
    if args.no_images:
        _fresh_dir(args.out)
        report = build_patch.build(out_dir=args.out, **build_kwargs)
    else:
        if not os.path.isdir(args.images):
            print("找不到贴图交付目录: %s" % args.images)
            return 2
        staging_data = os.path.join(args.staging, "FizAndTheRainbowPlanet_Data")
        # 1) 完整基线：文本注入与贴图回灌都需要未修改的 assets/bundle 作基础
        _fresh_dir(TEXT_STAGE)
        shutil.copytree(staging_data, TEXT_STAGE, dirs_exist_ok=True)
        # 2) 文本/字体注入（就地写进基线副本）
        report = build_patch.build(out_dir=TEXT_STAGE, **build_kwargs)
        # build_patch 会删掉「原版未改动、不再分发」的文件（如 sharedassets13），
        # 但贴图回灌还需要它们作为基础；补回（不覆盖已注入的文本/字体）。
        _copy_missing(staging_data, TEXT_STAGE)
        # 3) 贴图回灌到临时目录（只产出被改的 4 个文件）
        _fresh_dir(IMAGE_STAGE)
        print("== 贴图回灌: %s -> %s" % (args.images, IMAGE_STAGE))
        rc = subprocess.call([sys.executable, IMAGE_TOOL,
                              "--base-data-dir", TEXT_STAGE,
                              "--out-data-dir", IMAGE_STAGE,
                              "--images", args.images])
        if rc != 0:
            print("错误: 贴图回灌失败（rc=%d）" % rc)
            return rc
        report_path = os.path.join(IMAGE_STAGE, "image_patch_roundtrip.json")
        if os.path.isfile(report_path):
            shutil.move(report_path,
                        os.path.join(ROOT, "work", "_additive",
                                     "image_patch_roundtrip.json"))
        # 4) 合并「文本修改集 + 图像修改集 + 原版 catalog」
        _fresh_dir(args.out)
        for rel in _changed_files(TEXT_STAGE, staging_data):
            src = os.path.join(TEXT_STAGE, rel)
            dst = os.path.join(args.out, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        for rel in _walk_rel(IMAGE_STAGE):
            src = os.path.join(IMAGE_STAGE, rel)
            dst = os.path.join(args.out, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        catalog_rel = os.path.join("StreamingAssets", "aa", "catalog.json")
        shutil.copy2(os.path.join(staging_data, catalog_rel),
                     os.path.join(args.out, catalog_rel))
        shutil.rmtree(os.path.dirname(TEXT_STAGE), ignore_errors=True)
        shutil.rmtree(os.path.dirname(IMAGE_STAGE), ignore_errors=True)
    io.open(os.path.join(ROOT, "work", "_additive", "G1_build_raw.json"),
            "w", encoding="utf-8", newline="\n").write(
        json.dumps(report, ensure_ascii=False, indent=1))

    mode = report.get("mode") or {}
    got = mode.get("additive_font") or {}
    want = {str(k): list(v) for k, v in sorted(SLOT_FONT_BY_SIZE.items())}
    if got != want:
        print("错误: es 槽宿主映射写成 %r，应为 %r（见 SLOT_FONT_BY_SIZE 注释）"
              % (got, want))
        return 1
    fixes = sum(int(a.get("treasure_fix", 0)) for a in report["assets"])
    total_text = sum(int(a.get("text", 0)) for a in report["assets"])
    print("文本写入 %d 条；宝藏默认表错位修正 %d 处" % (total_text, fixes))
    cov = report.get("coverage") or {}
    if cov:
        print("覆盖: %s" % json.dumps(cov, ensure_ascii=False)[:300])
    if fixes != 1:
        print("警告: 期望恰好修正 1 处 TreasureText_default 错位，实际 %d" % fixes)
        return 1
    rc = _sync_catalog(args.out)
    if rc:
        print("错误: 数据目录 catalog 同步失败（rc=%d）" % rc)
        return rc
    print("OK -> %s" % args.out)
    return 0


def _check(out_dir, staging_root=None):
    """核对产物：TreasureText_default 必须是 [0,1,2,3,4]，且各槽非空。"""
    import unity_env
    from custom_types import decode
    from unity_env import open_env

    path = os.path.join(out_dir, "sharedassets3.assets")
    if not os.path.isfile(path):
        print("产物缺失: %s" % path)
        return 2
    env = open_env(path)
    sf = None
    for cand in env.files.values():
        if hasattr(cand, "objects") and hasattr(cand, "externals"):
            sf = cand
            break
    data = decode(sf.objects[491].get_raw_data(), "TextData")
    langs = [b.get("language") for b in data["textDatas"]]
    print("TreasureText_default langs = %s  blocks=%d" % (langs, len(langs)))
    ok = langs == [0, 1, 2, 3, 4]

    # 每个 es 槽必须镜像该 LocFontData 的 defaultFont 档位，且字号 == 宿主设计尺寸
    # （见 SLOT_FONT_BY_SIZE 注释）。这条不变量曾被静默破坏过，所以逐槽断言。
    import build_patch

    for fname in ("sharedassets3.assets", "sharedassets7.assets",
                  "sharedassets137.assets", "sharedassets153.assets"):
        fpath = os.path.join(out_dir, fname)
        if not os.path.isfile(fpath):
            # 不在产物里 = 本轮没有改动它。那它的原版值必须已经符合预期，
            # 否则就是「该改而没改」的漏网（构建报告看不出来），所以要核验原版。
            if staging_root:
                fpath = os.path.join(staging_root, "FizAndTheRainbowPlanet_Data", fname)
                print("  %-16s 未分发（未修改）→ 核验原版 %s"
                      % (fname.replace(".assets", ""), "存在" if os.path.isfile(fpath) else "缺失"))
            if not os.path.isfile(fpath):
                print("  %s 既不在产物也不在原版，无法核验" % fname)
                ok = False
                continue
        fenv = open_env(fpath)
        fsf = None
        for cand in fenv.files.values():
            if hasattr(cand, "objects") and hasattr(cand, "externals"):
                fsf = cand
                break
        ex = [os.path.basename(str(e.path)) for e in (fsf.externals or [])]
        for obj in fsf.objects.values():
            if obj.type.name != "MonoBehaviour":
                continue
            try:
                if unity_env.mb_class(obj, fsf) != "LocFontData":
                    continue
            except Exception:
                continue
            d = decode(obj.get_raw_data(), "LocFontData")
            default = d.get("defaultFont") or {}
            want_size = build_patch._additive_size_for(default)
            want_file, want_pid = SLOT_FONT_BY_SIZE[want_size]
            # 注意：文件不会把自己列进 externals，所以「同文件引用」永远是合法的，
            # 不能只判 `want_file not in ex`（那会把 sharedassets3 自己的
            # LocFontData -> sharedassets3:133 误判成不可解析）。
            if want_file != fname and want_file not in ex:   # 无镜像目标 -> 预期回退
                want_size = SLOT_FALLBACK_SIZE
                want_file, want_pid = SLOT_FONT_BY_SIZE[want_size]
            # defaultFont 自身的归属文件：PPtr 的 m_FileID 决定
            df_ref = (default.get("font") or {})
            df_fid = df_ref.get("m_FileID", 0)
            df_file = fname if df_fid == 0 else (ex[df_fid - 1] if 0 < df_fid <= len(ex) else "?")
            for b in d.get("fontDatas") or []:
                if b.get("language") != SLOT:
                    continue
                pid = (b.get("font") or {}).get("m_PathID")
                fid = (b.get("font") or {}).get("m_FileID", 0)
                got_file = fname if fid == 0 else (ex[fid - 1] if 0 < fid <= len(ex) else "?")
                good = (b.get("size") == want_size and got_file == want_file
                        and pid == want_pid)
                ok = ok and good
                print("  %-16s default=%-4s(size=%s) -> es: size=%s %s:%s  %s"
                      % (fname.replace(".assets", ""), df_file, default.get("size"),
                         b.get("size"), got_file, pid,
                         "OK" if good else "**与 SLOT_FONT_BY_SIZE 不符**"))
    for b in data["textDatas"]:
        if b.get("language") == SLOT:
            s = b.get("strings") or []
            print("  es 槽 strings = %s" % [x for x in s[:2]])
            ok = ok and len(s) >= 2 and bool(s[0])
    print("check: %s" % ("OK" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
