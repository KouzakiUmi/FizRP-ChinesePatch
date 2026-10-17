# FizRP 简体中文补丁工具链

**Fiz And The Rainbow Planet**（Unity 2021.3.45f1 / Mono，Steam app `FizRP`）的
解包、文本提取、翻译回写、像素字体/贴图替换与**可直接分发的中文补丁构建**。

> **当前安装包路线：X2 追加式**——中文写入游戏自带的 `es`（`Language.Spanish = 4`）槽位，
> 日文/英文原样保留，靠随包的 BepInEx 插件在运行时启用「第三项：中文」。
> X1 替换式已归档到 [`dist/legacy/X1/`](dist/legacy/X1/)，不再作为安装包主线维护。

替换字体：[TakWolf/fusion-pixel-font](https://github.com/TakWolf/fusion-pixel-font)（SIL OFL 1.1）。

---

## 三份文档的分工

- 本文（[README.md](README.md)）—— 当前产物、构建/发布流程、目录与限制；
- [docs/FINDINGS.md](docs/FINDINGS.md) —— 对游戏本体的逆向分析；
- [docs/TECHNICAL.md](docs/TECHNICAL.md) —— 内部实现、格式契约、校验门槛与坑（动代码前先读）。

发布说明的源文件在 [`docs/release/`](docs/release/)（`README-X2.txt` /
`KNOWN-ISSUES-X2.txt`，`{{VERSION}}` 由打包脚本替换）。

## 当前产物

| 产物 | 说明 |
| --- | --- |
| `dist/FizRP-ChinesePatch.exe` | 图形安装器（onefile；内嵌 125 个追加式载荷 + `manifest-additive.json` + 说明/授权） |
| `dist/FizRP-X2-v1.2.0.zip` | Python 版安装包（`payload/` + `patch_tool.py` + 说明 + 授权 + 安装/卸载.bat） |
| `dist-additive/payload/` | 载荷（发布源） |
| `dist-additive/manifest-additive.json` | 载荷权威清单（版本 1.2.0，125 文件） |
| `dist-additive/FizAndTheRainbowPlanet_Data/` | `build_additive_data.py` 的构建中间产物（不是直接分发物） |
| `dist/legacy/X1/` | X1 替换式归档（106 文件、版本 1.1.0、语言画面第二项） |

载荷构成（125）：**102 个数据文件**（98 个 `.assets` + 3 个串表 bundle + `catalog.json`）
+ **23 个 loader**（`winhttp.dll`、`doorstop_config.ini`、`.doorstop_version`、
`changelog.txt` + `BepInEx/` 19 个）。

关键设计：

- 中文槽位 `es`（`Language.Spanish = 4`），语言画面选**第三项「中文」**；
- 字体双档：`k8x12EXS → fusion-pixel-10px`、`k8x12EXL → fusion-pixel-8px`，
  中文与 10/8px 设计尺寸 1:1；
- 不修改游戏 DLL/场景，运行时由 `plugin/LangMenuPlugin.cs` 打完 Harmony 补丁；
- 16 张汉化贴图（v2.4，已集成）。

## 构建与发布流程

```bash
# 0) 原版资产（一次性）：work/_additive/staging/FizAndTheRainbowPlanet_Data
# 1) 文本 + 字体 + 贴图注入（slot=4 / locale=es / profile=zh_additive）
#    默认还会把 v2.4 的 16 张贴图回灌进数据目录，并同步 catalog。
python tools/build_additive_data.py

# 2) 组装载荷 + 生成 manifest-additive.json + 同步 catalog
python tools/build_additive_payload.py

# 3) 重建图形安装器（内嵌 additive-payload/）
python -m PyInstaller --noconfirm --clean FizRP-ChinesePatch.spec

# 4) 生成 Python 版发布目录 + zip + sha256
python tools/package_additive.py

# 5) 校验
python tools/patch_tool.py check            # 载荷自检（源码态自动走追加式）
python tools/package_additive.py --check    # zip 与清单逐文件哈希
python tools/catalog_sync.py dist-additive/payload/StreamingAssets/aa/catalog.json --verify
./dist/FizRP-ChinesePatch.exe --selftest    # 期望 125/125
```

> **顺序不能颠倒**：改了 `src/build_patch.py` 或 `translation/zh_Hans.csv` 之后必须先跑
> `build_additive_data.py`，再跑 `build_additive_payload.py`；否则载荷里还是上一版数据。

X1 历史路线（已归档）的构建方法见 [`dist/legacy/X1/README.md`](dist/legacy/X1/README.md)。

## 目录

```
src/
  unity_env.py       UnityPy 环境封装 + 两处关键 bug 修复（见 docs/FINDINGS.md）
  unity_raw.py       序列化字节最小 raw 解析器
  custom_types.py    5 个自定义 ScriptableObject 的字节级编解码器（362/362 往返校验）
  verify_codecs.py   回归测试：全部对象 解码→重编码→原字节比对
  fonts.py           字体提取 + OpenType name 表解析
  font_usage.py      统计每个 Font 资源被哪些 Text 组件引用
  extract_text.py    三套文本系统 -> translation/*.csv + work/text_index.json
  make_sheets.py     生成翻译工作表（ja 基准 / en 参考）
  build_patch.py     构建补丁（文本 + 字号 + 字体 + StringTable；X1/X2 共用）
  verify_patch.py    校验构建产物每一层
  font_patch.py      独立的纯字体替换（配置文件驱动）
  apply_text.py      文本-only 薄封装（委托 build_patch.build）
  loc_common.py      语言表 / bundle 名等常量
tools/
  fetch_fonts.py            下载并解包 fusion-pixel-font
  cmap_check.py             检查字体对汉字/假名/标点的覆盖
  package.py                X1 发布目录组装（已归档到 dist/legacy/X1/）
  install.py                开发期直接安装（X1 归档目录）
  build_additive_data.py    X2 原版资产 -> dist-additive/FizAndTheRainbowPlanet_Data/
  build_additive_payload.py X2 组装 payload/ + manifest-additive.json + catalog
  build_manifest.py         从载荷重生成清单（替换式 / --additive）
  catalog_sync.py           Addressables catalog 的 m_BundleSize/m_Crc/dataIndex 同步
  patch_tool.py             无头安装核心（替换式 / --additive）
  patch_launcher.py         图形安装器（GUI）
  package_additive.py       X2 发布目录 + zip + sha256
  build_image_patch.py      贴图回灌（默认 work/image_tickets_opt/deliverables-opt）
  validate_image_deliverables.py  贴图离线校验
  compose_image_tickets.py  v1 工单合成器；仍被 v2.4 build.py 用作 IMG-11 生成字形来源
  image_tickets/
    build.py                v2.4 交付构建（字体/贴图/渲染日志）
    package.py              v2.4 QA 包（PNG/日志/字体）
    validate.py             逐像素校验（字体来源、保护像素、黑白底合成）
    render_text.py          像素字渲染器（1 位 alpha + 描边）
    test_render_text.py     渲染器单元测试
  trace_object.py           单对象字段级解码追踪（排错用）
plugin/
  LangMenuPlugin.cs   BepInEx + Harmony 运行时插件（启用第三项「中文」）
  FizRPLangMenu.csproj
translation/          翻译工作表（UTF-8 BOM，Excel 可直接打开）
docs/                技术文档与发布说明源
dist/                发布物（exe、X2 zip、字体源、legacy X1 归档）
dist-additive/       X2 载荷与清单（发布源）
work/                中间产物
  _additive/staging/     原版资产（构建输入）
  _additive/bepinex/     BepInEx loader 源
  _additive/plugin/      插件 DLL 源
  fonts/ text_index.json font_map.json decompiled/ _crc/  构建输入
  image_tickets/ image_tickets_opt/  贴图工单与交付
fonts.config.json    字体替换映射（四套 profile：default / zh_hans / zh_patch / zh_additive）
```

`work/` 不进入版本控制；历史实验产物已在 2026-10-17 整理中删除，只保留上表列出的构建输入。

## 文本与工作表

- [translation/zh_Hans.csv](translation/zh_Hans.csv) —— **翻译主表**：
  `id, kind, source, path, comment, ja_source, en_reference, zh_Hans`；
- [translation/ALL.csv](translation/ALL.csv) —— 机器回写用，列名沿用游戏 `TextExporter.cs`；
- [translation/_synthetic.csv](translation/_synthetic.csv) —— 阶段 A 合成表，仅作
  `verify_patch.py` 的默认测试基线（**不要**拿它校验正式构建；会 1364 行全报 wrong）。

日语是原文，英语完成度约 88%；**以日语为基准、英语作参考**。

## 校验与自检

| 层 | 工具 | 断言 |
| --- | --- | --- |
| 字节编解码 | `src/verify_codecs.py` | 362/362 往返一致 + 语义不变量 |
| 构建覆盖率 | `src/build_patch.py` | `written == expected`，缺行 ABORT |
| 产物逐行定位 | `src/verify_patch.py` | 每行译文在确切位置读回一致 |
| 译文机械校验 | `src/check_translation.py` | 离线规则检查（不联网/不调 LLM） |
| 载荷完整性 | `tools/build_manifest.py` / `package_additive.py --check` / `catalog_sync --verify` | 逐文件 SHA-256、catalog 帧头与 dataIndex |
| 安装器 | `patch_tool.py check` / `exe --selftest` | 125/125 载荷自检与漂移检查 |

## 已知限制

- **依赖 loader**：X2 需要随包的 BepInEx（`winhttp.dll` 等），不装 loader 不会生效；
- 字体双档让日/英模式出现 1.2×/1.5× 非整数缩放（取舍见 TECHNICAL §6）；
- 16 张贴图只完成离线逐像素校验，实机显示仍有待核对；
- bundle 重打包后 Unity 运行时能否加载、`SerializedFile.save()` 的语义，仍缺实机证据；
- TextMeshPro 的 `k8x12EXS SDF` 图集已烘焙，未替换（仅 1 处 TextMeshProUGUI）；
- 分发必须保留 `LICENSE-fusion-pixel-font.txt`（SIL OFL-1.1）。

逐项实机待验清单见 [docs/release/KNOWN-ISSUES-X2.txt](docs/release/KNOWN-ISSUES-X2.txt)。

## 历史记录（X1 时期，已归档）

2026-10-16 的 X1 替换式曾经历「产物落后于源码/工作表」的漂移（325 处差异：309 条全角空格、
9 条半角空格、6 条角色卡横线、1 个缺键），随后按当前源码/工作表重打包并归档；
catalog 不自洽与 en 未压缩的问题也在重打包时修正。完整过程与重建命令见
[`dist/legacy/X1/README.md`](dist/legacy/X1/README.md)。
