"""Assemble the distributable patch folder (installers + payload + notices)."""
from __future__ import annotations

import argparse
import os
import shutil

GAME_DATA = os.environ.get("FIZRP_DATA_DIR",
                           r"E:\Steam\steamapps\common\FizRP\FizAndTheRainbowPlanet_Data")

PACKAGE = "dist/FizRP-Chinese-Patch"
PAYLOAD_DIRNAME = "FizAndTheRainbowPlanet_Data"

INSTALL_PS1 = r'''# Fiz And The Rainbow Planet - Simplified Chinese patch installer
param([string]$GamePath = "")

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$payload = Join-Path $here "files"

function Find-GameRoots {
    $roots = @()
    foreach ($reg in @("HKCU:\Software\Valve\Steam", "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam")) {
        try {
            $p = (Get-ItemProperty -Path $reg -ErrorAction Stop).SteamPath
            if ($p) { $roots += $p }
        } catch {}
    }
    $roots += $env:ProgramFiles + "\Steam", ${env:ProgramFiles(x86)} + "\Steam"
    $libraries = @()
    foreach ($r in $roots) {
        if (-not $r) { continue }
        $r = $r -replace "/", "\"
        $libraries += $r
        $vdf = Join-Path $r "steamapps\libraryfolders.vdf"
        if (Test-Path $vdf) {
            foreach ($line in Get-Content $vdf) {
                if ($line -match '"path"\s+"(.+?)"') {
                    $libraries += ($matches[1] -replace "\\\\", "\")
                }
            }
        }
    }
    return $libraries | Sort-Object -Unique
}

function Resolve-DataDir([string]$explicit) {
    if ($explicit) {
        if (Test-Path (Join-Path $explicit "FizAndTheRainbowPlanet_Data")) {
            return (Join-Path $explicit "FizAndTheRainbowPlanet_Data")
        }
        if ((Split-Path -Leaf $explicit) -eq "FizAndTheRainbowPlanet_Data") { return $explicit }
    }
    foreach ($lib in Find-GameRoots) {
        $candidate = Join-Path $lib "steamapps\common\FizRP\FizAndTheRainbowPlanet_Data"
        if (Test-Path (Join-Path $candidate "UnityPlayer.dll")) { return $candidate }
        if (Test-Path (Join-Path $candidate "app.info")) { return $candidate }
    }
    return ""
}

$dataDir = Resolve-DataDir $GamePath
if (-not $dataDir) {
    Write-Host "未能自动找到游戏，请把 FizAndTheRainbowPlanet_Data 文件夹拖到本窗口后回车：" -ForegroundColor Yellow
    $manual = Read-Host
    $manual = $manual.Trim('"', " ", "'")
    $dataDir = Resolve-DataDir $manual
}
if (-not $dataDir -or -not (Test-Path $dataDir)) {
    Write-Host "找不到游戏数据目录，安装中止。" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}

Write-Host "游戏目录: $dataDir" -ForegroundColor Cyan

# ---- version gate: refuse to mix a stale payload into an updated game ----
$infoPath = Join-Path $here "patch-info.json"
if (Test-Path $infoPath) {
    $info = Get-Content $infoPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $bad = @()
    foreach ($prop in $info.reference_hashes.PSObject.Properties) {
        $f = Join-Path $dataDir $prop.Name
        if (-not (Test-Path $f)) { $bad += ($prop.Name + " 缺失"); continue }
        $h = (Get-FileHash -Algorithm SHA256 -Path $f).Hash.ToLower()
        if ($h -ne $prop.Value) { $bad += ($prop.Name + " 哈希不符") }
    }
    if ($bad.Count -gt 0) {
        Write-Host "警告：目标游戏与补丁构建时的版本不一致" -ForegroundColor Red
        $bad | ForEach-Object { Write-Host ("   " + $_) -ForegroundColor Red }
        Write-Host "游戏可能已更新，强行安装可能造成资源错配。" -ForegroundColor Yellow
        $ans = Read-Host "仍要继续吗？(y/N)"
        if ($ans -ne "y" -and $ans -ne "Y") { exit 1 }
    } else {
        Write-Host "游戏版本校验通过。" -ForegroundColor Green
    }
}

$gameRoot = Split-Path -Parent $dataDir
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $gameRoot ("_FizRP_backup_" + $stamp)

$files = Get-ChildItem -Path $payload -Recurse -File
$copied = 0
foreach ($f in $files) {
    $rel = $f.FullName.Substring($payload.Length).TrimStart("\")
    $dst = Join-Path $dataDir $rel
    if (Test-Path $dst) {
        $b = Join-Path $backup $rel
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $b) | Out-Null
        Copy-Item $dst $b -Force
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    Copy-Item $f.FullName $dst -Force
    $copied++
}
Write-Host "已写入 $copied 个文件。" -ForegroundColor Green
Write-Host "原文件备份在: $backup" -ForegroundColor Green
Write-Host "下一次启动游戏时，语言选择画面请选第二项（中文）。" -ForegroundColor Yellow
Read-Host "按回车退出"
'''

UNINSTALL_PS1 = r'''# Restore the newest backup created by the Simplified Chinese patch.
param([string]$GamePath = "")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$payload = Join-Path $here "files"

function Resolve-DataDir([string]$explicit) {
    if ($explicit) {
        if (Test-Path (Join-Path $explicit "FizAndTheRainbowPlanet_Data")) {
            return (Join-Path $explicit "FizAndTheRainbowPlanet_Data")
        }
        if ((Split-Path -Leaf $explicit) -eq "FizAndTheRainbowPlanet_Data") { return $explicit }
    }
    $roots = @()
    foreach ($reg in @("HKCU:\Software\Valve\Steam", "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam")) {
        try { $roots += (Get-ItemProperty -Path $reg -ErrorAction Stop).SteamPath } catch {}
    }
    foreach ($r in $roots) {
        if (-not $r) { continue }
        $c = Join-Path ($r -replace "/", "\") "steamapps\common\FizRP\FizAndTheRainbowPlanet_Data"
        if (Test-Path $c) { return $c }
    }
    return ""
}

$dataDir = Resolve-DataDir $GamePath
if (-not $dataDir) { $dataDir = Read-Host "请把 FizAndTheRainbowPlanet_Data 文件夹拖进来" }
$dataDir = $dataDir.Trim('"', " ", "'")
$gameRoot = Split-Path -Parent $dataDir
$backups = Get-ChildItem -Path $gameRoot -Directory -Filter "_FizRP_backup_*" |
    Sort-Object Name -Descending
if (-not $backups) {
    Write-Host "找不到备份目录，无法还原。" -ForegroundColor Red
    Read-Host "按回车退出"
    exit 1
}
$backup = $backups[0].FullName
Write-Host "从 $backup 还原..." -ForegroundColor Cyan
$n = 0
foreach ($f in (Get-ChildItem -Path $backup -Recurse -File)) {
    $rel = $f.FullName.Substring($backup.Length).TrimStart("\")
    Copy-Item $f.FullName (Join-Path $dataDir $rel) -Force
    $n++
}
Write-Host "已还原 $n 个文件。" -ForegroundColor Green
Read-Host "按回车退出"
'''

BAT_TEMPLATE = """@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\{script}"
"""

README = """Fiz And The Rainbow Planet —— 简体中文补丁
================================================

【这个补丁做了什么】
  1. 把游戏里全部 1411 条文本（剧情对话、菜单、UI、结局字幕、战斗台词）
     写入到游戏自带的某一个语言槽位中，因此不需要改动引擎、不需要
     Addressables 目录、也不需要 mod 加载器。
  2. 字体整体替换为 TakWolf/fusion-pixel-font 的 12px/8px 比例像素字体，
     并对中文槽位使用简体字形（fusion-pixel-12px-proportional-zh_hans）。
     游戏原英文字体只有 205 个字形（纯 ASCII），根本画不出汉字，
     所以字体替换是必需的，不是可选项。

【怎么装】
  双击  install.bat
  脚本会自动在 Steam 库中查找游戏；找不到时会把游戏目录提示给你手动指定。
  安装前会把所有被覆盖的原文件备份到 游戏根目录\_FizRP_backup_<时间戳>\ 。

【怎么卸载】
  双击  uninstall.bat  —— 它会找最新的备份并把文件还原回去。

【装完之后】
  游戏只在「第一次启动、还没有存档」时显示语言选择画面，
  所以：
    * 新存档：启动后在语言画面选第二项（中文）。
    * 已有存档：删除游戏存档里的语言设置，或直接删除存档重来，
      也可以把存档中的 Language 值设为 2（英文槽位 = 本补丁的中文槽位）。
      存档位置： %USERPROFILE%\AppData\LocalLow\<公司名>\<产品名>\

【备份 / 安全】
  - 补丁只覆盖游戏数据目录下的文件，不动存档、不动 Steam 校验之外的东西。
  - 想彻底还原：删除游戏目录后让 Steam「验证游戏文件完整性」即可。

【授权】
  替换字体来自 https://github.com/TakWolf/fusion-pixel-font
  以 SIL Open Font License 1.1 发布，全文见 LICENSE-fusion-pixel-font.txt 。
  游戏原始资源版权归原作者所有；本补丁仅包含为本地化而必须修改的游戏文件。

【已知限制】
  - TextMeshPro 的 k8x12EXS SDF 字体资源图集已烘焙，未替换；游戏里只有
    1 处 TextMeshProUGUI 用到它。
  - 中文字号按游戏日语同款 12px，原本英文用 8px；极少数写死字号的地方
    文字可能比原来略大。
"""


def build(payload_src: str, out: str = PACKAGE, name: str = PAYLOAD_DIRNAME):
    files_dir = os.path.join(out, "files")
    if os.path.isdir(files_dir):
        shutil.rmtree(files_dir)
    os.makedirs(files_dir, exist_ok=True)
    count = 0
    for root, _dirs, names in os.walk(payload_src):
        for n in names:
            src = os.path.join(root, n)
            rel = os.path.relpath(src, payload_src)
            dst = os.path.join(files_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            count += 1

    tools = os.path.join(out, "tools")
    os.makedirs(tools, exist_ok=True)
    for fname, body in (("install.ps1", INSTALL_PS1), ("uninstall.ps1", UNINSTALL_PS1)):
        with open(os.path.join(tools, fname), "w", encoding="utf-8-sig") as fh:
            fh.write(body)
    for bat, script in (("install.bat", "install.ps1"), ("uninstall.bat", "uninstall.ps1")):
        with open(os.path.join(out, bat), "w", encoding="ascii", newline="\r\n") as fh:
            fh.write(BAT_TEMPLATE.format(script=script))
    with open(os.path.join(out, "README.txt"), "w", encoding="utf-8-sig") as fh:
        fh.write(README)
    import hashlib
    import json as _json
    refs = {}
    for name in ("globalgamemanagers", "level0", "app.info"):
        src = os.path.join(GAME_DATA, name)
        if os.path.exists(src):
            with open(src, "rb") as fh:
                refs[name] = hashlib.sha256(fh.read()).hexdigest()
    with open(os.path.join(out, "patch-info.json"), "w", encoding="utf-8") as fh:
        _json.dump({"payload_files": count, "reference_hashes": refs},
                   fh, ensure_ascii=False, indent=1)

    lic = "dist/fonts/source/OFL.txt"
    if os.path.exists(lic):
        shutil.copy2(lic, os.path.join(out, "LICENSE-fusion-pixel-font.txt"))
    return count


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", default="dist/" + PAYLOAD_DIRNAME)
    ap.add_argument("--out", default=PACKAGE)
    a = ap.parse_args()
    n = build(a.payload, a.out)
    print(f"package: {a.out}  ({n} payload files)")
