# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 规格：Fiz 与彩虹星球 简体中文补丁 安装器（onefile / windowed）。

在项目根执行：

    pyinstaller --noconfirm --clean FizRP-ChinesePatch.spec

产出 ``dist/FizRP-ChinesePatch.exe``（onefile）。datas 生成规则（契约 §4）：

  1. 5 个固定条目：``manifest.json``、``patch-info.json``、``README.txt``、
     ``KNOWN-ISSUES.txt``、``LICENSE-fusion-pixel-font.txt`` —— 全部落在 exe 根。
     其中后三者取自 ``dist/FizRP-Chinese-Patch/``，落到 ``.``（根）。
  2. 每个载荷文件一条：源 ``dist/FizRP-Chinese-Patch/files/<rel>``，
     目标 ``payload/<posix dirname(rel)>``（``dirname`` 为空时即 ``payload``）。

共 ``5 + N`` 条（N = 载荷文件数；2026-10-16 CRC 修复后 N=103 → 108 条）。
载荷条目**不手写**：优先读 ``manifest.json``（权威清单、顺序稳定），缺失时才回退遍历载荷目录。
期望条目数同样**动态**计算，避免载荷增减后闸门误报（历史上曾硬编码 107）。
"""

import json as _json
import os as _os
import posixpath as _ppath

# 规格目录：PyInstaller 注入 SPECPATH（spec 文件所在目录），独立 exec（如自检脚本）
# 时未定义，则退回当前工作目录 —— 两种情况都指向项目根。
try:
    _ROOT = _os.path.abspath(SPECPATH)  # noqa: F821  (PyInstaller 注入)
except NameError:
    _ROOT = _os.getcwd()

_MANIFEST = _os.path.join(_ROOT, 'manifest.json')
_PAYLOAD_SRC = _os.path.join('dist', 'FizRP-Chinese-Patch', 'files')
_PAYLOAD_SRC_ABS = _os.path.join(_ROOT, _PAYLOAD_SRC)
_PACKAGE = _os.path.join('dist', 'FizRP-Chinese-Patch')


def _payload_rel_paths():
    """载荷相对路径（posix），按 manifest.json 顺序；无清单则遍历目录后排序。"""
    if _os.path.isfile(_MANIFEST):
        with open(_MANIFEST, encoding='utf-8') as _fh:
            _data = _json.load(_fh)
        _paths = [_entry['path'] for _entry in _data['files']]
        if _paths:
            return _paths
    _found = []
    for _dirpath, _dirnames, _filenames in _os.walk(_PAYLOAD_SRC_ABS):
        _dirnames.sort()
        for _filename in sorted(_filenames):
            _abs = _os.path.join(_dirpath, _filename)
            _rel = _os.path.relpath(_abs, _PAYLOAD_SRC_ABS)
            _found.append(_rel.replace(_os.sep, '/'))
    _found.sort()
    return _found


# 5 个固定条目（顺序即契约 §4 顺序）
_datas = [
    ('manifest.json', '.'),
    ('dist/FizRP-Chinese-Patch/patch-info.json', '.'),
    ('dist/FizRP-Chinese-Patch/README.txt', '.'),
    ('dist/FizRP-Chinese-Patch/KNOWN-ISSUES.txt', '.'),
    ('dist/FizRP-Chinese-Patch/LICENSE-fusion-pixel-font.txt', '.'),
]

# N 条载荷条目，逐条校验源文件存在（缺失即中止，宁可失败也不产出缺载荷的 exe）
_PAYLOAD_RELS = _payload_rel_paths()
_MISSING = []
for _rel in _PAYLOAD_RELS:
    _rel = _rel.replace('\\', '/')
    _src = _PAYLOAD_SRC + '/' + _rel
    _subdir = _ppath.dirname(_rel)
    _dst = 'payload' if not _subdir else 'payload/' + _subdir
    _datas.append((_src, _dst))
    if not _os.path.isfile(_os.path.join(_ROOT, _src)):
        _MISSING.append(_src)

if _MISSING:
    raise SystemExit(
        'ERROR: 载荷源文件缺失 %d 个，拒绝构建（例：%s）'
        % (len(_MISSING), ', '.join(_MISSING[:3])))
_EXPECTED = 5 + len(_PAYLOAD_RELS)
if len(_datas) != _EXPECTED:
    raise SystemExit(
        'ERROR: datas 条目数 %d != 期望 %d（5 固定 + %d 载荷），拒绝构建'
        % (len(_datas), _EXPECTED, len(_PAYLOAD_RELS)))


a = Analysis(
    ['tools/patch_launcher.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FizRP-ChinesePatch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # 本机未安装 UPX，且载荷为已压缩资源，UPX 收益低、易误报
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
