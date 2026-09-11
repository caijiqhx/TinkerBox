"""CLI 承载层的输出辅助。"""

from __future__ import annotations

import sys

from core import registry

USAGE = """ToolBox —— 个人工具箱

用法：
  python3 src/main.py                     启动 Web UI（默认）
  python3 src/main.py <工具> <子命令> ...   直接调用某个工具的命令行功能
  python3 src/main.py doctor              环境自检（推荐在目标机上先跑一次）
  python3 src/main.py help                显示本帮助

选项：
  --ui=web|cli|none        指定界面承载方式（环境变量 TOOLBOX_UI 亦可）
  --port=端口              指定端口，默认 0 = 由系统分配空闲端口
  --host=地址              监听地址，默认 127.0.0.1（仅本机可访问）
  --browser=路径           指定浏览器可执行文件，默认自动探测
  --no-browser             只起服务，不自动打开浏览器

示例：
  python3 src/main.py --no-browser --port=8765
  python3 src/main.py todo add "买牛奶" --pri 1 --tag 生活
  python3 src/main.py todo list -p
  python3 src/main.py todo done a1b2c3d4e5f6

说明：
  Web UI 会自动以浏览器的 --app 模式打开一个无地址栏窗口，观感接近原生应用；
  关闭该窗口即退出程序。若系统未安装 Chromium 内核浏览器，会退化为默认浏览器，
  再不行则打印出 URL 供手动访问。
"""


def _write(text, stream=None):
    stream = stream or sys.stdout
    try:
        stream.write(text + "\n")
    except Exception:
        pass


def print_usage(stream=None):
    _write(USAGE, stream)


def print_tools(stream=None):
    items = registry.all_tools()
    if not items:
        _write("（尚未注册任何工具）", stream)
        return
    _write("可用工具：", stream)
    for tool in items:
        _write("  %-8s %s  —— %s" % (tool.meta.id, tool.meta.name, tool.meta.desc), stream)
