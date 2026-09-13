#!/bin/sh
# ToolBox 启动脚本（Linux / 统信 UOS）
#
#   ./run.sh                  启动后台服务（不弹浏览器，用书签访问）
#   ./run.sh --open           启动服务并自动打开浏览器窗口
#   ./run.sh status           查看服务状态
#   ./run.sh stop             关闭后台服务
#   ./run.sh doctor           环境自检
#   ./run.sh todo list        调用工具命令
#
# 服务跑在脱离终端的独立进程里，所以关掉这个终端不会把它带走。

cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo "未找到 python3，请先安装 Python 3。" >&2
    exit 1
fi

exec python3 src/main.py --detach "$@"
