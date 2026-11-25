# 项目架构账本

## 目录与职责

- `tools/patch_tool.py` 是 X2 安装、校验、备份、卸载和存档播种的唯一运行时入口。
- `tests/` 保存隔离临时目录回归测试；安装器测试不得访问真实 Steam 库或用户存档。
- `docs/` 与根目录 `README.md` 记录安装方式、运行时约束和发布说明；发布模板位于 `docs/release/README-X2.txt`。
- `dist-additive/` 是构建产物与权威载荷输入，不在此处维护第二套安装逻辑。

## 已确认设计

- 安装器只支持 X2 追加式载荷；游戏资源写入 `_Data`，loader/插件按清单路由到游戏根目录。
- 存档播种只在目标存档不存在时执行，`FIZRP_SAVE_ROOT` 是隔离测试的覆盖入口。
- Windows 使用用户 `AppData/LocalLow`；Linux Steam Proton 根据游戏所在 `steamapps/common/<install_dir>` 的 `appmanifest_*.acf` 读取 appid，并将存档定位到对应 `steamapps/compatdata/<appid>/pfx/drive_c/users/steamuser/AppData/LocalLow`。
- Linux 路径无法同时确认 Steam 库与 appmanifest 时，不向宿主机 HOME 写入伪存档，安装结果记录提示并由玩家在游戏语言选择画面完成设置。

## 维护约定

- 修改存档路径策略时只扩展 `tools/patch_tool.py` 的现有数据流，并同步更新 `tests/test_x2.py`、根 README 与发布说明。
- 新增平台路径必须提供临时目录回归测试；测试通过后再考虑构建或发布包更新。
- 不在 GUI、批处理入口或发布副本中复制存档定位逻辑。
