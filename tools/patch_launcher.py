# -*- coding: utf-8 -*-
"""Fiz 与彩虹星球 简体中文补丁 —— 图形安装器（阶段 F / W2 交付物）。

本文件实现冻结契约 §3：tkinter + ttk 图形外壳。

硬性边界：
  * 只调用 ``patch_tool``（契约 §2）的公共 API；GUI 自身不计算哈希、
    不读注册表、不拼接备份目录名。
  * 不引入任何外部图片/字体文件，不联网。
  * 界面文案全部为本文件自写中文，未沿用任何既有安装器的句子。

启动方式::

    python tools/patch_launcher.py             # 正常图形界面
    python tools/patch_launcher.py --selftest  # 无交互冒烟自检（构建界面 + 载荷完整性自检，
                                               # 1.5s 后自动关窗；退出码 0/1 可作机器判据）

冻结态自诊断（exe 为 console=False 的 windowed 构建，stdout 不可用，因此这些
installer.log 行是打包后判断内嵌资源是否解析正确的唯一证据；前缀固定可 grep）::

    patch_tool 载入: OK / patch_tool 载入失败: <原因>
    资源根: <ROOT>
    载荷: <N> 文件
    patch-info: payload_files=<值> | patch-info: 未找到 patch-info.json
    清单: payload_files=<值> | 清单: manifest 不可用: <原因>
    载荷自检: OK (125/125) | 载荷自检: 失败 <n> 条，首条=<相对路径>   # 仅 --selftest
"""

import logging
import os
import platform
import queue
import re
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, scrolledtext, ttk

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

APP_NAME = "Fiz 与彩虹星球 简体中文补丁"
APP_SUBTITLE = "把彩虹星球的旅途读成简体中文 · 安装前自动核对版本、备份将要覆盖的原文件"

LOG_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "FizRPChinesePatch",
    "logs",
)
LOG_FILE = os.path.join(LOG_DIR, "installer.log")

#: 主线程刷新间隔（契约 §3 要求 80ms）
DRAIN_MS = 80

#: 自检模式下自动关窗延时
SELFTEST_MS = 1500

#: 进度行形如 ``[3/102] 写入 xxx``
PROGRESS_RE = re.compile(r"^\s*\[\s*(\d+)\s*/\s*(\d+)\s*\]")

#: 童话像素风配色（柔和天空蓝 / 薄荷绿 / 暖黄）
COLORS = {
    "sky": "#e9f4fe",        # 柔和天空蓝：窗口底色
    "sky_line": "#bcdcf3",   # 天空蓝描边
    "mint": "#d8f3e5",       # 薄荷绿：状态栏
    "mint_deep": "#7fd0a9",  # 薄荷绿加深：主按钮 / 进度条
    "sun": "#ffe9b7",        # 暖黄：次按钮
    "sun_deep": "#f5c860",   # 暖黄加深：按钮按下态
    "sun_soft": "#fff6dd",   # 暖黄淡色：按钮悬停态
    "ink": "#28485c",        # 文字主色
    "ink_soft": "#5d7d90",   # 次要文字
    "paper": "#fbfdff",      # 日志区底色
    "disabled": "#eceff1",
    "disabled_ink": "#9aa7ae",
}

#: 字体族优先表（以系统已安装为准，逐级回退，不打包字体文件）
FONT_STACK = ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "TkDefaultFont")

#: 命令 → 界面上使用的中文名
CMD_LABEL = {
    "install": "安装中文补丁",
    "uninstall": "卸载并还原",
    "verify": "校验已安装文件",
    "check": "自检补丁载荷",
    "detect": "查找游戏目录",
}

#: 命令 → 完成后的状态文案（自写）
CMD_DONE = {
    "install": "安装完成：下次启动游戏时，语言选择画面请选第三项（中文）。",
    "uninstall": "还原完成：游戏文件已按备份还原到安装前状态。",
    "verify": "校验完成：文件比对结果见运行记录。",
    "check": "自检完成：补丁载荷检查结果见运行记录。",
}

#: 命令 → 结果里的计数字段（缺失的字段自动跳过，不报错）
COUNTER_LABELS = {
    "install": (("written", "已写入"), ("backed", "已备份"), ("skipped", "已跳过")),
    "uninstall": (("restored", "已还原"), ("skipped", "已跳过")),
    "verify": (("verified", "与载荷一致"), ("skipped", "缺失或不一致")),
    "check": (("skipped", "已跳过"),),
}


# --------------------------------------------------------------------------
# 窗口化安全：windowed 构建下 stdout/stderr 可能是 None
# --------------------------------------------------------------------------

class _DiscardWriter(object):
    """吞掉一切写入的假流对象，避免 windowed 运行时因 None 流崩溃。"""

    encoding = "utf-8"
    errors = "replace"

    def write(self, text):
        try:
            return len(text) if text else 0
        except TypeError:
            return 0

    def writelines(self, lines):
        return None

    def flush(self):
        return None

    def isatty(self):
        return False

    def fileno(self):
        raise OSError("假流没有文件描述符")


def ensure_std_streams():
    """把为 None 的标准流替换为丢弃写入器（契约 §3 窗口化安全）。"""
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            try:
                setattr(sys, name, _DiscardWriter())
            except Exception:  # pragma: no cover - 极端环境
                pass
    if getattr(sys, "stdin", None) is None:
        try:
            sys.stdin = _DiscardWriter()
        except Exception:  # pragma: no cover
            pass


def _say(text):
    """尽力向控制台打一行；windowed 下静默丢弃。"""
    stream = getattr(sys, "stdout", None)
    if stream is None:
        return
    try:
        stream.write(text + "\n")
        stream.flush()
    except Exception:
        pass


# --------------------------------------------------------------------------
# 日志
# --------------------------------------------------------------------------

def setup_logging(path=None):
    """配置追加式 utf-8 文件日志；成功返回日志文件路径。"""
    target = path or LOG_FILE
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        handler = logging.FileHandler(target, mode="a", encoding="utf-8")
    except Exception:
        logging.getLogger(__name__).exception("日志文件初始化失败：%s", target)
        return None
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for existing in list(root.handlers):
        base = getattr(existing, "baseFilename", None)
        if base and os.path.abspath(base) == os.path.abspath(target):
            return target
    root.addHandler(handler)
    return target


class CoreLogSink(object):
    """承接 ``patch_tool`` 的日志输出。

    同时支持两种约定：可调用对象（``log(line)``）与类文件对象（``log.write``），
    这样 GUI 与核心模块之间不会因为参数约定不同而丢失输出。
    """

    def __init__(self, emit):
        self._emit = emit
        self._buffer = ""

    def __call__(self, line):
        self._emit(str(line))

    def write(self, text):
        if not text:
            return 0
        text = str(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._emit(line)
        return len(text)

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def flush(self):
        if self._buffer.strip():
            self._emit(self._buffer)
        self._buffer = ""

    def isatty(self):
        return False


# --------------------------------------------------------------------------
# 核心模块导入（缺失时界面仍可打开，但功能会给出明确提示）
# --------------------------------------------------------------------------

try:
    import patch_tool
except Exception as _exc:  # 保持界面可启动，把原因留到日志与提示里
    patch_tool = None
    PATCH_TOOL_ERROR = "%s: %s" % (type(_exc).__name__, _exc)
else:
    PATCH_TOOL_ERROR = None


def _data_dir_name():
    """游戏数据目录名：取自 patch_tool 的公共常量，不在界面里复制字面量。"""
    rel = getattr(patch_tool, "GAME_REL", None) if patch_tool is not None else None
    if isinstance(rel, (list, tuple)) and rel:
        return str(rel[-1])
    return "游戏数据目录（*_Data）"


# --------------------------------------------------------------------------
# 图形界面
# --------------------------------------------------------------------------

class InstallerApp(tk.Tk):
    """补丁安装器主窗口。"""

    def __init__(self, interactive=True, log_path=None):
        tk.Tk.__init__(self)
        self.interactive = bool(interactive)
        self._alive = True
        self.busy = False
        self.events = queue.Queue()
        self._after_ids = []
        self.log_path = log_path or LOG_FILE
        self._job_log_lines = 0
        #: 仅 --selftest 使用：内嵌载荷完整性自检结果
        self.selftest_ok = False
        self.selftest_message = ""
        #: 载荷漂移判据（ok / drift / unknown；常规启动也记一行）
        self.drift_state = "unknown"
        self.drift_message = ""

        self.family = self._pick_font_family()
        self.f_title = (self.family, 17, "bold")
        self.f_sub = (self.family, 9)
        self.f_ui = (self.family, 10)
        self.f_ui_bold = (self.family, 10, "bold")
        self.f_log = (self.family, 9)

        self.title(APP_NAME)
        self.geometry("900x720")
        self.minsize(780, 620)
        self.configure(background=COLORS["sky"])

        self.data_dir = tk.StringVar(value="")
        self.status = tk.StringVar(value="准备就绪：正在自动查找游戏目录…")

        self._build_style()
        self._build_ui()

        self._note("窗口已打开：%s" % APP_NAME)
        self._note("界面语言：简体中文；日志文件：%s" % self.log_path)
        logging.info(
            "安装器启动：Python %s，frozen=%s，平台=%s",
            platform.python_version(),
            bool(getattr(sys, "frozen", False)),
            platform.platform(),
        )
        logging.info("日志文件：%s", self.log_path)
        self._log_environment()
        self._startup_diagnostics()
        if patch_tool is None:
            self._disable_actions()
            self._notify(
                "error",
                "核心模块缺失",
                "无法加载补丁核心模块（patch_tool）。\n\n"
                "界面可以打开，但安装、卸载与校验都无法进行，相关按钮已停用。\n"
                "请确认补丁包完整，然后把日志目录中的 installer.log 交给维护者。",
            )

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._schedule(DRAIN_MS, self._drain)
        self._schedule(250, self.start_detect)

    # -- 基础设施 ---------------------------------------------------------

    def _pick_font_family(self):
        try:
            available = set(tkfont.families(self))
        except Exception:
            available = set()
        for name in FONT_STACK:
            if name in available:
                return name
        return "TkDefaultFont"

    def _log_environment(self):
        if patch_tool is None:
            return
        for attr in ("ROOT", "PAYLOAD_DIR", "MANIFEST"):
            value = getattr(patch_tool, attr, None)
            if value is not None:
                logging.info("核心模块常量 %s = %s", attr, value)

    def _diag(self, text):
        """冻结态诊断行：同时进滚动日志区与 installer.log（前缀固定，可 grep）。"""
        logging.info("%s", text)
        self._note(text)

    def _startup_diagnostics(self):
        """常规启动的计数类自诊断；不做全量哈希，保证启动速度。

        设计前提：exe 是 console=False 的 windowed 构建，stdout 不可用，
        因此这些行是打包后判断“内嵌载荷 / patch-info 是否解析正确”的唯一证据。
        """
        if patch_tool is None:
            self._diag("patch_tool 载入失败: %s" % (PATCH_TOOL_ERROR or "原因未知"))
            return False
        self._diag("patch_tool 载入: OK")

        root = getattr(patch_tool, "ROOT", None)
        self._diag("资源根: %s" % (root if root else "(未提供)"))

        try:
            rels = list(patch_tool.payload_rel_paths() or [])
        except Exception as exc:
            self._diag("载荷: 读取失败（%s: %s）" % (type(exc).__name__, exc))
        else:
            self._diag("载荷: %d 文件" % len(rels))

        try:
            info = patch_tool.load_patch_info()
        except Exception as exc:
            self._diag("patch-info: 读取失败（%s: %s）" % (type(exc).__name__, exc))
        else:
            if isinstance(info, dict) and info:
                self._diag("patch-info: payload_files=%s"
                           % info.get("payload_files", "(缺少该字段)"))
            else:
                self._diag("patch-info: 未找到 patch-info.json")

        try:
            manifest = patch_tool.load_manifest()
        except Exception as exc:
            self._diag("清单: manifest 不可用: %s: %s" % (type(exc).__name__, exc))
        else:
            if isinstance(manifest, dict):
                count = manifest.get("payload_files", "(缺少该字段)")
                files = manifest.get("files")
                if isinstance(files, list):
                    count = "%s（记录 %d 条）" % (count, len(files))
                self._diag("清单: payload_files=%s" % count)
            else:
                self._diag("清单: manifest 不可用: 返回了非字典结果")

        # 载荷漂移（只比较相对路径集合，不比较大小/哈希；常规启动绝不因此失败或弹窗）
        self.drift_state, _detailed, compact = self._payload_drift()
        self.drift_message = _detailed
        self._diag(compact)
        return True

    # -- 载荷漂移判据 -----------------------------------------------------

    @staticmethod
    def _fmt_rel_list(items, limit=5):
        if not items:
            return "[无]"
        text = "、".join(items[:limit])
        if len(items) > limit:
            text += " …（共 %d 条）" % len(items)
        return "[" + text + "]"

    def _payload_drift(self):
        """比较「磁盘载荷文件集合」与「payload_rel_paths() 清单集合」。

        返回 (state, detailed_text, compact_text)：
          state   ∈ "ok" / "drift" / "unknown"
          detailed = 自检用（漂移时列出多出/缺失，最多各 5 条）
          compact  = 常规启动用（漂移时只写「有（磁盘 N / 清单 M）」）
        只比较相对路径集合，不比较大小/哈希（那部分由 _selftest_payload_hashes 负责）；
        任一来源取不到 → "unknown"，只记一行且不影响退出码。
        """
        if patch_tool is None:
            text = "载荷漂移: 无法比对（patch_tool 不可用）"
            return "unknown", text, text
        payload_dir = patch_tool.payload_dir()
        if not payload_dir or not os.path.isdir(payload_dir):
            text = "载荷漂移: 无法比对（找不到载荷目录：%s）" % (payload_dir or "未提供")
            return "unknown", text, text
        try:
            listed = set(
                str(rel).replace("\\", "/") for rel in (patch_tool.payload_rel_paths() or [])
            )
        except Exception as exc:
            text = "载荷漂移: 无法比对（清单读取失败：%s: %s）" % (type(exc).__name__, exc)
            return "unknown", text, text
        if not listed:
            text = "载荷漂移: 无法比对（清单为空）"
            return "unknown", text, text
        on_disk = set()
        try:
            for dirpath, _dirnames, filenames in os.walk(payload_dir):
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    on_disk.add(os.path.relpath(full, payload_dir).replace(os.sep, "/"))
        except Exception as exc:
            text = "载荷漂移: 无法比对（载荷目录遍历失败：%s: %s）" % (type(exc).__name__, exc)
            return "unknown", text, text
        extra = sorted(on_disk - listed)
        missing = sorted(listed - on_disk)
        if not extra and not missing:
            text = "载荷漂移: OK (%d/%d)" % (len(on_disk), len(listed))
            return "ok", text, text
        detailed = ("载荷漂移: 磁盘 %d 个 / 清单 %d 个，多出=%s，缺失=%s"
                    % (len(on_disk), len(listed),
                       self._fmt_rel_list(extra), self._fmt_rel_list(missing)))
        compact = "载荷漂移: 有（磁盘 %d / 清单 %d）" % (len(on_disk), len(listed))
        return "drift", detailed, compact

    def selftest_payload_check(self):
        """仅 --selftest：载荷 sha256 全量比对 + 载荷漂移判据。

        退出码判据：两项都通过 = 0；哈希不符或存在漂移 = 1；
        漂移「无法比对」不影响退出码（只记一行）。
        """
        hashes_ok = self._selftest_payload_hashes()
        state, detailed, _compact = self._payload_drift()
        self.drift_state = state
        self.drift_message = detailed
        self._diag(detailed)
        self.selftest_ok = bool(hashes_ok) and state != "drift"
        return self.selftest_ok

    def _selftest_payload_hashes(self):
        """用 patch_tool.sha256 逐条比对 payload_rel_paths() 与 manifest 记录的 sha256。"""
        if patch_tool is None:
            self.selftest_message = ("载荷自检: 失败（patch_tool 载入失败: %s）"
                                     % (PATCH_TOOL_ERROR or "原因未知"))
            self._diag(self.selftest_message)
            return False
        try:
            rels = list(patch_tool.payload_rel_paths() or [])
            manifest = patch_tool.load_manifest()
        except Exception as exc:
            self.selftest_message = "载荷自检: 失败（无法读取载荷或清单：%s: %s）" % (
                type(exc).__name__, exc)
            self._diag(self.selftest_message)
            return False
        if not rels:
            self.selftest_message = "载荷自检: 失败（载荷文件列表为空）"
            self._diag(self.selftest_message)
            return False

        recorded = {}
        for item in (manifest or {}).get("files") or []:
            if isinstance(item, dict) and item.get("path"):
                recorded[str(item["path"])] = str(item.get("sha256") or "")
        payload_dir = patch_tool.payload_dir()

        bad = []
        for rel in rels:
            want = recorded.get(rel)
            if want is None:
                bad.append(rel)
                continue
            full = os.path.join(payload_dir, rel.replace("/", os.sep))
            try:
                got = patch_tool.sha256(full)
            except Exception:
                got = ""
            if str(got).lower() != want.lower():
                bad.append(rel)

        if bad:
            self.selftest_message = "载荷自检: 失败 %d 条，首条=%s" % (len(bad), bad[0])
            self._diag(self.selftest_message)
            return False
        self.selftest_message = "载荷自检: OK (%d/%d)" % (len(rels), len(rels))
        self._diag(self.selftest_message)
        return True

    def _disable_actions(self):
        """核心模块不可用时停用会调用它的按钮。"""
        for button in self.action_buttons + [self.browse_button, self.redetect_button]:
            try:
                button.state(["disabled"])
            except tk.TclError:
                pass
        self._set_status("补丁核心模块不可用，操作按钮已停用。")

    def _schedule(self, delay_ms, callback):
        """登记定时回调，便于关窗时统一取消（避免 Tk 报 invalid command name）。"""
        ident = self.after(delay_ms, callback)
        self._after_ids.append(ident)
        return ident

    def _cancel_timers(self):
        # 用 getattr 兜底：即使控件在 __init__ 早期失败、属性尚未建立，也不能让关窗抛异常
        for ident in getattr(self, "_after_ids", None) or []:
            try:
                self.after_cancel(ident)
            except Exception:
                pass
        self._after_ids = []

    def destroy(self):
        self._alive = False
        try:
            self._cancel_timers()
        except Exception:
            logging.exception("取消定时器时出错（已忽略，继续关窗）")
        logging.info("窗口关闭，安装器退出")
        try:
            tk.Tk.destroy(self)
        except tk.TclError:
            pass

    def report_callback_exception(self, exc, value, tb):
        """Tk 回调里的未捕获异常：写日志 + 弹窗，绝不静默消失。"""
        detail = "".join(traceback.format_exception(exc, value, tb))
        logging.error("界面回调出现未捕获异常：\n%s", detail)
        try:
            self._note("界面内部错误：%s: %s" % (getattr(exc, "__name__", exc), value))
        except Exception:
            pass
        self._notify(
            "error",
            "程序内部错误",
            "界面遇到了未预期的错误，操作可能没有完成。\n\n"
            "%s: %s\n\n详细信息已写入日志：%s"
            % (getattr(exc, "__name__", exc), value, self.log_path),
        )

    # -- 样式与布局 -------------------------------------------------------

    def _build_style(self):
        style = ttk.Style(self)
        for theme in ("clam", "alt", "default"):
            if theme in style.theme_names():
                try:
                    style.theme_use(theme)
                    break
                except tk.TclError:
                    continue
        c = COLORS
        style.configure(".", background=c["sky"], foreground=c["ink"], font=self.f_ui)
        style.configure("Fiz.TFrame", background=c["sky"])
        style.configure("Fiz.TLabel", background=c["sky"], foreground=c["ink"], font=self.f_ui)
        style.configure("FizTitle.TLabel", background=c["sky"], foreground=c["ink"], font=self.f_title)
        style.configure("FizSub.TLabel", background=c["sky"], foreground=c["ink_soft"], font=self.f_sub)
        style.configure("FizHint.TLabel", background=c["sky"], foreground=c["ink_soft"], font=self.f_sub)
        style.configure(
            "FizStatus.TLabel",
            background=c["mint"],
            foreground=c["ink"],
            font=self.f_ui,
            padding=(12, 7),
            borderwidth=2,
            relief="solid",
        )
        style.configure(
            "Fiz.TLabelframe",
            background=c["sky"],
            bordercolor=c["sky_line"],
            borderwidth=2,
            relief="solid",
        )
        style.configure(
            "Fiz.TLabelframe.Label",
            background=c["sky"],
            foreground=c["ink"],
            font=self.f_ui_bold,
        )
        style.configure(
            "Fiz.TButton",
            background=c["sun"],
            foreground=c["ink"],
            font=self.f_ui,
            padding=(12, 7),
            borderwidth=2,
            relief="raised",
            focusthickness=2,
            focuscolor=c["sun_deep"],
        )
        style.map(
            "Fiz.TButton",
            background=[("pressed", c["sun_deep"]), ("active", c["sun_soft"]), ("disabled", c["disabled"])],
            foreground=[("disabled", c["disabled_ink"])],
            relief=[("pressed", "sunken"), ("!pressed", "raised")],
        )
        style.configure(
            "FizAccent.TButton",
            background=c["mint_deep"],
            foreground="#14313f",
            font=self.f_ui_bold,
            padding=(12, 7),
            borderwidth=2,
            relief="raised",
            focusthickness=2,
            focuscolor=c["mint_deep"],
        )
        style.map(
            "FizAccent.TButton",
            background=[("pressed", "#5fbf95"), ("active", "#9adfc0"), ("disabled", c["disabled"])],
            foreground=[("disabled", c["disabled_ink"])],
            relief=[("pressed", "sunken"), ("!pressed", "raised")],
        )
        style.configure(
            "Fiz.TEntry",
            fieldbackground="#ffffff",
            foreground=c["ink"],
            bordercolor=c["sky_line"],
            lightcolor=c["sky_line"],
            darkcolor=c["sky_line"],
            padding=5,
            font=self.f_ui,
        )
        style.map(
            "Fiz.TEntry",
            fieldbackground=[("readonly", "#f4fbff")],
            foreground=[("readonly", c["ink"])],
        )
        style.configure(
            "Fiz.Horizontal.TProgressbar",
            background=c["mint_deep"],
            troughcolor=c["sky_line"],
            bordercolor=c["sky_line"],
            lightcolor=c["mint"],
            darkcolor=c["mint_deep"],
            thickness=16,
        )

    def _build_ui(self):
        c = COLORS
        # 顶部像素风色带（不依赖任何图片资源）
        strip = tk.Frame(self, background=c["mint_deep"], height=7)
        strip.pack(fill="x", side="top")

        outer = ttk.Frame(self, padding=16, style="Fiz.TFrame")
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(6, weight=1)

        ttk.Label(outer, text=APP_NAME, style="FizTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(outer, text=APP_SUBTITLE, style="FizSub.TLabel", wraplength=820).grid(
            row=1, column=0, sticky="w", pady=(5, 13)
        )

        # 「游戏目录」区
        path_frame = ttk.LabelFrame(outer, text="游戏目录", padding=10, style="Fiz.TLabelframe")
        path_frame.grid(row=2, column=0, sticky="ew")
        path_frame.columnconfigure(0, weight=1)
        self.dir_entry = ttk.Entry(
            path_frame, textvariable=self.data_dir, state="readonly", style="Fiz.TEntry"
        )
        self.dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.browse_button = ttk.Button(path_frame, text="浏览…", command=self.on_browse, style="Fiz.TButton")
        self.browse_button.grid(row=0, column=1, padx=(0, 8))
        self.redetect_button = ttk.Button(
            path_frame, text="重新检测", command=self.start_detect, style="Fiz.TButton"
        )
        self.redetect_button.grid(row=0, column=2)
        ttk.Label(
            path_frame,
            text="窗口打开时会自动查找；找不到时点「浏览…」选择游戏根目录，或直接选择 %s 目录。"
            % _data_dir_name(),
            style="FizHint.TLabel",
            wraplength=800,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(9, 0))

        # 按钮行
        actions = ttk.Frame(outer, style="Fiz.TFrame")
        actions.grid(row=3, column=0, sticky="ew", pady=(13, 11))
        self.install_button = ttk.Button(
            actions, text="安装中文补丁", command=self.on_install, style="FizAccent.TButton"
        )
        self.install_button.pack(side="left", padx=(0, 9))
        self.uninstall_button = ttk.Button(
            actions, text="卸载并还原", command=self.on_uninstall, style="Fiz.TButton"
        )
        self.uninstall_button.pack(side="left", padx=(0, 9))
        self.verify_button = ttk.Button(
            actions, text="校验已安装文件", command=self.on_verify, style="Fiz.TButton"
        )
        self.verify_button.pack(side="left", padx=(0, 9))
        self.logdir_button = ttk.Button(
            actions, text="打开日志目录", command=self.on_open_log_dir, style="Fiz.TButton"
        )
        self.logdir_button.pack(side="left")
        #: 执行期间会被禁用的按钮（日志目录按钮保持可用）
        self.action_buttons = [self.install_button, self.uninstall_button, self.verify_button]

        # 状态栏
        ttk.Label(
            outer, textvariable=self.status, style="FizStatus.TLabel", anchor="w", justify="left"
        ).grid(row=4, column=0, sticky="ew")

        # 进度条
        self.progress = ttk.Progressbar(
            outer, mode="indeterminate", style="Fiz.Horizontal.TProgressbar"
        )
        self.progress.grid(row=5, column=0, sticky="ew", pady=(11, 11))

        # 滚动日志区
        log_frame = ttk.LabelFrame(outer, text="运行记录", padding=8, style="Fiz.TLabelframe")
        log_frame.grid(row=6, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_view = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            state="disabled",
            wrap="word",
            font=self.f_log,
            background=c["paper"],
            foreground=c["ink"],
            insertbackground=c["ink"],
            relief="flat",
            borderwidth=0,
        )
        self.log_view.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            log_frame,
            text="窗口只保留最近记录；完整内容见日志文件 installer.log。",
            style="FizHint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(7, 0))

    # -- 日志 / 状态 / 进度 ----------------------------------------------

    def _note(self, text):
        """向界面日志区追加一行（带本地时间戳），同时写文件日志。"""
        if not self._alive:
            return
        stamp = time.strftime("%H:%M:%S")
        try:
            self.log_view.configure(state="normal")
            self.log_view.insert("end", "[%s] %s\n" % (stamp, text))
            self.log_view.see("end")
            self.log_view.configure(state="disabled")
        except tk.TclError:
            return

    def _set_status(self, text):
        if self._alive:
            self.status.set(text)

    def _progress_indeterminate(self):
        try:
            self.progress.stop()
            self.progress.configure(mode="indeterminate")
            self.progress.start(14)
        except tk.TclError:
            pass

    def _progress_determinate(self, done, total):
        try:
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=max(1, total))
            self.progress["value"] = min(done, total)
        except tk.TclError:
            pass

    def _progress_reset(self):
        try:
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=100)
            self.progress["value"] = 0
        except tk.TclError:
            pass

    def _notify(self, kind, title, text):
        """提示框；自检模式只写日志，避免阻塞无人值守运行。"""
        logging.log(
            logging.ERROR if kind == "error" else logging.INFO, "提示[%s] %s：%s", kind, title, text
        )
        if not self.interactive:
            self._note("（自检模式已跳过弹窗）%s：%s" % (title, text.replace("\n", " ")))
            return
        try:
            if kind == "error":
                messagebox.showerror(title, text, parent=self)
            elif kind == "warning":
                messagebox.showwarning(title, text, parent=self)
            else:
                messagebox.showinfo(title, text, parent=self)
        except tk.TclError:
            pass

    def _ask(self, title, text):
        logging.info("询问用户 %s：%s", title, text.replace("\n", " "))
        if not self.interactive:
            self._note("（自检模式没有交互，默认按“放弃”处理）%s" % title)
            return False
        try:
            return bool(messagebox.askyesno(title, text, parent=self))
        except tk.TclError:
            return False

    # -- 事件循环 ---------------------------------------------------------

    def _drain(self):
        try:
            while True:
                self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        except Exception:
            logging.exception("刷新界面时出现异常")
        if self._alive:
            self._schedule(DRAIN_MS, self._drain)

    def _handle(self, item):
        if not isinstance(item, tuple) or not item:
            return
        kind = item[0]
        if kind == "log":
            self._on_core_log(item[1])
        elif kind == "detect":
            self._on_detect(item[1], item[2])
        elif kind == "precheck":
            self._on_precheck(item[1], item[2])
        elif kind == "precheck_failed":
            self._on_precheck_failed(item[1], item[2])
        elif kind == "done":
            self._on_done(item[1], item[2])

    def _on_core_log(self, text):
        line = str(text).rstrip("\r\n")
        if not line.strip():
            return
        self._job_log_lines += 1
        self._note(line)
        logging.info("[核心] %s", line)
        match = PROGRESS_RE.match(line)
        if match:
            done, total = int(match.group(1)), int(match.group(2))
            self._progress_determinate(done, total)
            self._set_status("正在处理：第 %d / %d 个文件…" % (done, total))

    # -- 自动检测 ---------------------------------------------------------

    def start_detect(self):
        if self.busy:
            return
        self._note("开始自动查找游戏目录（只读探测，不改动任何文件）…")
        self._set_status("正在自动查找游戏目录…")
        self._progress_indeterminate()
        threading.Thread(target=self._detect_worker, daemon=True).start()

    def _detect_worker(self):
        dirs = []
        error = None
        try:
            if patch_tool is None:
                error = "无法加载补丁核心模块：%s" % (PATCH_TOOL_ERROR or "原因未知")
            else:
                finder = getattr(patch_tool, "find_game_dirs", None)
                if callable(finder):
                    try:
                        dirs = [str(item) for item in (finder() or [])]
                    except Exception as exc:
                        error = "自动查找出错：%s: %s" % (type(exc).__name__, exc)
                else:
                    error = "补丁核心模块没有提供目录查找接口。"
                if not dirs and not error:
                    resolver = getattr(patch_tool, "resolve_data_dir", None)
                    if callable(resolver):
                        try:
                            found, reason = resolver(None)
                        except Exception as exc:
                            found, reason = None, "%s: %s" % (type(exc).__name__, exc)
                        if found:
                            dirs = [str(found)]
                        elif reason:
                            error = str(reason)
                    else:
                        error = "补丁核心模块没有提供目录解析接口。"
        except Exception:
            error = "查找线程异常：\n" + traceback.format_exc()
        self.events.put(("detect", dirs, error))

    def _on_detect(self, dirs, error):
        self._progress_reset()
        if dirs:
            for index, path in enumerate(dirs, 1):
                self._note("候选目录 %d/%d：%s" % (index, len(dirs), path))
            current = self.data_dir.get().strip()
            chosen = current if current in dirs else dirs[0]
            self.data_dir.set(chosen)
            self._note("本次将使用：%s" % chosen)
            if len(dirs) > 1:
                self._note("共有 %d 个候选，如不正确请点「浏览…」改选。" % len(dirs))
            self._set_status("已定位游戏目录，可以开始安装或校验。")
            logging.info("自动检测成功：%s", chosen)
        else:
            self._note("没有找到可用的游戏目录。" + (error or ""))
            self._set_status("未能自动定位游戏目录，请点「浏览…」手动选择。")
            logging.warning("自动检测失败：%s", error)
            self._notify(
                "warning",
                "未能自动找到游戏目录",
                "没有在常见的 Steam 安装位置找到《Fiz and the Rainbow Planet》。\n\n"
                "请点「浏览…」选择游戏所在文件夹；游戏根目录或 %s 目录都可以。\n\n%s"
                % (_data_dir_name(), error or ""),
            )

    # -- 目录选择 ---------------------------------------------------------

    def on_browse(self):
        if self.busy:
            return
        try:
            chosen = filedialog.askdirectory(title="请选择游戏目录", parent=self)
        except tk.TclError:
            chosen = ""
        if not chosen:
            return
        chosen = os.path.abspath(chosen)
        self.data_dir.set(chosen)
        self._note("手动选择目录：%s" % chosen)
        logging.info("用户手动选择目录：%s", chosen)
        self._set_status("已使用手动选择的目录。")

    def on_open_log_dir(self):
        folder = os.path.dirname(self.log_path) if self.log_path else LOG_DIR
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as exc:
            self._notify("error", "无法创建日志目录", "%s\n\n目标位置：%s" % (exc, folder))
            return
        try:
            starter = getattr(os, "startfile", None)
            if starter is None:
                raise OSError("当前系统不支持直接打开文件夹")
            starter(folder)
            self._note("已请求打开日志目录：%s" % folder)
        except Exception as exc:
            self._notify("error", "无法打开日志目录", "%s\n\n请手动打开：%s" % (exc, folder))

    # -- 命令流程 ---------------------------------------------------------

    def on_install(self):
        self._begin_command("install")

    def on_verify(self):
        self._begin_command("verify")

    def on_uninstall(self):
        if self.busy:
            return
        confirmed = self._ask(
            "再次确认卸载",
            "卸载会优先从首次备份还原游戏文件，并移除随包 loader。\n\n"
            "· 只还原备份目录中记录过的文件；\n"
            "· 备份目录本身会保留下来，不会自动删除；\n"
            "· 如果之后还想玩中文，需要重新安装补丁。\n\n"
            "确定要现在还原吗？",
        )
        if not confirmed:
            self._note("已取消卸载操作，未改动任何文件。")
            self._set_status("卸载已取消。")
            return
        self._begin_command("uninstall")

    def _begin_command(self, cmd):
        if self.busy:
            return
        label = CMD_LABEL.get(cmd, cmd)
        data_dir = self.data_dir.get().strip() or None
        self.busy = True
        self._job_log_lines = 0
        self._set_busy(True)
        self._note("")
        self._note("===== 开始：%s =====" % label)
        if data_dir:
            self._note("目标目录：%s" % data_dir)
        else:
            self._note("未指定目录，交由补丁核心自动查找。")
        self._set_status("正在检查现场：%s …" % label)
        self._progress_indeterminate()
        logging.info("开始命令 %s，目录=%r", cmd, data_dir)
        threading.Thread(target=self._precheck_worker, args=(cmd, data_dir), daemon=True).start()

    def _set_busy(self, busy):
        # 核心模块缺失时不允许恢复可点击状态（否则点下去只会报错）
        if not busy and patch_tool is None:
            self._disable_actions()
            return
        for button in self.action_buttons:
            try:
                button.state(["disabled"] if busy else ["!disabled"])
            except tk.TclError:
                pass
        for button in (self.browse_button, self.redetect_button):
            try:
                button.state(["disabled"] if busy else ["!disabled"])
            except tk.TclError:
                pass
        self.logdir_button.state(["!disabled"])

    def _precheck_worker(self, cmd, data_dir):
        try:
            if patch_tool is None:
                self.events.put(
                    (
                        "precheck_failed",
                        cmd,
                        "无法加载补丁核心模块：%s" % (PATCH_TOOL_ERROR or "原因未知"),
                    )
                )
                return
            result = patch_tool.precheck(cmd, data_dir)
            if not isinstance(result, dict):
                result = {"ok": False, "error": "补丁核心返回了非预期的检查结果。", "warnings": []}
            self.events.put(("precheck", cmd, result))
        except Exception:
            self.events.put(
                ("precheck_failed", cmd, "检查阶段出现异常：\n" + traceback.format_exc())
            )

    def _on_precheck_failed(self, cmd, message):
        self._note("检查未通过：%s" % message)
        self._set_status("检查未通过，操作已中止。")
        logging.error("precheck 异常 cmd=%s：%s", cmd, message)
        self._notify("error", "无法继续", "%s\n\n没有改动任何游戏文件。" % message)
        self._finish_command(cmd, 1)

    def _on_precheck(self, cmd, result):
        data_dir = (result.get("data_dir") or "").strip() or self.data_dir.get().strip() or None
        if data_dir:
            self.data_dir.set(data_dir)
            self._note("确认目录：%s" % data_dir)
        state = result.get("state") or {}
        if state:
            self._note(
                "文件概况：应有 %s 个，已汉化 %s 个，备份目录 %s 个%s"
                % (
                    state.get("total", "?"),
                    state.get("installed", "?"),
                    len(state.get("backups") or []),
                    "，疑似 Steam 校验残留" if state.get("residue") else "",
                )
            )
            logging.info("precheck 状态 cmd=%s state=%r", cmd, state)
        warnings = [str(item) for item in (result.get("warnings") or [])]
        for warning in warnings:
            self._note("[提醒] %s" % warning)
        error = str(result.get("error") or "").strip()
        if error or not result.get("ok", False):
            message = error or "检查未通过，为避免损坏游戏文件，操作已中止。"
            self._note("检查未通过：%s" % message)
            self._set_status("检查未通过，操作已中止。")
            self._notify("error", "无法继续", "%s\n\n没有改动任何游戏文件。" % message)
            self._finish_command(cmd, 1)
            return

        assume_yes = True
        if result.get("needs_confirm"):
            body = "检查发现下面的情况，需要你确认：\n\n"
            body += "\n".join("· %s" % item for item in warnings) if warnings else "· （无具体条目）"
            body += "\n\n现在继续「%s」吗？" % CMD_LABEL.get(cmd, cmd)
            assume_yes = self._ask("请确认后继续", body)
            self._note("用户选择：%s" % ("继续" if assume_yes else "放弃"))
            logging.info("用户确认结果 cmd=%s assume_yes=%s", cmd, assume_yes)
        self._set_status("正在执行：%s …" % CMD_LABEL.get(cmd, cmd))
        self._progress_indeterminate()
        threading.Thread(
            target=self._execute_worker, args=(cmd, data_dir, assume_yes), daemon=True
        ).start()

    def _execute_worker(self, cmd, data_dir, assume_yes):
        sink = CoreLogSink(lambda line: self.events.put(("log", line)))
        try:
            result = patch_tool.execute(cmd, data_dir, log=sink, assume_yes=assume_yes)
            sink.flush()
            if not isinstance(result, dict):
                result = {"exit": 1, "error": "补丁核心返回了非预期的执行结果。"}
        except Exception:
            try:
                sink.flush()
            except Exception:
                pass
            result = {"exit": 1, "error": "执行阶段出现异常：\n" + traceback.format_exc()}
        self.events.put(("done", cmd, result))

    def _on_done(self, cmd, result):
        exit_code = result.get("exit", 1)
        if not isinstance(exit_code, int):
            exit_code = 1
        if self._job_log_lines == 0:
            # 兼容核心模块只把输出放进返回值的情况
            for line in result.get("log") or []:
                self._on_core_log(line)
        for key, name in COUNTER_LABELS.get(cmd, ()):
            value = result.get(key)
            if isinstance(value, int):
                self._note("%s：%d 个文件" % (name, value))
        if exit_code == 0:
            message = CMD_DONE.get(cmd, "操作完成。")
            self._note(message)
            self._set_status(message)
            logging.info("命令完成 cmd=%s", cmd)
            self._notify("info", "操作完成", message)
        else:
            reason = str(result.get("error") or "操作没有完成，请查看运行记录。").strip()
            self._note("操作未完成（退出码 %d）：%s" % (exit_code, reason))
            self._set_status("操作未完成（退出码 %d）。" % exit_code)
            logging.error("命令失败 cmd=%s exit=%d reason=%s", cmd, exit_code, reason)
            self._notify(
                "error",
                "操作未完成",
                "%s\n\n部分文件可能已写入，请检查备份和运行记录；如需帮助，请把 installer.log 交给维护者。"
                % reason,
            )
        self._finish_command(cmd, exit_code)

    def _finish_command(self, cmd, exit_code):
        self.busy = False
        self._set_busy(False)
        self._progress_reset()
        self._note("===== 结束：%s（退出码 %d）=====" % (CMD_LABEL.get(cmd, cmd), exit_code))


def run_selftest():
    """无交互冒烟自检。

    构建完整界面 → 200ms 时做内嵌载荷完整性自检（sha256 全量比对 + 载荷漂移判据）
    → 1.5 秒后自动关窗。
    退出码：界面构建成功、载荷 sha256 全对、且磁盘/清单无漂移 = 0；任一失败 = 1
    （供打包后的 `FizRP-ChinesePatch.exe --selftest` 作为机器判据）。
    """
    started = time.time()
    log_path = setup_logging()
    logging.info("自检模式启动：构建界面后将自动关闭")
    try:
        app = InstallerApp(interactive=False, log_path=log_path)
    except Exception:
        detail = traceback.format_exc()
        logging.error("自检失败：界面构建异常\n%s", detail)
        _say("selftest FAILED: 界面构建异常")
        _say(detail)
        return 1

    def _shutdown():
        """关窗兜底：即使 destroy() 出问题也必须结束主循环，绝不让自检挂死。"""
        try:
            app.destroy()
        except Exception:
            logging.exception("自检关窗异常，改用 quit() 强制退出主循环")
            try:
                app.quit()
            except Exception:
                pass

    app._schedule(200, app.selftest_payload_check)
    app._schedule(SELFTEST_MS, _shutdown)
    try:
        app.mainloop()
    except Exception:
        logging.exception("自检中主循环异常")
        _say("selftest FAILED: 主循环异常")
        return 1
    elapsed_ms = int((time.time() - started) * 1000)
    message = app.selftest_message or "载荷自检: 失败（自检未执行）"
    drift = app.drift_message or "载荷漂移: 无法比对（自检未执行）"
    logging.info("%s", message)
    logging.info("%s", drift)
    logging.info("自检结束：界面构建正常，用时 %d ms", elapsed_ms)
    _say("selftest: %s" % message)
    _say("selftest: %s" % drift)
    _say("selftest: 界面构建正常，用时 %d ms" % elapsed_ms)
    _say("selftest 日志文件: %s" % (log_path or "(不可用)"))
    if not app.selftest_ok:
        _say("selftest FAILED: 内嵌载荷自检未通过（哈希或漂移判据）")
        return 1
    _say("selftest OK")
    return 0


def main(argv=None):
    ensure_std_streams()
    args = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in args:
        return run_selftest()

    log_path = setup_logging()
    try:
        app = InstallerApp(interactive=True, log_path=log_path)
    except Exception:
        detail = traceback.format_exc()
        logging.error("界面初始化失败\n%s", detail)
        _say(detail)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(APP_NAME, "界面初始化失败：\n\n%s" % detail)
            root.destroy()
        except Exception:
            pass
        return 1
    try:
        app.mainloop()
    except Exception:
        logging.exception("主循环异常退出")
        _say(traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
