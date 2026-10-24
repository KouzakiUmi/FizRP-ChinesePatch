# 文本、字体与图片映射

本文件描述 v1.2.9 实际维护的数据路径及覆盖边界，不承诺所有玩家可见文案都已本地化。安装、升级见 [README](../README.md)，实现契约见 [TECHNICAL](TECHNICAL.md)。

## 1. 语言选择与内容来源

```text
Japanese=0, English_Machine=1, English=2, French=3, Spanish=4, Max=5
中文使用 Spanish=4 / locale es；不是独立 zh-Hans locale。
```

游戏把存档语言映射为 Unity Localization locale，又通过 locale 名称返回 Language 枚举；插件开放既有第三选项，使其落到 Spanish 分支。仅增加翻译表而不开放菜单，玩家无法正常选中中文。

文本内容与字体切换是两套机制：`LocalizeStringEvent` 更新字符串，`LocalizedText` 只设置字体、字号、行距；后者不能作为“文案已翻译”的证据。

## 2. 已纳入主表的五类文案

[译文主表](../translation/zh_Hans.csv)与本地提取索引使用以下 ID。写入规则见 [build_patch.py](../src/build_patch.py)，提取规则见 [extract_text.py](../src/extract_text.py)。

| 系统 | ID | 行数 | 中文落点 / 运行时选择 |
| --- | --- | --- | --- |
| StringTable | localization:表名:键名 | 162 | es bundle 的 m_Localized，由 LocalizeStringEvent 消费 |
| AutoTalk_Data | AutoTalk:资源名:下标 | 734 | locTalkDatas[language=4]，保留说话人/等待/事件结构 |
| DamageTalk_Data | DamageTalk:列表:角色下标:行下标 | 238 | DamageTalkData_es 内对应列表，不改 ja/en 资源 |
| Title_Data | Title:资源名:label/info/infoDisable | 147 | 字段后缀 _es，由标题菜单脚本选择 |
| TextData | TextData:资源名:下标 | 130 | textDatas[language=4].strings，按语言查块 |
| 合计 | | 1,411 | 1,364 条非空译文；47 行源文为空 |

自定义资源共 247 AutoTalk、55 TextData、49 Title、5 DamageTalk，另有 6 个字体配置资源。2026-10-23 的全量扫描在现有提取文件清单之外没有发现新增的这些对象；未来游戏版本变化后仍应重新普查，不能只验证旧索引。

### 字符串表

| 表 | 键数 | 主要内容 |
| --- | --- | --- |
| Ending Table | 65 | 结局字幕、署名与版权 |
| UI Table | 34 | 暂停、角色卡、GameOver、过场标题 |
| Title Contents Table | 31 | 标题/设置/语言选择 |
| Message Table | 18 | 教学消息 |
| SubGames UI Table | 14 | 莉芙、钓鱼小游戏 |

以上 **162 个文本键**与另外 **6 个 Sprite Table 图片键**分开统计。不能把图片键当未翻译文本，也不能把 SharedTableData 的键表当译文。

字符串条目的 m_Id 必须经 SharedTableData 反查；各 locale 条目集合并不相同，写入时缺键须补齐，而不是按数组位置替换。

### ScriptableObject 的运行时消费者

- Title_Data 的 label/info/infoDisable 由标题菜单脚本按语言缓存选择；根菜单刚加载时仍可能短暂保留场景初始值，不能只凭资源值断言首屏时序。
- 世界地图关名、宝物说明、部分暂停文本来自 TextData；这些 Text 没有 StringEvent 也可能正确显示中文。
- 对白与剧情来自 AutoTalk；DamageTalk 是独立的每语言资源，不是 AutoTalk 的同一个数组。
- 富文本标签、内联按键符号和换行会影响布局/图标位置。[机械检查](../src/check_translation.py)保护这些结构，但不替代实机排版验收。

## 3. 过场大标题不是 Sprite 横幅

| 路径 | 载体 | 本版策略 |
| --- | --- | --- |
| 首次到达新世界的中央标题 | UI Table:MovieCanvasCamera_Stage2…7 → Text | 原字号 24，首行 `<size=16>`；保留大字号 |
| 普通关卡进入横幅 | stageCallPanels_Upper / _en → Sprite | Japanese 分支用 JP 图，中文走非日语图 |
| 世界地图关名 | TextData:StageSelectText_WorldName | 由语言块选择，不是修改场景初始字符串 |
| 旧 GameSceneManager HUD 关名 | 场景 stageName 字段 | 部分场景保留旧路径，需要实际启用情况确认 |

字号处理只影响字体/排版，不会替代文本翻译。大标题修复由 [FontSizePolicy](../plugin/FontSizePolicy.cs) 与[插件接入](../plugin/LangMenuPlugin.cs)共同实现：普通 8/10 档保持，超过 12 的字号不再被全局压缩。新版本的实际过场观感仍需复测。

## 4. 字体映射与限制

| 配置 | 作用 |
| --- | --- |
| k8x12EXS / sharedassets0:14 | 共享 Font blob 替换为 Fusion Pixel 10px zh-Hans |
| k8x12EXL / sharedassets3:133 | 共享 Font blob 替换为 Fusion Pixel 8px zh-Hans |
| LocFontData 的 es 字体引用 | 按默认 8/12 档映射，存在外部引用不可用时的回退 |
| 插件普通字号 | 不大于 8→8，9～12→10；大字号保留 |
| TitleCanvas / InfoText 等既有专门策略 | 仍可强制 10px；主菜单补高度，非全游戏统一高度 |
| 三个暂停页脚提示 | 仅对挂载的中文实例设置绝对横向偏移 |

6 个 LocFontData：MainTalk、TitleControllerSetting、TitleInfo、Opening、Ending_Role、LeafurMegaphill_Sub。默认值/序列化 size=12 与 10px blob 是不同层的量，最终普通中文字号靠运行时策略对齐。

2026-10-23 扫描有 1,824 Text、1 TMP、159 LocalizedText，不能继续沿用早期局部扫描的“134 Text / 1 LocalizedText”描述。插件存在 TMP 接管路径，但唯一 TMP 的初始串 NPC TALK 为纯拉丁，不因此被中文接管。

共享字体 blob 的替换也影响其它语言；纯拉丁文本通常不被插件主动替换，但它若引用了已替换的共享 Font，底层字形仍可能变化。不要承诺日英视觉完全原样。

## 5. 图片键、纹理与切片

[图片策略](../tools/image_patch_policy.py)按运行时资源身份识别，不靠 IMG 编号或文件名是否含日文判断。

| 工单 | 内容 | v1.2.9 正式回灌 |
| --- | --- | --- |
| IMG-01 / IMG-02 | 非日语主标题 / 莉芙标题 | 保留中文替换 |
| IMG-03 | SoracoFishingLogo | 保留非日语切片；恢复 JP `_0` 切片 |
| IMG-04 | 必杀禁止牌 | 保留非日语切片；恢复 JP `_0` 切片 |
| IMG-05 | 暂停区门牌 | 保留非日语切片；恢复 JP `_0` / `_Hiroba` |
| IMG-06 | JP 关卡开始横幅 | 排除整纹理 |
| IMG-07 | 非日语关卡开始横幅 | 保留中文替换 |
| IMG-08 | 角色名图集 | 保留非日语切片；恢复 6 个 `_jp_` 角色名 |
| IMG-09～14 | 宝物/HUD/结算/重播等 | 保留既有替换 |
| IMG-15 / IMG-16 | JP 主标题 / 莉芙标题 | 排除整纹理 |

历史美术工单仍为 16 张；**中文运行时替换只有 13 张**，位于 sharedassets3、sharedassets13、shared 图片 bundle 三个宿主文件。JP 专用图片 bundle 不分发，不从游戏里删除其原版。

10 个 JP 切片按实际 Sprite textureRect，从适配版本的原版 PNG 恢复 RGBA；不通过“删除所有含日文名的图片”清理，也不重新绘制或翻译这些切片。图片回灌报告分别记录排除项、保护区域和序列化回读结果。

### en 与 es 仍共用图片

es Sprite Table 的六个资源引用与 en 相同：非日语主标题、两块门牌、非日语莉芙标题、必杀禁止、钓鱼标题。中文图片覆盖这些共享纹理后，英文也会看到相同图片；这不是字符串槽覆盖，但确实影响英文画面。

## 6. 已知漏接与旁路

### 已有中文但没有绑定到对应标签

| 表键后缀 | 现有译文 | 场景/脚本旁路 |
| --- | --- | --- |
| Title_DisplaySettings_MildMode | 温和模式 | MILD MODE |
| Title_ControlSettings_Vibration | 震动 | VIBRATION : ON/OFF |
| Title_SoundSettings_Master | 主音量 | MASTER |
| Title_SoundSettings_Bgm | 背景音乐 | BGM |
| Title_SoundSettings_Se | 音效 | SE |
| Title_SoundSettings_Env | 环境音 | ENV |
| Title_SoundSettings_Voice | 语音 | VOICE |

本版没有为这些旁路新增文案补丁。其它设置项如 ICON TYPE、TYPE A/B、TEXTGEN 说明/输入提示，也不能以主表覆盖率证明已汉化。

### 不在主表完整覆盖范围内

- 莉芙标题页的日文开始/键鼠说明，及钓鱼标题页的 LEVEL1/2/3 等固定文字。
- 音乐鉴赏的 52 条 title/titleEng 元数据：非日语走英文或回退原文，没有独立中文字段；曲名是否保留原文需按翻译范围决定。
- 剧场 9 条 contentString：直接写 OPENING、SORACO…ENDING 等文字，无语言分支。
- Steam 连接异常、外部 MOD 确认、计时挑战恢复等启动提示：代码直接拼日文/英文。
- 隐藏模板、测试/演示场景中的日文只列为候选；是否出现在正常流程需额外判断。

### 不能简单删除的“未引用”与“初始日文”

全量扫描的 730 个 StringEvent 中，725 个引用可在当前文本表中解析；5 个异常引用在旧测试场景。12 个文本键没有静态场景事件引用，但不能仅凭该结果删除：还需排除动态消费者、同义标题以及特殊流程。

同样，Text 的初始值可能被 SO 或游戏代码覆盖；判断漏译要同时追踪事件目标、脚本赋值和启用条件。`HasCJK` 只控制字体接管，不会把日文自动翻译成中文。

## 7. 验证与数量口径

2026-10-23 的复核覆盖 159 个 BuildSettings 场景、161 个序列化资源文件；重新发现的自定义文本和 StringTable 非空行没有旧索引之外的遗漏。54 项隔离回归覆盖安装流程、字号范围、整图过滤、Sprite 坐标与原版 RGBA 恢复、loader 文档过滤；不等同于游戏全流程验收。

[verify_patch.py](../src/verify_patch.py)按目标文件/对象/语言/下标回读 1,364 条；[verify_codecs.py](../src/verify_codecs.py)校验 362 个自定义对象；[package_additive.py](../tools/package_additive.py)校验包内容与清单。图片需要另查 13 纹理及 10 JP 切片，不能用译文检查替代。

本版的过场大标题、JP 图集恢复、各分辨率及条件提示未在本轮做完整实机验收。已知漏项和待验项分列于[随包问题清单](release/KNOWN-ISSUES-X2.txt)，不再把已确认缺口统称为“只是证据不足”。
