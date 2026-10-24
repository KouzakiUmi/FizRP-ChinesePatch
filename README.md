# Fiz 与彩虹星球 简体中文补丁

《Fiz and the Rainbow Planet》Steam / Windows 版的非营利简体中文补丁，由 **KouzakiUmi（呜咪 / 神前海）**维护。

**当前版本：v1.2.12 · 唯一维护路线：X2（复用 es 槽位）**

[下载与历史版本](https://github.com/KouzakiUmi/FizRP-ChinesePatch/releases) · [技术架构](docs/TECHNICAL.md) · [文本与图片映射](docs/TEXT-MAPPING.md) · [已知限制](docs/release/KNOWN-ISSUES-X2.txt)

## 补丁实际如何工作

- 构建工具把中文写入既有 `es` / `Language.Spanish = 4` 数据，安装器替换对应资源文件；**不是由插件在启动时加载全部译文和图片**。
- 随包 BepInEx / Harmony 插件开放第三项「中文」，处理中文字形、字号与局部像素定位。
- 不改游戏的 `Assembly-CSharp.dll`，也不分发或改写 `level*` 场景文件；会替换部分 `.assets`、两个 bundle 和 catalog。
- 日文、英文的对白/字符串表不被中文覆盖，但**字体与部分图片为语言共享资源**，不能保证日英画面完全不变。非日语图片由 en/es 共用，英文模式也可能显示中文图片。

| 内容 | 当前范围 |
| --- | --- |
| 游戏 | Unity 2021.3.45f1 / Mono，Steam 产品目录名 FizRP |
| 译文主表 | [zh_Hans.csv](translation/zh_Hans.csv)：1,411 行，1,364 条非空；47 行源文为空 |
| 图片回灌 | 13 张纹理；排除 3 张 JP 专用纹理，另保护 4 张共享图集中的 10 个 JP 切片 |
| 载荷 | 117 文件：101 数据 + 16 游戏根 loader/插件文件 |
| 数据构成 | 98 个 `.assets` + es 串表 bundle + shared 图片/键表 bundle + catalog |
| 字体 | Fusion Pixel 8px / 10px，另新增 12px 宿主供两处大字（12px / 24px）渲染 |
| 要求 | EXE 无需 Python；ZIP 安装入口需要 Python 3.8+ |

**已有翻译表写入完整，不等于全部 UI 已翻译。** 一些设置标签、小游戏说明、鉴赏目录和异常提示绕过翻译表，仍可能是日文/英文，详见[覆盖边界](docs/TEXT-MAPPING.md)。

## v1.2.12 更新

- **两处大字改用 12px 设计字体渲染**（在 v1.2.11 的 10px 方案上再进一步）：关卡选择左上角世界名按 12px 1:1 渲染，首次到达新关卡的中央过场标题按 24px（2× 整数倍）渲染。12px 宿主是补丁**新增的 Font 对象**（`FizRP12pxZhHans`，按译表实际用字子集化（1402 字符），241 KB），游戏自带的字体槽位全部保持原样，日英界面不受影响。
- 起因：8px 设计网格里「糖/浆/饼」等密笔画汉字**没有字腔**，整数倍放大只会把实心块放大（v1.2.10 实测）；10px 能画但字腔仍被游戏自研 `PixelOutline` 的固定描边挤压（v1.2.11 实测偏小）；12px 才有足够像素承载密笔画。
- 像素对齐网格按实际宿主与字号计算（1 设计像素 = fontSize/设计尺寸 个 canvas 单位），大字按 2 单位对齐，小字仍按 1 单位。
- 译文沿用 v1.2.9，本次不改文案；保留 13 张中文贴图、10 个 JP 专用切片保护与 117 文件精简载荷。

本版需实机复核两处大字的清晰度与版面容纳情况。离线测试不能替代这些验收。

## v1.2.11 更新

- **两处大字改用 10px 设计字体渲染**（重做 v1.2.10 的方案）：关卡选择左上角世界名按 10px 1:1 渲染，首次到达新关卡的中央过场标题按 20px（2× 整数倍）渲染。**8px 字体不再用于大字**——8px 设计网格里「糖/浆/饼」等密笔画汉字没有字腔，放大后字腔会被填成实心。
- 像素对齐网格按实际宿主与字号计算（1 设计像素 = fontSize/设计尺寸 个 canvas 单位），大字按 2 单位对齐，小字仍按 1 单位。
- 译文沿用 v1.2.9，本次不改文案；保留 v1.2.8 的大标题字号策略、13 张中文贴图与 10 个 JP 专用切片保护、117 文件精简载荷。

本版需实机复核两处大字的清晰度与版面容纳情况。离线测试不能替代这些验收。

## v1.2.10 更新

- v1.2.10 曾尝试用 8px 设计字体做大字整数倍放大，实机复测后**效果更差**（密笔画汉字字腔糊成实心），已在 v1.2.11 改回 10px 设计字体。

## v1.2.9 更新

- 全量审校并重写 **202 条**译文（涵盖剧情对白、受击台词、宝物图鉴、标题说明与教学提示），消除日式「名词＋逗号」省略语义、形式体言/敬语补助动词生硬直译与长定语堆砌，按角色性格与场景上下文还原自然中文语气。
- 修正 `S3_God_4Lea:2` 呼语缺逗号导致的语义反转、露贝尔低体力台词的玩家黑话（`得回血才行` → `得快点恢复才行`）、神明塔翁加台词中混入的孩童化语气词，以及「大叶子」「双生的龙」「列车长」等跨表译名一致性。
- 保留 v1.2.8 的过场大标题字号策略、13 张中文贴图回灌与 10 个 JP 专用切片保护、117 文件精简载荷，以及 v1.2.7 的暂停提示绝对偏移修复。

本版继承 v1.2.8 待实机复核项：中央标题保持大字号、JP 切片显示、新修订译文在各分辨率下的实际排版及旧版升级后的资源还原。离线测试不能替代这些验收。

## 安装、升级与卸载

### 首次安装

1. 关闭游戏，备份个人 MOD。
2. EXE：运行 `FizRP-ChinesePatch.exe`，按图形界面操作；ZIP：完整解压后双击 `install.bat`。
3. 找不到游戏时，选择 `FizAndTheRainbowPlanet_Data` 的上一级游戏目录。
4. 进入语言选择画面，选第三项「中文」。已有中文存档无需重置。

ZIP 的命令行（在解压目录执行）：

```cmd
python patch_tool.py check
python patch_tool.py install --game-dir "<游戏根目录>"
python patch_tool.py verify --game-dir "<游戏根目录>"
python patch_tool.py uninstall --game-dir "<游戏根目录>"
```

### 从 v1.2.7 或更早版本升级

**先使用旧版安装器卸载并还原，再安装本版，不建议直接覆盖。** 本版不再携带 JP bundle 和部分 loader 文档；只复制新载荷不会自动还原旧包曾改写、现已退出清单的文件。保留原来的首次备份和滚动备份，卸载不会删除存档。

### 安全与还原

- 安装前核对版本门禁及完整清单；缺文件、额外文件、大小/哈希错误会阻止写入。`--yes` 只确认现场警告，不跳过载荷完整性检查。
- 数据首次备份至 `_FizRP_original/`，另创建 `_FizRP_backup_<时间戳>/`。首次备份不被后续安装覆盖。
- 卸载优先使用首次备份，缺少时回退滚动备份；保留用户存档、备份及不属于补丁的插件。
- 新存档不存在时才可播种 `Language=4`，默认不覆盖已有存档。不要为本版清理重置进度。
- 安装器不会为已有 loader 冲突额外备份；有其它 MOD 时请先自行备份。Steam 校验文件完整性可作为最后的原版恢复手段。

## 源码与构建

| 目录 / 入口 | 职责 |
| --- | --- |
| [src](src/) | 资源编解码、文本提取、译文检查、数据构建与回读验证 |
| [tools](tools/) | 数据/载荷组装、catalog、安装器与发布打包 |
| [plugin](plugin/) | C# 语言菜单、字体与像素定位插件 |
| [tests](tests/) | 临时目录内的安装、图像范围、字号策略等隔离回归 |
| [translation](translation/) | 主译表与提取工作表 |
| [dist-additive](dist-additive/) | 已生成的数据、安装载荷与权威清单；不是原版输入 |
| [game-reference.json](config/game-reference.json) | 游戏版本门禁基线 |
| [docs](docs/) | 当前架构与覆盖边界；发布记录为历史快照 |

源码维护只保留 X2；旧 `--additive` 是兼容别名，`--replacement` 不受支持。

完整重建需要合法游戏的原版输入、[requirements.txt](requirements.txt)、[requirements-images.txt](requirements-images.txt)、.NET SDK / .NET Framework 4.8 targeting pack，以及打包环境中的 PyInstaller。安装与发布不需要玩家安装这些构建依赖。原版提取与美术输入放在工作区本地，不随源码自动提供。

在仓库根执行，先核实 [C# 项目](plugin/FizRPLangMenu.csproj)中的本地游戏程序集引用路径与离线依赖：

```cmd
python -B -m unittest discover -s tests -v

dotnet build plugin/FizRPLangMenu.csproj -c Release --no-restore
:: 将编译的 DLL 同步到 work/_additive/plugin/FizRPLangMenu.dll
python -B tools/build_additive_data.py
python -B tools/build_additive_payload.py
python -B tools/build_additive_data.py --check
python -B src/verify_patch.py
python -B tools/patch_tool.py check
python -B -m PyInstaller --noconfirm FizRP-ChinesePatch.spec
python -B tools/package_additive.py
python -B tools/package_additive.py --check
```

**顺序不能省略。** 改译文要先构建数据，改插件要重编 DLL，改载荷后要刷新清单再打包；只重建 EXE 不会自动重编插件或注入译文。版本源为 [build_manifest.py](tools/build_manifest.py)，包的实际文件集合以 [manifest-additive.json](dist-additive/manifest-additive.json)为准。

仅修改不进入安装包的文档、且安装包输入及载荷哈希确实不变时，不需要重打包；随包说明变化也属于安装包输入变化。

## 限制与验证口径

- 译文检查和 1,364 条回读只覆盖已登记的数据，不覆盖所有场景硬编码。
- `MILD MODE`、声音/震动等标签有已译表键却未接到对应 Text；音乐鉴赏、剧场及部分小游戏/异常提示没有完整中文路径。
- 共享字体会改变日英字形/缩放；共享的 en/es 图片也没有语言隔离。JP 专用切片恢复不等于英文图片恢复。
- 保留大字号优先保证标题版式，不保证非整数缩放的点阵标题和所有分辨率都同样锐利。
- bundle、布局、内联图标及存档相关条件分支需实机验收，详见[已知问题与实机待验](docs/release/KNOWN-ISSUES-X2.txt)。

## 许可与致谢

本项目与游戏开发者、发行商无关联。游戏由**にじいろドラゴン（虹色龙）**开发、**Forever Entertainment S. A.** 发行；游戏原作、美术、音频、剧情与人物等权利归原权利方。请购买正版，不分发游戏本体。

原创代码、译文与工具采用 [CC BY-NC-SA 4.0](LICENSE)，仅用于非营利分享；游戏素材和第三方组件不因此获得项目许可。中文字体使用 [fusion-pixel-font](https://github.com/TakWolf/fusion-pixel-font)，按 SIL OFL 1.1 分发。完整第三方清单见 [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt)。不得因为精简文档而移除项目、第三方或字体许可。
