# Fiz 与彩虹星球 简体中文补丁

**《Fiz and the Rainbow Planet》的非营利性中文汉化补丁，面向 PC（Steam）版。**

![Status](https://img.shields.io/badge/Status-Stable-success?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Windows-blue?style=flat-square)
![Engine](https://img.shields.io/badge/Engine-Unity%202021.3-blueviolet?style=flat-square)
![Version](https://img.shields.io/badge/Version-v1.2.7-blue?style=flat-square)
![Patch](https://img.shields.io/badge/Patch-X2%20Additive-orange?style=flat-square)
![License](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey?style=flat-square)

> **By KouzakiUmi（呜咪 / 神前海）**

---

**项目说明**：本补丁覆盖全文对白、界面文本、16 张汉化贴图与像素字体，仅维护 **X2 追加式**，不提供替换式分支：
中文写入游戏自带的 `es`（`Language.Spanish = 4`）槽位，日文/英文原样保留，语言菜单新增第三项「中文」。
不修改游戏 DLL 与场景文件；文本、字体和贴图由随包 BepInEx 插件在运行时加载。安装前自动备份，卸载可还原。

| 项目 | 说明 |
| --- | --- |
| 适用游戏 | Steam《Fiz and the Rainbow Planet》（产品代号 `FizRP`） |
| 游戏引擎 | Unity 2021.3.45f1 / Mono（PC / Steam） |
| 补丁路线 | **X2 追加式**：中文进 `es` 槽，日/英原样保留 |
| 补丁规模 | 125 个载荷文件（102 个数据文件 + 23 个 loader）；1,364 条非空译文；16 张汉化贴图 |
| 当前版本 | **v1.2.7**：修复暂停菜单按键提示在启动、重选中文或返回标题后偶发模糊的问题 |
| 运行要求 | 图形安装器无需 Python；zip 版命令行需要 Python 3.8+ |
| 字体 | [fusion-pixel-font](https://github.com/TakWolf/fusion-pixel-font)（SIL OFL 1.1） |

### v1.2.7 更新（2026-10-22）

- **暂停提示清晰度修复**：修复第三页等暂停菜单按键提示有时清晰、有时模糊，重选中文或重新进入关卡后表现变化的问题。
- **避免重复补偿**：不再移动未激活、未挂载 Canvas 的提示模板；实际实例采用绝对横向偏移，避免继承模板偏移后再次累加。
- **限定影响范围**：仅处理三条暂停菜单中文按键提示，不改字体、字号或纵坐标，其他 UI 保持原处理。
- **回归与实测**：37 项隔离回归通过；用户复测直接进入、重选中文和反复进入菜单后提示清晰，日志中 3 个重建实例均未再累积偏移。未逐项覆盖全部分辨率与屏幕模式。
- 译文、双档字体和 16 张汉化贴图保持 v1.2.6；正式包不包含临时诊断插件。

### v1.2.6 更新（2026-10-20）

- **遗留补修**：在 v1.2.5 基础上补修 9 处——`S6_Plain_Battle_win:1` 的说话人标注、`あばばばばば` 的拟声用字、7 处「感叹词＋句子」的停顿。
- **说明**：说话人标注属工作表元数据，不改变游戏行为；游戏内 `chara` 字段本身标为旁白。
- 译文仍为 1,364 条非空；插件、字体与贴图沿用 v1.2.5。

### v1.2.5 更新（2026-10-20）

- **译文修订**：修订 62 条对白、菜单说明与拟声词，重点修正场景语气、施动/施受关系、日式句式直译；仍为 1,364 条非空译文。
- **场景修正**：库玛展示水阵、车长送站、莉芙坠落等场景的说话人与动作主体按上下文校正。
- **语病清理**：「只能…才能」「也许…也说不定」「要好好做好」等叠用与语义重复已修正。
- **体例统一**：菜单说明改为统一句式；受击拟声统一采用「呜」系。
- **三轮交叉复核**：GLM-5.3-Flash、MiMo-V2.6-Flash 独立复核，GPT-6.1 Sol 终审通过。

### v1.2.4 更新（2026-10-18）

- **冷启动显示修复**：修复画面设置等主菜单中文标签首次启动时不显示、重选中文才出现的问题。
- **菜单字号统一**：仅 `TitleCanvas` 内中文菜单使用 10px，并为文字补足高度，避免被原 8px 高文本框裁切；对白、游戏内 HUD 和纯英文文本不套用此规则。
- **无需改存档**：已正确保存 `Language=4` 的玩家不必重置或改写存档。
- **回归与实测**：新增 10 项菜单策略/接入回归，与 X2 安装回归合计 27 项；用户已实机确认本次显示问题恢复正常。

### v1.2.3 更新（2026-10-18）

- **译文修订**：相较 v1.2.2 修正 86 条对白、菜单说明、拟声词与结局署名；仍为 1,364 条非空译文。
- **仅维护 X2**：统一构建、安装与打包路径；游戏版本门禁使用独立入库基线，不再依赖本机归档。
- **安装逻辑修复**：修正 GUI 预检查模式和 zip 资源定位；写入前强制核对清单与全部载荷，缺失或损坏时中止。
- **回归与发布校验**：增加 17 项标准库隔离回归；zip 校验同时核对安装入口、内嵌清单与随包说明，防止旧代码混入。
- **存档安全**：新存档采用独占创建，避免检查与写入之间出现新存档时被覆盖。
- **载荷字节保真**：禁用发布资源的 Git 换行转换，确保入库内容与清单哈希一致。

### v1.2.2 更新（2026-10-18）

- **项目许可证补入**：采用 CC BY-NC-SA 4.0，新增 [LICENSE](LICENSE)，并随 zip/exe 分发；新增 [第三方组件声明](THIRD-PARTY-NOTICES.txt)。
- **安装器提示修正**：安装完成提示由“第二项”改为实际的**第三项（中文）**；卸载提示改为“还原到安装前状态”。
- **安装包内容修正**：exe 内 README / KNOWN-ISSUES / LICENSE 落点改到根目录；zip 内增加项目 LICENSE 与第三方声明。
- v1.2.1 的标题图、文本与字体修复保持不变。

### v1.2.1 更新（2026-10-18）

- **主标题图重制**：采用「菲兹与 / 彩虹之星」新设计，替换 IMG-01；保留底部英文 `Fiz and the Rainbow Planet`。
- **标题译名统一**：由「菲兹与彩虹星」改为「**菲兹与彩虹之星**」。
- **字体接管修复**：修正语言界面/标题版权行的字号基准与版权行字体接管；作者名、公司名改为「日文原文（中文译名）」。
- **构建包优化**：安装/卸载脚本改为 ASCII 名 `install.bat` / `uninstall.bat`；zip 固定时间戳可复现；PyInstaller 排除未使用模块。
- 新增 [文本系统与映射文档](docs/TEXT-MAPPING.md)。

### v1.2.0 回顾（2026-10-17）

- X2 追加式首个正式版本：中文写入 `es` 槽，语言菜单新增第三项；
- 125 个载荷文件、双档像素字体（10/8px）与 16 张汉化贴图；
- 配套图形安装器与 Python 版 zip 包。

---

## 📥 安装 / 卸载 / 检查

Windows 玩家直接运行发布包中的 `FizRP-ChinesePatch.exe`，无需安装 Python。安装器包含完整补丁数据，可安装、卸载、检查与验证。

zip 版需要 Python 3.8+，双击 `install.bat` / `uninstall.bat` 即可；也可使用包内根目录的命令行：

```cmd
python patch_tool.py detect
python patch_tool.py install  [--game-dir PATH] [--yes]
python patch_tool.py verify   [--game-dir PATH]
python patch_tool.py uninstall [--game-dir PATH] [--yes]
python patch_tool.py check
```

> 源码仓库中对应路径是 `tools\patch_tool.py`；发布 zip 根目录已包含 `patch_tool.py`。

| 命令 | 作用 |
| --- | --- |
| `detect` | 定位游戏根目录（也可用 `--game-dir` 手动指定） |
| `install` | 备份将被覆盖的文件，写入补丁与 loader |
| `verify` | 逐文件核对安装结果与清单 |
| `check` | 检查载荷完整性（不写游戏目录） |
| `uninstall` | 从备份还原被覆盖文件，移除新增 loader |

> 💡 首次启动游戏时，语言选择画面请选**第三项「中文」**。
> 已有存档且界面仍为日/英时，可把存档中的 `Language` 设为 `4`（`es` 槽位）；
> 安装器只在存档不存在时播种语言，不会覆盖已有存档。
> 安装/卸载前请关闭游戏；卸载会保留备份目录，不会删除用户存档。

---

## 🎮 安装与还原机制

1. **定位游戏**：自动扫描 Steam 库中的游戏目录；找不到时提示手动指定游戏根目录（`FizAndTheRainbowPlanet_Data` 的上一级）。
2. **完整性与备份**：先验证 X2 清单及全部载荷的 SHA-256；缺失、损坏或多余文件一律中止，`--yes` 也不绕过。被覆盖的原文件复制到游戏根目录 `_FizRP_backup_<时间戳>/`，随后写入补丁。
3. **运行时加载**：BepInEx + Harmony 插件在中文语言下启用第三项，替换文本、字体与贴图；不修改游戏 DLL/场景文件。
4. **卸载还原**：优先从 `_FizRP_original/` 首次备份逐字节还原；缺少时回退最新滚动备份。移除随包 loader，保留备份和其它用户插件。
5. **存档安全**：补丁不删除、不改写用户存档（语言值设置除外，且默认不覆盖已有存档）。

> 💡 兜底方案：Steam → 游戏属性 → 已安装文件 → 验证游戏文件完整性。

---

## 🧩 补丁内容

| 内容 | 说明 |
| --- | --- |
| `payload/` | 125 文件：98 个 `.assets` + 3 个串表 bundle + `catalog.json` + 23 个 loader |
| 文本 | 1,411 条记录、1,364 条非空译文；对白、界面、结局、小游戏、战斗台词 |
| 字体 | `k8x12EXS → fusion-pixel-10px`、`k8x12EXL → fusion-pixel-8px`，中文 1:1 |
| 图片 | 16 张汉化/重制贴图：标题 Logo、舞台开始 UI、钓鱼 Logo、角色卡装饰、宝物/血条等 |
| 插件 | `BepInEx/plugins/FizRPLangMenu.dll`：启用第三项「中文」、字体/字号接管 |

---

## 📁 目录结构

```
dist/                 发布物（exe、X2 zip；本机生成，不入库）
dist-additive/        X2 载荷与权威清单（发布源）
config/               独立游戏版本门禁基线（不依赖本机归档）
src/                  解包、文本提取、X2 构建与校验
tests/                标准库隔离回归（不操作真实游戏）
tools/                构建/打包/安装核心与图形安装器
plugin/               BepInEx + Harmony 插件源码
translation/          翻译主表与工作表
docs/                 技术文档、发布说明、文本映射
work/                 本地原版资产与中间产物（不入库）
```

更细的模块说明见 [docs/TECHNICAL.md](docs/TECHNICAL.md) 与 [docs/TEXT-MAPPING.md](docs/TEXT-MAPPING.md)。

---

## 🛠️ 技术细节

### 译文如何生效

X2 把中文写入游戏的 `es`（`Language.Spanish = 4`）本地化槽位，`StringTable`、`Title_Data`、
`TextData`、`AutoTalk_Data`、`DamageTalk_Data` 与场景文本分别按各自载体写入。语言菜单的第三项由
`plugin/LangMenuPlugin.cs` 在运行时启用；游戏 DLL 与场景文件保持原样。

### 字体为什么分两档

中文使用 fusion-pixel 的 10px / 8px 两档设计尺寸，插件按原宿主字号把中文文本量化到对应档位，
避免点阵字被非整数缩放放大后发虚。主菜单及设置子页中文固定使用 10px，并同步补足文本框高度；对白/HUD 仍沿用原有量化规则。日/英模式保留原字号，可能出现 1.2× / 1.5× 非整数缩放。

### 校验机制

| 层 | 工具 | 断言 |
| --- | --- | --- |
| 字节编解码 | `src/verify_codecs.py` | 362/362 往返一致 |
| 翻译机械校验 | `src/check_translation.py` | 占位符/标签/换行/长度规则，errors=0 |
| 构建覆盖率 | `src/build_patch.py` | `written == expected`，缺行中止 |
| 产物逐行定位 | `src/verify_patch.py` | 每行译文在确切位置读回一致 |
| 载荷完整性 | `tools/build_manifest.py` / `package_additive.py --check` | 逐文件 SHA-256、125/125 |
| 安装器 | `patch_tool.py check` / `exe --selftest` | 载荷自检与漂移检查，125/125 |

---

## 📘 术语与体例

| 原文 | 译法 | 说明 |
| --- | --- | --- |
| フィズ | 菲兹 | 主角，全篇统一 |
| キューマ | 库玛 | 水中最快的龙 |
| リーファー | 莉芙 | 毛茸茸的小龙 |
| ルーベル | 露贝尔 | 操纵丝线的大姐姐 |
| リュトロン | 琉特隆 | 火焰小龙 |
| ソラコ | 索拉科 | 好奇心旺盛的小龙 |
| オーブ | 宝珠 | 贯穿主线的收集物 |
| にじいろのほし | 彩虹之星 | 游戏标题中的星球名；标题图与文本统一 |
| 作者/公司名 | 日文原文（中文译名） | 结局鸣谢与版权行保留原文并附译名 |

体例：以日语原文为准，英语仅作参考；对白保持可爱、温和的日系奇幻语气；专有名词全篇统一；
中文标点全角；菜单项句式同构，不加多余句末句号。

---

## ⚙️ 构建与发布（维护者）

zip 安装入口需要 Python 3.8+；完整重建需满足图像依赖的 Python 3.11+ 要求（本机使用 3.12）。重建插件还需要 .NET SDK 和 .NET Framework 4.8 目标包。发布顺序固定：

```cmd
:: 0) 安装/打包逻辑回归：只使用临时游戏与存档
python -B -m unittest discover -s tests -v

:: 1) 文本 + 字体 + 贴图注入（slot=4 / locale=es / profile=zh_additive）
python tools\build_additive_data.py

:: 2) 组装载荷 + 生成 manifest-additive.json + 同步 catalog
python tools\build_additive_payload.py

:: 3) 重建图形安装器
pyinstaller --noconfirm --clean FizRP-ChinesePatch.spec

:: 4) 生成发布目录 + zip + sha256
python tools\package_additive.py --force

:: 5) 校验
python tools\patch_tool.py check
python tools\package_additive.py --check
dist\FizRP-ChinesePatch.exe --selftest
```

> **顺序不能颠倒**：改了 `translation/zh_Hans.csv` 或 `src/build_patch.py` 后，必须先跑
> `build_additive_data.py`，再跑 `build_additive_payload.py`，否则载荷仍是上一版数据。
> `tools/build_manifest.py` 默认生成 X2 清单，版本门禁来自入库的 `config/game-reference.json`；不再读取本机历史归档。
> 构建前需准备原版 `work/_additive/staging/` 与 `dist/fonts/source/OFL.txt`（本地输入，不入库）。
> 修改插件源码后，还须先重编 DLL 并同步到 `work/_additive/plugin/FizRPLangMenu.dll`，再组装载荷；只重建数据或 exe 不会自动编译插件。

`tools/install.py` / `tools/package.py` 只是 X2 的快捷入口，不维护第二套实现。`--replacement` 已移除；旧 X2 脚本的 `--additive` 仅作为无行为差异的兼容别名。

版本号在 `tools/build_manifest.py`；发布时更新 README/发布说明的 `{{VERSION}}` 源，推送 `v*` tag 并创建 GitHub Release。发布资产包含 exe、zip、sha256 与 release notes。

---

## ⚠️ 已知限制与实机待验

- **依赖随包 loader**：X2 需要 `winhttp.dll` + `BepInEx/`，不安装 loader 不会生效；
- **部分设置界面标签未接本地化**：`MILD MODE`、声音标签（`MASTER/BGM/SE/ENV/VOICE`）、`VIBRATION` 等是场景硬编码，当前仍显示英文/原文；
- **TextMeshPro**：全游戏唯一的 `NPC TALK` TMP 组件为纯拉丁文本，未替换字体；
- **双档字体**：日/英模式下原字号与 10/8px 设计尺寸存在非整数缩放，可能发虚；
- **贴图与 bundle 运行时**：16 张图片和重打包 bundle 已完成离线校验，最终排版/加载仍需实机目视确认；
- 逐项实机待验清单见 [docs/release/KNOWN-ISSUES-X2.txt](docs/release/KNOWN-ISSUES-X2.txt)（10 项，均为证据不足项）。

---

## ⚠️ 版权与许可

- **原作者**：《Fiz and the Rainbow Planet》由 **にじいろドラゴン（虹色龙）** 开发、**Forever Entertainment S. A.** 发行；游戏原作、美术、音频、剧情与人物等权利均归原权利方所有。
- **素材声明**：本补丁包含基于游戏原版资源制作的译文、改版贴图与工具逻辑，不含游戏本体；请先自行购买并安装正版游戏。
- **非营利**：仅限非营利目的使用与分享，严禁商业用途。
- **项目许可证**：本补丁的代码、原创译文与工具以 **[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)** 授权，全文见 [LICENSE](LICENSE)。游戏原作、美术、音频、剧情与人物等仍归原权利方，不在此许可范围内。
- **非官方同人声明**：本项目与游戏开发者/发行商无关联；如权利方提出异议，将停止分发。译文与改版贴图属于对原作的演绎物，仍受原权利方约束。
- **第三方组件**：随包 BepInEx、Doorstop、Harmony、MonoMod、Mono.Cecil 按各自许可证分发；清单与上游链接见 [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt)，项目 CC 许可不覆盖它们。
- **许可证范围**：CC BY-NC-SA 4.0 用于本非营利同人项目的代码、原创译文与工具，不额外附加许可条件。如将代码用于其他软件项目，欢迎告知作者；CC 协议不提供专利许可或源码/目标码保证。
- **字体**：中文界面使用 fusion-pixel-font，以 **SIL OFL 1.1** 随补丁分发；分发时必须保留
  `LICENSE-fusion-pixel-font.txt`（zip 与 exe 内均已包含）。

---

## 🔗 相关文档

- [docs/TECHNICAL.md](docs/TECHNICAL.md) —— 实现细节、格式契约与构建坑
- [docs/TEXT-MAPPING.md](docs/TEXT-MAPPING.md) —— 六套文本系统、语言/字体槽位与映射表
- [docs/FINDINGS.md](docs/FINDINGS.md) —— 游戏本体逆向分析
- [docs/release/](docs/release/) —— 发布说明与实机待验清单源
- [GitHub Releases](../../releases) —— 历史版本与下载
