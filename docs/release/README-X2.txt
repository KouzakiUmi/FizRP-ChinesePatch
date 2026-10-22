Fiz 与彩虹星球 简体中文补丁 v{{VERSION}}（追加式 X2）

【这个包是什么】
  X2 追加式：中文写入游戏自带的 es（Language.Spanish = 4）槽位，
  日文/英文原样保留；语言菜单新增第三项「中文」。
  不修改游戏的 DLL 与场景文件，文本/字体/贴图由随包插件在运行时加载。

【包含什么】
  payload/                    125 个文件
    *.assets                  数据文件（文本、字号、字体、贴图）
    StreamingAssets/aa/...    es 串表 bundle + catalog.json
    winhttp.dll / BepInEx/    追加式 loader（随包，无需另装）
  LICENSE                     项目许可证（CC BY-NC-SA 4.0）
  THIRD-PARTY-NOTICES.txt     第三方组件声明（BepInEx/Doorstop/Harmony 等）
  LICENSE-fusion-pixel-font.txt  字体授权（SIL OFL 1.1）
  安装后游戏根目录会多出 BepInEx/、winhttp.dll、doorstop_config.ini、.doorstop_version；
  被覆盖的原文件会备份到游戏根目录 _FizRP_backup_<时间戳>/。

【安装】
  exe 版（推荐，不需要 Python）：
    双击 FizRP-ChinesePatch.exe，按图形界面提示操作。
  zip 版（需要本机 Python 3.8+）：
    双击 install.bat；卸载双击 uninstall.bat。

  安装器会自动在 Steam 库中查找游戏；找不到时会提示手动指定游戏根目录
  （FizAndTheRainbowPlanet_Data 的上一级）。安装前会比对版本门禁文件，
  不符时告警并要求确认。写入前还会强制校验完整清单与所有载荷哈希，损坏时禁止安装。

【装完之后】
  首次启动游戏时，语言选择画面请选第三项「中文」。
  已有存档：把存档中的 Language 值设为 4（es 槽位 = 本补丁的中文槽位）；
  存档位置：%USERPROFILE%\AppData\LocalLow\<公司名>\<产品名>。

【本版特点】
  修复暂停菜单按键提示在启动、重选中文或返回标题后偶发模糊的问题。
  仅对三条已挂载的中文暂停提示做绝对横向补偿，不改字体、字号和纵坐标，避免模板与实例重复位移。
  正式包不含临时诊断插件；已验证重复进入菜单，其他分辨率和屏幕模式仍需按实机核对。
  保留冷启动主菜单中文设置标签不显示、重新选择中文后字号偏小的修复。
  主菜单及设置子页中文统一 10px，并为文字保留足够高度；对白和 HUD 不套用此规则。
  已正确使用中文的存档无需修改或重置，也不再需要每次启动后重新选择中文。
  字体双档：k8x12EXS -> fusion-pixel-10px、k8x12EXL -> fusion-pixel-8px
  中文写入 es 槽位，日/英原样保留
  依赖 BepInEx（随包 winhttp.dll + BepInEx/ + 插件），无需手动配置
  含 16 张汉化贴图

【卸载】
  exe 版：在安装器界面点「卸载并还原」。
  zip 版：双击 uninstall.bat。
  两者都优先从 _FizRP_original 首次备份还原；缺少时回退最新滚动备份。
  移除随包 loader，保留其它用户插件、存档与备份目录。

【字体授权】
  SIL OFL-1.1，见 LICENSE-fusion-pixel-font.txt，分发时必须保留。
