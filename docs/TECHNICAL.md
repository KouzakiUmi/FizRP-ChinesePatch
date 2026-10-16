# FizRP 简体中文补丁 — 技术实现文档

> **本文定位**：写给维护者看的**内部实现**参考。三份文档分工如下——
> * `README.md` —— 面向使用者的工作流与命令、当前进展与复核记录；
> * `docs/FINDINGS.md` —— 对游戏本体的**逆向分析**（资源布局、语言枚举、字体清单、覆盖率）；
> * `docs/TECHNICAL.md`（本文）—— **各组件如何工作、格式契约、不变量、校验门槛与已知坑**。
>
> 项目根目录：`D:\FizRP-ChinesePatch`（2026-10-16 自 `C:\Users\Fractal\FizRP-Localization` 迁入）。
> 游戏安装位置：`E:\Steam\steamapps\common\FizRP`。**游戏目录一律只读**——所有写入只发生在
> `work/`、`dist/`、`dist-additive/` 与沙箱目录。

---

## 1. 目标与硬约束

把一款只有日/英/法/西的 Unity 游戏做成**可直接分发给别人**的简体中文补丁。

三条约束按优先级排列，后续所有设计取舍都由它们决定：

| 优先级 | 约束 | 后果 |
| --- | --- | --- |
| 1 | **拷到任何一台装了正版游戏的电脑上都能直接玩** | 排除"依赖本机环境/需要用户自己装一堆东西"的方案；也排除"改 `Assembly-CSharp.dll` 后只在我机器上验证过"的方案 |
| 2 | 不改动游戏原始 DLL 与场景文件 | 因此不新造 `Language` 枚举值、不改 `catalog.json` 的键空间 |
| 3 | 尽量保留原有语言 | 中文**占用一个既有但空置的槽位**，而不是覆盖日/英 |

约束 1 与 2 联手排除了"新增 `zh-Hans` locale"：那需要同时改 DLL 枚举、
重建 Addressables catalog、并放开语言选择界面的 clamp。取而代之的是**槽位复用**。

---

## 2. 游戏画像

| 项 | 值 |
| --- | --- |
| 引擎 | Unity **2021.3.45f1**，**Mono** 后端（`MonoBleedingEdge/`，脚本在 `Managed/*.dll`） |
| 构建名 | `NijiiroDragon` / `FizAndTheRainbowPlanet` |
| Steam app | `FizRP` |
| 资源 | `level*.assets`（场景）+ `sharedassets*.assets` + `resources.assets`；每个 `.assets` 配同名 `.resS` / `.resource` 存流式数据 |
| 现代内容 | **Addressables 1.22.2**：`StreamingAssets/aa/catalog.json` + `StandaloneWindows64/*.bundle` |
| 存档/日志 | `%USERPROFILE%\AppData\LocalLow\NijiiroDragon\FizAndTheRainbowPlanet\`（Easy Save 3 + `Player.log`） |

`Managed/` 里的 DLL 是**还原类型树的关键输入**：`src/unity_env.py` 用
`TypeTreeGeneratorAPI` 从这些 DLL 生成 MonoBehaviour 类型树（见 §5）。

---

## 3. 两条交付路线

同一个仓库同时维护两种形态，二者载荷、安装器、清单都**互相独立**。

| | **X1 替换式** | **X2 追加式** |
| --- | --- | --- |
| 产物 | `dist/FizRP-Chinese-Patch/`（+ `.exe`） | `dist-additive/` |
| 载荷 | `files/`，**103** 个文件（101 `.assets` + 1 es/en 串表 bundle + `catalog.json`），约 67 MB | `payload/`，**122** 个文件（97 数据 + 22 BepInEx loader + 3 其它），约 22.5 MB |
| 清单 | `manifest.json` | `manifest-additive.json`（多 `"mode":"additive"`） |
| 中文槽位 | `en`（`Language.English = 2`） | **`es`（`Language.Spanish = 4`）** |
| 字体 profile | `zh_patch` | `zh_additive` |
| 改英文吗 | 是——界面第二项变成中文，英文不可选（文件里仍保留） | 否——**新增第三项「中文」**，日/英原样 |
| 需要运行库 | 否 | **是**：BepInEx + Harmony + Doorstop（`winhttp.dll`） |
| 改游戏 DLL/场景 | 否 | 否（插件在**运行时**打补丁） |
| 安装器 | `patch_tool.py` / `patch_launcher.py`（GUI） | 同一套安装器加 `--additive` |
| 优点 | 无依赖、最稳、任何环境都能跑 | 体积小 2/3、不牺牲英文、字号 1:1 更锐利 |
| 代价 | 牺牲英文选项；中文按 12px 排 | 依赖 loader；需 BepInEx 兼容性 |

**X2 的中文槽位为什么是 `es`**：`Language` 枚举里 `Spanish = 4` 的本地化数据在该 build
中**几乎全空**（5 张表合计仅 13 行非空，1411 行文本里西语只占 13 行），且语言菜单
原本 clamp 在 `0..1` 根本选不到它——属于事实上的死槽位。X2 把它启用，代价最小。

---

## 4. 文本的三个存储系统

游戏把文本放在**三套互不相干**的系统里，任何只处理一套的方案都会漏掉大半。

| 系统 | 载体 | 数量 | 语言组织 |
| --- | --- | --- | --- |
| Unity Localization | `StringTable` MonoBehaviour，在 Addressables bundle 内 | 5 表 × 4 语言 = **162 键** | 每语言一个 `StringTable_xx` + 共享 `SharedTableData`（在独立 bundle `localization-assets-shared`） |
| 自定义 SO（列表式） | `TextData`(55) / `AutoTalk_Data`(247) | 302 个对象 | 组件内 `List<...Class>`，每项带 `language` 枚举 |
| 自定义 SO（字段式） | `Title_Data`(49) / `DamageTalk_Data`(5) | 54 个对象 | `label` / `label_en` / `label_fr` …；DamageTalk 是**每语言一个资源** |

合计提取出 **1411 行**可翻译文本（`localization` 162 / `AutoTalk` 734 / `DamageTalk` 238 /
`Title` 147 / `TextData` 130）。

**`Language` 枚举**（`work/decompiled/Language.cs`，取自 `Assembly-CSharp.dll`）：

```
Japanese = 0, English_Machine = 1, English = 2, French = 3, Spanish = 4, Max = 5
```

`English_Machine = 1` 是机翻占位槽（数据几乎为空）；`Language.Max` 全项目无人使用。
两套自定义系统的 `language` 字段就是这个枚举的整数值——**因此"写中文"= 往某个整数槽位写**，
不需要任何代码改动，这正是槽位复用方案成立的根本原因。

`FileId`/键映射还有一个易错点：`StringTable` 条目的 `m_Id` 才是键，必须经
`SharedTableData.m_Entries` 反查成 `m_Key` 才能得到稳定 id；而**各 locale 的 `m_Id` 集合并不相同**
（fr/es 是子集），所以提取时按 `m_Id` 并集出行、缺该 locale 就留空。

---

## 5. Unity 序列化字节级契约

**这是整个项目最容易出错的一层，改动前务必先读 `docs/FINDINGS.md` 与本节。**

### 5.1 通用规则（Unity 2021.3 Mono）

```
每个字段都从 4 字节边界开始
bool / UInt8 / char / SInt16 等 1、2 字节字段，读完补齐到 4 字节
string  = align + int32 长度 + UTF-8 字节 + align
List<T> = int32 数量 + N 个元素
MonoBehaviour 头 = PPtr<GameObject>(4+8) + m_Enabled(1+3) + PPtr<MonoScript>(4+8) + m_Name(string)
```
`m_Name` 之后即自定义字段。

### 5.2 UnityPy 1.25.4 的两个必修 bug

1. **生成的类型树缺 `kAlignBytes`(0x4000)。** `TypeTreeGeneratorAPI` 依据 DLL 生成的节点
   没带对齐标志，于是 `m_Enabled` 之后所有字段提前 3 字节读出——`m_Script.m_FileID` 会变成
   `16777216`，`PPtr.deref()` 报 `invalid m_FileID`。修法：递归给
   `UInt8/SInt8/char/bool/UInt16/SInt16` 节点补 flag，**但跳过父节点是 `Array` 的元素节点**
   （否则数组元素被逐个对齐，会毁掉 string 与数组）。
2. **C++ 加速读取器忽略该 flag。** 必须 `TypeTreeHelper.read_typetree_boost = None`。

两处补丁都在 `src/unity_env.py`，由幂等的 `install_patches()` 施加，`patches_installed()` 查询。
**注意这是进程级全局副作用**：import 本模块即改变整个进程的 UnityPy 行为。

### 5.3 为什么不用类型树、改成手写编解码器

补完对齐后仍有类**生成错节点**，且错法各不相同：

* `TextData` 的 `List<string>` 字段被标成 `m_Type="string"`，`read_value` 先命中
  `FUNCTION_READ_MAP["string"]`，永远进不了 vector 分支 → 只读 208/904 字节；
* `DamageTalk_Data` 生成的节点漏了一个列表（枚举里有 `miss_capture` 但类里没有对应字段）；
* `ButtonImageData` 直接让生成器抛 `NullReferenceException`。

因此 5 个游戏自定义类改为**按反编译源码手写字节级编解码器**（`src/custom_types.py`），
用 `(字段名, 类型) 规格表` 描述，`Reader`/`Writer` 共用同一份规格。

**验收方式**：`src/verify_codecs.py` 对全部 **362** 个对象做「解码 → 重编码 → 与原字节比对」，
并要求 362/362 完全一致；同时校验语义不变量（字符串不得含未解码字节、list 长度合理、
`m_FileID` 范围）。

> ⚠️ **字节往返相等不等于语义正确。** 曾经漏了逐字段对齐，`isCheckViewedFlag`(bool) 与
> `talkedFlagKey`(string) 从错误偏移读出，往返却仍然字节一致——因为 0/1 的字节模式
> 恰好能原样写回。这正是后来必须补语义不变量的原因。

### 5.4 写回

* `.assets`：`obj.set_raw_data(header + encode(data)) ` → `sf.save()`。
  **绝不改 `.resS` / `.resource`**：对象 path_id 不变，流式数据引用依然有效。
* bundle：`obj.save_typetree(tt)` → `bundle.save(packer="original")`。
  `packer="original"` 复现原 bundle 的压缩与目录标志（原版 en 串表为
  LZ4HC，`data_flag=0x243 / block_info=0x3`）；用默认 packer 会写成未压缩。

---

## 6. 字体子系统

游戏 17 个字体**全部是动态 `UnityEngine.Font`**，完整 TTF/OTF 就存在 `m_FontData` 里
（`m_CharacterRects` 为空、图集未烘焙），因此**换字体 = 换这段 blob**，无需重建图集。
唯一的例外是 `sharedassets14.assets:43` 的 `k8x12EXS SDF`——那是 TextMeshPro 字体资源、
图集已烘焙，只换源 TTF 不生效；全游戏仅 1 处 `TextMeshProUGUI` 用到它，故不处理。

**逐语言换字体由 `LocFontData` 驱动**：`LocalizedText.cs` 在运行时
`FindIndex(x => x.language == lang)` 后设置 `text.font / fontSize / lineSpacing`，
找不到就回落 `defaultFont`。全游戏共 **6** 个 `LocFontData` 资源。

替换体为 [fusion-pixel-font](https://github.com/TakWolf/fusion-pixel-font)（SIL OFL-1.1），
各变体字形覆盖相同（约 28k–35k 字形，汉字/假名/拉丁齐备），差别只在汉字的**字形偏好**
（`-ja` / `-zh_hans` / `-latin`）。`fonts.config.json` 用三套 profile 表达取舍：

| profile | 用途 | 日文槽位 | 中文槽位 |
| --- | --- | --- | --- |
| `default` | 纯像素化 | `12px-ja` | — |
| `zh_hans` | 中文补丁（简中字形优先） | `12px-zh_hans` | `12px-zh_hans` |
| `zh_patch` | **X1 使用** | `12px-ja`（保留日文字形） | `12px-zh_hans`（en 槽） |
| `zh_additive` | **X2 使用** | 不动 | `k8x12EXS→10px` / `k8x12EXL→8px` |

`zh_additive` 的设计要点：**按宿主原字号选设计尺寸**（EXS 原为 12px 级、EXL 原为大号），
由插件把 `Text` 字号量化到 10 / 8 两档，使中文与设计尺寸 **1:1 锐利**；
代价是日/英模式下 EXS@12 为 1.2×、EXL@12 为 1.5× 非整数缩放。
X1 的已知取舍：`resources.assets:101`（`PerfectDOSVGA437`，被 **100** 处 Text 引用）
实测字号 16(×95)/15/24(×3)/12，而可用设计尺寸只有 8/10/12——非整数放大后像素边缘会软，
但那些 Text 会显示中文，必须保留 CJK 覆盖，故**接受**。

字体提取与普查在 `src/fonts.py`（含自写的 OpenType `name` 表读取）与 `src/font_usage.py`
（递归扫 `Text.m_FontData.m_Font` 统计引用数）；`tools/cmap_check.py` 校验字形覆盖，
其 cmap format-4 解析器的 `idRangeOffset` 偏移曾被写错（把 `了/人/个/日` 误报为缺失），已修。

---

## 7. 构建流水线

### 7.1 X1 替换式

```
src/fonts.py            17 个内嵌字体      -> work/fonts/original/ + work/fonts/info.json
src/extract_text.py     三套文本系统       -> translation/*.csv + work/text_index.json
                                            + work/font_map.json（LocFontData -> 所在文件）
src/make_sheets.py      ja 基准 + en 参考  -> translation/zh_Hans.csv
（人工翻译）
src/build_patch.py      文本 + 字号 + 字体 + StringTable -> dist/FizAndTheRainbowPlanet_Data/
tools/package.py        组装分发目录        -> dist/FizRP-Chinese-Patch/ (+ exe)
```

`src/build_patch.py` 一次遍历同时改四样东西，避免同一文件被多次改写：

1. **自定义 SO 文本**：按 `KIND_TO_CLASS` 把索引里的短名（`AutoTalk`）映射到 C# 类名
   （`AutoTalk_Data`）。**这个映射缺失过两次**，两次都表现为"静默丢弃 1119 行却报成功"。
2. **DamageTalk 补齐**：每语言一个资源且列表长度不同；先按语言解析一次目标文件
   （`damage_file` 映射），再用日文模板补齐目标资源的列表（实例：`padded=12`）。
   注意**只补列表长度不够——那些行在索引的 `others` 里没有目标语言条目，
   会在路由阶段就被丢掉**，两处都要修。
3. **`LocFontData` 字号**：目标槽位 8 → 12（X1）。`LocFontData` 不带文本，
   所以它所在文件由 `work/font_map.json` 发现，**不靠硬编码清单**
   （硬编码曾漏掉 `sharedassets137.assets` 的 `LocFontData_Ending_Role`）。
4. **StringTable 改写**：目标 locale 的 bundle 内逐条改 `m_Localized`；
   若目标语言表**缺某个键**（en UI 表只有 33/34），则追加一条表项——
   与 Unity Localization 运行时行为一致（实例：`added=1`）。bundle 以
   `packer="original"` 保存。

> ⚠️ `catalog.json` **不由 `build_patch.py` 产出**，`tools/package.py` 也不碰它。
> X1 已发布的那份是手工改的，且**不自洽**（见 §12）。X1 要完全可复现必须补上
> `tools/catalog_sync.py` 这一步。

**覆盖率门槛**：`build_patch` 末尾对账 `written == expected`，**缺行默认 `ABORT`**
（`--allow-missing` 可降级为告警）。这是防止"少写了却报成功"的最后一道闸。

### 7.2 X2 追加式

比 X1 多三个环节：

```
tools/build_additive_data.py     work/_additive/staging 的原版资产
                                 -> dist-additive/FizAndTheRainbowPlanet_Data/
                                    （slot=4 / locale=es / profile=zh_additive，
                                      仅替换 k8x12EXL 一个字体 blob）
tools/build_additive_payload.py  上一步产物 -> dist-additive/payload/ + manifest-additive.json
                                 （含调 tools/catalog_sync.py 生成 catalog.json）
tools/patch_tool.py install --additive
```

两个坑写在脚本 docstring 里，值得单独强调：

* **`build_additive_payload.py` 只做组装，不重跑文本注入。** 改了
  `src/build_patch.py` 或 `translation/zh_Hans.csv` 之后**必须先跑 `build_additive_data.py`**，
  否则载荷里还是上一版数据——曾踩过：清单时间戳没变、安装"成功"，文本却没更新。
* **loader 条目必须投放到游戏根目录，不是 `*_Data`。** BepInEx 5 的 Doorstop 代理
  `winhttp.dll` 依赖 Windows DLL 搜索顺序（从 exe 所在目录开始），`*_Data` 不在搜索路径里；
  `doorstop_config.ini`、`.doorstop_version`、`BepInEx/` 也必须同级。因此载荷是**平铺**的，
  由安装器按"相对路径首段"分流：
  ```
  payload/*.assets                -> <游戏根>/FizAndTheRainbowPlanet_Data/*.assets
  payload/StreamingAssets/**      -> <游戏根>/FizAndTheRainbowPlanet_Data/StreamingAssets/**
  payload/winhttp.dll             -> <游戏根>/winhttp.dll
  payload/doorstop_config.ini     -> <游戏根>/doorstop_config.ini
  payload/.doorstop_version       -> <游戏根>/.doorstop_version
  payload/BepInEx/**              -> <游戏根>/BepInEx/**
  ```
  路由常量两侧共用（`ADDITIVE_GAME_ROOT_NAMES` / `ADDITIVE_GAME_ROOT_PREFIXES`），
  并在构建时校验载荷里不存在第三条路由。

### 7.3 运行时插件 `plugin/LangMenuPlugin.cs`

X2 能做到"新增第三项而不改 DLL/场景"，靠的是 BepInEx + Harmony 两处运行时补丁：

1. **`LanguageSetting.Start` 的 Postfix**——激活原场景里已存在但未启用的第三项
   （源码里 `Update()` 的 switch 早就写好了 `case 2 → Language.Spanish`，
   只是 `nowSelectingIndex` 被 clamp 在 `0..1`，且场景里第三个选项没被启用），
   并把它的文本置为「中文」。
2. **`LanguageSetting.Update` 的 Transpiler**——把 clamp 常量 `1` 改成 `2`，
   使光标能选到 index 2，从而由原版逻辑落到 `Language.Spanish`（即中文槽位）。
3. 另有一个 `FontApplierBehaviour`：语言为 Spanish 时把 `Text.font` 换成中文字体。

磁盘上的游戏 DLL 与场景文件**不做任何修改**——这是 X2 体积小又不牺牲英文的关键。

---

## 8. Addressables `catalog.json` 二进制格式

`tools/catalog_sync.py` 把这份格式实测清楚了（不是推测）。替换 bundle 内容后，
必须同步 catalog 里该 bundle 的 `m_BundleSize` 与 `m_Crc`，否则 Addressables 会因
CRC Mismatch 拒绝加载。

```
catalog.json = UTF-8、无 BOM、无结尾换行的紧凑 JSON（separators=(",", ":")）

m_ExtraDataString = base64(.NET BinaryWriter 流)，每个 bundle 一段：
    [153 字节常量类型头][int32 LE = 该段 JSON 的 UTF-16 字节长度][UTF-16LE JSON]
  * 153 字节类型头在 11/11 段上完全一致（程序集名 + 类型名，各带 .NET 7-bit 长度前缀）
  * 段起点用 MARK = '{"m_Hash":' 的 UTF-16LE 编码定位
  * 每段 JSON 是 AssetBundleRequestOptions，12 个键；关键：m_Crc(uint32，可 >2^31)、
    m_BundleSize、m_BundleName、m_UseCrcForCachedBundles
  * json.dumps(obj, separators=(",", ":"), ensure_ascii=False) 与游戏原样序列化逐字相同
    （3 份样本 × 11 段全部验证），脚本每次运行都自检这一点

m_EntryDataString：每条 entry = 7×int32
    (internalIdIdx, providerIdx, dependencyKeyIdx, dependencyHash,
     dataIndex, primaryKeyIdx, resourceTypeIdx)
  * dataIndex >= 0 时指向该 bundle 对应 extra-data 段的**类型头绝对偏移**
    （= json_at - 157），不是段号、也不是 JSON 起点
  * **某段长度变化时，它之后所有段的 dataIndex 必须同步平移** —— 只改帧头不改
    dataIndex 会让 Addressables 从错误位置反序列化
```

**CRC 算法未破解**，脚本不做任何 CRC 计算：回填值一律来自 `--crc`。
占位流程是先 `--crc 0` 让尺寸进 catalog，**实机首跑**后从 `Player.log` 的 `calculated`
行取真实值，再 `--crc <真实值> --write`。**因此"重建并重发"不是纯离线操作，必须配一次实机验证。**

写回采用**外科式替换**：只替换 `"m_EntryDataString":"<b64>"` 与 `"m_ExtraDataString":"<b64>"`
两个字面量（各自必须恰好出现一次，否则中止），其余字节原样保留，因此键序/空白/其它 blob
不可能被改动。任何格式不符一律中止并打印实际字节证据。

---

## 9. 清单与冻结契约

`manifest.json` / `manifest-additive.json` 是**载荷的权威清单**，安装器只依赖它就完成
自检与版本门禁。字段（阶段 F 冻结契约 v1 §4）：

```json
{"name","game","version","built","payload_files","payload_bytes",
 "patch_info":{"reference_hashes":{"globalgamemanagers":sha256,"level0":sha256,"app.info":sha256}},
 "files":[{"path": posix 相对路径, "sha256", "size"}],   // 按 path 排序，稳定可复现
 "mode":"additive"}                                       // 仅追加式
```

* `reference_hashes` 是**版本门禁基线**：安装前逐条比对游戏里这三个未被修改的文件，
  不符则告警并要求用户确认（防止游戏更新后把旧载荷盖上去）。
* 追加式清单的 `patch_info` 复用替换式的 `reference_hashes`（同一游戏 build 的门禁基线），
  `payload_files` 按 additive 载荷重算。
* `tools/build_manifest.py` 只读载荷、只写清单，不触碰 `dist/` 既有内容、不做打包。

## 10. 校验层（五道）

| 层 | 工具 | 断言 |
| --- | --- | --- |
| 1. 字节编解码 | `src/verify_codecs.py` | 362/362 解码↔重编码字节一致 **+ 语义不变量** |
| 2. 构建覆盖率 | `src/build_patch.py` 末尾对账 | `written == expected`，缺行 `ABORT` |
| 3. 产物逐行定位 | `src/verify_patch.py` | 每行译文在**确切位置**读回一致 + 结构不变性（对象表/path_id/class_id/externals） |
| 4. 译文工作表 | `src/check_translation.py` | 离线机械校验（不联网、不调 LLM、不做语义判断）；判定规则写死在文件里 |
| 5. 载荷完整性 | `tools/build_manifest.py` / `--check` / `catalog_sync --verify` | 逐文件 SHA-256、catalog 帧头与 dataIndex 自洽 |

> `verify_patch.py` 曾经只检查"标记子串是否出现在对象 repr 里"——那种实现**不是校验**：
> 值落错下标、槽位写错、238 行里少写 12 行，全都能通过。现在改为逐行定位比对。
>
> `verify_patch.py` 的 `--csv` **默认值是阶段 A 的合成表** `translation/_synthetic.csv`
> （`zh_Hans` 列是 `【译】`+日文原文的占位串）。对正式表校验必须显式传
> `--csv translation/zh_Hans.csv --column zh_Hans`，否则 1364 行全被报成 `wrong`。

## 11. 已知漂移与问题

截至 2026-10-17 的现状复核（详见 `README.md` 同名小节）：

* **产物落后于源码与工作表。** `dist/` 产物是 2026-10-16 05:30 构建的，而
  `translation/zh_Hans.csv`（16:38 空格清理）与 `src/build_patch.py`（18:43 `added` 修复）
  都在其后。对当前产物跑 `verify_patch` 得 **1039/1364、wrong 325**，逐类拆解：
  309 条仅全角空格 U+3000、9 条仅半角空格、6 条角色卡装饰横线、1 条键缺失
  （`localization:UI Table:MovieCanvasCamera_Stage8`，因为产物的 UI 表只有 33 条目，
  `added=1` 分支当时未生效）。**这是工作树漂移，不是校验器误报**——
  用 04:04 的 pre-space-cleanup 快照复验同一份产物得 1363/1，完全吻合。
* **X1 发布的 `catalog.json` 不自洽**：段 `dataIndex` 与段头偏移错位 `-4`，影响
  `seg[08..10]`（fr / ja / es 三个串表段；中文所在的 `seg[07]` 本身 size 正确）。
  `catalog_sync --verify` 判 FAILED；沙箱新生成的判 OK。
* **X1 发布的 en 串表 bundle 是未压缩的**（25,723 字节，原版 9,585 / LZ4HC，沙箱重建 9,654）。
  与 catalog 声明的 `m_BundleSize` 自洽，Addressables 能正常读，只是体积浪费。
* **X1 的可复现性缺口**：7 步流程只产出 102 个文件，第 103 个 `catalog.json` 没有脚本化
  生成步骤（X2 那条路有）。补上需 `catalog_sync.py` + **实机 CRC 回填**。

* **已编译的插件 DLL 内嵌旧绝对路径。** `dist-additive/payload/BepInEx/plugins/FizRPLangMenu.dll`
  由 `plugin/` 在 `C:\Users\Fractal\FizRP-Localization` 时期编译，`.NET` 会把源码路径写进
  程序集（调试信息/`AssemblyInformationalVersion`），因此 `git grep` 能命中旧路径。
  功能无影响，但**发布版应从新位置重新编译**以免泄漏本机路径。

## 12. 未验证项与残余风险

1. **bundle 重打包后 Unity 运行时能否加载——始终没有验证过。** 已证的只是：
   StringTable 写回字节精确、UnityPy 能读回自己写的 bundle、压缩/目录标志与原文件一致、
   `packer="original"` 可复现原压缩。**这是唯一没被覆盖的一环，必须实机确认。**
2. `SerializedFile.save()` 同样只对比了结构（对象表/path_id/class_id/externals 0 差异），
   没经过 Unity 加载器验证。
3. X1 的符号定位：中文按 12px，原本英文 8px。方框容得下 12px（日文本就是 12px），
   但个别写死字号的控件可能溢出。
4. X1 的 `resources.assets:101` 字号失配（§6），已记为接受的风险。
5. **贴图内嵌文字未处理**：`Sprite Table` 的 6 组本地化图片
   （`タイトルロゴ_JPN/_Eng`、`扉サイン_PauseArea_*_En`、`rifatitlemini(_en)`、
   `ひっさつ禁止_0/2`、`SoracoFishingLogo_0/1`）是把文字画进位图的，字符串管线碰不到，
   需走图像编辑 + Alpha/去底色键 + 双底核验 + staging 的流程
   （见 `.dsh/skills/game-image-localization`）。
6. 分发必须保留 `LICENSE-fusion-pixel-font.txt`（SIL OFL-1.1）。

## 13. 踩坑速查

| 症状 | 根因 | 处置 |
| --- | --- | --- |
| `invalid m_FileID` / `m_Script` 值离谱 | 类型树缺 `kAlignBytes` 或 boost 读取器未关 | 确认 `unity_env.install_patches()` 已跑 |
| 某类字段整体错位但往返仍"一致" | 逐字段对齐漏了 | 用 `verify_codecs` 的语义不变量兜底 |
| 译文写不进去却报成功 | 索引短名 vs C# 类名映射缺失 | 用 `KIND_TO_CLASS`；看构建的 coverage 行 |
| 某行永远 missing | 该行在 `others` 里没有目标语言条目 → 未路由 | 修路由，不只修列表长度 |
| `LocFontData` 字号没改 | 硬编码文件清单漏了它所在文件 | 改由 `work/font_map.json` 发现 |
| 改完文本却没生效 | X2 只跑了 payload 组装，没重跑 data | 先 `build_additive_data.py` |
| 安装后 loader 不生效 | `winhttp.dll` 放进了 `*_Data` | 必须在游戏根目录（DLL 搜索顺序） |
| Addressables CRC Mismatch | 换了 bundle 但没同步 catalog | `catalog_sync --write`（CRC 需实机回填） |
| 控制台日文/中文报 GBK 错 | 编码 | `PYTHONIOENCODING=utf-8` |
| 原生 Python 找不到 `/c/...` | MSYS 路径不被原生 Python 理解 | 用相对路径或 `D:/...` |
| 长 heredoc 被截断 | 单次写入过大 | 分段 `cat >>` |
