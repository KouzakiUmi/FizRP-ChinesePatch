# 游戏资源结构与复核结论

当前说明对应 v1.2.13；实现细节以 [TECHNICAL](TECHNICAL.md) 为准，文本/图片逐类映射以 [TEXT-MAPPING](TEXT-MAPPING.md) 为准。此文件不记录早期方案的推演或把局部扫描数字当全游戏数量。

## 游戏与资源边界

- Unity 2021.3.45f1，Mono 后端；Managed 程序集用于类型识别和本地构建，不随补丁替换。
- BuildSettings 列出 159 个场景，文件为 `level0` 等无扩展名场景文件，**不是 `level*.assets`**。
- 其它序列化文件包括 `sharedassets*.assets`、`resources.assets` 和 `globalgamemanagers.assets`，流式资源另存 `.resS` 等。
- 本地化通过 Addressables bundle 与 catalog 组织，另有场景字段、脚本硬编码和图片文字；不存在一个能覆盖所有玩家可见文案的单一翻译表。

## 2026-10-23 复核口径

| 项目 | 结果 |
| --- | --- |
| 扫描范围 | 159 场景 + 161 个其它序列化文件，共 320 |
| 文本组件 | 1,824 Text + 1 TextMeshProUGUI |
| 本地化事件 | 730 LocalizeStringEvent，40 LocalizeSpriteEvent |
| 随语言字体组件 | 159 LocalizedText，仅管字体/字号/行距 |
| 自定义对象 | 247 AutoTalk、55 TextData、49 Title、5 DamageTalk、6 LocFontData，共 362 |
| 工作表 | 1,411 行，1,364 条非空；47 行源文为空 |
| 纹理元数据 | 542 项，名称筛选候选 93 项；未对全部图像 OCR |
| 原版互证 | staging 与首次备份重叠的 102 个文件一致；三项游戏门禁匹配 |

自定义对象及五张 StringTable 的已登记行无提取遗漏，但不能以此排除场景硬编码。37 个 CanvasCamera 的完整生成类型树读取受限，相关语言分支以反编译源码和可解析的 Sprite/表结构交叉核对；没有声称完整读取这些对象的所有字段。

## 文本系统

五张文本表共 162 键：Ending 65、UI 34、Title Contents 31、Message 18、SubGames UI 14；另有 Sprite Table 六个图片键。自定义文案采用语言块、字段后缀或每语言一份资源三种形式。

语言枚举为 Japanese=0、English_Machine=1、English=2、French=3、Spanish=4。现有 es 文案覆盖稀少且菜单原本不可选，补丁复用它，而不是新增 zh-Hans 枚举。

小游戏/鉴赏/异常提示中存在旁路；温和模式、震动与五个声音标签虽然有中文表键，实际 Text 没接入。完整列表见 [TEXT-MAPPING 的覆盖边界](TEXT-MAPPING.md#6-已知漏接与旁路)。

## 字体不是完全按语言隔离

字体配置会替换共享 Font blob。当前只替换 k8x12EXS 与 k8x12EXL，为 10px/8px Fusion Pixel；引用它们的其它语言也受影响。

普通中文最终字号由插件量化；LocFontData 的序列化 size=12 与 10px blob 设计尺寸不同。大标题原字号 24，不应被普通小字号策略压缩。首次到达新世界的中央大标题来自 UI StringTable/Text，而普通进入关卡横幅来自 Sprite，两者不能混为一谈。

早期“只有 134 个 Text”“EXL 无 Text 引用”“只有一个 LocalizedText”的小范围结论不适用于上述全量口径。

## 图片要区分纹理与切片

- 历史工单 16 张，不等于当前需要分发 16 张：三个 JP 专用整纹理已退出中文回灌。
- 四张共享图集同时含 JP 与非日语切片；本版恢复其中十个 JP 切片，仍保留中文使用区域。
- es/en 的图片引用相同，中文覆盖共享纹理也改变英文模式的图片；恢复日语片区不能证明英文原图完全保留。
- 图集名称含日文并不意味着整图只由 JP 使用；删共享图或 shared bundle 会丢有效中文资源。

## 构建与读取注意事项

[unity_env.py](../src/unity_env.py)包含 UnityPy 1.25.4 的本游戏兼容层；import 有进程级副作用。五类自定义对象使用[手写编解码规格](../src/custom_types.py)，不依赖生成树读取全部字段。

四字节对齐、PPtr 的外部表下标、DamageTalk 各语言列表不等长、TreasureText_default 重复语言块，均需按实际结构处理。不能只看编码往返，也不能仅搜索译文子串证明字段正确。

当前发行只维护 X2；关于新增 locale、纯运行时翻译或其它替换路线的早期设想不是当前实现。变更游戏版本后，应重新核对门禁、对象清单、场景消费者和美术输入，而不是沿用历史扫描数字。
