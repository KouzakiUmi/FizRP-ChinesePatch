# X2 技术架构与维护契约

当前维护版本：v1.2.10。面向维护者；使用与升级见 [README](../README.md)，数据覆盖见 [TEXT-MAPPING](TEXT-MAPPING.md)，待验与已知漏项见 [KNOWN-ISSUES](release/KNOWN-ISSUES-X2.txt)。历史发布记录描述当时版本，不是当前实现规范。

## 1. 架构边界

游戏为 Unity 2021.3.45f1 / Mono。中文复用 `Language.Spanish=4`、locale `es`，不新增枚举或 locale，不修改游戏 DLL，不分发 `level*` 场景。

```text
原版 staging + 译表 + 字体配置 + 美术 PNG
  → build_additive_data：改 SO/es 串表/共享字体/图片，生成数据目录
  → build_additive_payload：组装 loader/插件，同步 catalog，生成 manifest
  → PyInstaller / package_additive：EXE 与 ZIP
  → patch_tool：验证、备份、复制、卸载还原

运行时 BepInEx 插件：第三语言选项 + 字体/字号 + 局部像素定位
```

内容在构建时写入资源，并非由插件在游戏启动时统一注入。en/ja 文本槽不被中文写入，但共享图片和字体仍可能影响其它语言，不能把“复用 es”解释成“资源完全隔离”。

## 2. 组件与唯一真源

| 组件 | 真源与职责 |
| --- | --- |
| 提取 | [extract_text.py](../src/extract_text.py)：生成工作表与本地索引；其自定义文件列表是显式清单，不是任意新版本的自动全量发现 |
| 译文 | [zh_Hans.csv](../translation/zh_Hans.csv)，1,411 行、1,364 非空；不是所有场景文案的全集 |
| 编解码 | [custom_types.py](../src/custom_types.py)：TextData、AutoTalk_Data、Title_Data、DamageTalk_Data、LocFontData |
| Unity 环境 | [unity_env.py](../src/unity_env.py)：游戏根/类型树及对齐兼容；import 会安装进程级补丁 |
| 数据写入 | [build_patch.py](../src/build_patch.py)：四类文案、LocFontData、字体 blob、es StringTable |
| 图片范围 | [image_patch_policy.py](../tools/image_patch_policy.py)：整图排除及 JP Sprite 名单；不依工单编号或资源名是否含日文猜语言 |
| 图片回灌 | [build_image_patch.py](../tools/build_image_patch.py)：合成受保护图像、写回、逐像素回读；不安装、不改 catalog |
| 数据流水线 | [build_additive_data.py](../tools/build_additive_data.py)：原版副本→文本→图片→合并修改文件→同步 catalog |
| 载荷流水线 | [build_additive_payload.py](../tools/build_additive_payload.py)：数据、运行时 DLL、插件、catalog 与计数/路由门槛 |
| 版本与清单 | [build_manifest.py](../tools/build_manifest.py)，独立基线 [game-reference.json](../config/game-reference.json) |
| 安装核心 | [patch_tool.py](../tools/patch_tool.py)，[GUI](../tools/patch_launcher.py)委托同一公共 API |
| 分发 | [package_additive.py](../tools/package_additive.py)、[PyInstaller spec](../FizRP-ChinesePatch.spec) |

原版 staging、Managed DLL、提取索引、原版 PNG、美术 PNG、字体和 loader 输入为本地构建输入，不随仓库自动提供。不要把已安装补丁的目录当原版输入。

## 3. 文本写入契约

- 主表 ID 与索引定位必须一致，禁止仅凭显示文本子串验证写入。
- `TextData`：写 `textDatas[language==4].strings[index]`，缺块时新建。
- `AutoTalk_Data`：写 `locTalkDatas[language==4].talkDatas[index].text`；沿用 ja 的结构，保持说话人、表情、事件和等待字段。
- `Title_Data`：写 `label_es`、`info_es`、`infoDisable_es`。
- `DamageTalk_Data`：每语言一个资源，仅改 es 资源；目标列表按日文模板补长，不能因 es 原本缺下标丢行。
- `StringTable`：通过 SharedTableData 的 ID/键映射写 `m_Localized`，目标缺键则追加；不是把其它 locale 的数组位置当键。
- `TreasureText_default` 原版多一个重复 ja 块，构建移除重复块以对齐宝物表索引；这是数据修正，不是新增翻译。
- 默认覆盖门槛为 `written == expected`；`verify_patch` 按文件、对象、语言、字段/下标回读。1,364 条通过只证明已登记行写对，不证明硬编码 UI 全覆盖。

### 序列化安全

MonoBehaviour 头、字符串长度、列表和字段对齐以编解码规格为准，不应泛化为“所有字段都固定四字节对齐”。小整数/布尔字段存在对齐标志，数组元素另有语义。

UnityPy 1.25.4 的生成树在本游戏存在小字段对齐与部分类型节点问题；环境兼容层补齐 `kAlignBytes`、关闭相应 boost 读取路径，自定义类走手写编解码。修改规格必须执行 [verify_codecs.py](../src/verify_codecs.py) 的字节往返与语义不变量检查。字节往返相等不等于语义正确。

对象 ID、class ID、external 表必须保持；`.resS` 不作为本补丁分发目标。替换 Texture2D 将像素内联并清空其旧流引用，其余对象不应跟随重写。

## 4. 字体、字号与像素定位

[字体配置](../fonts.config.json)只替换两个共享 Font 的 blob：

| 宿主 | blob 设计尺寸 |
| --- | --- |
| sharedassets0.assets:14 / k8x12EXS | Fusion Pixel 10px zh-Hans |
| sharedassets3.assets:133 / k8x12EXL | Fusion Pixel 8px zh-Hans |

6 个 LocFontData 的 es 槽按默认 8/12 档位镜像字体引用；**序列化 size=12 不等于字体设计尺寸=12**。最终普通中文字号由插件改为 8/10。

[运行时插件](../plugin/LangMenuPlugin.cs)由 Harmony 属性补丁、渲染前修正及扫描共同处理：

- 中文语言下，含 CJK 的 Text 才换中文宿主；纯拉丁通常保持原字体，不承担翻译文案职责。
- [FontSizePolicy](../plugin/FontSizePolicy.cs)：普通字号不大于 8→8，9～12→10，超过 12→保留；过场标题原字号 24，不应套入普通小字号档。
- 基准字号记录该实例见过的最大值，用于抵抗游戏后续小字号写入。主菜单、InfoText 和版权等既有强制 10px 范围仍由原策略决定。
- [TitleMenuFontPolicy](../plugin/TitleMenuFontPolicy.cs)：TitleCanvas 中文使用 10px，补足不足的文本框高度，不改变宽度/位置。
- [PauseHintPixelPolicy](../plugin/PauseHintPixelPolicy.cs)：仅三条挂载到 Canvas 的中文暂停提示，按绝对横向偏移纠正，不移动未激活模板，不累加继承偏移。
- TMP 有独立接管路径；当前唯一 TMP 初始串为纯拉丁 NPC TALK，不能误写成“没有 TMP 支持”或“该文本已翻译”。
- [LargeTitlePixelPolicy](../plugin/LargeTitlePixelPolicy.cs)：仅两处大字——关卡选择世界名（go=StageName）与中央过场标题（`<size=16>第N关</size>`）——换 8px 设计宿主并把字号吸附到 8 的整数倍（24=3×8、16=2×8、14→16）。非整数倍放大（如 24px@10 设计 = 2.4×）会在光栅内部产生灰阶发虚，位置对齐救不了，只有整数倍放大能消除；对齐网格仍是整数 canvas 单位（1 texel = 1 canvas 单位，与设计尺寸无关）。范围严格受限：对白内 `<size=24>` 富文本、教学板 75px 等不适用。

共享 Font 替换对引用该对象的其它语言也有效；原字号/设计尺寸可能产生非整数缩放。大标题保留字号不意味着点阵字在所有缩放下锐利。

## 5. 图片范围与 JP 保护

历史美术集 16 张，正式回灌 13 张：

- 排除 IMG-06（JP 关卡横幅）、IMG-15（JP 主标题）、IMG-16（JP 小游戏标题）。JP 图片 bundle 不再进入中文载荷。
- IMG-03/04/05/08 是共享图集，不能整张删除。回灌时按实际 Sprite 的 textureRect 定位，恢复其中 10 个 JP 专用切片。
- 保护矩形从 Unity 左下角坐标转换为 PNG 左上角坐标，向外包围浮点矩形，越界/缺失/重复 Sprite 都中止。
- 原版片区从原版提取 PNG 直接复制 RGBA，**不用 alpha mask 混合**，以保留透明像素；PNG 尺寸必须匹配。
- 其余区域沿用批准的中文 PNG。原始美术输入不被改写；序列化后与合成后的期望图逐像素比对，格式/过滤方式保持，非目标对象字节保持。

参数 `--images` 指定美术 PNG，`--original-images` 指定原版 PNG。默认均为工作区本地输入，构建前需核对它们来自适配版本。

es/en 的六个 Sprite Table 条目目前相同。恢复 JP 片区不会隔离英文模式；真正的独立中文图像层是另一项架构变更，本版未实现。

## 6. 当前载荷与目录路由

**117 个载荷文件**，以[权威清单](../dist-additive/manifest-additive.json)为准：

| 投放目标 | 文件 |
| --- | --- |
| Data：101 | 98 `.assets` + es 字符串 bundle + shared 图片/键表 bundle + catalog |
| 游戏根：16 | winhttp.dll、doorstop_config.ini、.doorstop_version + BepInEx/core 12 个 DLL + 插件 DLL |

loader 原始输入仍可包含完整 SDK 文档；组装时排除 changelog 和 core XML API 文档，**不裁剪运行时 DLL**。项目、第三方、字体许可保留于发布包根目录。路由常量保留历史 changelog 兼容识别，不代表本版仍分发它。

安装器以源码、ZIP、冻结环境分别定位本包资源，不靠当前工作目录。数据与 loader 的路由边界由相对路径首段决定，不能把 winhttp.dll 放进 Data。

ZIP 为 117 个载荷 + 9 个清单/安装/说明/许可文件。EXE 固定数据为清单与 5 个说明/许可文件，再按清单动态收集 117 个载荷；此外带 Python/Tk 运行依赖，不能按所有归档条目数判断游戏载荷数量。

## 7. catalog 与完整性

修改 bundle 后同步其实际大小与 CRC 策略，不能只同步 es 串表而漏掉 shared。退出载荷的 JP bundle 不应继续沿用修改后的 catalog 记录。

[catalog_sync.py](../tools/catalog_sync.py)对 catalog 的两个二进制字符串字段定点更新。当前格式包括：extra-data 段、长度前缀、七个 int32 的 entry，以及指向类型头的绝对 dataIndex。段长变化必须同步后续偏移；脚本做格式往返与引用检查。

构建对已修改 bundle 使用 `--crc 0`，意图是禁用对应 CRC 校验，不是声称已离线算出真实 CRC。离线自洽/回读不等于 Unity 运行时加载验收。

清单约束包括模式、版本、文件路径唯一性、相对路径合法性、大小、哈希和三项游戏版本门禁。门禁来自独立配置，不从已安装补丁文件重新采样。安装器发现载荷缺失/多余/损坏即禁止写入，`--yes` 不跳过此检查。

## 8. 安装与升级

首次数据备份与滚动备份由安装核心维护；已有存档不覆盖，新存档可播种中文语言。loader 冲突需玩家自行备份，安装器不承诺对其它 MOD 自动回滚。

**从 v1.2.7 及更早升级时先用旧版卸载，再安装本版。** 本版退出清单的 JP bundle/文档不会在覆盖安装时被自动还原。不能因为新包不再带这些文件，就宣称旧安装现场已清理。勿删除玩家首次备份或存档。

## 9. 构建、验证与发布顺序

1. 固定原版 staging、译表、字体/原版图片/美术 PNG、loader、C# 引用程序集与依赖环境。
2. 修改插件则离线编译 DLL，再同步到载荷组装入口；构建脚本不会自动重编插件。
3. 数据构建（默认含图片）→ 数据检查/文本回读/编解码检查。
4. 载荷组装 → 全 bundle catalog 同步 → 清单。
5. EXE / ZIP → 清单与包内容哈希核验 → 发布说明及校验和。
6. 包内容变化才发布新安装包；仅不入包文档变化、输入与产物哈希不变时只更新文档。随包说明也属于包内容。

命令与依赖准备见 [README 构建章节](../README.md#源码与构建)。不要在未核对目标路径时清空构建输出；旧版本 Release 不覆盖，保留可回退版本。

| 验证 | 能证明什么 |
| --- | --- |
| check_translation | 占位符、标签、换行、空译等机械规则；不替代语义审校 |
| verify_codecs | 362 个自定义对象的字节往返及语义不变量 |
| verify_patch | 1,364 条已登记译文在目标位置读回 |
| 图像回灌报告 | 13 纹理期望图一致、10 JP 区域保护、非目标对象不变 |
| patch_tool check / package --check | 本包文件、哈希、内嵌清单和安装入口一致 |
| 标准库隔离回归 | 在临时游戏/存档内检查安装器、字号及图像范围策略 |
| 实机复测 | 首次过场标题、图像切片、各分辨率和条件界面的实际表现 |

## 10. 已知覆盖边界

2026-10-23 全量复核扫描 159 场景和 161 个序列化资源文件，发现 1,824 Text、1 TMP、730 字符串事件、40 图片事件。自定义对象和 StringTable 的登记行未发现遗漏，但场景硬编码仍存在。

温和模式、震动、五个声音标签属于“有译文无绑定”；小游戏标题提示、52 条音乐鉴赏元数据、9 条剧场目录、启动异常提示有旁路。未使用静态表键、隐藏模板、测试场景、被脚本覆写的初始日文不能一律当漏译或多余资源删除。详见 [TEXT-MAPPING](TEXT-MAPPING.md)。
