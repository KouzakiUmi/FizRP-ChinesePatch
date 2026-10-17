# -*- coding: utf-8 -*-
"""Fiz 与彩虹星球 简体中文补丁 —— 无头核心 + 命令行 (纯标准库, Python 3.8+)

用法:
  python patch_tool.py detect                              # 自动探测游戏数据目录
  python patch_tool.py check                               # 载荷自检
  python patch_tool.py verify    [--game-dir PATH]         # 校验游戏内文件是否与载荷一致
  python patch_tool.py install   [--game-dir PATH] [--yes] # 安装中文补丁
  python patch_tool.py uninstall [--game-dir PATH] [--yes] # 从最新备份还原英文原版
  # 追加式中文（X2）：以上子命令都支持 --additive
  python patch_tool.py install   --additive [--game-dir PATH] [--yes] [--no-seed-save]
  python patch_tool.py uninstall --additive [--game-dir PATH] [--yes]
  # 所有子命令都支持 --json: 最后一行输出 json.dumps(结果, ensure_ascii=False)

语义约定 (与 dist/FizRP-Chinese-Patch/tools/install.ps1 / uninstall.ps1 保持一致):
  * 替换式载荷目录: ROOT/payload, 回退 ROOT/dist/FizRP-Chinese-Patch/files
  * 追加式载荷目录: ROOT/additive-payload, 回退 ROOT/dist-additive/payload
    (ROOT 在打包态是 sys._MEIPASS, 源码态是 tools/ 的上一级)
  * 安装: 先把"将被覆盖"的游戏内现有文件备份到
    <游戏根>/_FizRP_backup_<yyyyMMdd-HHmmss>, 再复制载荷; 不写任何状态文件
  * 卸载: 从 <游戏根> 下同名备份目录中"最新"的一个还原, 且不删除备份目录
  * 退出码只有 0 与 1; 输出为中文

追加式（--additive）与替换式的差别 —— 只为 additive 分支增加行为，替换式路径逐字节不变:
  1. 载荷是一个平铺目录，按相对路径首段分流投放:
       Data 侧  (顶层 *.assets / StreamingAssets/**)  -> <游戏根>/FizAndTheRainbowPlanet_Data/
       loader   (winhttp.dll / doorstop_config.ini / .doorstop_version / changelog.txt /
                 BepInEx/**)                        -> <游戏根>/
     loader 必须与游戏 exe 同级（Windows DLL 搜索顺序），放进 Data 目录不会生效。
  2. loader 条目**不进备份、也不从备份还原**: 安装器自己复制进去，卸载器删除"载荷列出的
     那些文件"，再自底向上清掉因此变空的目录；用户自己的 BepInEx 内容（例如 config/、
     其它插件）一律保留。
  3. V6 备份缺口: 载荷里 Data 侧文件若安装前不存在（游戏里本来没有），备份目录不会有它，
     卸载时无法还原 —— 对这类文件只在"内容与载荷逐字节一致"（可证明是本安装器写入的）时
     才删除，否则保留并警告。
  4. 存档播种（X3）: 仅当
     %USERPROFILE%/AppData/LocalLow/NijiiroDragon/FizAndTheRainbowPlanet/SaveFile.es3
     **不存在**时才写入最小合法存档（Language=4=Spanish，即中文所在的 es 槽位）；
     已存在则一个字节都不改。格式取自实机存档逐字节核验（CRLF + TAB 缩进 +
     {"__type":..,"value":..} 嵌套，无 BOM、无结尾换行），见 es3_render_json()。
     测试可用环境变量 FIZRP_SAVE_ROOT 覆盖 LocalLow 根（默认 %USERPROFILE%/AppData/LocalLow）。
"""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# PyInstaller --onefile 会把 datas 解包到 sys._MEIPASS; 源码态则是 tools/ 的上一级。
ROOT = getattr(sys, "_MEIPASS", os.path.dirname(HERE))


def _first_existing(*candidates):
    """取第一个存在的路径 (都不存在时返回最后一个候选, 便于报错时显示)。"""
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return candidates[-1]


# ROOT/payload → ROOT/dist/FizRP-Chinese-Patch/files (打包态 / 源码态)
PAYLOAD_DIR = _first_existing(
    os.path.join(ROOT, "payload"),
    os.path.join(ROOT, "dist", "FizRP-Chinese-Patch", "files"),
)
# ROOT/patch-info.json → ROOT/dist/FizRP-Chinese-Patch/patch-info.json
PATCH_INFO = _first_existing(
    os.path.join(ROOT, "patch-info.json"),
    os.path.join(ROOT, "dist", "FizRP-Chinese-Patch", "patch-info.json"),
)
MANIFEST = os.path.join(ROOT, "manifest.json")

# 追加式（X2）载荷与清单：ROOT/additive-payload → ROOT/dist-additive/payload（源码态）；
# 清单里的 patch_info 一并复用（reference_hashes 来自替换式 patch-info.json）。
ADDITIVE_PAYLOAD_DIR = _first_existing(
    os.path.join(ROOT, "additive-payload"),
    os.path.join(ROOT, "dist-additive", "payload"),
)
ADDITIVE_MANIFEST = _first_existing(
    os.path.join(ROOT, "manifest-additive.json"),
    os.path.join(ROOT, "dist-additive", "manifest-additive.json"),
)

# 追加式载荷里属于**游戏根**（与 exe 同级）的条目：首段名 与 首段前缀。
# 其余条目（顶层 *.assets / StreamingAssets/**）落 Data 目录。两侧常量必须与
# tools/build_additive_payload.py 的 GAME_ROOT_NAMES / GAME_ROOT_PREFIXES 一致。
ADDITIVE_GAME_ROOT_NAMES = ("winhttp.dll", "doorstop_config.ini",
                            ".doorstop_version", "changelog.txt")
ADDITIVE_GAME_ROOT_PREFIXES = ("BepInEx/",)

# 替换式补丁态 / additive 态的特征文件与尺寸（现场核验值，非推测）：
#   原版 en 串表 bundle = 9585 B；替换式把中文写进 en 槽位后 = 25723 B
#   原版 es 串表 bundle = 4339 B；additive 写入中文后    = 8936 B
EN_STRING_TABLE_NAME = "localization-string-tables-english(en)_assets_all.bundle"
ES_STRING_TABLE_NAME = "localization-string-tables-spanish(es)_assets_all.bundle"
BUNDLE_SUBDIR = ("StreamingAssets", "aa", "StandaloneWindows64")
CATALOG_REL = "StreamingAssets/aa/catalog.json"
EN_STRING_TABLE_PRISTINE_BYTES = 9585
ES_STRING_TABLE_PRISTINE_BYTES = 4339
ES_STRING_TABLE_ADDITIVE_BYTES = 8936

# 存档播种（X3）
SAVE_VENDOR_DIR = ("NijiiroDragon", "FizAndTheRainbowPlanet")
SAVE_FILENAME = "SaveFile.es3"
SAVE_ROOT_ENV = "FIZRP_SAVE_ROOT"       # 测试钩子：覆盖 LocalLow 根（只读环境变量）
LANGUAGE_SPANISH = 4                    # Language 枚举: Japanese=0..Spanish=4, Max=5
SAVE_LANGUAGE_TYPE = "Language,Assembly-CSharp"
SAVE_DUMMY_TYPE = "int"
# V6 备份缺口的关键文件：这些相对路径一定在安装前存在，必须落到备份目录里
V6_TRACKED_RELS = (CATALOG_REL,)

BACKUP_PREFIX = "_FizRP_backup_"
# 不可变原版副本：首次安装时按"首次见到的内容"留档，之后的安装绝不覆盖它；
# 卸载优先从这里还原。滚动备份（BACKUP_PREFIX）存的是"上一次安装前"的状态，
# 在多次安装之后它已是我们自己的版本，不能作为还原原版的依据。
ORIGINAL_PREFIX = "_FizRP_original"
LEGACY_BACKUP_DIRNAMES = (".fizrp-backup",)
GAME_REL = ("steamapps", "common", "FizRP", "FizAndTheRainbowPlanet_Data")
DATA_DIRNAME = GAME_REL[-1]
# 判定"这确实是 Fiz 的数据目录"的特征文件 (Unity 数据目录必备的若干文件之一)
DATA_MARKERS = ("globalgamemanagers", "resources.assets", "sharedassets0.assets",
                "app.info", "level0", "UnityPlayer.dll")

MSG_VERSION_MISMATCH = "目标游戏与补丁构建版本不一致，强行安装可能造成资源错配。"
MSG_ALREADY_PATCHED = ("游戏当前已是汉化态；继续安装会把已汉化文件当作备份，"
                       "该备份无法还原英文原版。")
MSG_RESIDUE_TEMPLATE = ("检测到补丁备份残留：存在 %d 个备份目录，但游戏当前是英文原版"
                        "（补丁已不在游戏中；可能刚完成卸载，或被 Steam 校验/更新还原）。"
                        "备份目录保留可随时还原，不再需要可手动删除。")
# 以下两条只是"非权威"推断后缀: 仅追加到警告文案, 不影响 residue / needs_confirm / 退出码 / 写入
SUFFIX_STEAM_REVERT = "（游戏文件时间戳已刷新，疑似 Steam 校验/更新还原）"
SUFFIX_JUST_UNINSTALLED = "（游戏文件时间戳与备份一致，可能是刚完成卸载）"
MSG_NEEDS_CONFIRM = "需要确认后才能继续；请确认后加 --yes 重试（本次未写入任何文件）。"
MSG_NO_BACKUP = "找不到备份目录，无法还原"

# 追加式专属文案
MSG_ADDITIVE_MIXED_STATE = (
    "游戏当前是替换式汉化态（中文被写进 en 槽位），不能直接叠加追加式补丁："
    "追加式载荷里的 catalog.json 按原版尺寸（en 串表 9585 B）生成，"
    "叠在替换式 catalog 上会让 en 段尺寸与实际文件不符，Addressables 会加载失败。"
    "请先卸载替换式补丁（python tools/patch_tool.py uninstall --yes）再装追加式。")
MSG_ADDITIVE_ALREADY = ("游戏当前已是追加式汉化态（es 槽位已被中文占用）。"
                        "继续安装会用当前（已汉化）文件覆盖备份，该备份无法还原原版。")
MSG_ADDITIVE_LOADER_CONFLICT = (
    "游戏根目录已存在 %s（本补丁要部署的 BepInEx loader）。"
    "它可能是其它 MOD 的加载器；继续安装会直接覆盖且**不留备份**，"
    "请先自行备份或移除该文件。")
MSG_ADDITIVE_TA_MIXED = (
    "游戏当前混用了替换式（en 槽位）与追加式（es 槽位或 loader）特征，"
    "catalog 与 bundle 可能已经错配；建议先用 Steam 校验游戏文件再装追加式。")

_CMD_NAMES = ("detect", "verify", "install", "uninstall", "check")

# --------------------------------------------------------------------------
# 模式（替换式 / 追加式）——模块级单例，只由 CLI 与测试写入；默认替换式，
# 因此所有历史调用路径（含 patch_launcher.py）的行为逐字节不变。
# --------------------------------------------------------------------------
_ADDITIVE_MODE = bool(ADDITIVE_PAYLOAD_DIR)
# 打包态只带追加式载荷时自动走追加式；带替换式载荷（X1）时仍为 False。


def set_additive(enabled):
    """切换 additive 模式；返回切换前的值（便于调用方恢复）。"""
    global _ADDITIVE_MODE
    previous = _ADDITIVE_MODE
    _ADDITIVE_MODE = bool(enabled)
    return previous


def is_additive():
    return _ADDITIVE_MODE


def payload_dir():
    """当前模式的载荷目录。"""
    return ADDITIVE_PAYLOAD_DIR if _ADDITIVE_MODE else PAYLOAD_DIR


def manifest_path():
    """当前模式的清单路径。"""
    return ADDITIVE_MANIFEST if _ADDITIVE_MODE else MANIFEST


def patch_info_path():
    """当前模式的门禁信息文件。

    additive 的 patch_info 内嵌在 manifest-additive.json 里（见
    tools/build_manifest.py::build_additive_manifest），因此这里返回清单本身；
    文件缺失时 load_patch_info() 返回 {}，与替换式缺 patch-info.json 同语义。
    """
    return ADDITIVE_MANIFEST if _ADDITIVE_MODE else PATCH_INFO


def _basename(rel):
    return str(rel).replace("\\", "/").rsplit("/", 1)[-1]


def additive_route(rel):
    """追加式载荷相对路径 → "game_root" / "data"。"""
    rel = str(rel).replace("\\", "/")
    head = rel.split("/", 1)[0]
    if head in ADDITIVE_GAME_ROOT_NAMES or rel.startswith(ADDITIVE_GAME_ROOT_PREFIXES):
        return "game_root"
    return "data"


def _target_path(data_dir, rel):
    """载荷相对路径 → 目标绝对路径（替换式模式下恒等于 _data_path）。"""
    rel_posix = str(rel).replace("\\", "/")
    if _ADDITIVE_MODE and additive_route(rel_posix) == "game_root":
        return os.path.join(game_root_of(data_dir), rel_posix.replace("/", os.sep))
    return _data_path(data_dir, rel_posix)


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def sha256(path):
    """文件 sha256 (小写十六进制)。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


_HASH_CACHE = {}


def _sha256_cached(path):
    """载荷文件哈希缓存 (同一进程内只算一次; 键含大小与 mtime 以便失效)。"""
    try:
        stat = os.stat(path)
        key = (os.path.abspath(path), stat.st_size, stat.st_mtime_ns)
    except OSError:
        return sha256(path)
    hit = _HASH_CACHE.get(key)
    if hit is None:
        hit = sha256(path)
        _HASH_CACHE[key] = hit
    return hit


def _walk_files(root):
    """递归列出目录内所有文件, 返回 [(相对路径(posix), 绝对路径)], 按相对路径排序。"""
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            out.append((rel, full))
    out.sort(key=lambda item: item[0])
    return out


def payload_rel_paths():
    """载荷相对路径 (posix 风格)。优先按 manifest.files 顺序; 清单不可用时回退实际遍历。"""
    try:
        manifest = load_manifest()
    except RuntimeError:
        manifest = None
    if isinstance(manifest, dict):
        paths = []
        for entry in manifest.get("files") or []:
            rel = entry.get("path") if isinstance(entry, dict) else None
            if rel:
                paths.append(str(rel).replace("\\", "/"))
        if paths:
            return paths
    return [rel for rel, _full in _walk_files(payload_dir())]


def payload_status(data_dir):
    """载荷在目标目录中的安装状态。"""
    detail = _payload_detail(data_dir)
    return {"total": detail["total"], "installed": detail["installed"],
            "missing": detail["missing"], "mismatch": detail["mismatch"]}


def _payload_path(rel):
    return os.path.join(payload_dir(), rel.replace("/", os.sep))


def _data_path(data_dir, rel):
    return os.path.join(data_dir, rel.replace("/", os.sep))


def _payload_detail(data_dir):
    rels = payload_rel_paths()
    rows = []
    installed = missing = mismatch = 0
    for rel in rels:
        src = _payload_path(rel)
        dst = _target_path(data_dir, rel)
        if not os.path.isfile(dst):
            status = "missing"
            missing += 1
        elif not os.path.isfile(src):
            status = "mismatch"
            mismatch += 1
        elif _sha256_cached(src) != _sha256_cached(dst):
            status = "mismatch"
            mismatch += 1
        else:
            status = "ok"
            installed += 1
        rows.append((rel, status))
    return {"total": len(rels), "installed": installed, "missing": missing,
            "mismatch": mismatch, "rows": rows}


def load_manifest():
    """读取当前模式的清单; 读不到或结构损坏 → 抛 RuntimeError (中文原因)。"""
    path = manifest_path()
    if not os.path.isfile(path):
        raise RuntimeError("找不到清单文件 %s：%s" % (os.path.basename(path), path))
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        raise RuntimeError("清单文件 %s 无法解析：%s（%s）"
                           % (os.path.basename(path), path, exc))
    if not isinstance(data, dict):
        raise RuntimeError("清单文件 %s 结构异常：顶层不是对象（%s）"
                           % (os.path.basename(path), path))
    if not isinstance(data.get("files"), list):
        raise RuntimeError("清单文件 %s 结构异常：缺少 files 列表（%s）"
                           % (os.path.basename(path), path))
    return data


def load_patch_info():
    """读取门禁信息; 缺失/损坏 → 返回 {} (版本门禁随之跳过)。

    替换式读 patch-info.json; 追加式读 manifest-additive.json 内嵌的 patch_info
    (由 tools/build_manifest.py 生成, reference_hashes 与替换式同源)。
    """
    if _ADDITIVE_MODE:
        try:
            with open(ADDITIVE_MANIFEST, encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        info = data.get("patch_info")
        if not isinstance(info, dict):
            return {}
        # 清单自身的计数是权威值; patch_info 里的 payload_files 仅作兜底。
        merged = dict(info)
        if "payload_files" not in merged and "payload_files" in data:
            merged["payload_files"] = data["payload_files"]
        return merged
    try:
        with open(PATCH_INFO, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


# --------------------------------------------------------------------------
# Steam / 游戏目录探测
# --------------------------------------------------------------------------
def _read_library_folders(steam_root):
    """读取 libraryfolders.vdf 中的 "path" 条目 (兼容 v1/v2 与 \\\\ 转义)。"""
    out = []
    for vdf in (os.path.join(steam_root, "steamapps", "libraryfolders.vdf"),
                os.path.join(steam_root, "libraryfolders.vdf")):
        if not os.path.isfile(vdf):
            continue
        try:
            with open(vdf, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text, re.IGNORECASE):
            raw = match.group(1).replace("\\\\", "\\").replace("/", os.sep)
            raw = os.path.normpath(raw) if raw else raw
            if raw and raw not in out:
                out.append(raw)
    return out


def _norm_key(path):
    """大小写无关的路径比较键 (Windows 下 e:/steam 与 E:\\Steam 是同一目录)。"""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def find_steam_roots():
    """注册表 + Program Files + libraryfolders.vdf 全库, 去重并保持发现顺序。"""
    roots = []
    seen = set()

    def _add(path):
        if not path:
            return
        try:
            norm = os.path.normpath(str(path).replace("/", os.sep))
            key = _norm_key(norm)
        except Exception:
            return
        if norm and key not in seen:
            seen.add(key)
            roots.append(norm)

    try:
        import winreg
    except Exception:
        winreg = None
    if winreg is not None:
        keys = ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"))
        for hive, sub in keys:
            try:
                key = winreg.OpenKey(hive, sub)
            except Exception:
                continue
            for value_name in ("SteamPath", "InstallPath"):
                try:
                    _add(winreg.QueryValueEx(key, value_name)[0])
                except Exception:
                    pass
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if base:
            _add(os.path.join(base, "Steam"))
    # libraryfolders.vdf: 一次扩展即可覆盖常见多库布局 (嵌套库再追一层)
    for _round in range(2):
        added = False
        for root in list(roots):
            for lib in _read_library_folders(root):
                key = None
                try:
                    key = _norm_key(lib)
                except Exception:
                    key = None
                if key is not None and key not in seen:
                    seen.add(key)
                    roots.append(lib)
                    added = True
        if not added:
            break
    return roots


def _candidate_data_dirs(steam_root):
    """由 Steam 根/库根推出 Fiz 数据目录候选。"""
    norm = os.path.normpath(steam_root)
    if os.path.basename(norm).lower() == "steamapps":
        rel = GAME_REL[1:]
    else:
        rel = GAME_REL
    return [os.path.join(norm, *rel)]


def find_game_dirs():
    """自动探测到的有效数据目录 (含 _Data 特征文件), 按可信度 (发现顺序) 排序。"""
    out = []
    seen = set()
    for root in find_steam_roots():
        for cand in _candidate_data_dirs(root):
            try:
                key = _norm_key(cand)
            except Exception:
                key = cand
            if key in seen:
                continue
            seen.add(key)
            if os.path.isdir(cand) and not validate_data_dir(cand):
                out.append(cand)
    return out


def validate_data_dir(path):
    """合法返回 None, 否则返回中文原因。"""
    if not path:
        return "未指定游戏数据目录"
    full = os.path.abspath(path)
    if not os.path.exists(full):
        return "目录不存在：%s" % full
    if not os.path.isdir(full):
        return "不是目录：%s" % full
    hit = [name for name in DATA_MARKERS
           if os.path.isfile(os.path.join(full, name))]
    if not hit:
        return ("不是有效的游戏数据目录：%s 内找不到 %s 等特征文件"
                % (full, "、".join(DATA_MARKERS[:3])))
    return None


def resolve_data_dir(explicit=None):
    """接受游戏根目录或 _Data 目录本身; 返回 (data_dir, error)。"""
    if explicit:
        raw = str(explicit).strip().strip('"').strip("'")
        full = os.path.abspath(os.path.expanduser(raw)) if raw else ""
        if not full:
            return None, "未指定游戏数据目录"
        inner = os.path.join(full, DATA_DIRNAME)
        data_dir = inner if os.path.isdir(inner) else full
        err = validate_data_dir(data_dir)
        if err:
            return None, err
        return data_dir, None
    dirs = find_game_dirs()
    if not dirs:
        return None, ("未自动找到游戏数据目录，请用 --game-dir 指定游戏根目录"
                      "或 %s 目录" % DATA_DIRNAME)
    return dirs[0], None


def game_root_of(data_dir):
    """_Data 的父目录 (备份目录写在这里)。"""
    return os.path.dirname(os.path.abspath(data_dir))


def find_backups(game_root):
    """`_FizRP_backup_*` + 兼容别名 `.fizrp-backup`, 按名称降序 (最新在前)。"""
    out = []
    if not game_root or not os.path.isdir(game_root):
        return out
    try:
        names = os.listdir(game_root)
    except OSError:
        return out
    for name in names:
        if not (name.startswith(BACKUP_PREFIX) or name in LEGACY_BACKUP_DIRNAMES):
            continue
        full = os.path.join(game_root, name)
        if os.path.isdir(full):
            out.append(full)
    out.sort(key=lambda item: os.path.basename(item), reverse=True)
    return out


def _is_residue(installed, total, backups):
    """有备份但游戏已是英文原版: 补丁已不在游戏中 (可能刚卸载, 也可能被 Steam 校验/更新还原)。"""
    return bool(backups) and total > 0 and installed == 0


_RESIDUE_SAMPLE_MAX = 5


def _residue_timestamp_hint(data_dir, backups):
    """非权威时间戳提示 (copy2 会保留 mtime)。

    抽样比较"最新备份"与游戏侧同一相对路径的 mtime, 全部一致偏向"刚卸载",
    全部不同偏向"Steam 校验/更新还原"; 抽样混杂或取不到时间戳时不给任何推断。
    本函数只影响警告文案, 绝不影响 residue / needs_confirm / 退出码 / 是否写入;
    任何异常一律吞掉并返回空串。
    """
    try:
        if not backups:
            return ""
        backup_dir = backups[0]
        same = differ = 0
        for rel in payload_rel_paths():
            game_file = _target_path(data_dir, rel)
            backup_file = os.path.join(backup_dir, rel.replace("/", os.sep))
            if not (os.path.isfile(game_file) and os.path.isfile(backup_file)):
                continue
            try:
                game_mtime = os.path.getmtime(game_file)
                backup_mtime = os.path.getmtime(backup_file)
            except OSError:
                continue
            if abs(game_mtime - backup_mtime) < 1e-6:
                same += 1
            else:
                differ += 1
            if same + differ >= _RESIDUE_SAMPLE_MAX:
                break
        if same + differ == 0:
            return ""
        if differ and not same:
            return SUFFIX_STEAM_REVERT
        if same and not differ:
            return SUFFIX_JUST_UNINSTALLED
        return ""
    except Exception:
        return ""


def _residue_warning(data_dir, backups):
    """残留警告: 中性文案 (两种成因都成立) + 非权威时间戳提示。"""
    return (MSG_RESIDUE_TEMPLATE % len(backups or [])
            + _residue_timestamp_hint(data_dir, backups))


# --------------------------------------------------------------------------
# 追加式（X2）：现场状态探针 / 存档播种
# --------------------------------------------------------------------------
def _try_catalog_sync():
    """尽力导入同目录的 catalog_sync（源码态可用；打包态需 spec 加 hiddenimports）。"""
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import catalog_sync
        return catalog_sync
    except Exception:
        return None


def bundle_path(data_dir, name):
    return os.path.join(data_dir, *BUNDLE_SUBDIR, name)


def probe_additive_state(data_dir):
    """只读探测游戏当前形态，返回 additive 安装的前置状态。

    返回 dict:
        en_bytes / es_bytes   en、es 串表 bundle 的实际字节数（不存在为 None）
        catalog               "pristine"/"replacement"/"additive"/"missing"/"unreadable"
        catalog_en_size       catalog 里 en 段声明的 m_BundleSize（None=未读到）
        catalog_es_size       catalog 里 es 段声明的 m_BundleSize
        dataindex_shifted     catalog 里 dataIndex 与段头偏移是否已错位（None=未读到）
        replacement / additive  两个布尔判据
        notes                 探针局限（例如 catalog_sync 不可用）
    """
    info = {"en_bytes": None, "es_bytes": None, "catalog": "missing",
            "catalog_en_size": None, "catalog_es_size": None,
            "dataindex_shifted": None, "replacement": False, "additive": False,
            "notes": []}
    en_path = bundle_path(data_dir, EN_STRING_TABLE_NAME)
    es_path = bundle_path(data_dir, ES_STRING_TABLE_NAME)
    if os.path.isfile(en_path):
        info["en_bytes"] = os.path.getsize(en_path)
    if os.path.isfile(es_path):
        info["es_bytes"] = os.path.getsize(es_path)

    catalog = _data_path(data_dir, CATALOG_REL)
    if not os.path.isfile(catalog):
        info["notes"].append("游戏内找不到 catalog.json（%s）" % catalog)
    else:
        module = _try_catalog_sync()
        if module is None:
            info["notes"].append(
                "catalog_sync 不可用（未随安装包分发），catalog 层面的判据已跳过，"
                "仅按 bundle 实际尺寸判断。")
        else:
            try:
                ctx = module.open_catalog(catalog)
                by_name = {}
                for seg in ctx["segs"]:
                    by_name[seg["bundle_name"].lower()] = seg
                en_seg = by_name.get(EN_STRING_TABLE_NAME.lower())
                es_seg = by_name.get(ES_STRING_TABLE_NAME.lower())
                if en_seg is not None:
                    info["catalog_en_size"] = en_seg["obj"]["m_BundleSize"]
                if es_seg is not None:
                    info["catalog_es_size"] = es_seg["obj"]["m_BundleSize"]
                info["dataindex_shifted"] = bool(
                    module.check_consistency(ctx["doc"], ctx["segs"]))
                info["catalog"] = "readable"
            except Exception as exc:
                info["catalog"] = "unreadable"
                info["notes"].append("catalog 探针失败（%s: %s）"
                                     % (type(exc).__name__, exc))

    # 判据 1：en 串表 bundle 实际尺寸（替换式把中文写进 en 槽位 → 25723）
    en_replaced = (info["en_bytes"] is not None
                   and info["en_bytes"] != EN_STRING_TABLE_PRISTINE_BYTES)
    # 判据 2：catalog 里 en 段声明的尺寸
    en_declared_replaced = (info["catalog_en_size"] is not None
                            and info["catalog_en_size"] != EN_STRING_TABLE_PRISTINE_BYTES)
    # 判据 3：catalog 的 dataIndex 错位（替换式改动了 en 段长度却未平移后续段）
    info["replacement"] = bool(en_replaced or en_declared_replaced
                               or info["dataindex_shifted"])
    # additive 判据：es 槽位已被中文占用（文件或 catalog 任一成立）
    info["additive"] = bool(
        (info["es_bytes"] is not None
         and info["es_bytes"] == ES_STRING_TABLE_ADDITIVE_BYTES)
        or (info["catalog_es_size"] is not None
            and info["catalog_es_size"] == ES_STRING_TABLE_ADDITIVE_BYTES))
    return info


def additive_state_warnings(state, cmd):
    """按探针结果给出 additive 安装/校验的警告文案列表。"""
    warnings = []
    if cmd == "verify":
        if state["replacement"]:
            warnings.append(MSG_ADDITIVE_MIXED_STATE)
        return warnings
    if state["replacement"] and state["additive"]:
        warnings.append(MSG_ADDITIVE_TA_MIXED)
    elif state["replacement"]:
        warnings.append(MSG_ADDITIVE_MIXED_STATE)
    return warnings


def additive_loader_conflicts(data_dir):
    """游戏根目录里"已存在且与载荷不同"的 loader 条目（安装会覆盖，且不留备份）。"""
    conflicts = []
    if not is_additive():
        return conflicts
    game_root = game_root_of(data_dir)
    for rel in payload_rel_paths():
        if additive_route(rel) != "game_root":
            continue
        dst = os.path.join(game_root, rel.replace("/", os.sep))
        src = _payload_path(rel)
        if not os.path.isfile(dst):
            continue
        if os.path.isfile(src) and _sha256_cached(src) == _sha256_cached(dst):
            continue
        conflicts.append(rel)
    return conflicts


# ---------------------------- ES3 存档格式 ----------------------------
def es3_render_json(entries):
    """按 Easy Save 3 的 JSON 风格渲染 ``{键: {"__type":..,"value":..}}``。

    ``entries`` 为 ``[(key, type_name, value_text)]``，顺序即输出顺序。
    风格取自实机 ``SaveFile.es3`` 的逐字节核验（work/decompiled + 实读存档）：
    CRLF 换行、TAB 缩进、``" : "`` 分隔、UTF-8 无 BOM、**无结尾换行**。
    与 ES3 自身写出的字节一致（自验脚本做了原文件往返逐字节比对）。
    """
    parts = []
    for key, type_name, value_text in entries:
        parts.append('\t%s : {\r\n\t\t"__type" : %s,\r\n\t\t"value" : %s\r\n\t}'
                     % (json.dumps(key, ensure_ascii=False),
                        json.dumps(type_name, ensure_ascii=False),
                        value_text))
    return "{\r\n" + ",\r\n".join(parts) + "\r\n}"


def es3_value_text(value):
    """把 Python 标量渲染成 ES3 的 value 字面量。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return json.dumps(value, ensure_ascii=False)


def save_root_dir():
    """LocalLow 根目录（测试可用 FIZRP_SAVE_ROOT 覆盖）。"""
    override = os.environ.get(SAVE_ROOT_ENV)
    if override:
        return override
    profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(profile, "AppData", "LocalLow")


def save_file_path():
    return os.path.join(save_root_dir(), *SAVE_VENDOR_DIR, SAVE_FILENAME)


def _seed_save_bytes():
    """最小合法存档：Language=4(Spanish，即中文所在的 es 槽位)。

    同时带上 ``Dummy``：游戏自身在存档缺失时也是先用 ``ES3.Save("Dummy", 0)``
    建文件（FizRpSave.SetupCache），选中语言后由 LanguageSetting 写入 Language 键；
    其余设置键（Vibration/MildMode/ButtonUI/...）读取时都带默认值
    （FizRpResidentFlagManager:398-424），缺失即等价于默认，因此不预写。
    """
    return es3_render_json([
        ("Dummy", SAVE_DUMMY_TYPE, es3_value_text(0)),
        ("Language", SAVE_LANGUAGE_TYPE, es3_value_text(LANGUAGE_SPANISH)),
    ]).encode("utf-8")


def _existing_save_note(path, emit):
    """已存在存档时的只读提示（绝不修改）。"""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(4096)
    except OSError as exc:
        emit("提示: 检测到已有存档 %s，未做任何修改（读取失败：%s）。" % (path, exc))
        return {"save_existing": True, "save_language_key": None}
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except Exception:
        emit("提示: 检测到已有存档 %s，未做任何修改（格式无法解析，保持原样）。" % path)
        return {"save_existing": True, "save_language_key": None}
    has_language = isinstance(doc, dict) and "Language" in doc
    if has_language:
        emit("提示: 检测到已有存档 %s，未做任何修改（语言设置保持原样）。" % path)
    else:
        emit("提示: 检测到已有存档 %s，未做任何修改；该存档没有 Language 键，"
             "首次启动仍会进入语言选择画面，请选第三项「中文」。" % path)
    return {"save_existing": True, "save_language_key": bool(has_language)}


def seed_save_if_absent(result, emit):
    """存档播种（X3）：只在存档**不存在**时写入；存在则一个字节都不动。"""
    path = save_file_path()
    if os.path.isfile(path):
        result.update(_existing_save_note(path, emit))
        result["save_seeded"] = False
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(_seed_save_bytes())
    except OSError as exc:
        emit("警告: 无法写入存档播种文件（%s：%s）。安装已完成；首次启动时请手动在"
             "语言选择画面选第三项「中文」。" % (path, exc))
        result["save_seeded"] = False
        result["save_error"] = "%s: %s" % (type(exc).__name__, exc)
        return False
    emit("已播种存档: %s（Language=4，即中文所在的 es 槽位）" % path)
    result["save_seeded"] = True
    result["save_path"] = path
    return True


# --------------------------------------------------------------------------
# 版本门禁
# --------------------------------------------------------------------------
def check_version_gate(data_dir):
    """逐条中文问题描述 (缺失/哈希不符); 无问题 → []。"""
    hashes = load_patch_info().get("reference_hashes") or {}
    issues = []
    if not isinstance(hashes, dict):
        return issues
    for name in hashes:
        want = str(hashes[name]).strip().lower()
        path = _data_path(data_dir, str(name))
        if not os.path.isfile(path):
            issues.append("%s 缺失" % name)
        elif sha256(path) != want:
            issues.append("%s 哈希不符" % name)
    return issues


# --------------------------------------------------------------------------
# 载荷自检 (check)
# --------------------------------------------------------------------------
def _payload_selfcheck():
    """兼容包装: 返回 (ok, lines)。需要具体问题列表时用 _payload_selfcheck_detail()。"""
    ok, lines, _problems = _payload_selfcheck_detail()
    return ok, lines


def _payload_selfcheck_detail():
    """返回 (ok, lines, problems)。

    lines 是完整的自检明细 (调用方必须逐行输出, 通过与否都要);
    problems 是逐条中文问题描述 (供 error 字段给出具体原因)。
    清单缺失只降级为警告, 载荷计数与 patch-info 仍强制核对。
    """
    lines = []
    problems = []
    active_payload = payload_dir()
    actual = _walk_files(active_payload)
    total = len(actual)
    lines.append("载荷目录: %s" % active_payload)
    if is_additive():
        lines.append("模式: 追加式（additive）")
    if not os.path.isdir(active_payload):
        lines.append("载荷目录不存在。")
        problems.append("载荷目录不存在：%s" % active_payload)
        lines.append("Payload: 异常 (%d)" % len(problems))
        return False, lines, problems
    lines.append("载荷文件数: %d" % total)
    actual_paths = set(rel for rel, _full in actual)
    if is_additive():
        routes = {"data": 0, "game_root": 0}
        for rel in sorted(actual_paths):
            routes[additive_route(rel)] += 1
        lines.append("投放路由: Data=%d, 游戏根=%d" % (routes["data"],
                                                     routes["game_root"]))

    try:
        manifest = load_manifest()
    except RuntimeError as exc:
        manifest = None
        lines.append("警告: %s" % exc)
        lines.append("警告: 已跳过 manifest 清单比对（仅核对载荷计数与 patch-info.json）。")
    if isinstance(manifest, dict):
        recorded = []
        for entry in manifest.get("files") or []:
            rel = entry.get("path") if isinstance(entry, dict) else None
            if rel:
                recorded.append(str(rel).replace("\\", "/"))
        lines.append("清单记录文件数: %d" % len(recorded))
        if len(recorded) != total:
            problems.append("manifest 记录 %d 个文件，实际载荷 %d 个"
                            % (len(recorded), total))
        absent = [rel for rel in recorded if rel not in actual_paths]
        if absent:
            problems.append("manifest 记录的文件在载荷中缺失 %d 个" % len(absent))
            for rel in absent[:20]:
                lines.append("   载荷缺失: %s" % rel)
        extra = sorted(actual_paths - set(recorded))
        if extra:
            problems.append("载荷中有 %d 个文件未记入 manifest" % len(extra))
            for rel in extra[:20]:
                lines.append("   载荷多出（manifest 未记录）: %s" % rel)
        bad = []
        for entry in manifest.get("files") or []:
            if not isinstance(entry, dict):
                continue
            rel = str(entry.get("path") or "").replace("\\", "/")
            want = str(entry.get("sha256") or "").strip().lower()
            if not rel or not want:
                continue
            src = _payload_path(rel)
            if os.path.isfile(src) and _sha256_cached(src) != want:
                bad.append(rel)
        if bad:
            problems.append("manifest 与载荷哈希不符 %d 个" % len(bad))
            for rel in bad[:20]:
                lines.append("   哈希不符: %s" % rel)
        else:
            lines.append("manifest 哈希: OK (%d)" % len(recorded))

    info = load_patch_info()
    # 文案与替换式保持逐字一致；additive 才知道自己其实读的是 manifest-additive.json
    label = "门禁信息（manifest-additive.json）" if is_additive() else "patch-info.json"
    if not info:
        problems.append("%s 缺失或无法解析：%s"
                        % ("门禁信息" if is_additive() else "patch-info.json",
                           patch_info_path()))
        lines.append("%s: 缺失或无法解析" % label)
    else:
        recorded_count = info.get("payload_files")
        lines.append("%s: payload_files=%s" % (label, recorded_count))
        if recorded_count != total:
            problems.append("%s 记录的 payload_files=%s 与实际载荷 %d 不一致"
                            % (label, recorded_count, total))

    if problems:
        for problem in problems:
            lines.append("问题: %s" % problem)
        lines.append("Payload: 异常 (%d)" % len(problems))
        return False, lines, problems
    lines.append("Payload: OK (%d)" % total)
    return True, lines, []


def _check_error_text(problems):
    """check 失败时的 error 文案: 带上第一条具体原因 (多条时附条数)。"""
    if not problems:
        return "载荷自检未通过"
    first = str(problems[0])
    if len(problems) > 1:
        return "载荷自检未通过: %s（另有 %d 个问题）" % (first, len(problems) - 1)
    return "载荷自检未通过: %s" % first


# --------------------------------------------------------------------------
# precheck
# --------------------------------------------------------------------------
def _empty_state():
    return {"total": 0, "installed": 0, "backups": [], "residue": False,
            "patched": False}


def _new_result(cmd):
    return {"cmd": cmd, "ok": True, "error": None, "data_dir": None,
            "needs_confirm": False, "warnings": [], "state": _empty_state()}


def _fill_state(result, data_dir, detail=None):
    detail = detail if detail is not None else _payload_detail(data_dir)
    backups = find_backups(game_root_of(data_dir))
    state = {
        "total": detail["total"],
        "installed": detail["installed"],
        "backups": backups,
        "residue": _is_residue(detail["installed"], detail["total"], backups),
        "patched": detail["total"] > 0 and detail["installed"] == detail["total"],
    }
    result["state"] = state
    return state


def _resolve_into(result, data_dir):
    """解析目录并填充 data_dir; 失败返回 False。"""
    resolved, error = resolve_data_dir(data_dir)
    if error:
        result["ok"] = False
        result["error"] = error
        return False
    result["data_dir"] = resolved
    return True


def precheck(cmd, data_dir=None, additive=False):
    """安装/卸载前的检查。返回结构见契约 §2.1 (字段名冻结)。

    ``additive=True`` 走追加式（X2）载荷；默认 False 即替换式，历史行为不变。
    """
    set_additive(additive)
    cmd = str(cmd or "").lower()
    result = _new_result(cmd)
    result["mode"] = "additive" if additive else "replace"
    if cmd not in _CMD_NAMES:
        result["ok"] = False
        result["error"] = "未知命令：%s" % (cmd or "(空)")
        return result

    if cmd == "detect":
        dirs = find_game_dirs()
        if not dirs:
            result["ok"] = False
            result["error"] = ("未自动找到游戏数据目录，请用 --game-dir 指定游戏根目录"
                               "或 %s 目录" % DATA_DIRNAME)
            return result
        result["data_dir"] = dirs[0]
        _fill_state(result, dirs[0])
        return result

    if cmd == "check":
        ok, _lines, problems = _payload_selfcheck_detail()
        result["ok"] = ok
        if not ok:
            result["error"] = _check_error_text(problems)
        result["state"] = {"total": len(_walk_files(payload_dir())), "installed": 0,
                           "backups": [], "residue": False, "patched": False}
        result["warnings"] = [] if ok else ["载荷自检未通过，请重新获取补丁包。"]
        return result

    if not _resolve_into(result, data_dir):
        return result
    resolved = result["data_dir"]

    if not os.path.isdir(payload_dir()):
        result["ok"] = False
        result["error"] = "找不到载荷目录：%s" % payload_dir()
        return result

    detail = _payload_detail(resolved)
    if detail["total"] == 0:
        result["ok"] = False
        result["error"] = "载荷为空：%s" % payload_dir()
        return result
    state = _fill_state(result, resolved, detail)

    if cmd == "verify":
        if not state["patched"]:
            result["ok"] = False
            result["error"] = ("校验未通过：仅 %d/%d 个文件与载荷一致"
                               % (state["installed"], state["total"]))
        if state["residue"]:
            result["warnings"].append(_residue_warning(resolved, state["backups"]))
        if additive:
            probe = probe_additive_state(resolved)
            result["additive_state"] = probe
            result["warnings"].extend(additive_state_warnings(probe, "verify"))
            result["warnings"].extend(probe["notes"])
        return result

    if cmd == "install":
        if not load_patch_info():
            result["warnings"].append(
                "找不到或无法解析 %s（%s），已跳过版本门禁校验。"
                % ("manifest-additive.json" if additive else "patch-info.json",
                   patch_info_path()))
        issues = check_version_gate(resolved)
        if issues:
            result["warnings"].append(MSG_VERSION_MISMATCH)
            result["warnings"].extend(issues)
        if additive:
            probe = probe_additive_state(resolved)
            result["additive_state"] = probe
            result["warnings"].extend(additive_state_warnings(probe, "install"))
            result["warnings"].extend(probe["notes"])
            if probe["additive"]:
                result["warnings"].append(MSG_ADDITIVE_ALREADY)
            conflicts = additive_loader_conflicts(resolved)
            if conflicts:
                result["loader_conflicts"] = conflicts
                result["warnings"].append(
                    MSG_ADDITIVE_LOADER_CONFLICT
                    % ("、".join(conflicts[:5])
                       + ("（共 %d 个）" % len(conflicts) if len(conflicts) > 5 else "")))
        elif state["patched"]:
            result["warnings"].append(MSG_ALREADY_PATCHED)
        if state["residue"]:
            result["warnings"].append(_residue_warning(resolved, state["backups"]))
        result["needs_confirm"] = bool(result["warnings"])
        return result

    if cmd == "uninstall":
        if not state["backups"]:
            result["ok"] = False
            result["error"] = MSG_NO_BACKUP
        return result

    return result


# --------------------------------------------------------------------------
# execute
# --------------------------------------------------------------------------
def execute(cmd, data_dir=None, *, log=None, assume_yes=False, additive=False,
            seed_save=True):
    """执行命令。返回契约 §2.2 结构 (含 exit / log / 计数)。

    ``additive=True`` 走追加式（X2）：载荷平铺，loader 条目落游戏根、数据文件落
    Data 目录，安装后按策略播种存档；默认 False 即替换式，历史行为不变。
    ``seed_save=False`` 关闭 additive 安装的存档播种。
    """
    set_additive(additive)
    cmd = str(cmd or "").lower()
    lines = []

    def emit(text):
        line = "" if text is None else str(text)
        lines.append(line)
        if log is not None:
            try:
                log(line)
            except Exception:
                pass

    result = precheck(cmd, data_dir, additive=additive)
    exit_code = 0 if (result.get("ok") and not result.get("error")) else 1
    for warning in result.get("warnings") or []:
        emit("警告: %s" % warning)

    if not data_dir and cmd in ("verify", "install", "uninstall"):
        # 自动探测到多个安装时, 提示本次使用的是第一个 (契约 §2.4; check 与游戏目录无关, 不提示)
        candidates = find_game_dirs()
        if len(candidates) > 1:
            emit("提示: 找到多个安装，使用第一个: %s" % candidates[0])

    if cmd == "check":
        # check 与游戏目录无关: 通过与否都要逐行输出自检明细, 末尾再补一行汇总原因
        _ok, check_lines, _problems = _payload_selfcheck_detail()
        for line in check_lines:
            emit(line)
        if result.get("error"):
            emit(result["error"])

    elif result.get("error"):
        emit(result["error"])

    elif cmd == "detect":
        dirs = find_game_dirs()
        emit("检测到游戏数据目录（共 %d 个）:" % len(dirs))
        for index, path in enumerate(dirs, 1):
            emit("  [%d] %s" % (index, path))
        if len(dirs) > 1:
            emit("提示: 找到多个安装，使用第一个: %s" % dirs[0])
        result["dirs"] = dirs

    elif cmd == "verify":
        detail = _payload_detail(result["data_dir"])
        label = {"ok": "一致", "missing": "缺失", "mismatch": "不一致"}
        for index, (rel, status) in enumerate(detail["rows"], 1):
            emit("[%d/%d] %s: %s" % (index, detail["total"], label[status], rel))
        emit("校验完成: %d/%d" % (detail["installed"], detail["total"]))
        result["verified"] = detail["installed"]
        result["skipped"] = detail["missing"] + detail["mismatch"]

    elif cmd == "install":
        if result.get("needs_confirm") and not assume_yes:
            emit(MSG_NEEDS_CONFIRM)
            exit_code = 1
        else:
            exit_code = _do_install(result, emit, seed_save=seed_save)

    elif cmd == "uninstall":
        exit_code = _do_uninstall(result, emit)

    result["exit"] = int(exit_code)
    result["log"] = lines
    return result


def _original_dir(game_root):
    """不可变原版副本目录（首次安装时留档）。"""
    return os.path.join(game_root, ORIGINAL_PREFIX)


def _snapshot_original(game_root, rel, src):
    """把首次见到的原版文件留档到 _FizRP_original/（已存在则不动）。"""
    orig_file = os.path.join(_original_dir(game_root), rel.replace("/", os.sep))
    if os.path.isfile(orig_file):
        return
    parent = os.path.dirname(orig_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    shutil.copy2(src, orig_file)


def _new_backup_dir(game_root):
    """本次安装的备份目录。

    目录名是 ``_FizRP_backup_<yyyyMMdd-HHmmss>``（历史约定）；同一秒内再次安装时
    追加 ``-2``/``-3``… 后缀，避免两次安装复用同一个目录、把上一次（更接近原版的）
    备份内容覆盖掉。仅在"目录已存在"这一条路径上有别于历史行为。
    """
    base = BACKUP_PREFIX + time.strftime("%Y%m%d-%H%M%S")
    candidate = os.path.join(game_root, base)
    index = 1
    while os.path.exists(candidate):
        index += 1
        candidate = os.path.join(game_root, "%s-%d" % (base, index))
    return candidate


def _do_install(result, emit, seed_save=True):
    data_dir = result["data_dir"]
    additive = is_additive()
    rels = payload_rel_paths()
    total = len(rels)
    backup_dir = _new_backup_dir(game_root_of(data_dir))
    written = backed = skipped = 0
    backed_rels = []
    # 安装前逐文件记录"游戏里本来就有"与关键文件的安装前哈希（V6 备份缺口核对的依据）
    pre_existing = {}
    for rel in rels:
        dst = _target_path(data_dir, rel)
        if os.path.isfile(dst):
            pre_existing[rel] = dst
    v6_pre_hashes = {}
    for rel in V6_TRACKED_RELS:
        dst = pre_existing.get(rel)
        if dst:
            try:
                v6_pre_hashes[rel] = sha256(dst)
            except OSError:
                pass

    loader_written = 0
    for index, rel in enumerate(rels, 1):
        src = _payload_path(rel)
        dst = _target_path(data_dir, rel)
        if not os.path.isfile(src):
            emit("警告: 载荷缺少 %s，已跳过。" % rel)
            skipped += 1
            continue
        is_loader = additive and additive_route(rel) == "game_root"
        if os.path.isfile(dst) and not is_loader:
            backup_file = os.path.join(backup_dir, rel.replace("/", os.sep))
            parent = os.path.dirname(backup_file)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.copy2(dst, backup_file)
            _snapshot_original(game_root_of(data_dir), rel, dst)
            backed += 1
            backed_rels.append(rel)
        elif is_loader and os.path.isfile(dst):
            # loader 条目按设计不进备份（卸载器按载荷清单删除它们）；已存在则显式告警
            emit("警告: 覆盖已存在的 loader 文件 %s（按设计不留备份；"
                 "原文件如需保留请先自行备份）" % rel)
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.copy2(src, dst)
        written += 1
        if is_loader:
            loader_written += 1
        emit("[%d/%d] 写入 %s" % (index, total, rel))
    emit("已写入 %d 个文件。" % written)

    # ---- 还原「上一版改过、这一版不再管理」的文件 ----------------------------
    # 踩过的坑：某次安装把 sharedassets2.assets 的字体 blob 换成了中文字体；后来
    # 方案变更、这一版不再修改该文件，于是载荷里没有它 —— 而安装器只做「按载荷
    # 覆盖」，不会把它还原，游戏里就一直留着上一版改过的字体（构建侧、载荷清单、
    # 安装日志三方都看不出问题）。
    # 规则：_FizRP_original/ 里留档过的每个文件，只要当前与原版不同、且不在本次
    # 载荷清单内，就用原版覆盖回去。
    restored = []
    orig_root = _original_dir(game_root_of(data_dir))
    payload_rels = set(rels)
    if os.path.isdir(orig_root):
        for dirpath, _dirnames, filenames in os.walk(orig_root):
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, orig_root).replace(os.sep, "/")
                if rel in payload_rels:
                    continue                      # 载荷管理的文件，按载荷覆盖
                dst = _target_path(data_dir, rel)
                if not os.path.isfile(dst):
                    continue
                try:
                    same = (os.path.getsize(full) == os.path.getsize(dst)
                            and open(full, "rb").read() == open(dst, "rb").read())
                except OSError:
                    continue
                if same:
                    continue
                backup_file = os.path.join(backup_dir, rel.replace("/", os.sep))
                parent = os.path.dirname(backup_file)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                shutil.copy2(dst, backup_file)
                shutil.copy2(full, dst)
                restored.append(rel)
        if restored:
            emit("已还原 %d 个上一版改过、本版不再需要的文件: %s"
                 % (len(restored), ", ".join(sorted(restored)[:5])
                    + (" …" if len(restored) > 5 else "")))
    if additive:
        emit("其中 loader/插件条目 %d 个落在游戏根目录。" % loader_written)
    emit("原文件备份在: %s" % backup_dir)
    emit("下一次启动游戏时，语言选择画面请选第二项（中文）。" if not additive else
         "下一次启动游戏时，语言选择画面请选第三项（中文）。")
    result["written"] = written
    result["backed"] = backed
    result["skipped"] = skipped
    result["backup_dir"] = backup_dir

    if additive:
        result["loader_written"] = loader_written
        _verify_v6_backup(result, emit, rels, pre_existing, v6_pre_hashes)
        if seed_save:
            seed_save_if_absent(result, emit)
        else:
            emit("提示: 已按 --no-seed-save 跳过存档播种。")
            result["save_seeded"] = False
    return 0


def _verify_v6_backup(result, emit, rels, pre_existing, pre_hashes):
    """V6 核对：安装前存在的 Data 侧文件必须真的落进备份目录。

    替换式/追加式都只备份"安装前存在"的文件，因此这里逐条回读备份件哈希，
    与安装前记录的哈希比对；不一致（或备份缺失）即为 V6 缺口，必须显式告警。
    """
    backup_dir = result["backup_dir"]
    checked = []
    problems = []
    for rel in V6_TRACKED_RELS:
        if rel not in rels:
            continue
        dst = pre_existing.get(rel)
        backup_file = os.path.join(backup_dir, rel.replace("/", os.sep))
        if dst is None:
            emit("警告: 安装前游戏内不存在 %s（异常状态）；卸载时无法还原原版该文件，"
                 "必要时请用 Steam「校验游戏文件完整性」修复。" % rel)
            checked.append({"path": rel, "pre_existing": False, "backed_up": False})
            continue
        if not os.path.isfile(backup_file):
            problems.append(rel)
            emit("警告: %s 未进入备份目录（V6 缺口）：%s" % (rel, backup_file))
            checked.append({"path": rel, "pre_existing": True, "backed_up": False})
            continue
        want = pre_hashes.get(rel)
        got = sha256(backup_file)
        ok = (want is None) or (want == got)
        if not ok:
            problems.append(rel)
            emit("警告: %s 的备份内容与安装前不一致（V6 缺口）" % rel)
        else:
            emit("备份核对: %s 已备份（sha256 %s）" % (rel, got[:16] + "…"))
        checked.append({"path": rel, "pre_existing": True, "backed_up": True,
                        "sha256": got, "matches_pre_install": ok})
    result["v6_backup_check"] = checked
    result["v6_ok"] = not problems


def _do_uninstall(result, emit):
    data_dir = result["data_dir"]
    additive = is_additive()
    backups = result["state"]["backups"]
    if not backups:
        emit(MSG_NO_BACKUP)
        return 1
    orig_dir = _original_dir(game_root_of(data_dir))
    orig_rels = list(_walk_files(orig_dir)) if os.path.isdir(orig_dir) else []
    if orig_rels:
        backup_dir = orig_dir
        emit("从不可变原版副本 %s 还原（%d 个文件；优先于滚动备份）..."
             % (orig_dir, len(orig_rels)))
    else:
        backup_dir = backups[0]
        emit("警告: 未找到不可变原版副本 %s，改用滚动备份（它可能已是补丁版本）。"
             % orig_dir)
        emit("从 %s 还原..." % backup_dir)
    restored = 0
    backup_rels = set()
    for rel, full in _walk_files(backup_dir):
        backup_rels.add(rel)
        dst = _data_path(data_dir, rel)
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.copy2(full, dst)
        restored += 1
        emit("[%d] 还原 %s" % (restored, rel))
    emit("已还原 %d 个文件。" % restored)
    result["restored"] = restored
    result["restored_from"] = backup_dir
    result["skipped"] = 0
    if additive:
        _remove_additive_payload(result, emit, data_dir, backup_rels)
    emit("备份目录仍在: %s（未删除；如需清理请手动删除）" % backup_dir)
    return 0


def _remove_additive_payload(result, emit, data_dir, backup_rels):
    """追加式卸载的收尾：删掉"本安装器写入、原版没有"的 Data 文件与整棵 loader 树。

    * loader 条目（游戏根）: 载荷清单列出的那些文件直接删除，再自底向上清空目录；
      用户自己的其它 BepInEx 内容（config/、别的插件、日志）一律保留。
    * Data 侧文件: 只在"备份目录里没有它"且"当前内容与载荷逐字节一致"（可证明是本
      安装器写入的）时才删除；否则保留并警告 —— 绝不误删可能是原版/他人写入的文件。
    * 存档（LocalLow 下的 SaveFile*.es3）绝不触碰。
    """
    game_root = game_root_of(data_dir)
    rels = payload_rel_paths()
    removed_loader = []
    kept_loader = []
    removed_data = []
    kept_data = []
    emptied_dirs = []

    for rel in rels:
        dst = _target_path(data_dir, rel)
        src = _payload_path(rel)
        if not os.path.isfile(dst):
            continue
        if additive_route(rel) == "game_root":
            try:
                os.remove(dst)
            except OSError as exc:
                kept_loader.append((rel, str(exc)))
                emit("警告: 无法删除 loader 文件 %s（%s），请手动删除。" % (dst, exc))
            else:
                removed_loader.append(rel)
                emit("已移除 loader 文件: %s" % rel)
            continue
        # Data 侧：原版文件已在上面从备份还原；这里只处理"备份里没有"的飞地
        if rel in backup_rels:
            continue
        same = os.path.isfile(src) and _sha256_cached(src) == _sha256_cached(dst)
        if same:
            try:
                os.remove(dst)
            except OSError as exc:
                kept_data.append((rel, str(exc)))
                emit("警告: 无法删除补丁新增文件 %s（%s），请手动删除。" % (dst, exc))
            else:
                removed_data.append(rel)
                emit("已移除补丁新增文件（原版没有该文件）: %s" % rel)
        else:
            kept_data.append((rel, "内容与载荷不一致"))
            emit("警告: %s 不在备份中且内容与载荷不一致，已保留（请自行确认）。" % dst)

    # 清空因删除 loader 而变空的目录（只删空目录，自底向上）
    bepinex_root = os.path.join(game_root, "BepInEx")
    if os.path.isdir(bepinex_root):
        # topdown=False：先子后父；根目录也参与（清空后一并移除，不留空壳）
        for dirpath, _dirnames, _filenames in os.walk(bepinex_root, topdown=False):
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
                    emptied_dirs.append(os.path.relpath(dirpath, game_root)
                                        .replace(os.sep, "/"))
                    emit("已移除空目录: %s" % emptied_dirs[-1])
            except OSError:
                pass

    result["removed_loader"] = removed_loader
    result["kept_loader"] = kept_loader
    result["removed_added_data"] = removed_data
    result["kept_data"] = kept_data
    result["emptied_dirs"] = emptied_dirs
    result["save_untouched"] = True
    emit("存档未做任何改动（补丁不删除、不还原用户存档）。")


def run_command(cmd, data_dir=None, *, log=None, assume_yes=False, additive=False,
                seed_save=True):
    """执行命令并只返回退出码 (0/1)。"""
    return int(execute(cmd, data_dir, log=log, assume_yes=assume_yes,
                       additive=additive, seed_save=seed_save)["exit"])


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
class _NullWriter(object):
    """windowed exe 下 sys.stdout/stderr 为 None 时的丢弃写入器。"""

    encoding = "utf-8"
    errors = "replace"

    def write(self, text):
        return len(text) if text else 0

    def flush(self):
        return None

    def isatty(self):
        return False


def _ensure_stdio():
    """窗口化安全: stdout/stderr 不可用时替换为丢弃写入器, 绝不裸 print 崩溃。"""
    if sys.stdout is None:
        sys.stdout = _NullWriter()
    if sys.stderr is None:
        sys.stderr = _NullWriter()
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if not stream.isatty():
                # 重定向到文件/管道时固定用 UTF-8, 免去控制台代码页带来的乱码
                reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _stdin_is_tty():
    """标准输入是否为可交互终端。

    Windows 上额外要求句柄真的是控制台: 某些环境 (Git Bash 的 /dev/null、被接管的
    stdin) 会让 isatty() 误报为 True, 那时交互读取会立刻 EOF 或永久阻塞, 因此宁可
    判为"非终端", 走"请确认后加 --yes 重试"的安全分支。
    """
    stream = sys.stdin
    if stream is None:
        return False
    try:
        if not stream.isatty():
            return False
    except Exception:
        return False
    if os.name == "nt":
        try:
            import ctypes
            import msvcrt
            handle = msvcrt.get_osfhandle(stream.fileno())
            mode = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetConsoleMode(
                    ctypes.c_void_p(handle), ctypes.byref(mode)):
                return False
        except Exception:
            return False
    return True


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="patch_tool.py",
        description="Fiz 与彩虹星球 简体中文补丁 —— 无头核心与命令行",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    for name in _CMD_NAMES:
        sub = subparsers.add_parser(name, help="%s 子命令" % name)
        if name != "check":
            sub.add_argument("--game-dir", default=None,
                             help="游戏根目录或 %s 目录；省略则自动探测" % DATA_DIRNAME)
        if name in ("install", "uninstall"):
            sub.add_argument("--yes", action="store_true",
                             help="跳过确认，直接执行")
        sub.add_argument("--additive", action="store_true",
                         help="使用追加式（X2）载荷：dist-additive/payload + "
                              "manifest-additive.json；loader 条目落游戏根目录")
        if name == "install":
            sub.add_argument("--no-seed-save", action="store_true",
                             help="追加式安装时不播种存档（默认仅在存档不存在时写入）")
        sub.add_argument("--json", action="store_true",
                         help="最后一行输出 JSON 结果")
    return parser


def _emit_json(result):
    try:
        print(json.dumps(result, ensure_ascii=False))
    except Exception:
        pass


def _finish_precheck(pre, exit_code, lines, as_json):
    result = dict(pre)
    result["exit"] = int(exit_code)
    result["log"] = list(lines)
    if as_json:
        _emit_json(result)
    return int(exit_code)


def main(argv=None):
    _ensure_stdio()
    parser = _build_parser()
    args = parser.parse_args(argv)
    cmd = str(args.cmd or "").lower()
    game_dir = getattr(args, "game_dir", None)
    as_json = bool(getattr(args, "json", False))
    assume_yes = bool(getattr(args, "yes", False))
    additive = bool(getattr(args, "additive", False))
    seed_save = not bool(getattr(args, "no_seed_save", False))
    set_additive(additive)

    if cmd in ("install", "uninstall") and not assume_yes:
        pre = precheck(cmd, game_dir, additive=additive)
        if pre.get("needs_confirm") and _stdin_is_tty():
            lines = ["警告: %s" % warning for warning in (pre.get("warnings") or [])]
            for line in lines:
                print(line)
            try:
                answer = input("仍要继续吗？(y/N) ")
            except (EOFError, KeyboardInterrupt):
                answer = None
            if answer is None:
                # 终端读不到输入: 交给下面的非交互分支给出「请加 --yes」提示
                pass
            elif str(answer).strip().lower() in ("y", "yes"):
                assume_yes = True
            else:
                lines.append("已取消，未写入任何文件。")
                print(lines[-1])
                return _finish_precheck(pre, 1, lines, as_json)

    result = execute(cmd, game_dir, log=print, assume_yes=assume_yes,
                     additive=additive, seed_save=seed_save)
    if as_json:
        _emit_json(result)
    return int(result["exit"])


if __name__ == "__main__":
    sys.exit(main())
