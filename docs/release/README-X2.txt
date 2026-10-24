Fiz 与彩虹星球 简体中文补丁 v{{VERSION}}（X2）

【工作方式】
中文复用 es / Language.Spanish=4 槽位。构建时把文案、字体和贴图写入资源，
安装时复制这些资源；随包 BepInEx 插件开放第三语言选项并处理字体、字号和局部像素定位。
不修改游戏 DLL，不替换 level* 场景。

不是完全隔离的中文资源层：日英对白/字符串槽不被中文覆盖，但共享字体会影响其它语言，
en/es 共用部分图片，因此英文模式也可能显示中文图片。

【包含什么】
117 个载荷文件：101 数据（98 assets、2 bundle、catalog）+ 16 loader/插件。
1,364 条非空译文；13 张中文替换纹理，另保护共享图集中的 10 个 JP 专用切片。
不分发 JP 专用图片 bundle、XML API 文档和更新日志；保留运行时 DLL 和许可。
包根有安装入口、清单、说明、项目/第三方/字体许可；这些不是游戏载荷。

【本版变更】
全量审校并重写 202 条译文，消除日式逗号省略语义与直译腔，按角色性格与上下文还原中文语气。
保留 v1.2.8 大字号过场标题策略、13 张中文纹理与 10 个 JP 专用切片保护、117 文件精简载荷。
保留 v1.2.7 暂停提示的绝对横向补偿，不重复移动模板和实例。
设置硬编码等覆盖缺口见 KNOWN-ISSUES.txt。
本版修订译文排版、大标题及 JP 片区恢复需实机复核，离线验证不代表全流程画面验收。

【首次安装】
关闭游戏并备份已有 MOD。
EXE：双击 FizRP-ChinesePatch.exe，无需 Python。
ZIP：完整解压后双击 install.bat；命令行需 Python 3.8+。
未找到游戏时，选择 FizAndTheRainbowPlanet_Data 的上一级游戏根目录。
语言选择画面选第三项“中文”；已正确保存中文的存档无需重置。

命令行（ZIP 包根）：
  python patch_tool.py check
  python patch_tool.py install --game-dir "<游戏根目录>"
  python patch_tool.py verify --game-dir "<游戏根目录>"
  python patch_tool.py uninstall --game-dir "<游戏根目录>"

【从 v1.2.7 或更早版本升级】
先使用旧版安装器卸载并还原，再安装本版，不建议直接覆盖。
新包不再带旧版曾改写的 JP bundle 和部分 loader 文档；覆盖安装不会自动还原退出清单的文件。
保留 _FizRP_original 和 _FizRP_backup_<时间戳>，不要为清理资源删除存档。

【完整性、备份与卸载】
安装前检查游戏门禁和全部载荷哈希；损坏、缺失、多余文件会阻止写入。
--yes 只确认现场警告，不跳过载荷检查。
数据首次备份到 _FizRP_original，另保留滚动备份；已有 loader 冲突需自行备份。
新存档不存在时才可播种 Language=4，不默认覆盖已有存档。
卸载优先还原首次备份，缺少时回退滚动备份；保留其它用户插件、备份及存档。
EXE 选择“卸载并还原”，ZIP 可双击 uninstall.bat。

【许可】
项目：LICENSE（CC BY-NC-SA 4.0）；第三方：THIRD-PARTY-NOTICES.txt；
字体：LICENSE-fusion-pixel-font.txt（SIL OFL 1.1）。分发必须保留。
原游戏及其素材权利归原权利方，本项目非官方且仅供非营利使用，请支持正版。
