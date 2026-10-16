"""翻译工作表机械校验器（确定性、离线：不联网、不调用 LLM、不做语义判断）。

用途
----
`translation/zh_Hans.csv` 这类工作表在批量回填进 `src/build_patch.py` **之前**的
构建门槛：只做字符串/计数的机械比较，判定标准完全由下面的规则写死。

为什么必须 `io.open(..., encoding="utf-8-sig", newline="")` + `csv`
------------------------------------------------------------------
本表的单元格里含**真实换行符**。实测（逐 codepoint 探针，2026-10-16）：
  * `ja_source` 含真实 LF(0x0a) 的记录 **561** 条（恰好 1 个的 492 条、≥2 个的 69 条），
    `en_reference` 533 条、`comment` 15 条、`path` 与 `id` 各 4 条；
  * **字面 `\\n` 转义（反斜杠 + 字母 n，两个字符）在全表任何列都是 0 处** ——
    真正被使用的一直是真实换行；
  * 另有 **3 个孤立 CR(0x0d)**，全部落在同一条记录
    `AutoTalk:TestTalk_Lang:2`（起始物理行 1725）的 `ja_source`
    （值 = `スペイン語` + 1 个真实 LF + `ñÑ\\ráíúéó\\rÁÍÚÉÓ\\r¿¡`），
    此外还有位于单元格内的 CRLF（如 `en_reference` 21 条记录含 CR）。

任何 `splitlines()` / 逐行 `readline()` 的写法都会把一条记录切成多条，导致列错位与
行号错位，因此一律交给 `csv` 模块处理。

错误级规则（任一命中 → 有 error，退出码 1，阻断构建）
--------------------------------------------------
1. ``placeholder``      占位符一致性。四类 token 各自用 `collections.Counter` 提取后
                        逐一比对（重复次数也必须一致）；**同时**统计出现次数：
                          a) 花括号 `{...}`（如 `{0}`）：正则 ``\\{[^{}]*\\}``
                          b) printf `%s/%d/%f/%@`（含 `%1$s`、`%-5d`、`%.2f`）：
                             先把 `%%` 替换成空串屏蔽转义百分号，再用
                             ``%(?:\\d+\\$)?[-+ #0]*[\\d*]*(?:\\.\\d+)?[sdf@]``
                          c) **真实换行**：`\\r\\n` / 孤立 `\\r` / 孤立 `\\n` 的出现次数
                             （`RE_LINE_BREAK` 口径：`\\r\\n` 记 1 个，与 `csv` 模块及下面
                             反推起始行号的口径完全一致；孤立 CR 与本表实际存在的那 3 个
                             一样会被计入，译文丢掉它同样报错）
                          d) **字面** `\\n` 转义（反斜杠 + 字母 n，两个字符）的出现次数
                             （实测真实表 0 处，该类别专门用于捕获译者手写 `\\n` 的失误）
                        c 与 d 是**两个不同的 token 类别，互不抵消**：源文 1 个真实
                        换行、译文写成 1 个字面 `\\n` 仍然报错（进游戏会显示成字面
                        `\\n`）。同一行只输出 1 条 placeholder 错误，message 里列出
                        全部不一致的类别、缺失/多出的 token 及两侧总数。
2. ``control-leak``     控制标记泄漏：`speaker=` / `wait=` 这类标记只应留在 `comment`
                        列（标记的来源），译文里出现即判定为泄漏（大小写敏感子串匹配）。
3. ``empty``            `zh_Hans.strip()` 为空（`--allow-empty` 时整行跳过，见下）。
4. ``kana-residue``     疑似残留日文：去掉所有空白字符（`\\n`、`\\t`、半角空格、
                        全角空格 U+3000 等，用 `str.isspace()` 判定）后，
                        假名字符数 / 总字符数 > 0.30。假名范围：平假名
                        U+3040–U+309F、片假名 U+30A0–U+30FF、半角片假名 U+FF66–U+FF9D。
5. ``tag``              Unity 富文本标签一致性（错误级）。正则 ``</?[a-z]+[^>]*>``
                        （大小写敏感、小写字母开头）提取**有序列表**，要求种类、参数、
                        顺序全部一致；顺序不同也报错。message 写出第一处不一致的位置
                        （1 起）与两侧内容，以及两侧标签总数。

警告级规则（不阻断，退出码仍为 0）
--------------------------------
6. ``too-long``         `len(zh_Hans) > 1.8 * len(ja_source)`：补丁把字号从 8px 提到
                        12px 像素字体，行宽余量有限，过长译文会溢出对话框。
7. ``duplicate-divergence``  同文异译：按 `ja_source.strip()` 分组（只有译文非空的
                        行参与；源文为空的行无法判定「同文」，不参与），同组出现
                        ≥2 种不同译文时输出 **1 条**警告，位置取组内最先出现的那一行，
                        message 列出「出现 N 处、译法 M 种」及各自的首次位置与译文摘要。
                        组内译法完全一致则不输出任何内容。
8. ``zh-filled-but-source-empty``  反向保护：源文为空（`ja_source.strip() == ""`）却有
                        译文 → 1 条警告，message 说明「源文为空却有译文，疑为合并错位」。

**源文为空的行豁免（规则 3/4/1/5/6 全部不适用）**
真实表有 **47 行** `ja_source` 是真空串（`kind` 分布：Title 44 / DamageTalk 2 /
AutoTalk 1，例 `Title:TitleData_lv0_DemoRoot:infoDisable`）——这些行**无内容可译**，
`zh_Hans` 应保持空白，因此不得对它们报 `empty`。判定以**源文列 strip 后为空**为准；
这类行除规则 8 那一条警告外不产生任何 error/warning，只计入汇总的 `source_empty`。

规格变更记录（相对最初规格，来自上游两轮补充需求）
------------------------------------------------
* 原「附加警告 `newline-mismatch`」**作废**：真实换行（含孤立 CR）已并入规则 1（错误级）。
* 原「附加警告 `tag-mismatch`（多重集合、以日文为基准、日文无标签则跳过）」
  **升级为错误级规则 5 `tag`**，并改为**有序序列**逐一比对。多重集合基准与
  「无标签则跳过」的写法一并作废：`</?[a-z]+[^>]*>` 要求小写字母紧接 `<`（可带 `/`）
  且必须有闭合 `>`，纯文本里偶然的 `<` 不会被误匹配，因此译文侧凭空多出标签同样
  应当报错。`[附加]` 前缀不再使用（规则 6/7 已无“附加”语义）。
* 新增规则 7 `duplicate-divergence`（警告级）。
* 新增规则 8 `zh-filled-but-source-empty`（警告级）与**源文为空的行豁免**；
  `Report` 增加字段 `source_empty`（源文为空的行数），汇总行在**原有四个字段之后**
  追加该字段：`check_translation: rows=1411 nonempty=0 errors=0 warnings=0
  source_empty=47`（前四个字段的顺序与格式不变）。
* 新增 CLI `--source-column` 与 `text_ja` 自动回退；`Report` 相应增加只读附加字段
  `source_column` / `source_fallback`（既有字段名与语义不变）。
* 行号口径改为**编辑器 LF 口径**（排除孤立 CR，见下）；而**换行 token 计数**
  （规则 1c）仍把孤立 CR 当真实换行 —— 两者口径不同是有意的。

其他接口约定
----------
* ``line`` = 该记录在文件中的**起始物理行号**（表头为第 1 行），口径与编辑器 /
  `wc -l` 一致：**孤立 CR 不计入物理行号**。推导分两步：
    1. csv 口径的起始行 = `reader.line_num - 该记录各字段内换行总数`；
       其中「换行总数」按 `RE_LINE_BREAK` 计（`\\r\\n` 记 1，孤立 `\\r` 与孤立 `\\n` 各记 1）——
       因为在 `newline=''` 下 `csv` 把**孤立 CR 也当成一次换行**。
    2. 显示行号 = csv 口径起始行 − **之前记录**里累计的孤立 CR 数
       （当前记录自己的孤立 CR 出现在其起始行之后，不影响起始行；也不影响它自身的
       `reader.line_num` 落点）。孤立 CR 计数用 `\\r(?!\\n)`。
  真实表实测：LF 共 3011 个，孤立 CR 共 3 个（都在第 725 条记录
  `AutoTalk:TestTalk_Lang:2`、起始行 1725 的 `ja_source` 里）。于是 csv/RE 口径的
  物理行数是 3014，而编辑器口径的总行数是 **3011**（= `wc -l translation/zh_Hans.csv`）；
  1411 条记录修正后行号**严格递增**、最后一条记录起始行 = **3011**（旧口径会报 3014）。
  若不排除孤立 CR（旧实现），第 725 条记录之后的 **686** 条记录行号会被顶偏 +1～+3
  （实测 686 条与编辑器口径不符）；`work/_ct_worker_selftest.py` 会逐条比对编辑器
  口径的累加真值，并留一条「孤立 CR 行之后仍有记录」的回归用例。
  注意两种口径是**故意分开**的：**换行 token 计数**（规则 1c）把孤立 CR 当真实换行，
  因为译文丢掉它同样会改变显示；**行号显示**排除孤立 CR，只为了让行号能直接对上
  编辑器 / `wc -l`。
* ``row`` = 数据行序号，从 1 开始（不含表头）。
* **输出恒为「一条问题一行」**：`[ERROR] line=<起始物理行号> row=<数据行号> id=<id>
  rule=<规则> <message>`（`[WARN]` 同，`]` 后多一个空格以对齐）。`id` 可能含**空格**
  （真实表 167 条 id 含空格，如 `AutoTalk:S1_0_101_T5 (DEMO):0`）与**真实换行**
  （4 条记录的 id 带尾随 LF，如 `localization:Ending Table:Ending_NP03_03` + LF）；
  `message` 里也可能嵌有带换行的 token。`_format_entry()` 对 `id` 与 `message` 统一
  过 `_visible()`，把 `\\r\\n` / `\\n` / `\\r` 全部换成 `⏎`，因此**任何字段都不会往输出里
  注入裸换行**（对已是可见形态的文本幂等）。按行解析时 `id` 取到 `" rule="` 之前为止
  （正则可用 `id=(.*?)\\s+rule=([\\w-]+)`），末尾两行恒为汇总。
* ``not_started`` 与 ``source_empty`` 的交互（保留短路，统计提前）：
  当**全部**数据行的译文列都为空时视为「翻译尚未开始」→ `errors`/`warnings` 保持为空、
  `main()` 返回 0，提示为 `[NOTICE] <列> 列全空（0/1411 行有译文）：翻译尚未开始，
  跳过校验`；只要存在 1 行非空译文就按正常规则校验，其余空行照常报 `empty`（源文为空
  的行已被豁免，见上）。
  0 条数据行同样 `not_started=True`、退出码 0，提示改为「工作表无数据行」，跳过校验。
  **`source_empty` 在短路之前统计**，因此真实表（译文仍全空）会**三段并存**：
  ```
  [NOTICE] zh_Hans 列全空（0/1411 行有译文）：翻译尚未开始，跳过校验
  [NOTICE] 源文为空的行 47 行：无需译文，已豁免译文相关规则
  check_translation: rows=1411 nonempty=0 errors=0 warnings=0 source_empty=47
  check_translation: OK
  ```
  （exit=0。若去掉短路，这 1364 行未译行会报 1364 条 `empty`，既非预期也破坏
  「翻译尚未开始仍可构建」。）`source_empty > 0` 时的那行 NOTICE 属 NOTICE 类，
  `--quiet` 下也会打印。
* 源文列：默认 `ja_source`。`--source-column NAME` 可改；若默认列不存在但表头有
  `text_ja`（本仓库 `translation/ALL.csv` 系列就是这种布局）则**自动回退**并打印
  `[NOTICE] 源文列表头无 ja_source，改用 text_ja`（不改变退出码）。两列都没有 → 退出码 2。
* 退出码：有 error 级问题 → 1；无 → 0；CSV 不存在/缺列/解析失败 → 2（原因打到 stderr）。

实现中的两处解释（与原始规格的文字差异，均已在报告中说明）
--------------------------------------------------------
* 规则 2 的触发以**译文**为准：译文中出现 `speaker=` / `wait=` 即报错，无论该行的
  `comment` 是否含标记。这是规格最小条件的超集（「comment 含标记 且 译文含标记」
  的情形必然被覆盖），理由是这类标记不该出现在任何面向玩家的字符串里。
* `--allow-empty` 下，译文为空的行会跳过**全部**单元格级校验：既然上游明确允许
  「尚未翻译」，就不该再拿空单元格去比对占位符/换行/标签，否则门槛会被噪声淹没。
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import os
import re
import sys

__all__ = [
    "DEFAULT_COLUMN",
    "DEFAULT_PATH",
    "DEFAULT_SOURCE_COLUMN",
    "FALLBACK_SOURCE_COLUMN",
    "SheetError",
    "Report",
    "check_file",
    "main",
]

DEFAULT_COLUMN = "zh_Hans"
DEFAULT_PATH = os.path.join("translation", "zh_Hans.csv")
#: 源文列：默认 `ja_source`，缺失时回退 `text_ja`（ALL.csv 系列的列名）。
DEFAULT_SOURCE_COLUMN = "ja_source"
FALLBACK_SOURCE_COLUMN = "text_ja"

#: 12px 像素字体排版约束：译文字符数不得超过日文的该倍数（警告级）。
TOO_LONG_FACTOR = 1.8
#: 去掉空白后，假名字符占比超过该值即视为日文残留（错误级）。
KANA_RATIO_LIMIT = 0.30
#: 控制标记：只允许出现在 `comment` 列，不得进入译文。
CONTROL_MARKERS = ("speaker=", "wait=")
#: 同文异译警告里译文摘要的最大长度。
SUMMARY_LIMIT = 24

RE_BRACE = re.compile(r"\{[^{}]*\}")
RE_PRINTF = re.compile(r"%(?:\d+\$)?[-+ #0]*[\d*]*(?:\.\d+)?[sdf@]")
RE_TAG = re.compile(r"</?[a-z]+[^>]*>")
#: 一个真实换行（`\r\n` 记 1 个），用于从 line_num 反推记录起始行号。
RE_LINE_BREAK = re.compile(r"\r\n|\r|\n")
#: **孤立** CR（后面不是 LF）：`csv` 会把它当换行，编辑器 / `wc -l` 不会。
RE_LONE_CR = re.compile("\r(?!\n)")
KANA_RANGES = ((0x3040, 0x309F), (0x30A0, 0x30FF), (0xFF66, 0xFF9D))
#: 少任一列就无法完成机械校验，直接判为工作表错误（退出码 2）。
REQUIRED_COLUMNS = ("id",)
#: 译文中真实换行/换行的显示用代字符（保证一条问题只占一行）。
VISIBLE_NEWLINE = "⏎"


class SheetError(Exception):
    """工作表层面的错误（文件不存在 / 缺列 / 解析失败）→ `main()` 返回 2。"""


class Report:
    """一次校验的完整结果。字段名即上游 `src/build_patch.py` 的接入契约，勿改。

    `source_column` / `source_fallback` / `source_empty` 是补充需求新增的**只读附加字段**
    （源文列解析结果与源文为空的行数），不影响既有字段名与语义。
    """

    def __init__(self, path: str, column: str) -> None:
        self.path = path
        self.column = column
        self.rows = 0                                   # 数据行总数（不含表头）
        self.nonempty = 0                               # 译文列非空行数
        self.errors: list[dict] = []                    # {"line","row","id","rule","message"}
        self.warnings: list[dict] = []                  # 同上结构
        self.not_started = False                        # 翻译尚未开始（全空 / 无数据行）
        self.source_column = DEFAULT_SOURCE_COLUMN      # 实际使用的源文列
        self.source_fallback = False                    # 是否回退到 text_ja
        self.source_empty = 0                           # 源文（strip 后）为空的行数

    @property
    def ok(self) -> bool:
        """无错误级问题（警告不影响）。"""
        return not self.errors


# --------------------------------------------------------------------------- #
# 占位符 / 换行 token 提取与比对
# --------------------------------------------------------------------------- #
def _tokens_brace(text: str) -> collections.Counter:
    return collections.Counter(RE_BRACE.findall(text))


def _tokens_printf(text: str) -> collections.Counter:
    # `%%` 是转义百分号，不是格式占位符：先屏蔽成空串再匹配。
    return collections.Counter(RE_PRINTF.findall(text.replace("%%", "")))


def _tokens_real_newline(text: str) -> collections.Counter:
    # 真实换行：`\r\n` 记 1 个，孤立 `\r` 与孤立 `\n` 各记 1 个。
    # 用 RE_LINE_BREAK 而不是 text.count("\n")，否则漏掉孤立 CR（真实表里确实存在 3 个）。
    count = len(RE_LINE_BREAK.findall(text))
    return collections.Counter({"真实换行": count}) if count else collections.Counter()


def _tokens_literal_newline(text: str) -> collections.Counter:
    # 字面 `\n`：反斜杠 + 字母 n，共两个字符（不是真实换行 0x0a）。
    count = text.count("\\n")
    return collections.Counter({"\\n": count}) if count else collections.Counter()


def _diff_tokens(base: collections.Counter,
                 other: collections.Counter) -> tuple[list[str], list[str]]:
    """以 base（源文）为基准比对 other（译文），返回（缺失, 多出）的可读 token 列表。"""
    missing, extra = [], []
    for token in sorted(base):
        delta = base[token] - other.get(token, 0)
        if delta > 0:
            missing.append(f"{token}×{delta}")
    for token in sorted(other):
        delta = other[token] - base.get(token, 0)
        if delta > 0:
            extra.append(f"{token}×{delta}")
    return missing, extra


#: 参与占位符比对的四类 token（固定顺序，保证输出确定性）。
TOKEN_CATEGORIES = (
    ("花括号", _tokens_brace),
    ("printf", _tokens_printf),
    ("真实换行", _tokens_real_newline),
    ("字面转义", _tokens_literal_newline),
)


def _placeholder_problem(ja: str, zh: str) -> str:
    """四类 token 逐一比对；有问题返回可读描述（类别 + 缺失/多出的 token + 两侧总数）。"""
    clauses: list[str] = []
    for label, extract in TOKEN_CATEGORIES:
        source, target = extract(ja), extract(zh)
        if source == target:
            continue
        missing, extra = _diff_tokens(source, target)
        detail = ", ".join([f"缺失 {token}" for token in missing]
                           + [f"多出 {token}" for token in extra])
        clauses.append(f"{label}: {detail}"
                       f"（源共{sum(source.values())}/译文{sum(target.values())}）")
    return "; ".join(clauses)


def _visible(text: str) -> str:
    """把 token 内的真实换行换成可见代字符，保证一条问题只占一行。"""
    return text.replace("\r\n", VISIBLE_NEWLINE).replace("\n", VISIBLE_NEWLINE)\
               .replace("\r", VISIBLE_NEWLINE)


def _tag_problem(ja: str, zh: str) -> str:
    """有序比对两侧富文本标签序列；一致返回空串，否则给出第一处不一致的位置与内容。"""
    source, target = RE_TAG.findall(ja), RE_TAG.findall(zh)
    if source == target:
        return ""
    position = 0
    for position in range(max(len(source), len(target))):
        left = source[position] if position < len(source) else None
        right = target[position] if position < len(target) else None
        if left != right:
            break
    left_text = _visible(left) if left is not None else "无"
    right_text = _visible(right) if right is not None else "无"
    return (f"标签序列不一致: 位置{position + 1} 源={left_text} 译文={right_text}; "
            f"源共{len(source)}个/译文{len(target)}个")


# --------------------------------------------------------------------------- #
# 假名
# --------------------------------------------------------------------------- #
def _is_kana(ch: str) -> bool:
    code = ord(ch)
    return any(low <= code <= high for low, high in KANA_RANGES)


def _kana_ratio(zh: str) -> tuple[int, int, float]:
    """返回（假名字符数, 去空白后总字符数, 占比）；总字符数为 0 时占比记 0.0。"""
    compact = "".join(ch for ch in zh if not ch.isspace())
    if not compact:
        return 0, 0, 0.0
    kana = sum(1 for ch in compact if _is_kana(ch))
    return kana, len(compact), kana / len(compact)


def _summary(zh: str) -> str:
    """同文异译警告里的译文摘要：去空白、真实换行转可见代字符、超长截断。"""
    text = _visible(zh.strip())
    if len(text) > SUMMARY_LIMIT:
        text = text[:SUMMARY_LIMIT] + "…"
    return text


# --------------------------------------------------------------------------- #
# 逐行规则
# --------------------------------------------------------------------------- #
def _check_row(ja: str, zh: str, allow_empty: bool) -> tuple[list[tuple[str, str]],
                                                              list[tuple[str, str]]]:
    """对一条记录做全部机械校验，返回（错误列表, 警告列表），元素为 (rule, message)。"""
    errors: list[tuple[str, str]] = []
    warnings: list[tuple[str, str]] = []

    if not ja.strip():
        # 源文为空 = 无内容可译（真实表 47 行）：豁免全部译文相关规则
        # （empty / kana-residue / placeholder / tag / too-long），只在译文非空时给一条
        # 反向保护警告——该行除这条警告外不再产生任何 error/warning。
        if zh.strip():
            warnings.append((
                "zh-filled-but-source-empty",
                "源文为空却有译文，疑为合并错位（该行其余译文规则一并豁免）",
            ))
        return errors, warnings

    if allow_empty and not zh.strip():
        # 上游明确允许空译文：空单元格没有可校验的内容，整行跳过（含警告）。
        return errors, warnings

    # 1. placeholder（含真实换行 / 字面 \n，两个类别互不抵消）
    problem = _placeholder_problem(ja, zh)
    if problem:
        errors.append(("placeholder", problem))

    # 2. control-leak（以译文为准；comment 只是这些标记的合法归属地）
    leaked = [marker for marker in CONTROL_MARKERS if marker in zh]
    if leaked:
        errors.append(("control-leak", "译文出现控制标记 " + " / ".join(leaked)))

    # 3. empty
    if not zh.strip():
        errors.append(("empty", "译文为空（该列未填写）"))

    # 4. kana-residue
    kana, total, ratio = _kana_ratio(zh)
    if total and ratio > KANA_RATIO_LIMIT:
        errors.append((
            "kana-residue",
            f"疑似日文残留: 假名 {kana}/{total} 字符 = {ratio * 100:.1f}%"
            f" (>{KANA_RATIO_LIMIT * 100:g}%)",
        ))

    # 5. tag（错误级：种类 / 参数 / 顺序全一致）
    problem = _tag_problem(ja, zh)
    if problem:
        errors.append(("tag", problem))

    if ja:
        # 6. too-long（长度按解析出的单元格字符串原样计 len()）
        if len(zh) > TOO_LONG_FACTOR * len(ja):
            warnings.append((
                "too-long",
                f"译文长度 {len(zh)} > 日文 {len(ja)} × {TOO_LONG_FACTOR:g}",
            ))

    return errors, warnings


# --------------------------------------------------------------------------- #
# 读取
# --------------------------------------------------------------------------- #
def _read_records(path: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """解析工作表，返回 (表头, [(起始物理行号, 字段列表), ...])；出错抛 SheetError。"""
    if not os.path.isfile(path):
        raise SheetError(f"CSV 文件不存在或不是普通文件: {path}")
    try:
        with io.open(path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                raise SheetError(f"CSV 为空（连表头都没有）: {path}") from None
            records: list[tuple[int, list[str]]] = []
            lone_cr_before = 0      # 之前记录里累计的孤立 CR 数（csv 会把它们各算一行）
            for fields in reader:
                if not fields:
                    continue            # 空行不算数据行
                # 起始行号推导（口径与编辑器一致，详见模块 docstring）：
                #   ① csv 口径起始行 = reader.line_num − 该记录字段内换行数
                #      （记录内部每含一个换行，line_num 就多计一行）；
                #   ② 再减去**之前记录**里累计的孤立 CR 数（csv 把孤立 CR 也当换行，
                #      而编辑器 / wc -l 不算；当前记录自身的孤立 CR 在其起始行之后，
                #      不影响起始行）。
                embedded = sum(len(RE_LINE_BREAK.findall(value)) for value in fields)
                lone_cr_here = sum(len(RE_LONE_CR.findall(value)) for value in fields)
                records.append((reader.line_num - embedded - lone_cr_before, fields))
                lone_cr_before += lone_cr_here
    except UnicodeDecodeError as exc:
        raise SheetError(f"解码失败（应为 UTF-8 / UTF-8 BOM）: {path}: {exc}") from exc
    except csv.Error as exc:
        raise SheetError(f"CSV 解析失败: {path}: {exc}") from exc
    except OSError as exc:
        raise SheetError(f"读取失败: {path}: {exc}") from exc
    return header, records


def _column_index(header: list[str], name: str) -> int:
    """定位列（完全匹配优先，其次忽略首尾空白），找不到返回 -1。"""
    for index, title in enumerate(header):
        if title == name:
            return index
    for index, title in enumerate(header):
        if title.strip() == name:
            return index
    return -1


def _scan(path: str, column: str, allow_empty: bool, source_column: str) -> Report:
    """完成一次完整校验（不打印），返回 Report；工作表级错误抛 SheetError。"""
    header, records = _read_records(path)

    report = Report(path, column)

    # 源文列：默认 ja_source；缺失时回退 text_ja（ALL.csv 系列的列名）。
    source_index = _column_index(header, source_column)
    if source_index < 0 and source_column == DEFAULT_SOURCE_COLUMN:
        fallback = _column_index(header, FALLBACK_SOURCE_COLUMN)
        if fallback >= 0:
            source_index = fallback
            report.source_column = FALLBACK_SOURCE_COLUMN
            report.source_fallback = True
    if source_index < 0:
        if source_column == DEFAULT_SOURCE_COLUMN:
            reason = f"缺少列: {source_column}（表头既无 {source_column} 也无 {FALLBACK_SOURCE_COLUMN}）"
        else:
            reason = f"缺少列: {source_column}"
        raise SheetError(f"{reason}（表头: {', '.join(header)}）")

    needed = [column] + [name for name in REQUIRED_COLUMNS if name != column] + ["comment"]
    index_of: dict[str, int] = {}
    for name in needed:
        if name not in index_of:
            index_of[name] = _column_index(header, name)
    missing = [name for name in needed if name != "comment" and index_of[name] < 0]
    if missing:
        raise SheetError(f"缺少列: {', '.join(missing)}（表头: {', '.join(header)}）")

    report.rows = len(records)

    rows: list[tuple[int, str, str, str, str]] = []
    for line, fields in records:
        if len(fields) != len(header):
            raise SheetError(
                f"第 {line} 行有 {len(fields)} 个字段，表头为 {len(header)} 个"
                f"（列错位，拒绝校验）")
        comment_index = index_of["comment"]
        rows.append((
            line,
            fields[index_of["id"]],
            fields[comment_index] if comment_index >= 0 else "",
            fields[source_index],
            fields[index_of[column]],
        ))

    report.nonempty = sum(1 for row in rows if row[4].strip())
    # source_empty 必须在 not_started 短路**之前**统计：真实表译文仍全空时，
    # 「47 行源文为空」这条信息也要照常出现在输出里（三段并存，见模块 docstring）。
    report.source_empty = sum(1 for row in rows if not row[3].strip())

    if not rows or report.nonempty == 0:
        # 翻译尚未开始（或工作表为空）：任何规则都不适用，交由 main() 返回 0。
        report.not_started = True
        return report

    # 同文异译分组：按 ja_source.strip()，只有译文非空的行参与；
    # 源文为空的行无从判定「同文」，不参与（dict 保持首次出现顺序）。
    groups: dict[str, list[tuple[int, int, str, str]]] = {}

    for number, (line, row_id, _comment, ja, zh) in enumerate(rows, start=1):
        errors, warnings = _check_row(ja, zh, allow_empty)
        report.errors.extend(
            {"line": line, "row": number, "id": row_id, "rule": rule, "message": message}
            for rule, message in errors
        )
        report.warnings.extend(
            {"line": line, "row": number, "id": row_id, "rule": rule, "message": message}
            for rule, message in warnings
        )
        if zh.strip() and ja.strip():
            groups.setdefault(ja.strip(), []).append((line, number, row_id, zh))

    # 7. duplicate-divergence（警告级，组级：每组至多 1 条，位置取组内最先出现的一行）
    for members in groups.values():
        if len(members) < 2:
            continue
        first_of: dict[str, tuple[int, int, str, str]] = {}
        for member in members:
            first_of.setdefault(member[3], member)
        if len(first_of) < 2:
            continue
        head = members[0]
        detail = "; ".join(f"line={member[0]}/row={member[1]}/{_summary(member[3])}"
                           for member in first_of.values())
        report.warnings.append({
            "line": head[0],
            "row": head[1],
            "id": head[2],
            "rule": "duplicate-divergence",
            "message": f"相同源文出现 {len(members)} 处、译法 {len(first_of)} 种: {detail}",
        })

    return report


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #
def _format_entry(level: str, entry: dict) -> str:
    pad = " " if level == "WARN" else ""       # 与 [ERROR] 对齐
    # 集中消毒，保证「一条问题一行」：输出里任何字段都不许注入裸换行。
    #   * id 可能含**真实换行**（真实表 4 条记录的 id 带尾随 LF）与空格；
    #   * message 里可能嵌入带换行的 token（如标签序列比对）。
    # `_visible()` 把 \r\n / \n / \r 换成 ⏎，对已是可见形态的文本是幂等的。
    return (f"[{level}]{pad} line={entry['line']} row={entry['row']} "
            f"id={_visible(entry['id'])} rule={entry['rule']} "
            f"{_visible(entry['message'])}")


def _print_report(report: Report, stream, problems: bool = True) -> None:
    """打印校验结果；problems=False 时（`--quiet`）只输出 NOTICE 与汇总行。"""
    if report.source_fallback:
        print(f"[NOTICE] 源文列表头无 {DEFAULT_SOURCE_COLUMN}，"
              f"改用 {FALLBACK_SOURCE_COLUMN}", file=stream)

    if problems:
        for entry in report.errors:
            print(_format_entry("ERROR", entry), file=stream)
        for entry in report.warnings:
            print(_format_entry("WARN", entry), file=stream)

    if report.not_started:
        if report.rows == 0:
            print("[NOTICE] 工作表无数据行，跳过校验", file=stream)
        else:
            # column 名来自 CLI/表头，同样过一遍 _visible 以免注入裸换行
            print(f"[NOTICE] {_visible(report.column)} 列全空"
                  f"（{report.nonempty}/{report.rows} 行有译文）："
                  f"翻译尚未开始，跳过校验", file=stream)

    if report.source_empty:
        # 源文为空的行豁免译文规则；这条提示属 NOTICE 类，--quiet 下也打印。
        print(f"[NOTICE] 源文为空的行 {report.source_empty} 行："
              f"无需译文，已豁免译文相关规则", file=stream)

    print(f"check_translation: rows={report.rows} nonempty={report.nonempty} "
          f"errors={len(report.errors)} warnings={len(report.warnings)} "
          f"source_empty={report.source_empty}", file=stream)
    if report.ok:
        print("check_translation: OK", file=stream)
    else:
        print(f"check_translation: FAILED ({len(report.errors)} errors)", file=stream)


def _reconfigure(stream) -> None:
    """让 Windows 控制台也能打印中日文（不改变任何文件的读取编码）。"""
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):       # 已被外部包装/重定向时忽略
            pass


# --------------------------------------------------------------------------- #
# 公共接口
# --------------------------------------------------------------------------- #
def check_file(path, column: str = DEFAULT_COLUMN, allow_empty: bool = False,
               verbose: bool = True, stream=None,
               source_column: str = DEFAULT_SOURCE_COLUMN) -> Report:
    """解析并校验工作表；verbose=True 时把问题列表与汇总打印到 stream（默认 stdout）。

    `source_column` 为补充需求新增的**末尾关键字参数**（默认 `ja_source`），
    既有位置参数与关键字参数的用法不受影响。
    """
    out = sys.stdout if stream is None else stream
    report = _scan(path, column, allow_empty, source_column)
    if verbose:
        _print_report(report, out)
    return report


def main(argv=None) -> int:
    """CLI 入口：返回 0 通过 / 1 有错误级问题 / 2 用法或 IO 错误。"""
    _reconfigure(sys.stdout)
    _reconfigure(sys.stderr)

    parser = argparse.ArgumentParser(
        prog="check_translation",
        description="翻译工作表机械校验器（占位符/换行 / 控制标记 / 空译文 / 假名残留 / "
                    "富文本标签 + 超长、同文异译警示）",
    )
    parser.add_argument("csv", nargs="?", default=DEFAULT_PATH,
                        help=f"工作表路径（默认 {DEFAULT_PATH}）")
    parser.add_argument("--column", default=DEFAULT_COLUMN,
                        help=f"要校验的译文列（默认 {DEFAULT_COLUMN}）")
    parser.add_argument("--source-column", default=DEFAULT_SOURCE_COLUMN,
                        help=f"源文列（默认 {DEFAULT_SOURCE_COLUMN}；缺失时自动回退 "
                             f"{FALLBACK_SOURCE_COLUMN}）")
    parser.add_argument("--allow-empty", action="store_true",
                        help="允许空译文（跳过该行的全部单元格级校验）")
    parser.add_argument("--quiet", action="store_true", help="只打印汇总与 NOTICE")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:               # argparse 的用法错误（2）与 --help（0）
        code = exc.code
        return code if isinstance(code, int) else (0 if code is None else 2)

    try:
        report = check_file(args.csv, args.column, args.allow_empty,
                            verbose=not args.quiet, stream=sys.stdout,
                            source_column=args.source_column)
    except SheetError as exc:
        print(f"check_translation: {_visible(str(exc))}", file=sys.stderr)
        return 2

    if args.quiet:
        _print_report(report, sys.stdout, problems=False)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
