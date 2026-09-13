"""CLI 承载层的输出辅助。"""

from __future__ import annotations

import sys

from core import registry

USAGE = """ToolBox —— 个人工具箱

用法：
  python3 src/main.py                     启动服务并打开界面（已在运行则直接打开）
  python3 src/main.py status              查看服务状态（端口、运行时长）
  python3 src/main.py stop                关闭后台服务
  python3 src/main.py <工具> <子命令> ...   直接调用某个工具的命令行功能
  python3 src/main.py doctor              环境自检（推荐在目标机上先跑一次）
  python3 src/main.py help                显示本帮助

选项：
  --ui=web|cli|none        指定界面承载方式（环境变量 TOOLBOX_UI 亦可）
  --port=端口              指定端口，默认取配置里的 port（8765）
  --host=地址              监听地址，默认 127.0.0.1（仅本机可访问）
  --browser=路径           指定浏览器可执行文件，默认自动探测
  --no-browser             只起服务，不自动打开浏览器
  --force                  忽略「已有服务在运行」，强行再起一个

示例：
  python3 src/main.py
  python3 src/main.py status
  python3 src/main.py stop
  python3 src/main.py todo add "买牛奶" --due 2026-09-20
  python3 src/main.py todo list -p

说明：
  默认是**常驻模式** —— 关掉浏览器窗口后服务继续留在后台，一天只需启动一次；
  再次运行会直接打开界面，不会重复起服务。
  关闭服务有三条路：界面上点「关闭服务」、执行 stop、连续 12 小时无请求自动退出。
  端口固定为 8765 是为了让浏览器书签稳定；被占用时会明确报错而不会偷偷换端口。
  以上都可在 data/config.json 里调整（port / keep_alive / idle_exit_hours）。
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
