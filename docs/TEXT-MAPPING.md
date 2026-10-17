# FizRP 文本系统与文字映射关系（TEXT-MAPPING）

> **本文定位**：回答「游戏里的每一段文字**存在哪里**、**运行时怎么被选中**、**补丁在哪一步写入**」。
> 三份文档分工：`README.md`（使用者流程） / `docs/FINDINGS.md`（逆向概况） /
> `docs/TECHNICAL.md`（实现细节与格式契约） / **本文（文本系统清单 + 映射表 + 覆盖边界）**。
>
> * 编写日期：2026-10-18（v1.2.2 发布前复核）
> * 工作区：仓库根目录；游戏安装目录：本机 Steam 的 FizRP（只读，命令中用 `FIZRP_ROOT` / `FIZRP_GAMEDATA` 指定）
> * 原版基线：`work/_additive/staging/FizAndTheRainbowPlanet_Data/`（103 个 `.assets`，
>   **不含** `level*` 场景文件）
> * 产物基线：`dist-additive/`（X2 追加式，`manifest-additive.json` 版本 1.2.2）
>
> **证据标注约定**（本文所有结论都带其中一种）：
> * 【实测】= 本次用 UnityPy / 反编译源码现场扫描得出的数字或字段值，命令见 §5；
> * 【源码】= 直接读 `work/decompiled/*.cs` 的类/方法/行号；
> * 【未验证】= 需要运行游戏才能确认，本文不替它下结论。
>
> ⚠️ 本文档最初由只读分析任务生成，不修改游戏目录、不构建、不安装；后续发布提交同时包含本文与构建/插件/翻译改动，具体范围以 Git 提交为准。

---

## 0. 一页速览

游戏把文字放在**三类载体**（Addressables bundle / 自定义 ScriptableObject / 场景序列化字段）
下的**六套子系统**里，任何只处理其中一套的方案都会漏掉一大半：

| # | 系统 | 资源载体 | 对象数【实测】 | 语言组织 | 切换语言时是否跟着变 |
| --- | --- | --- | --- | --- | --- |
| 1 | Unity Localization `StringTable` | Addressables bundle（`StreamingAssets/aa/StandaloneWindows64/*.bundle`） | 168 个键 / 5 张文本表 + 1 张 Sprite 表 | 每 locale 一个 `StringTable_<locale>` + 共享 `SharedTableData` | ✅ 由 `LocalizeStringEvent` 在运行时重设（730 个组件） |
| 2 | `Title_Data`（字段式 SO） | `sharedassets3.assets`（49 个，path_id 498 起） | 49 | `label` / `info` / `infoDisable` + `_en_machine/_en/_es/_fr` 后缀 | ✅ 但取决于 `langBuf`（见 §2.4、§4.2） |
| 3 | `TextData`（列表式 SO） | 22 个 `.assets` | 55 | `textDatas[]` 每语言一个块，块内 `strings[]` | ✅ 按 `GetLanguage()` 反查块下标 |
| 4 | `AutoTalk_Data`（列表式 SO） | 93 个 `.assets` | 247 | 日文 `talkDatas[]` + `locTalkDatas[]` 每语言一份 | ✅ 按 `GetLanguage()` 反查块下标 |
| 5 | `DamageTalk_Data`（每语言一个资源） | `sharedassets3.assets`（5 个） | 5 | 资源名区分语言（`DamageTalkData_es` = 484 等） | ✅ 由 `CanvasCamera` 的 `switch` 选资源 |
| 6 | **场景直接序列化的 `UnityEngine.UI.Text`** | `level*.assets`（159 个场景）+ `sharedassets*.assets` + `resources.assets` | 1824 个 Text + **1** 个 TMP | 无语言维度：字符串就是最终值，除非挂了本地化组件 | ❌ 大多不变（详见 §4） |

字体侧另有两个独立机制：`LocFontData`（随语言换字体，6 个资源，只被 159 个 `LocalizedText` 使用）
与 BepInEx 插件的**全场景字体接管**（X2 实际生效的那条路径）。

**中文槽位**：`Language.Spanish = 4`（locale 代码 `es`）。X2 把中文写进这一格，
日/英/法数据保持原样，语言菜单由插件新增第三项「中文」。

---

## 1. 文本系统清单与数据流

### 1.1 Unity Localization `StringTable`

**载体**：Addressables bundle，不在 `.assets` 里。

| bundle | 内容 |
| --- | --- |
| `localization-assets-shared_assets_all.bundle` | `SharedTableData`（键表本身），也是 5 张贴图的宿主 |
| `localization-string-tables-japanese(ja)_assets_all.bundle` | `StringTable_ja` × 5 张表 |
| `localization-string-tables-english(en)_assets_all.bundle` | `StringTable_en` × 5 张表 |
| `localization-string-tables-french(fr)_assets_all.bundle` | `StringTable_fr` |
| `localization-string-tables-spanish(es)_assets_all.bundle` | `StringTable_es` ← **中文写入这里** |
| `localization-locales_assets_all.bundle` | `Locale` 资产（`ja` / `en` / `fr` / `es`，名称形如 `Japanese (ja)`） |
| `localization-asset-tables-<locale>_assets_all.bundle` | AssetTable 定义（4 份，**载荷里不带**） |
| `localization-assets-japanese(ja)_assets_all.bundle` | AssetTable 的**资源本体**（实测：2 个 `Texture2D` + 2 个 `Sprite`，**无 MonoBehaviour**）。载荷里带它只为**贴图**汉化（2 张），与文本无关 |

**表与键**【实测】`SharedTableData` 共 **168** 键：

| 表 | 键数 | 内容 |
| --- | --- | --- |
| `Ending Table` | 65 | 结局字幕（角色名 + `by <作者>` + 关卡名 + 版权页） |
| `UI Table` | 34 | 暂停面板、角色卡、GameOver、Movie 舞台标题 |
| `Title Contents Table` | 31 | 标题菜单/设置界面/语言选择 |
| `Message Table` | 18 | 关卡内教学提示 |
| `SubGames UI Table` | 14 | 小游戏（Leafur / SoracoFishing） |
| `Sprite Table` | 6 | 本地化**贴图**（不是文字），由 `LocalizedSprite` 类组件使用 |

**各 locale 的实际覆盖率**【实测，原版基线，逐表条目数】：

| 表 | `ja` | `en` | `fr` | `es` |
| --- | --- | --- | --- | --- |
| `Ending Table` | 65 | 65 | 5 | 5 |
| `Message Table` | 18 | 18 | 18 | 18 |
| `SubGames UI Table` | 14 | 14 | 14 | 14 |
| `Title Contents Table` | 31 | 31 | 29 | 29 |
| `UI Table` | 34 | **33** | 2 | **0** |
| 合计 | 162 | 161 | 68 | **66** |

非空条目数：`ja` 162 / `en` 161 / `fr` **13** / `es` **10**。

→ 原版 `es` 是准空槽（这就是选它当中文槽位的依据）；`en` 少的那 1 条在 `UI Table`（33/34），
补丁在缺键时会**追加表项**（与 Unity Localization 运行时行为一致）。
`fr`/`es` 的表本身就比 ja 短，说明**各 locale 的 `m_Id` 集合并不相同**。

**locale 资产名**【实测 `localization-locales_assets_all.bundle`】：
`Locale` 资产恰为 `Japanese (ja)` / `English (en)` / `French (fr)` / `Spanish (es)`
（`m_Identifier.m_Code` = `ja`/`en`/`fr`/`es`）——这正是 §2.2 里
`GetLanguage()` 字符串匹配能成立的前提。

**键的定位方式**：`StringTable.m_TableData[].m_Id` → 用 `SharedTableData.m_Entries` 反查
`m_Key`。**各 locale 的 `m_Id` 集合并不相同**（fr/es 是子集），所以提取时按并集出行、
缺该 locale 就留空（`src/extract_text.py:94-114`）。

### 1.2 `Title_Data`

**载体**：`sharedassets3.assets`，49 个对象，path_id 498 起（`TitleData_lv0_root` 541 等）【实测】。

**语言组织**：字段式后缀，五套并列【源码 `work/decompiled/Title_Data.cs:27-59`】：

```
label             label_en_machine  label_en  label_es  label_fr
info              info_en_machine   info_en   info_es   info_fr
infoDisable       infoDisable_...             infoDisable_es  infoDisable_fr
```

**运行时选择**【源码 `work/decompiled/TitleUiScript.cs`】：

* 按钮名：`setButtons()`（:303）与 `backButtons()`（:625）里 `switch (langBuf)` → `label_es`（:536-582、:652-699）；
* 底部滚动说明 `InfoText`：`ResetInfoText()`（:225）里 `switch (langBuf)` → `info_es` / `infoDisable_es`（:233-280）；
* 未解锁时前缀硬编码 `"???......"`（:260 起，逐语言分支 :260-280）。

**`langBuf` 的更新时机【源码，关键】**：`langBuf` 是私有字段（:125），
**全文件只有一处赋值**——`Update()`（:166）里

```csharp
if (MyControlExpantion.GetButtonDown(MyControlExpantion.KeyType.Submit)) {
    if (nowD == 0 && FizRpResidentFlagManager.Instance) langBuf = ...GetLanguage();  // :173-176
    setButtons();                                                                    // :177
}
```

即：**进入标题场景后，玩家第一次在根菜单按下确定键之前，`langBuf` 一直是默认值
`Language.Japanese`（0）**。后果见 §4.2。

### 1.3 `TextData`

**载体**【实测】：55 个对象，分布在 **22** 个 `.assets`（`sharedassets3/4/14/16/21/29/36/40/56/58/70/74/85/93/96/105/107/109/112/123/129/153.assets`）。

**语言组织**【源码 `work/decompiled/TextData.cs:9-23`】：`textDatas[]` 每语言一块，
块内 `strings` 是**多行数组**（`[0]`=标题、`[1]`=正文，可由调用方任意使用）。

**运行时选择**：`FindIndex(x => x.language == GetLanguage())`，找不到回落 index 0。
代表：`StageSelectManager.cs:128`（世界地图名，`StageSelectText_WorldName`）、
`CanvasCamera.cs:852-890`（`UpdateTreasureText`，宝物页标题/正文）。

### 1.4 `AutoTalk_Data`

**载体**【实测】：247 个对象，分布在 **93** 个 `.assets`（其中 36 个在 `sharedassets96.assets`、
34 个在 `sharedassets65.assets`，与关卡一一对应）。

**语言组织**【源码 `work/decompiled/AutoTalk_Data.cs:9-56`】：
日文原文在 `talkDatas[]`（每个元素含 `chara`/`faceSpriteMode`/`charaSprite`/`text`/`wait`/
事件下标）；其它语言在 `locTalkDatas[]`，每个元素是 `{language, talkDatas[]}`，
**下标与日文列表一一对应**。

**运行时选择**：`CanvasCam_AutoTalk.cs:360`、`NPCBase.cs:243`、`CanvasCamera.cs:743/855` 等
按 `GetLanguage()` 反查；`GetLanguage(_isUseBuffer:true)` 走缓存版本（避免每帧字符串比较）。

### 1.5 `DamageTalk_Data`

**载体**【实测】：**5 个对象全在 `sharedassets3.assets`**，资源名即语言：

| 资源名 | path_id | 语义 |
| --- | --- | --- |
| `DamageTalkData_ja` | 486 | 日文（补长模板） |
| `DamageTalkData_enMachine` | 483 | 机翻占位 |
| `DamageTalkData_en` | 482 | 英文 |
| `DamageTalkData_es` | 484 | **中文写入这个** |
| `DamageTalkData_fr` | 485 | 法文 |

**结构**【源码 `work/decompiled/DamageTalk_Data.cs`】：`player[] → SinglePlayerTalk`
含 **16** 个 `List<DamageTalk>`（`damage_normal`…`specialAttack`）。
两个坑：① 枚举 `DamageTalkSetting` 里的 `miss_capture`（:24）**没有对应字段**，
照枚举写会多解析一个列表；② 各语言资源的列表长度**不一致**（英/西比日文短），
补丁必须先按日文补齐长度（`src/build_patch.py:209-234`）。

**运行时选择**【源码 `CanvasCamera.cs:1035-1046`】：

```csharp
damageTalk_Data = FizRpResidentFlagManager.Instance.GetLanguage(_isUseBuffer: true) switch {
    Language.English_Machine => damageTalkData_en_Machine,
    Language.English         => damageTalkData_en,
    Language.Spanish         => damageTalkData_es,   // ← 中文槽
    Language.French          => damageTalkData_fr,
    _                        => damageTalkData,      // ← 默认 = 日文
};
```

### 1.6 `LocalizedText`

**【源码 `work/decompiled/LocalizedText.cs`】** 只做**字体/字号/行距**，不碰文字：

* `Start()`（:14）先按 `locFontData.defaultFont` 设一遍；
* `FixedUpdate()`（:26）每 11 帧、`OnEnable()`（:35）各调一次 `CheckLanguage()`；
* `CheckLanguage()`（:40）→ `fontDatas.FindIndex(x => x.language == lang)`（:50），
  命中就设 `text.font / fontSize / lineSpacing`（:53-55），否则回落 `defaultFont`（:59-61）。

**规模**【实测】：全游戏 **159** 个 `LocalizedText` 组件——即**只有 159/1824 个 Text
的字体是随语言走的**，其余 1665 个靠序列化值或插件接管。

> 插件注释 `plugin/LangMenuPlugin.cs:409-411` 写的「本作共 134 个 Text，只有 1 个挂了
> LocalizedText」与实测不符（134 更像是 `src/font_usage.py` 的旧口径，见 §5.3）。

### 1.7 `LocFontData`

**【源码 `work/decompiled/LocFontData.cs:9-27`】**`defaultFont` + `fontDatas[]`
（每项 `{memo, language, font, size, lineSpacing}`）。

**6 个资源**【实测，含所在 `文件:path_id` 与全部语言映射】：

| 资源 | 文件:path_id | defaultFont（日文档） | 原版 es 槽 |
| --- | --- | --- | --- |
| `LocFontData_MainTalk` | `sharedassets3.assets:478` | `sharedassets0.assets:14`(k8x12EXS) size 12, ls 1.0 | `sharedassets2.assets:18` size 8 |
| `LocFontData_TitleControllerSetting` | `sharedassets3.assets:479` | `sharedassets0.assets:15`(YoshiAtari8) size 8, ls 1.25 | `sharedassets2.assets:18` size 8 |
| `LocFontData_TitleInfo` | `sharedassets3.assets:480` | `sharedassets0.assets:15` size 8, ls 1.0 | `sharedassets0.assets:14` size 12 |
| `LocFontData_Opening` | `sharedassets7.assets:675` | `sharedassets0.assets:14` size 12, ls 1.5 | `sharedassets2.assets:18` size 8 |
| `LocFontData_Ending_Role` | `sharedassets137.assets:84` | `sharedassets0.assets:15` size 8, ls 1.0 | `sharedassets2.assets:18` size 8 |
| `LocFontData_LeafurMegaphill_Sub` | `sharedassets153.assets:148` | `sharedassets0.assets:15` size 8, ls 1.0 | `sharedassets2.assets:18` size 8 |

六个资源的 `en_machine` / `en` / `fr` / `es` 四项**内容完全相同**（同一个字体同一个字号），
只有 `defaultFont`（日文）不同。

### 1.8 `InlineImage`

**【源码 `work/decompiled/InlineImage.cs`】** 不是文本系统，而是**文字里的内联图标**：
`Update()`（:34）用正则 `\<(.+?)\>`（:38）把富文本标签剥掉，再把 `replaceText`
（如 `⑪`）的**字符位置换算成顶点下标**（:54-55，`num * 4`），把图标 GameObject 摆到
对应字符位置（:61-68）。**全游戏 388 个 `InlineImage` 组件**【实测】。

维护含义：译文里**破坏字符序列**（少一个 `⑪`、把全角 `⑪` 换成 `(11)`）会让图标错位或消失。
`src/check_translation.py` 的占位符规则就是在守这条线。

### 1.9 场景直接序列化的 `Text` / `TMP` 文本

这是最大的一块，也是最容易被「只改资源」的方案漏掉的一块。

| 项 | 数量【实测】 |
| --- | --- |
| `UnityEngine.UI.Text` 组件 | **1824** |
| `TextMeshProUGUI` 组件 | **1** |
| `LocalizeStringEvent` 组件 | **730**（引用 **154** 个不同键 id；其中 **729** 条 `m_UpdateString` 调用能解析到同文件的 Text 目标，差额来自未设 key 或目标不在同一 serialized file 的个别组件） |
| `LocalizedText` 组件 | 159 |
| `InlineImage` 组件 | 388 |
| `LocalizeSpriteEvent` 组件 | **40**（分布在 39 个场景，引用 **6** 个 `Sprite Table` 键 → 本地化**贴图**，不是文字） |
| `LocalizationSettings` 组件 | 1（全局初始化） |

* **1824 个 Text 分布在 159 个 `level*` 场景 + 161 个 `.assets`**；`level*` 场景**从未被补丁修改**
  （X2 载荷 125 个文件里没有任何 `level*`，见 §3.3），所以场景里的字体引用与字符串
  保持原版，只能靠**插件在运行时**接管。
* 场景里的 Text 有三类命运：
  1. 挂了 `LocalizeStringEvent` → 运行时由本地化表覆盖（含中文字串）；
  2. 没挂本地化组件、但被脚本在 `Start/Update` 里赋值 → 值来自脚本内的**硬编码字面量**
     或某个 SO（`Title_Data` / `TextData` 等）；
  3. 既没挂组件、也没被脚本赋值 → **序列化值就是最终显示值**。

判定第 3 类的方法（本文所用）：解析 `LocalizeStringEvent.m_UpdateString.m_PersistentCalls[].m_Target`
指向的 Text，得到「哪个 Text 被哪个键驱动」；再 `grep` 反编译源码确认有没有脚本赋值。

### 1.10 数据流总图

```
 ┌─────────────────────────── 文字的来源 ───────────────────────────┐
 │ StringTable(bundle)  Title_Data  TextData  AutoTalk  DamageTalk  │
 │        │                  │          │         │         │       │
 │        │ LocalizeString   │switch    │FindIndex│FindIndex│ switch│
 │        ▼   Event(730)     ▼ (langBuf)▼(GetLanguage)  ▼        ▼   │
 │   UnityEngine.UI.Text / TextMeshProUGUI（1824 + 1 个组件）        │
 └───────────────▲──────────────────────────────────────────────────┘
                 │ 字体：LocalizedText(159) → LocFontData(6) → Font
                 │ 字体（X2 实际生效）：插件全场景扫描 → Fusion Pixel 宿主
                 │ 字号（X2）：插件拦截 Text.set_fontSize → 量化到 10 / 8
```

---

## 2. 语言与字体选择

### 2.1 语言枚举与槽位

**【源码 `work/decompiled/Language.cs`】**

```
Japanese = 0, English_Machine = 1, English = 2, French = 3, Spanish = 4, Max = 5
```

`Language.Max` 全项目无人使用；`English_Machine` 是机翻占位（数据大量留空）。
`src/loc_common.py:6-16` 的 `LANGS` 顺序必须与此枚举一致。

**X2 的中文槽位 = `Spanish = 4`（locale 代码 `es`）**，
由 `tools/build_additive_data.py:41-44` 固定（`SLOT=4 / LOCALE="es" / PROFILE="zh_additive"`）。

### 2.2 游戏怎么读语言

三条路径，**都以 locale 字符串为准**：

1. **存档 → locale**（启动时）【源码 `work/decompiled/FizRpSetupScript.cs:433-448`】
   `LoadNextScene()`：`KeyExistsOnStack("Language")` → `LoadFromStack("Language", Japanese)`
   → `ChangeLanguageByEnum(...)`；没有该键就进 `LanguageSetting` 场景（首次启动的语言选择）。
2. **枚举 → locale**【源码 `FizRpResidentFlagManager.cs:1106-1138`】
   `ChangeLanguageByEnum` → `ChangeLanguageByString("ja"/"en"/"es"/"fr")`
   → `Locale.CreateLocale(locale)` 赋给 `LocalizationSettings.SelectedLocale`。
3. **locale → 枚举**【源码 `FizRpResidentFlagManager.cs:1140-1168`】
   `GetLanguage(_isUseBuffer = false)` 用 `LocalizationSettings.SelectedLocale.name`
   **字符串匹配**：`"Japanese (ja)"`/`"Japanese"` → 0，`"English (en)"` → 2，
   `"French (fr)"` → 3，`"Spanish (es)"` → 4，**其它一律回落 Japanese**；
   并写入字段 `languageBuffer`。`_isUseBuffer = true` 时直接返回该缓存。

> 因为第 3 条是**字符串匹配**，中文能成立的前提是 `Locale.CreateLocale("es")`
> 造出的 locale 名字确实是 `Spanish (es)`（由 `localization-locales` bundle 决定），
> 新增一个 locale 名（如 `zh-Hans`）会直接掉进 `default → Japanese`——
> 这是「槽位复用」比「新增 locale」可靠的直接原因。

**语言选择界面**【源码 `LanguageSetting.cs`，场景 `level2`，组件 path_id 177】：

* `Start()`（:29）读存档语言映射到 `nowSelectingIndex`（:32-53），
  并摆光标 `new Vector2(-16f, 32 - index * 24)`（:55）；
* `Update()`（:58）里 `Submit` → `FizRpSave.StackSave("Language", nowSelectedLanguage)`（:76）；
* 上下键改 `nowSelectingIndex`，**clamp 在 `0..1`**（:95-102）；
* `switch (nowSelectingIndex)` 已经写好 `case 2 → Language.Spanish`（:115-117），
  只是永远走不到。

**场景实测（`level2`）**【实测】：

| GameObject | 文本 | 字体 | 字号 | `m_IsActive` |
| --- | --- | --- | --- | --- |
| `選択肢 (0)` | `日本語` | `sharedassets0.assets:14` (k8x12EXS) | 12 | true |
| `選択肢 (1)` | `English` | 同上 | 12 | true |
| `選択肢 (2)` | `Español` | 同上 | 12 | **false** |
| `選択肢 (3)` | `Français` | 同上 | 12 | **false** |
| `タイトル` | `どの　げんごで　あそびますか？` | 同上 | 12 | true（**无本地化组件**） |
| `SubTitle` | `PLEASE SELECT A LANGUAGE.` | `sharedassets2.assets:18` | 8 | true（`LocalizeStringEvent` → `Title Contents Table:LanguageSettings_SubHeader`） |

→ 插件正是「激活 `選択肢 (2)` + 改文本为『中文』+ 把 clamp 常量 1 改成 2」。

### 2.3 字体资源与字号双档

**17 个字体全是动态 `UnityEngine.Font`**（完整 TTF 内嵌在 `m_FontData`，`m_CharacterRects` 为空）
【实测：抽查 `sharedassets0.assets:14/15`、`sharedassets3.assets:132/133` 的 `m_CharacterRects` 长度均为 0，blob 1.2 MB 级】，
因此**换字体 = 换这段 byte[]**，无需重建图集。

**实际被 Text 引用的字体**【实测，含 159 个场景，共 1824 个 Text】：

| 字体资源 | 引用数 | 字号分布 | zh_additive 是否替换 |
| --- | --- | --- | --- |
| `sharedassets0.assets:14` `k8x12EXS` | **1006** | 12×942、75×64 | ✅ → **Fusion Pixel 10px** zh-Hans |
| `sharedassets0.assets:15` `YoshiAtari8` | 234 | 8×234 | ❌ 保持原版 |
| `sharedassets2.assets:18` `Yoshi5x8_v2.1` | 153 | 8×153 | ❌ 保持原版（advance 0.625em，换方形中文字会溢出 60%） |
| `sharedassets3.assets:132` `prstartk`（Press Start K） | 131 | 8×131 | ❌ 保持原版 |
| `sharedassets2.assets:17` `07やさしさゴシックボールド` | 128 | 12×111、14×3、16×2、24×9、30×3 | ❌ 保持原版 |
| `resources.assets:101` `PerfectDOSVGA437` | 100 | 16×95、24×3、15×1、12×1 | ❌ 保持原版 |
| `sharedassets3.assets:133` `k8x12EXL` | **49** | 12×49 | ✅ → **Fusion Pixel 8px** zh-Hans |
| `sharedassets6.assets:10` `PublicPixel` | 14 | 8×14 | ❌ 保持原版 |
| `sharedassets0.assets:16` `ロゴたいぷゴシック` | 6 | 30/50/60 | ❌（`disabled`） |
| `sharedassets154.assets:7` `x12y16pxMaruMonica` | 2 | 16×2 | ❌ 保持原版 |
| `unity default resources:10102`（Arial） | 1 | 50 | — |

**双档设计（X2 `zh_additive` profile，`fonts.config.json:9-77`）**：

| 宿主 | zh_additive 装入的 blob | 设计尺寸 | 插件常量 |
| --- | --- | --- | --- |
| `sharedassets0.assets:14` `k8x12EXS` | `fusion-pixel-10px-proportional-zh_hans.ttf` | 10px | `Font10Name="k8x12EXS"` / `SizeLarge=10`【源码 `plugin/LangMenuPlugin.cs:436-439`】 |
| `sharedassets3.assets:133` `k8x12EXL` | `fusion-pixel-8px-proportional-zh_hans.ttf` | 8px | `Font8Name="k8x12EXL"` / `SizeSmall=8` |

**替换结果实测**（读 `m_FontData` 并解析 OpenType `name` 表）：

| 字体对象 | 原版 | 产物 |
| --- | --- | --- |
| `sharedassets0.assets:14` | 族名 `k8x12EXS`，1,205,656 B，sha256 `c68de9b246a6…` | 族名 **`Fusion Pixel 10px Prop zh-Hans`**，4,048,740 B，sha256 `d5944040453e…` |
| `sharedassets3.assets:133` | 族名 `k8x12L`（资源名 `k8x12EXL`），1,210,144 B | 族名 **`Fusion Pixel 8px Prop zh-Hans`**，3,655,972 B |
| `sharedassets0.assets:15` `YoshiAtari8` | 56,460 B，sha `4d6769627e45…` | **字节不变** |
| `sharedassets3.assets:132` `prstartk` | 20,908 B，sha `b90965d4c795…` | **字节不变** |

→ 与配置一致：**只换了 2 个宿主 blob**，其余字体对象字节未变。

**`LocFontData` 的 es 槽改写（构建期）**【实测：原版 → 产物】：

| 资源 | defaultFont.size | es 槽：原版 → 产物 |
| --- | --- | --- |
| `LocFontData_MainTalk` | 12 | `sharedassets2:18` size 8 → **`sharedassets0.assets:14` size 12** |
| `LocFontData_TitleControllerSetting` | 8 | `sharedassets2:18` size 8 → **`sharedassets3.assets:133` size 8** |
| `LocFontData_TitleInfo` | 8 | `sharedassets0:14` size 12 → **`sharedassets3.assets:133` size 8** |
| `LocFontData_Opening` | 12 | `sharedassets2:18` size 8 → **`sharedassets0.assets:14` size 12** |
| `LocFontData_Ending_Role` | 8 | `sharedassets2:18` size 8 → **`sharedassets3.assets:133` size 8** |
| `LocFontData_LeafurMegaphill_Sub` | 8 | `sharedassets2:18` size 8 → **`sharedassets3.assets:133` size 8** |

规则：**es 槽镜像该资源 `defaultFont` 的档位**——取与 `defaultFont.size` 最接近的受支持档位
（`abs(size-8)` 与 `abs(size-12)` 比较，平局取较大档；`size ≤ 0` 时取 12/EXS；
六份资源的实际值都是 8 或 12，所以等价于「8 → EXL(133)、12 → EXS(14)」）。
映射常量在 `src/build_patch.py:78-92`（`ADDITIVE_FONTS_BY_SIZE` / `_additive_size_for`）与
`tools/build_additive_data.py:60-64`（`SLOT_FONT_BY_SIZE`），两侧必须一致，
`build_additive_data.py` 末尾会断言（不一致则返回 1）。

> **一处需要注意的不变量错位**：`LocFontData_MainTalk`/`_Opening` 的 es 槽序列化值是
> `size=12`，但宿主 `k8x12EXS` 装的是 **10px 设计**字体。之所以实机仍然 1:1 锐利，
> 是因为插件的 `Text.set_fontSize` 前缀补丁（`plugin/LangMenuPlugin.cs:1247-1268`）
> 会在 `LocalizedText` 写值时就把它量化成 10。
> 换言之：**「序号化的 size == 宿主设计尺寸」这条不变量只在插件生效时成立**；
> `tools/build_additive_data.py:50-59` 的注释仍写着「size 12 → fusion-12px-zh_hans」
> 与「插件常量 SizeLarge=12」，与当前代码不符（见 §5.2）。

### 2.4 哪些文本随语言切换、哪些写死

| 类别 | 是否随语言切换 | 证据 |
| --- | --- | --- |
| `StringTable` + `LocalizeStringEvent`（730 组件 / 154 键） | ✅ 运行时由 Unity Localization 重设 | `m_UpdateString.m_Target` → Text |
| `Title_Data` 按钮名 / 底部说明 | ✅（`label_es`/`info_es` 已是中文）**但受 `langBuf` 时机限制** | §1.2、§4.2 |
| `TextData`（含宝物页、世界地图名） | ✅ | `CanvasCamera.cs:852-881`、`StageSelectManager.cs:128` |
| `AutoTalk_Data` | ✅ | `CanvasCam_AutoTalk.cs:360` |
| `DamageTalk_Data` | ✅ | `CanvasCamera.cs:1035-1046` |
| 场景 Text + 无本地化组件 + 脚本硬编码 | ❌ 永远是日文/英文 | §4.1 表 |
| 场景 Text + 无本地化组件 + 由 SO 驱动 | ✅（值来自 SO） | `Choice1..6`←`Title_Data.label`；`TextTreasure*`←`TextData` |
| 唯一 TMP `NPC TALK` | 文本不变；字体由插件运行时建 TMP 资产接管 | §4.5 |
| 字体切换 | 只有 159 个 `LocalizedText` 走 `LocFontData`；其余靠插件全场景扫描 | §2.3 |

---

## 3. 映射表

### 3.1 键命名与写入位置

| 系统 | id 形式（`work/text_index.json` / `translation/zh_Hans.csv`） | 资源载体 | 写入的字段 |
| --- | --- | --- | --- |
| Unity Localization | `localization:<Table>:<Key>` | 对应 locale 的 `StringTable` bundle | `m_TableData[].m_Localized`（缺键则 `append`） |
| `TextData` | `TextData:<资源名>:<strings下标>` | 22 个 `.assets`（`sharedassets3.assets:488` 起等） | `textDatas[language==4].strings[idx]`（块不存在则新建） |
| `AutoTalk_Data` | `AutoTalk:<资源名>:<talkDatas下标>` | 93 个 `.assets` | `locTalkDatas[language==4].talkDatas[idx].text`（块不存在则新建，按 ja 深拷贝补长） |
| `Title_Data` | `Title:<资源名>:<label｜info｜infoDisable>` | `sharedassets3.assets` | `<group>_es` |
| `DamageTalk_Data` | `DamageTalk:<列表名>:<player下标>:<元素下标>` | `sharedassets3.assets` 的 5 个资源 | 目标语言资源 `player[p].<list>[i].text` |

**索引规模**【实测 `work/text_index.json`】：1411 条 =
`AutoTalk 734` + `DamageTalk 238` + `localization 162` + `Title 147` + `TextData 130`。
**译文表**：1411 行，`zh_Hans` 非空 **1364** 行；未译的 47 行**全部因为日文源为空**
（44 条 Title 的 `info/infoDisable`、1 条 AutoTalk、2 条 DamageTalk），不是漏译。

### 3.2 构建与拦截点（文件 : 函数 / 行号）

**数据侧（离线写入 .assets / bundle）**

| 位置 | 作用 |
| --- | --- |
| `src/build_patch.py:560` `build()` | 主入口；参数 `slot / locale_code / profile / additive` |
| `src/build_patch.py:100` `gate_translations()` | 构建前的译文表门槛（错误级问题直接 `ABORT`） |
| `src/build_patch.py:42-48` `KIND_TO_CLASS` / `DMG_ASSET_LANG` / `TITLE_SUFFIX` | 索引短名 ↔ C# 类名；`TITLE_SUFFIX = {0:"",1:"_en_machine",2:"_en",3:"_fr",4:"_es"}` |
| `src/build_patch.py:264` `patch_assets()` | 逐文件遍历，解码 → 改 → `obj.set_raw_data(header + encode(...))` |
| `src/build_patch.py:138` `_shift_text()` | `TextData` / `AutoTalk_Data` / `Title_Data` 三类的字段定位 |
| `src/build_patch.py:237` `_shift_damage()` / `:209` `_pad_damage()` | DamageTalk 写值与按 ja 补长 |
| `src/build_patch.py:177` `_fix_treasure_default()` | 修原版 `TreasureText_default` 的 `[0,0,1,2,3,4]` 错位 |
| `src/build_patch.py:336-373` | `LocFontData` es 槽的 `font`（PPtr）与 `size` 改写 |
| `src/build_patch.py:409-425` | `Font.m_FontData` blob 替换（`pick_blob_name` 按 profile 选 blob） |
| `src/build_patch.py:497` `patch_string_tables()` | es bundle 内逐条改 `m_Localized`；`packer="original"` 保存 |
| `src/build_patch.py:603-641` | 覆盖率对账：`written == expected`，缺行 `ABORT` |
| `src/custom_types.py:150-215` | 5 个类的字节级规格（字段名与顺序的唯一真源） |
| `src/extract_text.py:74-114` / `:185-265` | 5 类文本的提取与 id 生成（映射表的上游） |

**包与载荷侧**

| 位置 | 作用 |
| --- | --- |
| `tools/build_additive_data.py:41-44` | `SLOT=4 / LOCALE="es" / PROFILE="zh_additive" / COLUMN="zh_hans"` |
| `tools/build_additive_data.py:60-64` | `SLOT_FONT_BY_SIZE = {8: (sharedassets3,133), 12: (sharedassets0,14)}` |
| `tools/build_additive_data.py:191-227` | 文本注入 → 贴图回灌（16 张，4 个宿主文件）→ 合并产物 |
| `tools/build_additive_payload.py:80-82` | `GAME_ROOT_NAMES/PREFIXES`（loader 投放到游戏根） |
| `tools/build_additive_payload.py`（`--crc 0` 段，:39-41、:230、:266） | catalog 的 es bundle 尺寸/CRC 同步（**CRC 是占位值**，需实机回填） |
| `tools/catalog_sync.py` | catalog 二进制帧头与 `dataIndex` 平移 |
| `tools/patch_tool.py:96-98` | `ADDITIVE_GAME_ROOT_NAMES/PREFIXES`（与构建侧同源常量） |

**运行时侧（`plugin/LangMenuPlugin.cs`）**

| 位置 | 拦截点 | 作用 |
| --- | --- | --- |
| `:221-267` | `LanguageSetting.Start` **Postfix** | 激活场景里未启用的 `選択肢 (2)`、文本置「中文」、若存档已是 Spanish 则把光标索引改 2 |
| `:276-404` | `LanguageSetting.Update` **Transpiler** | 把 clamp 常量 `1` 改成 `2`（**严格匹配恰好 2 处，否则放弃补丁**，见 :312-316） |
| `:423-1174` `FontApplier` | — | 全场景字体接管 |
| `:487-499` `ForceLarge()` | — | 强制 10px 档：GameObject 名 `InfoText`、文本以 `©2024` 开头 |
| `:525-562` `FindFont()` / `GetFontFor()` | — | 按名字找 `k8x12EXL`/`k8x12EXS` 宿主（失败限流每秒重试） |
| `:565-617` `IsChineseLanguage()` | — | 反射 `FizRpResidentFlagManager.GetLanguage()`，`== 4` 才介入 |
| `:650-700` `HasKana()` / `HasCJK()` | — | 含 CJK 才接管；纯拉丁（百分比/`LIFE`/`Shift`）保持原版；`・`(U+30FB) 特判排除 |
| `:723-808` `SnapContentToPixelGrid()` | — | 把内容起点沿 x/y 补偿到整数设计像素（修半格发虚） |
| `:1116-1173` `ApplyAll()` | — | 每秒刷新 `Text`/`TMP_Text` 缓存，逐帧 O(1) 比对 |
| `:1186-1215` `FontApplierBehaviour` | `Application.onBeforeRender` + `LateUpdate` | 渲染前最后一刻纠错 |
| `:1221-1238` | `LocalizedText.CheckLanguage` **Postfix** | 防止它把字体切回日文字体 |
| `:1247-1268` | `Text.set_fontSize` **Prefix** | 游戏每次赋字号都当场量化到 8/10（解决「先大后小」跳变） |
| `:1271-1297` | `Text.set_font` **Prefix** | 按当前档位换成中文字体 |
| `:1040-1079` `GetChineseTMPFont()` | — | 运行时 `TMP_FontAsset.CreateFontAsset(f)`（**只用默认重载**，见 :1055-1062 的实测记录） |
| `:1082-1113` `ApplyTMP()` | — | 唯一 TMP 文本的字体接管 |

### 3.3 载荷构成与投放路由（125 个文件）

```
102 数据文件  98 个 .assets + 3 个 bundle + catalog.json
                ├─ .assets / StreamingAssets/** → <游戏根>/FizAndTheRainbowPlanet_Data/**
                └─ 3 个 bundle = es 串表 + localization-assets-shared + localization-assets-japanese(ja)
                   （后两个是**贴图**汉化的宿主：5 张 + 2 张）
 23 loader     winhttp.dll / doorstop_config.ini / .doorstop_version / changelog.txt
                + BepInEx/**（core 18 + plugins/FizRPLangMenu.dll）→ 游戏根（不是 *_Data）
```

* **`level*` 场景不在载荷内**【实测：`manifest-additive.json` 的 125 条 path 无任何 `level*`】，
  所以游戏目录里的 `level*.assets` 就是原版文件——本报告的「场景序列化值」实测
  在**未打补丁的语义下**成立。
* 16 张贴图的宿主文件【实测 `work/_additive/image_patch_roundtrip.json`】：
  `sharedassets3.assets`(8) / `sharedassets13.assets`(1) / `localization-assets-shared`(5) /
  `localization-assets-japanese(ja)`(2)。

---

## 4. 已知未覆盖或受限项

> 逐项给出**证据**。凡「实机是否可见」需要运行游戏才能确认的，明确标【未验证】。

### 4.1 设置界面里**根本没接本地化**的标签（实测：无 `LocalizeStringEvent`）

判定口径：解析 `LocalizeStringEvent.m_UpdateString.m_PersistentCalls[].m_Target` 得到
被驱动的 Text；下列 Text **不在**被驱动集合内，且（除注明外）反编译源码里也没有脚本写它们
（`grep -F` 全文无命中）。它们所在的 GameObject 自身与全部祖先 `m_IsActive` 均为 true。

场景 `level3`（= 标题场景，`TitleUiScript` 在 path_id 1070）：

| GameObject | 序列化文本 | 字体 | 字号 | 补充证据 |
| --- | --- | --- | --- | --- |
| `Title` | `MILD  MODE` | `sharedassets0.assets:15` | 8 | 键 `Title Contents Table:Title_DisplaySettings_MildMode`（= 中文化的「温和模式」）**存在于表中但无任何组件引用**；源码里 `"MILD"` 零命中 |
| `Title` | `BGM` / `SE` / `ENV` / `VOICE` / `MASTER` | `sharedassets0.assets:15` | 8 | 对应的 `Title_SoundSettings_{Bgm,Se,Env,Voice,Master}` 五个键**全部未被引用**；`TitleUiSoundScript.cs` 只写音量数值（:142、:300），不写标签 |
| `Vibration` | `VIBRATION :　ON` | `sharedassets0.assets:15` | 8 | 键 `Title_ControlSettings_Vibration` 未被引用；值由 `TitleUiControllerScript.cs:325/330/389/393` 直接赋英文 `"VIBRATION :  ON"/"OFF"` |
| `CONTROLLER TYPE` | `ICON TYPE : AUTO` | `sharedassets0.assets:15` | 8 | `TitleUiControllerScript.cs:292-307、368-386` 硬编码 `"ICON TYPE : AUTO/XBOX/Ninten/SONY"` |
| `Type` | `Type A` | `sharedassets0.assets:15` | 8 | `TitleUiControllerScript.cs:98/213/256/353` 硬编码 `"TYPE A"/"TYPE B"` |
| `Nostalgic` / `SC88` / `GPT3_5T` / `GPT4_0T` | `NOSTALGIC` / `SC-88 Pro` / `GPT3.5 turbo` / `GPT4.0 turbo` | `sharedassets0.assets:15` | 8 | 源码零命中 → 纯场景序列化 |
| `Title_APIKey` / `Title_USETExtGen` / `APITYPETitle` / `MainTitle` | `API KEY` / `TEXT GENERATION` / `API TYPE` / `TEXTGEN SETTINGS （PREVIEW）` | `sharedassets0.assets:15` | 8 | 源码零命中 |
| `Placeholder` / `ApiCheck` | `ENTER YOUR OPENAI API KEY...` / `PRESS ENTER TO SUBMIT` | `sharedassets3.assets:133` / `sharedassets2.assets:18` | 12 / 8 | `ApiCheck` 由 `TitleUiTextgenScript.cs:76、122` 硬编码赋值 |
| `Title`（`MINI TALKS`）/ `Title`（`ACHIEVEMENTS`）/ `DebugText` | `MINI TALKS` / `ACHIEVEMENTS` / `DEBUG\n` | `sharedassets0.assets:15` | 8 | 源码零命中 |
| `概要` | `※TEXTGENを有効にすると…`（4 行日文） | `sharedassets0.assets:14` | 12 | TEXTGEN 预览功能说明，源码零命中 |
| `Ver` | `(C) 2017-2024 Yoshi3110 / (C) 2024 NijiiroDragon / All Right, including the copyrights…` | `sharedassets2.assets:18` | 8 | **无任何本地化组件**；`Ending Table:Ending_P910/P911` 里有等价的版权页键，但那些键是给结局字幕用的，与这个 Text 无关 → **主标题这行英文版权块固定显示英文** |
| `Text_中断` / `Text_広場` / `Text_続ける` | `タイトルにもどる` / `広場にもどる` / `ゲームをつづける` | `sharedassets2.assets:17`（`07やさしさゴシックボールド`） | 12 | 源码零命中 → **这三条永远是日文**；且 zh_additive **不替换** `07やさしさ`，字形也不会变 |
| `Text`（`Stage1`…`Stage6`，场景 `level9`） | 关卡测试场景文本 | `sharedassets0.assets:14` | 12 | 测试场景 |
| `Level (1)(2)(3)`（场景 `level154`，钓鱼小游戏） | **`LEVEL1` / `LEVEL2` / `LEVEL3`** | `sharedassets6.assets:10`（PublicPixel） | 8 | 无本地化组件、源码零命中；纯拉丁 → 插件也**不介入**（`HasCJK` 为假）→ 保持 `LEVEL1/2/3` |
| `Level` / `Phase` / `Result` / `Score (2)`（同场景） | `- Lv 1 -` / `Phase1:…` / `けっかはっぴょう` / `・:RESTART ＊:EXIT` | `sharedassets0.assets:15` | 8 | 均无本地化组件（`Result` 的 `SubGames UI Table:SoracoFishing_Result` 键确实存在且被别处引用，但**这个 Text 没挂组件**） |

> 说明：`MILD  MODE` 与 `LEVEL1/2/3` 都在**场景序列化值**里，**不是**图片，
> 因此只能靠改场景文件或运行时插件改文本；X2 两者都没做。

**启动场景 `level0` 的硬编码英文**（同一判定口径，另附源码证据）：

* 【实测】`level0` 共 9 个 Text，序列化值包括 `NOW LOADING...`、`demo setup`、`Save`、`Title`、
  `COM:`、`Enter text...`（字体分别是 `sharedassets0.assets:15/16`、
  `unity default resources:10102`），字号 8/12/30/50/60；
* 【源码 `work/decompiled/FizRpSetupScript.cs:160-176`】Steam 连接失败分支把
  **一整段日文 + 英文注意提示**（`注意！` / `Steamクライアントとの接続を確認できませんでした。…`
  / `Attention!` / `The connection with the Steam client could not be verified.…`
  / `⑫ ：CLOSE AND RESTART GAME   ⑪ ：PLAY DEMO VERSION`）**逐行拼进 `StartText.text`**，
  没有任何本地化分支 → 该提示恒为日/英双语。

### 4.2 标题菜单在「首次按键前」显示的是场景占位文本（`langBuf` 时机问题）

证据链（全部为源码/实测）：

1. `langBuf` 只有一处赋值（`TitleUiScript.cs:175`），且只在 **`Submit` 且 `nowD == 0`** 时执行；
2. `setButtons()`（:303）与 `ResetInfoText()`（:225）都读 `langBuf`；
3. 场景 `level3` 里按钮 Text 的序列化值是**占位串**：`Choice1/2/3 = ゲームをはじめる`、
   `Choice4/5/6 = ゲーム設定`（实测：6 个 Choice GameObject 的 `m_Text`）；
4. `InfoText` 的序列化值是一段日文样例：
   `サウンドテスト......ゲームできいた　アノきょくを…`（实测，字体 `sharedassets0:15`，8px）。

⇒ **结论（代码层）**：进入标题场景后、玩家第一次按确定键之前，
`langBuf == Language.Japanese`，根菜单按钮与底部滚动说明显示的是上述**日文占位文本**；
第一次按键后 `langBuf` 才被刷新为当前语言（中文时 `Language.Spanish`），
按钮与说明随即变成 `label_es` / `info_es`（已实测为中文，例如
`TitleData_lv2_0_表示設定.info_es = '画面设置……可以更改画面显示相关的设置。'`）。
【未验证】首屏那一瞬间的实际观感（是否在玩家注意前就刷新）需实机确认。

### 4.3 关卡内 HUD 的关卡名来自场景序列化字段（未本地化）

* 【源码 `work/decompiled/GameSceneManager.cs:65`】
  `nowStageText.text = "STAGE" + nowStage + " - ACT" + nowAct;` —— 硬编码拉丁，语言无关；
* 【源码 `GameSceneManager.cs:66`】`nowStageNameText.text = stageName;`，
  而 `stageName` 是**每个关卡场景各自序列化的字符串**（:21）；
* 【实测】`level10` / `level122` / `level141` 的 `GameSceneManager.stageName = '隠れたカイダン'`；
* 【实测】`grep -c 隠れたカイダン translation/zh_Hans.csv` = **0** → 该文本不在翻译表里。

⇒ 关卡内 HUD 的关卡名固定显示日文。世界地图上的关卡名（`TextData:StageSelectText_WorldName`）
是**另一套**、已本地化。

### 4.4 宝物界面字体

【实测】宝物页的两行文本 `TextTreasure`（正文）/ `TextTreasureTitle`（标题）出现在
`level3`、`level91`、`level93`–`level96`、`sharedassets7/8.assets`，
**字体恒为 `sharedassets0.assets:14`（k8x12EXS），字号 12，无 `LocalizedText`、无 `LocalizeStringEvent`**。

* 文本内容来自 `TextData:TreasureText_default / TreasureText_stage01..06`（**已本地化**，es 槽实测为中文，例如 `剑形吊坠`、`晨昏之滴`）；
* 字体不随语言切换，只能由插件全场景扫描接管（含 CJK → 换 `k8x12EXS`，字号量化 12 → 10）；
* 已知的数据侧问题**已修**：原版 `TreasureText_default` 的块序列是 `[0,0,1,2,3,4]`
  （比各 stage 表多一个重复 `language=0` 块），产物已归位为 `[0,1,2,3,4]`【实测：原版/产物对比】。
  否则中文（`num=4`）会落到默认表里空的 French 块 → 「有图无字」。
* 【未验证】12 → 10 字号变化后宝物正文的换行与卡片高度需实机目视。

### 4.5 全游戏唯一的 TextMeshPro 组件（`NPC TALK`）

【实测】全游戏 `TextMeshProUGUI` **仅 1 个**：

```
文件        sharedassets14.assets
path_id     44
GameObject  'Text (TMP)' (path_id 21)，同 GameObject 还有 NpcTalk 组件
m_text      'NPC TALK'
m_fontSize  12.0
m_fontAsset sharedassets14.assets:43（TMP_FontAsset，图集已烘焙）
```

* 它是**预烘焙的 TMP 资产**，只换 `UnityEngine.Font` 的 TTF blob **不会**影响它
  （`fonts.config.json` 里相关 TMP 源字体都是 `disabled`）；
* 插件有专门的接管路径：`ApplyTMP()`（`LangMenuPlugin.cs:1082-1113`）+
  `GetChineseTMPFont()`（:1040-1079）在运行时 `TMP_FontAsset.CreateFontAsset(f)`；
  注释里明确记录了「带 `GlyphRenderMode` 的重载在本作必定抛异常并污染 TMP 静态状态，
  因此只用默认重载（SDF，略糊但字形正确）」；
* 因为文本是纯拉丁（`NPC TALK`），`HasCJK` 为假 → **插件不会介入这个文本**，它保持原版字体与内容。
* `docs/TECHNICAL.md` §6 说这一处「故不处理」，与插件现状（有 `ApplyTMP`）**口径不一致**（见 §5.2）。

### 4.6 其他受限项（与文本相关）

| 项 | 事实 | 影响 |
| --- | --- | --- |
| 日/英模式的非整数缩放 | zh_additive 把 `k8x12EXS` 换成 10px 设计字体，而 **942 个 Text 用 size 12** 引用它（12/10 = 1.2×）；`k8x12EXL` 换成 8px，而 **49 个 Text 用 size 12**（12/8 = 1.5×） | 日/英模式下点阵字可能发虚【未验证观感】；中文档位 1:1 |
| 纯拉丁文本 | 插件按 `HasCJK` 判定，`100%`、`LIFE`、`COIN`、`Shift`、`STAGE1 - ACT1`、`LEVEL1` 等**不换字体** | 保持原版像素字体（有意为之） |
| `resources.assets:101` `PerfectDOSVGA437` | 原版被 100 个 Text 引用，字号 16×95 / 24×3 / 15 / 12；zh_additive **不替换** | 这些 Text 若显示中文会走 Unity 字形回退（宽度不一致）【未验证实际占比】 |
| 硬编码 `"？？？"` / `"???......"` | `TitleUiScript.cs:558/676` 与 `:260` 起的未解锁前缀是**代码里的字面量**（全角问号） | 与译文里的 `？？？` 风格可能不统一 |
| `Sprite Table`（6 键） | 本地化**贴图**，由 **40 个 `LocalizeSpriteEvent`**（分布在 39 个场景）引用，**不是** `LocalizeStringEvent` | 我的「未被 `LocalizeStringEvent` 引用」统计里必然出现，**不代表失效**（见 §5.2 末行） |

---

## 5. 证据与可维护性

### 5.1 本文核心结论 → 证据位置

| 结论 | 证据 |
| --- | --- |
| 5 类文本资源的数量与分布（49/55/247/5/6） | 全量扫描 `work/_additive/staging/**/*.assets` |
| 6 个 `LocFontData` 及其全部语言映射 | 解码 `sharedassets3/7/137/153.assets` 的 `LocFontData`（字节级 `src/custom_types.py` 规格） |
| 1824 Text / 1 TMP / 730 `LocalizeStringEvent` / 159 `LocalizedText` | 用 `unity_raw.mb_header` 直接解 MonoScript PPtr，不依赖类型树 |
| 168 个键、154 个被 `LocalizeStringEvent` 引用、18 个未被引用 | `SharedTableData` + 全场景 `LocalizeStringEvent.m_StringReference.m_TableEntryReference.m_KeyId` |
| 那 18 个键里 6 个是 `Sprite Table`（贴图，非失效） | `LocalizeSpriteEvent` × 40（39 个场景）的 `m_LocalizedAssetReference.m_TableEntryReference.m_KeyId` 恰好是这 6 个 |
| 其余 12 个键没有任何运行时消费者 | `Ending_P920/P930`、`MovieCanvasCamera_Stage1/Stage8`、`LeafurMegaphyll_Title`、`Title_DisplaySettings_MildMode`、`Title_SoundSettings_{Bgm,Se,Env,Voice,Master}`、`Title_ControlSettings_Vibration` 在反编译源码里 `grep -F` 全部零命中；且全项目**没有**按名查表的调用（`GetLocalizedString` / `StringDatabase` / `GetTableEntry` 均零命中） |
| `MILD  MODE` / `LEVEL1..3` / `MINI TALKS` 等为场景硬编码 | 键未被引用 + 反编译源码 `grep -F` 零命中 + `m_IsActive` 链为 true |
| `langBuf` 只在 `Submit && nowD==0` 刷新 | `work/decompiled/TitleUiScript.cs:125/175/177/225/303/625` |
| 字体替换只动 2 个 blob | 对比原版/产物的 `Font.m_FontData` sha256 与 OpenType `name` 表族名 |
| `TreasureText_default` 错位已修 | 原版 langs `[0,0,1,2,3,4]` vs 产物 `[0,1,2,3,4]` |
| 载荷不含 `level*` | `dist-additive/manifest-additive.json` 的 125 条 path |

### 5.2 文档漂移（本文与旧文档不一致处，以本文实测为准）

| 位置 | 旧表述 | 实测 |
| --- | --- | --- |
| `docs/TECHNICAL.md` §6 | 「`k8x12EXS SDF` …全游戏仅 1 处 TextMeshProUGUI 用到它，**故不处理**」 | TMP 组件数确实只有 1 个，但插件**有** `ApplyTMP` 接管路径（`LangMenuPlugin.cs:1082`）；只是该文本为纯拉丁，`HasCJK` 为假才不介入 |
| `docs/TECHNICAL.md` §6 LocFontData 表 | 列了 5 个资源 | 实际 **6** 个（漏 `LocFontData_Ending_Role`，`sharedassets137.assets:84`） |
| `plugin/LangMenuPlugin.cs:409-411` 注释 | 「本作共 134 个 `UnityEngine.UI.Text`，其中只有 1 个挂了 `LocalizedText`」 | 实测 **1824** 个 Text、**159** 个 `LocalizedText`（159 与「1」差两个数量级，注释应更新） |
| `tools/build_additive_data.py:50-59` 注释 | 「size 12 → `sharedassets0.assets:14` `k8x12EXS` ← **fusion-12px**-zh_hans」「与插件常量 `Font10Name="k8x12EXS"/SizeLarge=12` 一一对应」 | `fonts.config.json:19` 的 zh_additive 是 **`fusion-pixel-10px-proportional-zh_hans.ttf`**；插件常量是 **`SizeLarge=10`**（`LangMenuPlugin.cs:439`）。实测 blob 族名为 `Fusion Pixel 10px Prop zh-Hans` |
| `fonts.config.json:14` 的 `role` 文案 | 「方案甲：装 12px 设计字体，使 size 12 的日/英/中三种模式都 1:1 锐利」 | 与同一条目的 `fusion.zh_additive`（10px）矛盾，`role` 文案过期 |
| `docs/FINDINGS.md` §4 字体表 | 「`k8x12EXL` … Text 扫描未命中」 | 实测被 **49** 个 Text 以 size 12 引用（`src/build_patch.py:53-59` 的更正注释是对的） |
| `docs/FINDINGS.md` §4 / `src/font_usage.py` 引用数 | `resources.assets:101` 100、`sharedassets0:14` 45 等小数字 | 该工具**只扫 `*_Data/*.assets`，不含 `level*` 场景**，所以口径偏小；含场景的口径见 §2.3 |

### 5.3 可执行的只读核验命令

**命令 A — 验证「`langBuf` 只有一处赋值」（§4.2 的关键前提）**

```bash
grep -n "langBuf" work/decompiled/TitleUiScript.cs
```

期望：只有 `125:`（声明）、`175:`（唯一赋值）、以及若干 `switch (langBuf)` 读取点。

**命令 B — 验证「场景 Text 是否被本地化事件驱动」（本文 §4.1 的核心判据）**

仓库里没有现成脚本做这件事，下面这段可直接粘贴运行（只读；本次实测输出见注释）：

```bash
cd "$(git rev-parse --show-toplevel)" && PYTHONIOENCODING=utf-8 python - <<'PY'
import os, sys
sys.path.insert(0, "src")
import unity_env
from unity_env import open_env
from unity_raw import mb_header
G = os.environ["FIZRP_GAMEDATA"]  # 例：<Steam>/FizRP/FizAndTheRainbowPlanet_Data
S = unity_env.script_classes()
env = open_env(os.path.join(G, "level3")); f = list(env.files.values())[0]

def cls(o):
    try:
        g, e, sp, n, off = mb_header(o.get_raw_data())
    except Exception:
        return None
    return S.get(sp[1])

texts = {p for p, o in f.objects.items()
         if o.type.name == "MonoBehaviour" and cls(o) in ("Text", "TextMeshProUGUI")}
drv = set()
for p, o in f.objects.items():
    if o.type.name != "MonoBehaviour" or cls(o) != "LocalizeStringEvent":
        continue
    tt = o.read_typetree()
    calls = ((tt.get("m_UpdateString") or {}).get("m_PersistentCalls") or {}).get("m_Calls") or []
    for c in calls:
        drv.add((c.get("m_Target") or {}).get("m_PathID"))
print("level3 Text=%d 被本地化事件驱动=%d" % (len(texts), len(texts & drv)))
PY
# 本次实测输出: level3 Text=119 被本地化事件驱动=46
# 把 level3 换成别的场景名（level2/level9/level154…）即可逐场景核对 §4.1 的表。
```

配套的两条辅助核验：

```bash
grep -rlF "MILD"  work/decompiled/   # 反编译源码里应为空 → 佐证 MILD MODE 是纯场景序列化值
PYTHONIOENCODING=utf-8 python src/font_usage.py   # 字体引用（口径：仅 *_Data/*.assets，不含场景）
```

**命令 C — 验证字节级编解码与文本类对象数量（§3.2 的 362 个对象）**

```bash
PYTHONIOENCODING=utf-8 python src/verify_codecs.py
```

本次实际输出：

```
round-trip OK: {'AutoTalk_Data': 247, 'TextData': 55, 'LocFontData': 6,
                'DamageTalk_Data': 5, 'Title_Data': 49} total 362
failures: 0
```

**命令 D — 对比原版与产物的字体 blob（§2.3）**

```bash
PYTHONIOENCODING=utf-8 python src/fonts.py    # 提取到 work/fonts/（会写文件，慎用）
```

更安全的只读替代：直接读 `m_FontData` 的长度与 `sha256`（本文做法），
或在产物目录上用 `fonts.read_name_table()` 读族名，期望出现
`Fusion Pixel 10px Prop zh-Hans` / `Fusion Pixel 8px Prop zh-Hans`。

> ⚠️ 注意：`src/font_usage.py` / `src/verify_codecs.py` 读的是 `src/unity_env.py` 里的
> `GAME_ROOT`（默认 `<Steam>/FizRP`，可用 `FIZRP_ROOT` 覆盖），即**已安装补丁后的游戏目录**。
> 要核对原版，先设 `FIZRP_ROOT` 指向 `work/_additive/staging`（该目录不含 `Managed/`，
> 类型树生成器仍需游戏目录，故建议用本文的「显式传文件路径 + `unity_env` 补丁」方式）。

### 5.4 未验证 / 不确定项（明确列出，不做结论）

1. **实机可见性**：本文判定「无本地化组件」的 Text，其 GameObject 自身与祖先 `m_IsActive`
   都为 true，但**是否被脚本在运行时整体隐藏/移出屏幕**只能实机确认——
   例如 `概要`、`Placeholder`、`ApiCheck` 属于 TEXTGEN 预览功能，可能在正式流程中不出现。
2. **`langBuf` 首屏窗口的时长**：代码层确定「首次 Submit 前为 Japanese」，
   但玩家实际能看到的时长（是否只在 1 帧内）未验证。
3. **`Title_Copy_Default` 的落点**：`Copy`（`©2024 にじいろドラゴン`）挂了
   `LocalizeStringEvent` → `Title Contents Table:Title_Copy_Default`，
   产物 es 值为 **`©2024 にじいろドラゴン（虹色龙）`**；`Copy_CS` →
   `Title_Copy_Consumer` = **`© 2024-2025 にじいろドラゴン（虹色龙）开发，\nForever Entertainment S. A. 发行。`**
   ——即**保留日文公司名 + 中文括注**。
   对比：`Ending Table:Ending_P920`（`にじいろドラゴン`）同样是
   **`にじいろドラゴン（虹色龙）`**；而 `Ending_P910` / `Ending_P911` 的整段
   `© 2017-2024 Yoshi3110 / © 2024 NijiiroDragon / All Rights…` 在产物里
   **与日文原文逐字相同（未翻译）**【实测 CSV 对比】。
   另外 `Ver` 这个场景 Text 的那段英文版权块则完全未本地化（§4.1）。
   三处风格是否要统一属于产品决策，本文不下判断。
4. **TMP 与日/英模式**：插件对 TMP 的接管条件是 `HasCJK`；`NPC TALK` 是纯拉丁，
   因此它的字体在两个语言下都不变，这一点是从代码读出的事实，未做实机比对。
5. **`Sprite Table` 的 6 个键**：本文把它们计入「未被 `LocalizeStringEvent` 引用」，
   但它们由 **40 个 `LocalizeSpriteEvent`**（39 个场景）实际使用，服务于本地化贴图，
   **不属于**文字覆盖缺口。
6. **`locTalkDatas` 的块存在性**：补丁在缺块时会新建并用 ja 列表**深拷贝**补长；
   本文核对了产物里 es 槽的写入结果，但**没有**逐个资源验证「补长后每行都有值」
   （该性质由 `src/build_patch.py` 的覆盖率对账 `written == expected` 间接保证）。
7. **插件对拉丁/日文混排文本的接管**：`HasCJK` 命中但混有假名的文本（如结局作者名
   「にじいろドラゴン（虹色龙）」）会换成 Fusion 字体——该字体同时含假名与汉字，
   代码注释如此声明，本文未做字形覆盖实测。

---

## 附录 A. 关键常量速查

| 常量 | 值 | 位置 |
| --- | --- | --- |
| 中文槽位 | `4`（`Language.Spanish`） | `tools/build_additive_data.py:41` |
| 中文 locale | `es` | 同上 :42 |
| 字体 profile | `zh_additive` | 同上 :43 |
| es 槽字体映射 | `{8: (sharedassets3.assets, 133), 12: (sharedassets0.assets, 14)}` | `src/build_patch.py:78-79`、`tools/build_additive_data.py:60-61` |
| 插件字号档 | `SizeSmall=8`（宿主 `k8x12EXL`）/ `SizeLarge=10`（宿主 `k8x12EXS`） | `plugin/LangMenuPlugin.cs:436-439` |
| 第三项 GameObject 名 | `選択肢 (2)`（兼容无空格写法） | 同上 :76-77 |
| 强制 10px 的对象 | GameObject 名 `InfoText`、文本以 `©2024` 开头 | 同上 :487-499 |
| 中文写入的 bundle | `localization-string-tables-spanish(es)_assets_all.bundle` | `tools/build_additive_data.py:65` |
| 键表 bundle | `localization-assets-shared_assets_all.bundle` | `src/loc_common.py:26` |
| 载荷 loader 路由 | `winhttp.dll` / `doorstop_config.ini` / `.doorstop_version` / `changelog.txt` / `BepInEx/` | `tools/build_additive_payload.py:80-82` |
| 未本地化键数 | 18（含 6 个 Sprite 键） | §1.1、§5.1 |

## 附录 B. 逐场景文本组件数量（抽样实测）

| 场景 | 文本组件数 | 被 `LocalizeStringEvent` 驱动 | 说明 |
| --- | --- | --- | --- |
| `level0` | — | — | 启动场景（`FizRpSetupScript`） |
| `level2` | 24 | 2 | 语言选择（`LanguageSetting`，path_id 177） |
| `level3` | **119** | 46 | 标题 / 暂停面板 / 设置界面（`TitleUiScript` path_id 1070） |
| `level9` | 49 | 15 | 关卡测试场景（含 75px 大字测试文本） |
| `level10` | 5 | 0 | 关卡 HUD（`STAGE1 - ACT1` 占位 + `stageName`） |
| `level154` | 14 | 3 | 钓鱼小游戏（含 `LEVEL1/2/3`） |
| 全游戏合计 | **1824**（+1 TMP） | 730 个组件 / 154 个键 | 159 个场景 + 161 个 `.assets` |
