#!/bin/sh
# ToolBox 启动脚本（Linux / 统信 UOS）
#
#   ./run.sh                  启动 Web UI
#   ./run.sh doctor           环境自检
#   ./run.sh todo list        调用工具命令

cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
    echo "未找到 python3，请先安装 Python 3。" >&2
    exit 1
fi

exec python3 src/main.py "$@"
