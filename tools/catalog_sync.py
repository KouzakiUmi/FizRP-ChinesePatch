# -*- coding: utf-8 -*-
"""Addressables catalog.json 同步器：把指定 bundle 的 m_BundleSize / m_Crc 回写进 catalog。

为「追加式中文（X2）」项目服务：我们会替换某个语言串表 bundle 的内容（例如
``localization-string-tables-spanish(es)_assets_all.bundle``），替换后必须同步
catalog 里记录的该 bundle 的 **m_BundleSize**（实际字节数）与 **m_Crc**，
否则 Addressables 加载时会因 CRC Mismatch 失败。

------------------------------------------------------------------------
catalog.json 的真实字节格式（现场核验结论，非推测）
------------------------------------------------------------------------
catalog.json 是 UTF-8、无 BOM、无结尾换行的紧凑 JSON（``separators=(",", ":")``）。
顶层 ``m_ExtraDataString`` 是 base64 的 .NET BinaryWriter 流，解开后每段布局为::

    [153 字节常量类型头][int32 LE = 该段 JSON 的 UTF-16 字节长度][UTF-16LE JSON]

* 153 字节类型头在 11/11 段上完全一致（程序集名 + 类型名，各带 .NET 7-bit 长度前缀）：
  ``\\x07L`` + ``Unity.ResourceManager, Version=0.0.0.0, Culture=neutral,
  PublicKeyToken=null`` + ``J`` +
  ``UnityEngine.ResourceManagement.ResourceProviders.AssetBundleRequestOptions``
* 段起点用 ``MARK = '{"m_Hash":'.encode("utf-16-le")`` 定位（沿用
  ``work/review/_F_catalog_check.py`` 的做法）。
* 每段 JSON 是 ``AssetBundleRequestOptions``，12 个键，关键是 ``m_Crc``（uint32，可 > 2^31）、
  ``m_BundleSize``、``m_BundleName``、``m_UseCrcForCachedBundles``。
* ``json.dumps(obj, separators=(",", ":"), ensure_ascii=False)`` 与游戏原样序列化**逐字相同**
  （3 份样本 × 11 段全部验证通过）；本脚本每次运行都会自检这一点，不一致即中止并报证据。

``m_EntryDataString`` 里每条 entry 是 7×int32：
``(internalIdIdx, providerIdx, dependencyKeyIdx, dependencyHash, dataIndex, primaryKeyIdx, resourceTypeIdx)``。
其中 ``dataIndex >= 0`` 的那条，指向该 bundle 对应 extra-data 段的**类型头绝对偏移**
（= ``json_at - 157``），不是段号、也不是 JSON 起点。因此：

    **某一段的长度变化时，它之后所有段的 dataIndex 必须同步平移。**
    只改帧头不改 dataIndex 会让 Addressables 从错误位置反序列化（fr/ja/es 三个串表
    bundle 曾在已发布的补丁里因此偏了 4 字节）。本脚本会一并重算并回写全部 dataIndex。

bundle → 段的映射完全取自 catalog 自身：``m_InternalIds[internalIdIdx]`` 取末段文件名
与 ``--bundle`` 比对，再按 dataIndex 升序与段偏移升序一一对应；**不使用 m_Hash 反推**
（m_Hash 的生成规则未核实，不做猜测）。

------------------------------------------------------------------------
用法
------------------------------------------------------------------------
::

    python tools/catalog_sync.py <catalog.json> --bundle-dir <dir> --bundle <文件名> [--crc <值>] [--write]
    python tools/catalog_sync.py <catalog.json> --verify          # 只核验，不改

参数：

* ``<catalog.json>``  要同步的 catalog 文件（会被就地修改，仅 --write 时）。
* ``--bundle-dir``     bundle 文件所在目录。直接给 ``.../StandaloneWindows64``，
                       或给其父目录（自动再探一层 ``StandaloneWindows64/``）。
* ``--bundle``         bundle 文件名，可**重复传参**多选；给完整 internalId 路径亦可
                       （按 ``\\`` 或 ``/`` 切末段后比对，不区分大小写）。
* ``--crc``            十进制或 ``0x`` 十六进制。**缺省时保持原值不动**；
                       显式传 ``--crc 0`` 表示「占位清零」（等实机 Player.log 回填）。
                       传了 ``--crc`` 时，该值应用于本次列出的**所有** bundle。
* ``--write``          真正落盘。**默认是 dry-run**，只打印旧值/新值。
                       落盘前自动把原文件备份为 ``<同名>.bak``。
* ``--verify``         只做一致性核验并打印，不修改任何字段（帧头 vs 实际长度、
                       dataIndex vs 段头偏移、bundle 名映射），退出码 0/1。

关于 CRC：**算法未破解，本脚本不做任何 CRC 计算**。回填值一律来自 ``--crc``。
占位流程是：先 ``--crc 0`` 让尺寸先进 catalog，实机首次运行后从
``%USERPROFILE%\\AppData\\LocalLow\\NijiiroDragon\\FizAndTheRainbowPlanet\\Player.log``
的 ``calculated`` 行取真实值，再 ``--crc <真实值> --write`` 覆盖一次。

------------------------------------------------------------------------
安全性与停止条件
------------------------------------------------------------------------
* 写回用**外科式替换**：只替换 ``"m_EntryDataString":"<base64>"`` 与
  ``"m_ExtraDataString":"<base64>"`` 两个字面量（各自必须**恰好出现一次**，
  否则中止），其余字节原样保留 —— 所以键序、空白、其它 blob 不可能被改动。
* 任何一处格式与预期不符（帧头自相矛盾、段数与 dataIndex 条数不等、
  base64 字面量不唯一、重序列化不能逐字还原原段）一律**中止并打印实际字节证据**，
  不猜测写回。
* 只读 ``--bundle-dir`` 里的 bundle 文件；不写 catalog 所在目录以外的任何文件。

退出码：0 = 成功（或 dry-run 无异常）；1 = 一致性核验失败 / 运行期错误；2 = 用法错误。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import struct
import sys

# 每段前置的常量类型头字节数（程序集名 + 类型名）；dataIndex 指向它的起点。
SEG_TYPE_HEADER_LEN = 153
# 段 = 类型头 + int32 长度帧头，JSON 起点相对段头偏移 157。
SEG_OVERHEAD = SEG_TYPE_HEADER_LEN + 4
# 段 JSON 的 UTF-16LE 起点标记，沿用既有核验脚本的定位方式。
SEG_MARK = '{"m_Hash":'.encode("utf-16-le")
# entry 记录的 int32 个数（internalIdIdx, providerIdx, dependencyKeyIdx,
# dependencyHash, dataIndex, primaryKeyIdx, resourceTypeIdx）。
ENTRY_INT32_COUNT = 7
DATA_INDEX_FIELD = 4  # entry 内 dataIndex 的 int32 下标

_UINT32_MAX = 0xFFFFFFFF


class CatalogFormatError(RuntimeError):
    """catalog 字节布局与已知格式不符；调用方应中止并报告实际字节证据。"""


# --------------------------------------------------------------------------
# 读取 / 分段解析
# --------------------------------------------------------------------------

def load_catalog(path):
    """读入 catalog，返回 (raw_bytes, doc, had_bom)。"""
    with open(path, "rb") as fh:
        raw = fh.read()
    had_bom = raw[:3] == b"\xef\xbb\xbf"
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except ValueError as exc:
        raise CatalogFormatError("%s: 顶层 JSON 解析失败: %s" % (path, exc))
    for key in ("m_ExtraDataString", "m_EntryDataString", "m_InternalIds"):
        if key not in doc:
            raise CatalogFormatError("%s: 缺少顶层键 %s" % (path, key))
    return raw, doc, had_bom


def find_segment_starts(blob):
    """返回段 JSON 的 UTF-16 起点偏移列表（升序）。"""
    starts = []
    pos = blob.find(SEG_MARK)
    while pos != -1:
        starts.append(pos)
        pos = blob.find(SEG_MARK, pos + 1)
    return starts


def parse_segments(blob):
    """把 m_ExtraDataString 的 blob 拆成段列表。

    每段返回 dict：index / json_at / header_at / declared / actual / obj / text。
    帧头不自洽（declared != 实际 UTF-16 字节数）或段头不齐即抛 CatalogFormatError。
    """
    starts = find_segment_starts(blob)
    if not starts:
        raise CatalogFormatError("m_ExtraDataString 里找不到任何 '%s' 段标记"
                                 % SEG_MARK.decode("ascii"))
    if starts[0] < SEG_OVERHEAD:
        raise CatalogFormatError(
            "首段 JSON 起点 %d < %d，段前缀不足，布局与预期不符；前 64 字节=%r"
            % (starts[0], SEG_OVERHEAD, blob[:64]))

    decoder = json.JSONDecoder()
    segs = []
    for i, json_at in enumerate(starts):
        header_at = json_at - SEG_OVERHEAD
        declared = struct.unpack_from("<i", blob, json_at - 4)[0]
        if declared < 0 or json_at + declared > len(blob):
            raise CatalogFormatError(
                "seg[%02d] 帧头越界: declared=%d, json_at=%d, blob=%d"
                % (i, declared, json_at, len(blob)))
        text = blob[json_at:json_at + declared].decode("utf-16-le", errors="replace")
        try:
            obj, end_chars = decoder.raw_decode(text)
        except ValueError as exc:
            raise CatalogFormatError(
                "seg[%02d] JSON 解析失败: %s；原文前 160 字符=%r"
                % (i, exc, text[:160]))
        actual = end_chars * 2
        if declared != actual:
            raise CatalogFormatError(
                "seg[%02d] 帧头不自洽: declared=%d actual=%d；原文前 160 字符=%r"
                % (i, declared, actual, text[:160]))
        # 类型头必须与首段一致，否则不能假定统一布局。
        if blob[header_at:header_at + SEG_TYPE_HEADER_LEN] != \
                blob[starts[0] - SEG_OVERHEAD:starts[0] - SEG_OVERHEAD + SEG_TYPE_HEADER_LEN]:
            raise CatalogFormatError(
                "seg[%02d] 的 153 字节类型头与首段不同，布局与预期不符；本段头=%r"
                % (i, blob[header_at:header_at + SEG_TYPE_HEADER_LEN]))
        segs.append({"index": i, "json_at": json_at, "header_at": header_at,
                     "declared": declared, "actual": actual, "obj": obj,
                     "text": text})
    return segs


def load_entries(doc):
    """解 m_EntryDataString，返回 (entry_count, raw_entry_bytes, [(internal_id_idx, data_index), ...])。"""
    ent = base64.b64decode(doc["m_EntryDataString"])
    if len(ent) < 4:
        raise CatalogFormatError("m_EntryDataString 只有 %d 字节" % len(ent))
    count = struct.unpack_from("<i", ent, 0)[0]
    expect = 4 + count * ENTRY_INT32_COUNT * 4
    if expect != len(ent):
        raise CatalogFormatError(
            "m_EntryDataString 长度不符: count=%d 期望 %d 实际 %d"
            % (count, expect, len(ent)))
    pairs = []
    for e in range(count):
        iid, _p, _dk, _dh, di, _pk, _rt = struct.unpack_from(
            "<7i", ent, 4 + e * ENTRY_INT32_COUNT * 4)
        if di >= 0:
            pairs.append((e, iid, di))
    return count, ent, pairs


def build_segment_map(doc, segs):
    """建立「段 -> bundle 文件名」与「段 -> dataIndex」双向映射。

    依赖两条现场事实：dataIndex 按段顺序升序、段偏移也按序升序。
    若 dataIndex 条数与段数不等 → 抛错（布局未理解，不猜）。
    """
    count, ent, pairs = load_entries(doc)
    if len(pairs) != len(segs):
        raise CatalogFormatError(
            "dataIndex>=0 的 entry 数 %d 与 extra-data 段数 %d 不等，无法可靠映射"
            % (len(pairs), len(segs)))
    internal_ids = doc["m_InternalIds"]
    for seg, (entry_no, iid, data_index) in zip(segs, pairs):
        if not 0 <= iid < len(internal_ids):
            raise CatalogFormatError(
                "entry %d 的 internalIdIdx=%d 越界（m_InternalIds 共 %d 条）"
                % (entry_no, iid, len(internal_ids)))
        seg["entry_index"] = entry_no
        seg["internal_id_idx"] = iid
        seg["data_index"] = data_index
        seg["data_index_ok"] = (data_index == seg["header_at"])
        seg["bundle_name"] = _basename(internal_ids[iid])
    return count, ent, pairs


def _basename(internal_id):
    """从 internalId 风格路径里取文件名（catalog 用反斜杠，也容忍正斜杠）。"""
    normalized = internal_id.replace("\\", "/")
    return normalized.rsplit("/", 1)[-1]


# --------------------------------------------------------------------------
# 重序列化
# --------------------------------------------------------------------------

def dumps_segment(obj):
    """按游戏原样风格重序列化段 JSON（已现场验证与 Unity 序列化逐字相同）。"""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def rebuild_blob(segs, seg_texts):
    """按新段文本重建 m_ExtraDataString 的 blob，并回写各段偏移。

    segs 的 ``type_header`` 必须来自原 blob（不改常量头）。
    返回 (new_blob, new_header_at[])。dataIndex 由调用方按新 header_at 回写。
    """
    out = bytearray()
    headers = []
    for seg, text in zip(segs, seg_texts):
        headers.append(len(out))
        out += seg["type_header"]
        payload = text.encode("utf-16-le")
        out += struct.pack("<i", len(payload))
        out += payload
    return bytes(out), headers


def patch_b64_literal(raw, key, new_b64, path):
    """外科式替换 ``"<key>":"<base64>"`` 字面量，其余字节原样保留。"""
    enc_key = ('"%s":"' % key).encode("ascii")
    if raw.count(enc_key) != 1:
        raise CatalogFormatError(
            "%s: 键字面量 %s 出现 %d 次（要求恰好 1 次）"
            % (path, enc_key.decode("ascii"), raw.count(enc_key)))
    head, _, tail = raw.partition(enc_key)
    start = len(head) + len(enc_key)
    # base64 值以 '"' 结束；base64 字母表不含 '"'，直接找下一个引号。
    end = raw.index(b'"', start)
    old_b64 = raw[start:end]
    return raw[:start] + new_b64 + raw[end:], old_b64


# --------------------------------------------------------------------------
# bundle 定位
# --------------------------------------------------------------------------

def resolve_bundle_file(bundle_dir, bundle_name):
    """在 bundle_dir 里定位 bundle 文件；支持直接给 StandaloneWindows64 或其父目录。"""
    direct = os.path.join(bundle_dir, bundle_name)
    nested = os.path.join(bundle_dir, "StandaloneWindows64", bundle_name)
    for cand in (direct, nested):
        if os.path.isfile(cand):
            return cand
    raise FileNotFoundError(
        "在 %s 下找不到 %s（也试过 %s）"
        % (bundle_dir, bundle_name, os.path.join(bundle_dir, "StandaloneWindows64", bundle_name)))


def parse_crc(text):
    """解析 --crc：十进制或 0x 十六进制 -> 0..0xFFFFFFFF。"""
    s = text.strip()
    try:
        value = int(s, 16) if s.lower().startswith("0x") else int(s, 10)
    except ValueError:
        raise ValueError("--crc 需要十进制或 0x 十六进制整数，收到 %r" % text)
    if not 0 <= value <= _UINT32_MAX:
        raise ValueError("--crc 超出 uint32 范围: %d" % value)
    return value


# --------------------------------------------------------------------------
# 核验
# --------------------------------------------------------------------------

def check_consistency(doc, segs):
    """返回不一致项列表（帧头 / dataIndex / 映射）。"""
    problems = []
    for seg in segs:
        if not seg.get("data_index_ok", True):
            problems.append(
                "seg[%02d] dataIndex=%d 与段头偏移 %d 不符（delta=%+d）"
                % (seg["index"], seg["data_index"], seg["header_at"],
                   seg["data_index"] - seg["header_at"]))
    names = {}
    for seg in segs:
        names.setdefault(seg["bundle_name"].lower(), []).append(seg["index"])
    for name, idxs in names.items():
        if len(idxs) > 1:
            problems.append("bundle %s 映射到多个段: %s" % (name, idxs))
    return problems


def print_table(segs, path):
    print("=== %s：%d 段" % (path, len(segs)))
    print("  %-5s %-9s %-9s %-9s %-12s %-8s %s"
          % ("seg", "json_at", "hdr_at", "entry", "m_Crc", "size", "bundle"))
    for seg in segs:
        print("  [%02d] %-9d %-9d %-9d %-12d %-8d %s"
              % (seg["index"], seg["json_at"], seg["header_at"],
                 seg.get("entry_index", -1), seg["obj"]["m_Crc"],
                 seg["obj"]["m_BundleSize"], seg["bundle_name"]))


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def open_catalog(path):
    """读 catalog 并完成全部分段解析（任何格式异常都在此抛出）。"""
    raw, doc, had_bom = load_catalog(path)
    blob = base64.b64decode(doc["m_ExtraDataString"])
    segs = parse_segments(blob)
    first_header = segs[0]["json_at"] - SEG_OVERHEAD
    for seg in segs:
        seg["type_header"] = blob[seg["header_at"]:seg["header_at"] + SEG_TYPE_HEADER_LEN]
    count, ent, pairs = build_segment_map(doc, segs)
    # 自检：未改动段重序列化必须逐字还原，否则说明风格假设不成立 → 中止。
    for seg in segs:
        if dumps_segment(seg["obj"]) != seg["text"]:
            raise CatalogFormatError(
                "seg[%02d] 重序列化与原文字节不一致，中止写回；\n"
                "  原=%r\n  新=%r"
                % (seg["index"], seg["text"][:200], dumps_segment(seg["obj"])[:200]))
    return {"path": path, "raw": raw, "doc": doc, "had_bom": had_bom,
            "blob": blob, "segs": segs, "entry_count": count,
            "ent": ent, "pairs": pairs, "first_header": first_header}


def plan_changes(resolved, crc_new):
    """按已定位的 (显示名, 段) 求变更计划。

    resolved: [(显示用名字, seg)]，seg["bundle"] 已带 {"path","size"}。
    crc_new 为 None 表示 m_Crc 保持原值。
    """
    plan = []
    for name, seg in resolved:
        new_size = seg["bundle"]["size"]
        new_crc = seg["obj"]["m_Crc"] if crc_new is None else crc_new
        new_obj = dict(seg["obj"])
        new_obj["m_BundleSize"] = new_size
        new_obj["m_Crc"] = new_crc
        new_text = dumps_segment(new_obj)
        if len(new_text.encode("utf-16-le")) == seg["declared"] and \
                new_obj == seg["obj"]:
            change = "（无变化）"
        else:
            change = ""
        plan.append({"seg": seg, "name": name, "path": seg["bundle"]["path"],
                     "old_size": seg["obj"]["m_BundleSize"], "new_size": new_size,
                     "old_crc": seg["obj"]["m_Crc"], "new_crc": new_crc,
                     "new_obj": new_obj, "new_text": new_text, "note": change})
    return plan


def apply_plan(ctx, plan):
    """执行修改并生成新的 catalog 字节。返回 (new_raw, 变更明细列表)。"""
    segs = ctx["segs"]
    seg_texts = [seg["text"] for seg in segs]
    old_objs = [dict(seg["obj"]) for seg in segs]
    for item in plan:
        seg_texts[item["seg"]["index"]] = item["new_text"]

    new_blob, new_headers = rebuild_blob(segs, seg_texts)

    # dataIndex 回写：按段顺序重算 header_at，并同步 m_EntryDataString。
    ent = bytearray(ctx["ent"])
    index_changes = []
    for seg, new_hdr in zip(segs, new_headers):
        ent_off = 4 + seg["entry_index"] * ENTRY_INT32_COUNT * 4
        old_val = struct.unpack_from("<i", ent, ent_off + DATA_INDEX_FIELD * 4)[0]
        struct.pack_into("<i", ent, ent_off + DATA_INDEX_FIELD * 4, new_hdr)
        if old_val != new_hdr:
            index_changes.append((seg["index"], seg["bundle_name"],
                                  old_val, new_hdr, new_hdr - old_val))

    raw = ctx["raw"]
    raw, _old = patch_b64_literal(raw, "m_ExtraDataString",
                                 base64.b64encode(new_blob), ctx["path"])
    raw, _old = patch_b64_literal(raw, "m_EntryDataString",
                                 base64.b64encode(bytes(ent)), ctx["path"])
    return raw, index_changes, old_objs


def verify_result(new_raw, old_raw, expected):
    """对新字节做独立复核：可解析、段帧头自洽、dataIndex 自洽、未改段逐字未变。"""
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".catalog.json")
    try:
        with os.fdopen(tmp_fd, "wb") as fh:
            fh.write(new_raw)
        raw2, doc2, _ = load_catalog(tmp_path)
        blob2 = base64.b64decode(doc2["m_ExtraDataString"])
        segs2 = parse_segments(blob2)
        count2, ent2, pairs2 = load_entries(doc2)
        problems = []
        hdrs = [seg["header_at"] for seg in segs2]
        if len(pairs2) != len(segs2):
            problems.append("dataIndex 条数 %d != 段数 %d" % (len(pairs2), len(segs2)))
        for seg, (_e, _i, di) in zip(segs2, pairs2):
            if di != seg["header_at"]:
                problems.append("seg[%02d] dataIndex=%d != hdr_at=%d"
                                % (seg["index"], di, seg["header_at"]))
        # 未改动段必须逐字相同
        old_seg_objs = expected["old_objs"]
        changed = expected["changed_indexes"]
        for seg, old_obj in zip(segs2, old_seg_objs):
            if seg["index"] not in changed and seg["text"] != dumps_segment(old_obj):
                problems.append("seg[%02d] 未在计划内却被改动" % seg["index"])
        for seg in segs2:
            if seg["index"] in changed:
                want = expected["want_objs"][seg["index"]]
                if seg["obj"] != want:
                    problems.append("seg[%02d] 回写值不符：%r" % (seg["index"], seg["obj"]))
        # 除两个 blob 外的顶层键必须逐字节不变
        doc_old = json.loads(old_raw.decode("utf-8-sig"))
        for key in doc_old:
            if key in ("m_ExtraDataString", "m_EntryDataString"):
                continue
            if doc_old[key] != doc2[key]:
                problems.append("顶层键 %s 被意外改动" % key)
        return problems, len(segs2)
    finally:
        os.unlink(tmp_path)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="catalog_sync.py",
        description="同步 Addressables catalog.json 中指定 bundle 的 m_BundleSize / m_Crc。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="默认 dry-run；加 --write 才落盘（落盘前自动备份 .bak）。"
               "CRC 不计算，值一律来自 --crc。",
    )
    ap.add_argument("catalog", help="catalog.json 路径")
    ap.add_argument("--bundle-dir", help="bundle 文件所在目录（可直接给 StandaloneWindows64）")
    ap.add_argument("--bundle", action="append", default=[], metavar="NAME",
                    help="bundle 文件名，可重复传参；给完整 internalId 路径亦可")
    ap.add_argument("--crc", default=None,
                    help="新的 m_Crc（十进制或 0x 十六进制）。缺省=保持原值；--crc 0=占位清零")
    ap.add_argument("--write", action="store_true", help="真正写盘（默认 dry-run）")
    ap.add_argument("--verify", action="store_true", help="只核验不改")
    args = ap.parse_args(argv)

    path = args.catalog
    if not os.path.isfile(path):
        print("错误：catalog 不存在 %s" % path, file=sys.stderr)
        return 2
    if not args.verify and not args.bundle:
        print("错误：需要 --bundle（或用 --verify 只核验）", file=sys.stderr)
        return 2
    if args.bundle and not args.bundle_dir:
        print("错误：--bundle 需要配合 --bundle-dir", file=sys.stderr)
        return 2

    try:
        ctx = open_catalog(path)
    except CatalogFormatError as exc:
        print("格式错误，已中止（未写任何文件）：\n  %s" % exc, file=sys.stderr)
        return 1

    print("catalog: %s (%d bytes, %d 段, entry=%d)"
          % (path, len(ctx["raw"]), len(ctx["segs"]), ctx["entry_count"]))
    print_table(ctx["segs"], path)

    problems = check_consistency(ctx["doc"], ctx["segs"])
    if problems:
        print("\n[输入即不自洽，将在本工具中被一并修正]")
        for p in problems:
            print("  ! %s" % p)
    if args.verify:
        print("\nVERIFY: %s（问题 %d）" % ("OK" if not problems else "FAILED", len(problems)))
        return 0 if not problems else 1

    try:
        crc_new = parse_crc(args.crc) if args.crc is not None else None
    except ValueError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2

    # 定位 bundle 文件并记录实际大小
    by_name = {}
    for seg in ctx["segs"]:
        by_name.setdefault(seg["bundle_name"].lower(), seg)
    resolved = []
    for name in args.bundle:
        seg = by_name.get(_basename(name).lower())
        if seg is None:
            print("错误：catalog 里找不到 bundle %s 对应的段" % _basename(name),
                  file=sys.stderr)
            print("       catalog 内 11 段分别是：%s"
                  % ", ".join(s["bundle_name"] for s in ctx["segs"]), file=sys.stderr)
            return 2
        try:
            fpath = resolve_bundle_file(args.bundle_dir, _basename(name))
        except FileNotFoundError as exc:
            print("错误：%s" % exc, file=sys.stderr)
            return 2
        seg["bundle"] = {"path": fpath, "size": os.path.getsize(fpath)}
        resolved.append((name, seg))

    plan = plan_changes(resolved, crc_new)

    print("\n=== 变更计划（%s）" % ("WRITE" if args.write else "DRY-RUN"))
    for item in plan:
        print("  seg[%02d] %s" % (item["seg"]["index"], item["name"]))
        print("    文件        : %s" % item["path"])
        print("    m_BundleSize: %d -> %d%s"
              % (item["old_size"], item["new_size"],
                 "" if item["old_size"] != item["new_size"] else "   (不变)"))
        print("    m_Crc       : %d (0x%08X) -> %d (0x%08X)%s"
              % (item["old_crc"], item["old_crc"], item["new_crc"], item["new_crc"],
                 "" if item["old_crc"] != item["new_crc"] else "   (不变)"))
        print("    段帧头      : %d -> %d B (UTF-16 JSON)"
              % (item["seg"]["declared"],
                 len(item["new_text"].encode("utf-16-le"))))
    print("    dataIndex    : 依段长变化自动重算（见下方写盘结果）")

    try:
        new_raw, index_changes, old_objs = apply_plan(ctx, plan)
    except CatalogFormatError as exc:
        print("格式错误，已中止（未写任何文件）：\n  %s" % exc, file=sys.stderr)
        return 1

    changed_indexes = {item["seg"]["index"] for item in plan}
    expected = {"old_objs": old_objs, "changed_indexes": changed_indexes,
                "want_objs": {item["seg"]["index"]: item["new_obj"] for item in plan}}
    try:
        vproblems, nsegs = verify_result(new_raw, ctx["raw"], expected)
    except CatalogFormatError as exc:
        print("回写结果自检失败，已中止（未写任何文件）：\n  %s" % exc, file=sys.stderr)
        return 1
    if vproblems:
        print("回写结果自检失败，已中止（未写任何文件）：", file=sys.stderr)
        for p in vproblems:
            print("  ! %s" % p, file=sys.stderr)
        return 1

    if new_raw == ctx["raw"]:
        print("\n结果：字节完全不变（%d bytes，与原文件逐字节一致）" % len(new_raw))
    else:
        print("\n结果：%d -> %d bytes" % (len(ctx["raw"]), len(new_raw)))
    if index_changes:
        print("dataIndex 修正 %d 条：" % len(index_changes))
        for idx, name, old_v, new_v, delta in index_changes:
            print("  seg[%02d] %s : %d -> %d (%+d)" % (idx, name, old_v, new_v, delta))
    else:
        print("dataIndex: 无需变化")
    print("回写自检: OK（%d 段帧头自洽、dataIndex 自洽、未改段逐字未变）" % nsegs)

    if not args.write:
        print("\n[DRY-RUN] 未写盘。确认无误后加 --write 执行。")
        return 0

    bak = path + ".bak"
    shutil.copy2(path, bak)
    tmp_out = path + ".tmp"
    with open(tmp_out, "wb") as fh:
        fh.write(new_raw)
    os.replace(tmp_out, path)
    print("\n已写盘: %s（备份: %s）" % (path, bak))
    return 0


if __name__ == "__main__":
    sys.exit(main())
