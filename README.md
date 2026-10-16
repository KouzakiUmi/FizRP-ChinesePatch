# FizRP 简体中文补丁工具链

**Fiz And The Rainbow Planet**（Unity 2021.3.45f1 / Mono，Steam app `FizRP`）的
解包、文本提取、翻译回写、像素字体替换与**可直接分发的中文补丁构建**。

替换字体：[TakWolf/fusion-pixel-font](https://github.com/TakWolf/fusion-pixel-font)（SIL OFL 1.1）。

---

## 最终产物形态（已定型）

**纯文件替换补丁**，不依赖任何运行库 / mod 加载器 / 重新打包的 Addressables 目录。

原因：新增语言需要同时改 `Assembly-CSharp.dll` 的 `Language` 枚举、重建
`catalog.json`（BinaryStorageBuffer 格式）、并放开语言选择界面的 clamp。
为了让补丁"拷到任何一台装了正版游戏的电脑上都能直接玩"，改为把简体中文
写入**游戏自带的一个语言槽位**——所有 bundle 名、Addressables 地址、
locale 代码、`Language` 枚举值全部保持不变，因此运行时不需要任何代码改动。

| 层 | 槽位 | 机制 |
| --- | --- | --- |
| Unity Localization（162 条 UI/菜单/结局字幕） | `en` | 直接改写 `localization-string-tables-english(en)` bundle 内的 StringTable 值 |
| `TextData` / `AutoTalk_Data` / `Title_Data` | `Language.English` = 2 | 写入 `textDatas` / `locTalkDatas` / `label_en` 等 |
| `DamageTalk_Data` | `DamageTalkData_en` 资源 | 该资源本身就是"英文版本"，直接改写 |
| `LocFontData` | slot 2 | 原字号 8 → 12 |
| `UnityEngine.Font` | `sharedassets2.assets:18`（原 `Yoshi5x8_v2.1`，仅 205 个字形） | 换成 `fusion-pixel-12px-proportional-zh_hans` |

日文槽位保留 `-ja` 字形，原文不受影响；玩家在首次启动的语言画面选第二项即进入中文。

```bash
python tools/fetch_fonts.py                 # 1. 下载 fusion-pixel-font（若未下载）
python src/fonts.py work/fonts/original work/fonts/info.json   # 2. 提取 17 个内嵌字体
python src/extract_text.py                  # 3. 提取全部文本
python src/make_sheets.py                   # 4. 生成翻译工作表（日语基准 + 英语参考）
#   ... 翻译 translation/zh_Hans.csv 的 zh_Hans 列 ...
python src/build_patch.py --profile zh_patch --translations translation/zh_Hans.csv \
       --out dist/FizAndTheRainbowPlanet_Data   # 5. 构建补丁
python src/verify_patch.py dist/FizAndTheRainbowPlanet_Data \
       --csv translation/zh_Hans.csv --column zh_Hans   # 6. 逐层校验
python tools/package.py                     # 7. 生成 dist/FizRP-Chinese-Patch/ 安装包
```

> 第 6 步必须显式传 `--csv translation/zh_Hans.csv --column zh_Hans`：
> `verify_patch.py` 的 `--csv` 默认值是阶段 A 的合成表 `translation/_synthetic.csv`
> （其 `zh_Hans` 列是 `【译】` + 日文原文的占位串，与主表 1364 行全部不同），
> 按默认值执行会把 1364 行全部报成 `wrong`。

安装包结构：`files/`（102 个游戏文件：101 个 `.assets` + 1 个 StringTable bundle）+ `install.bat` / `uninstall.bat`
（自动在 Steam 库中定位游戏、备份被覆盖的原文件、可一键还原）。

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
  build_patch.py     构建补丁（文本 + LocFontData + 字体 + StringTable bundle）
  verify_patch.py    校验构建产物每一层
  font_patch.py      独立的纯字体替换（配置文件驱动）
  loc_common.py      语言表 / bundle 名等常量
tools/
  fetch_fonts.py     下载并解包 fusion-pixel-font
  cmap_check.py      检查字体对汉字/假名/标点的覆盖
  package.py         组装分发目录（含 CDDL 安装脚本）
  install.py         开发期直接安装到本机游戏（带备份）
  trace_object.py    单对象字段级解码追踪（排错用）
translation/         翻译工作表（UTF-8 BOM，Excel 可直接打开）
work/                中间产物
dist/                分发包
fonts.config.json    字体替换映射表（三套 profile：default / zh_hans / zh_patch）
```

## 文本工作表

- `translation/zh_Hans.csv` —— **翻译用**：`id, kind, source, path, comment, ja_source, en_reference, zh_Hans`
- `translation/ALL.csv` —— 机器回写用，列名沿用游戏自带 `TextExporter.cs` 的命名

日语是原文（游戏即以日语撰写），英语完成度约 88%，法语/西语各只有 29/13 行，
因此**以日语为基准、英语作参考**。

## 已知限制

- TextMeshPro 的 `k8x12EXS SDF` 图集已烘焙，未替换（游戏内仅 1 处 `TextMeshProUGUI`）。
- 中文按日语同款 12px 排版；原本英文是 8px，极少数写死字号处文字会略大。
- 补丁占用英文槽位，英文内容在文件里仍然完整保留，但界面上不可选。

---

## 审查与修复记录

首轮代码审查（自查；`subagent_codex` 后端在本会话持续 product-error，4/4 失败，而
Codex 额度健康剩余 81% —— 即技能所说的"额度健康与推理成功是不同事实"）。

| 级别 | 问题 | 状态 |
| --- | --- | --- |
| P1 | `tools/install.py` 不递归，静默漏装 `StreamingAssets/` 下的 StringTable bundle（实测列出 100 文件、提及子目录 0 次） | 已修：改 `os.walk` |
| P1 | `src/apply_text.py` 用索引短名（`AutoTalk`）比对 C# 类名（`AutoTalk_Data`），1119/1249 行被静默丢弃却仍报成功 | 已修：删除双份实现，改为委托 `build_patch.build()` |
| P1 | 构建无覆盖率断言，缺行不会失败 | 已修：默认缺行即 `ABORT`（`--allow-missing` 可降级） |
| P1 | 12 行 DamageTalk 永远写不进去：这些行在 `others` 里没有 `en` 条目，**根本没被路由到目标文件**；且英文资源列表比日文短 | 已修：按语言解析一次目标文件 + 用日文模板补齐列表（本次 `padded=12`） |
| P1 | 英文 UI 表缺 1 个键（33/34），`localization:UI Table:MovieCanvasCamera_Stage8` 无处可写 | 已修：缺键时追加表项（与 Unity Localization 运行时行为一致，`added=1`） |
| P2 | `sharedassets137.assets` 的第 6 个 `LocFontData_Ending_Role` 从未被处理（不在 `CUSTOM_FILES`），字号停在 8 而字体已是 12px 设计 | 已修：补入提取清单；`build_patch` 改为从 `work/font_map.json` 发现 LocFontData 所在文件，不再靠硬编码 |
| P2 | `verify_patch` 只搜"标记子串是否出现"，值落错位置也通过 | 已修：重写为逐行定位比对 + 结构不变性检查 |
| P2 | `resources.assets:101`（`PerfectDOSVGA437`，100 处 Text）实测字号为 16(×95)/15/24(×3)/12，而替换体是 12px 设计 | **接受的风险**：这 100 处会显示中文，必须保留 CJK 覆盖；已记入下文限制 |
| P3 | `unity_env` 导入即改 UnityPy 全局状态 | 已修：抽出幂等的 `install_patches()` / `patches_installed()`，并在 docstring 说明 import 副作用 |
| P3 | `verify_codecs` 只证字节、不证语义 | 已修：补不变量（字符串不得含未解码字节、list 长度合理、`m_FileID` 范围） |
| P3 | 安装器不校验游戏版本 | 已修：包内 `patch-info.json` 记录未改动文件的 SHA-256，安装前比对，不符则告警并要求确认 |

修复后的实测结果：

```
verify_codecs : 362/362 对象「解码→重编码」字节一致 + 语义不变量通过
build_patch   : coverage expected=1364 written=1364 missing=0 unknown_ids=0
                text=1202  padded=12  locfont=5  fonts=9  tables=5 entries=162(added=1)
verify_patch  : expected 1364 / verified 1364 / wrong 0 / structural problems 0
sandbox 安装  : 版本匹配→写入 102 文件；版本不符→告警并中止
```
