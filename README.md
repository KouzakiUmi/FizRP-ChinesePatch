# FizRP-Localization

**Fiz And The Rainbow Planet**（`E:\Steam\steamapps\common\FizRP`，Unity 2021.3.45f1 / Mono）
的解包、文本提取、翻译回写与像素字体替换工具链。

替代字体使用 [TakWolf/fusion-pixel-font](https://github.com/TakWolf/fusion-pixel-font)
（OFL-1.1，随 `dist/fonts/source/OFL.txt` 分发，务必保留署名）。

---

## 快速开始

```bash
pip install UnityPy TypeTreeGeneratorAPI

python src/fonts.py work/fonts/original work/fonts/info.json   # 1. 提取 17 个内嵌字体
python src/extract_text.py                                     # 2. 提取全部文本 -> translation/
python src/font_patch.py dist/FizAndTheRainbowPlanet_Data      # 3. 生成替换字体后的游戏数据
python src/apply_text.py --lang-slot 5 --out dist/FizAndTheRainbowPlanet_Data  # 4. 回写译文
python tools/install.py --dry-run                              # 5. 预览安装（不带 --dry-run 即备份并覆盖）
```

## 目录结构

```
src/
  unity_env.py        UnityPy 环境封装 + 两处关键 bug 修复（见 docs/FINDINGS.md）
  unity_raw.py        序列化字节的最小 raw 解析器
  custom_types.py     游戏自定义 ScriptableObject 的字节级编解码器（已做往返校验）
  fonts.py            字体提取 + OpenType name 表解析
  font_usage.py       统计每个 Font 资源被哪些 Text 组件引用
  extract_text.py     文本提取 -> translation/*.csv + work/text_index.json
  apply_text.py       译文回写
  font_patch.py       字体替换（生成到 dist/，不动原游戏）
  verify_codecs.py    362 个自定义对象「解码→重编码」字节级回归测试
  loc_common.py       语言表 / bundle 名等常量
translation/          翻译工作表（CSV，UTF-8 BOM，Excel 可直接打开）
work/                 中间产物：原始字体、字体元数据、文本索引、字体映射
dist/                 可直接覆盖游戏的产物
tools/install.py      备份 + 安装
fonts.config.json     字体替换映射表（可改）
```

## 文本工作表

`translation/ALL.csv` 列结构沿用游戏自带 `TextExporter` 编辑器脚本的列名：

| 列 | 说明 |
| --- | --- |
| `id` | 稳定标识，回写时用来定位 |
| `kind` | `localization` / `TextData` / `AutoTalk` / `Title` / `DamageTalk` |
| `file`, `path_id` | 所在 `.assets` 文件与对象 path_id |
| `source`, `index`, `path` | 人类可读定位（表名 / 资源名 / 数组下标） |
| `comment` | 说话人、等待时间等上下文 |
| `text_ja`, `text_en_machine`, `text_en`, `text_fr`, `text_es` | 游戏现有五种语言 |
| `text_zh_Hans` | **留空，待翻译** |

翻译时只填 `text_zh_Hans`，然后：

```bash
python src/apply_text.py --column text_zh_Hans --lang-slot 5 \
    --out dist/FizAndTheRainbowPlanet_Data
```

`--lang-slot` 对应 `Language` 枚举（0=ja 1=en_machine 2=en 3=fr 4=es，5=新增中文）。

## 字体替换

`fonts.config.json` 列出每个 `<文件>:<path_id>` 游戏字体到 fusion-pixel-font 的映射，
支持两套方案：

* `--profile default`：日文用 `fusion-pixel-12px-proportional-ja`，拉丁用 `-latin`；
* `--profile zh_hans`：CJK 字体改用 `fusion-pixel-12px-proportional-zh_hans`。

游戏里所有字体都是**动态** `UnityEngine.Font`（整个 TTF 存在 `m_FontData` 里），
所以直接替换这段字节即可，无需重建图集。

## 已知限制

* Unity Localization 的 5 张 `StringTable` 在 Addressables bundle 内，新增 `zh-Hans`
  语言需要同时改 `catalog.json` 与 `Language` 枚举（DLL），见 `docs/FINDINGS.md`。
* `sharedassets14.assets` 里的 `k8x12EXS SDF` 是 TextMeshPro 字体资源，图集已烘焙，
  只换源 TTF 不生效；游戏里仅 1 处 `TextMeshProUGUI` 用到它。
