# 逆向分析报告 — Fiz And The Rainbow Planet

* 引擎：Unity **2021.3.45f1**，Mono 后端（`MonoBleedingEdge`，脚本在 `Managed/*.dll`）
* 构建名：`NijiiroDragon` / `FizAndTheRainbowPlanet`
* 资源布局：`level*.assets`（场景）+ `sharedassets*.assets` + `resources.assets`，
  每个 `.assets` 配同名 `.resS` / `.resource` 存放流式数据
* 现代内容（本地化）走 **Addressables**：`StreamingAssets/aa/catalog.json` +
  `StandaloneWindows64/*.bundle`

---

## 1. 文本存在三套彼此独立的系统里

| 系统 | 载体 | 数量 | 语言组织方式 |
| --- | --- | --- | --- |
| Unity Localization | `StringTable` MonoBehaviour，在 Addressables bundle 中 | 5 张表 × 4 语言 | 每语言一个 `StringTable_xx` + 共享 `SharedTableData` |
| 自定义 ScriptableObject（列表式） | `TextData`、`AutoTalk_Data` | 55 / 247 | 组件内 `List<...Class>`，每项带 `language` 枚举 |
| 自定义 ScriptableObject（字段式） | `Title_Data`、`DamageTalk_Data` | 49 / 5 | `label` / `label_en` / `label_fr` … 或每语言一个资源 |

5 张本地化表：`UI Table`(34)、`Message Table`(18)、`Title Contents Table`(31)、
`SubGames UI Table`(14)、`Ending Table`(65) —— 共 **162 个键**。

提取结果：**1411 行**文本（`localization` 162 / `AutoTalk` 734 / `DamageTalk` 238 /
`Title` 147 / `TextData` 130）。

## 2. 语言枚举

`Assembly-CSharp.dll` 中的 `Language`（`work/decompiled/Language.cs`）：

```
Japanese = 0, English_Machine = 1, English = 2, French = 3, Spanish = 4, Max = 5
```

* `English_Machine` 是机器翻译占位（`DamageTalkData_enMachine`、`text_en_machine`），
  在正式英文完成后大量留空。
* 语言选择界面 `LanguageSetting.cs` 把下标 clamp 在 `0..1`，即**界面上只能切日/英**，
  西/法仅在代码分支里存在（且数据覆盖极低）。
* `FizRpResidentFlagManager.GetLanguage()` 用 `LocalizationSettings.SelectedLocale.name`
  字符串匹配（`"Japanese (ja)"` 等），默认回落到日文 → **新增语言必须改 DLL**。

## 3. 现有翻译覆盖率（非空字符串占比）

| 表 | ja | en_machine | en | fr | es | 合计 |
| --- | --- | --- | --- | --- | --- | --- |
| Ending Table | 65 | 0 | 65 | 5 | 5 | 65 |
| Message Table | 18 | 0 | 18 | 0 | 0 | 18 |
| SubGames UI Table | 14 | 0 | 14 | 1 | 1 | 14 |
| Title Contents Table | 31 | 0 | 31 | 5 | 4 | 31 |
| UI Table | 34 | 0 | 33 | 2 | 0 | 34 |

全部 1411 行：ja 1364、en_machine 842、en 1235、**fr 29、es 13**。
→ 法语/西班牙语几乎是空壳，**中文属于从零新增**。

## 4. 字体

游戏内置 **17 个字体资源**，全部是**动态** `UnityEngine.Font`
（完整 TTF/OTF 存在 `m_FontData` 里，`m_CharacterRects` 为空）。

按“被谁引用”统计（`src/font_usage.py` 递归扫 `m_FontData.m_Font`）：

| 字体资源 | 族名 | 引用数 | 备注 |
| --- | --- | --- | --- |
| `resources.assets:101` | Perfect DOS VGA 437 | **100** | 使用最多 |
| `sharedassets0.assets:14` | k8x12EXS | 45 | 主日文 8x12 像素字体，也是 `LocFontData` 默认字体 |
| `sharedassets2.assets:18` | Yoshi5x8_V2.1 | 6 | `LocFontData` 的 en/fr/es 字体，5x8 像素 |
| `sharedassets2.assets:17` | 07YasashisaGothicBold | 6 | 非像素中黑体 |
| `sharedassets3.assets:132` | Press Start K | 6 | 街机像素字体 |
| `sharedassets0.assets:15` | YoshiAtari8 | 4 | 8px 像素 |
| `sharedassets14.assets:43` | k8x12EXS SDF | 1 (TMP) | TextMeshPro 字体资源，图集已烘焙 |
| 其余（`k8x12EXL`、`x12y16pxMaruMonica`、`Roboto-*`、`Bangers`、`Anton`、`Oswald-Bold`、`LiberationSans`、`Electronic Highway Sign`、`PublicPixel`、`ロゴたいぷゴシック`） | — | Text 扫描未命中 | 部分为 TMP 示例资源 |

### 按语言换字体的机制

`LocalizedText.cs` 在每个组件上持有 `LocFontData`，运行时 `FindIndex(x => x.language == lang)`
后设置 `text.font / fontSize / lineSpacing`，找不到就回落 `defaultFont`。

`LocFontData` 共 6 个资源（`work/font_map.json`）：

| 资源 | default (ja) | en / en_machine / fr / es |
| --- | --- | --- |
| `LocFontData_MainTalk` | `sharedassets0:14` size 12 | `sharedassets2:18` size 8 |
| `LocFontData_TitleControllerSetting` | `sharedassets0:15` size 8 | `sharedassets2:18` size 8, lineSpacing 1.25 |
| `LocFontData_TitleInfo` | `sharedassets0:15` size 8 | `sharedassets0:14` size 12 |
| `LocFontData_Opening` | `sharedassets0:14` size 12 | `sharedassets2:18` size 8, lineSpacing 1.5 |
| `LocFontData_LeafurMegaphill_Sub` | `sharedassets0:15` size 8 | `sharedassets2:18` size 8 |

→ **新增语言只需往 `fontDatas` 追加一条 `{language, font, size, lineSpacing}`**，
不必改任何代码。

## 5. UnityPy 1.25.4 的两个致命坑（已修）

1. **`TypeTreeGeneratorAPI` 生成的 typetree 缺 `kAlignBytes`(0x4000) 标志。**
   Unity 序列化时把 1/2 字节字段补齐到 4 字节，而生成的节点没带这个 flag，
   于是 `m_Enabled` 之后的字段全部提早 3 字节读出——`m_Script` 变成
   `m_FileID=16777216`，`deref()` 直接 `FileNotFoundError: invalid m_FileID`。
   修法：递归给 `UInt8/SInt8/char/bool/UInt16/SInt16` 节点（数组元素除外）补 flag。

2. **可选的 C++ 加速读取器 `UnityPyBoost` 完全忽略该 flag。**
   必须 `UnityPy.helpers.TypeTreeHelper.read_typetree_boost = None`
   （它在 typetree 由 TPK 提供时是对的，对我们生成的节点是错的）。

修好后 `LocFontData` / `AutoTalk_Data` 等立刻可读。

3. 但 `TypeTreeGeneratorAPI` 对部分类**直接生成错节点**
   （`TextData` 的 `List<string>` 被标成 `string`，`read_value` 的
   `FUNCTION_READ_MAP["string"]` 抢先命中，永远不会走 vector 分支；
   `DamageTalk_Data` 生成的节点少了 `miss_capture` 字段导致整体错位；
   `ButtonImageData` 直接抛 `NullReferenceException`）。

→ 因此 `src/custom_types.py` 改为**按反编译源码手写字节级编解码器**，
并用 `src/verify_codecs.py` 对全部 **362 个对象**做「解码 → 重编码 → 与原字节比对」，
当前 **362/362 全部字节一致**。这条路同时解决了“读”和“写回”。

### 串行化规则（Unity 2021.3 Mono）

```
每个字段 4 字节对齐
bool / UInt8 / SInt16 … 读完补 4 字节对齐
string = int32 长度 + UTF-8 字节，补 4 字节
List<T> = int32 数量 + N 个元素
MonoBehaviour 头 = PPtr<GameObject>(12) + m_Enabled(1+3) + PPtr<MonoScript>(12) + m_Name(string)
```

### 易错点

* `DamageTalk_Data.SinglePlayerTalk` 有 **16** 个 `List<DamageTalk>`，
  枚举 `DamageTalkSetting` 里的 `miss_capture` **没有对应字段** —— 照着枚举写就会多解析一个列表。
* `TextData` / `DamageTalk_Data` 的法语、西班牙语条目**存在但为空字符串**，
  不是“没有该语言”。

## 6. 写回与新增语言的路径

* **自定义组件**：`src/apply_text.py` 现在是文本-only 薄封装，委托
  `src/build_patch.py` 写回（底层 `obj.set_raw_data(header + encode(data))` → `sf.save()`）。
  已用「把现有英文写回英文槽位」的空操作测试验证：22 个文件对象数一致、内容一致。
* **Unity Localization**：`StringTable` 在 Addressables bundle 中，新增 `zh-Hans`
  需要 ①新建 Locale + 5 张 `StringTable_zh-Hans` + `AssetTable`，
  ②改 `catalog.json`（`m_BucketDataString` / `m_EntryDataString` 是
  `BinaryStorageBuffer` 序列化后的 base64，需按格式重建或改用运行时 mod），
  ③改 `Language` 枚举与 `GetLanguage()` / `ChangeLanguageByEnum()`。
* **界面**：`LanguageSetting.cs` 的 `nowSelectingIndex` clamp 需要放开到新增语言数。

替代方案：用 BepInEx + Harmony 在运行时注册 Locale、替换字体与字符串，
可完全绕开 catalog 重建，代价是需要装 mod 加载器。
