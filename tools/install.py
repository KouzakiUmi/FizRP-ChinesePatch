"""X2 安装快捷入口；所有校验、备份和路由均由 patch_tool 实现。"""
import sys
from patch_tool import main

if __name__ == "__main__":
    raise SystemExit(main(["install"] + sys.argv[1:]))
