#!/usr/bin/env python3
"""ToolBox 唯一入口。

    python3 src/main.py                      起 Web UI
    python3 src/main.py doctor               环境自检
    python3 src/main.py help                 查看用法与工具列表
    python3 src/main.py todo add "买牛奶"     调用工具的 CLI 子命令
    python3 src/main.py --ui=none --port=8765 只起服务不开浏览器

纯标准库，兼容 Python 3.7。不需要 pip、不需要联网、不需要 root。
"""

from __future__ import annotations

import os
import sys

# 把 src/ 放到 sys.path 最前：源码直接运行与将来的打包（--paths src）都走同一套绝对导入
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from cli import cli as cli_mod                      # noqa: E402
from core import registry                           # noqa: E402
from core.errors import ToolBoxError, ToolError     # noqa: E402
from services import config, logs                   # noqa: E402
import tools                                        # noqa: E402


# ----------------------------------------------------------------------
# 参数解析
# ----------------------------------------------------------------------
def _parse_port(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ToolError("端口必须是整数：%s" % (value,))
    if not (0 <= port <= 65535):
        raise ToolError("端口超出范围：%s" % (value,))
    return port


def parse_args(argv):
    """拆出全局选项与剩余命令。

    只识别**位于最前面**的全局选项，遇到第一个非选项参数即停止 ——
    这样 `todo add "买牛奶"` 的内容不会被误当成全局选项。
    """
    options = {"ui": None, "port": 0, "host": "127.0.0.1",
               "browser": "", "no_browser": False}
    rest = []

    index = 0
    while index < len(argv):
        token = argv[index]

        if not token.startswith("-"):
            rest = list(argv[index:])
            break

        name, has_eq, inline = token.partition("=")

        if name in ("--ui", "--port", "--host", "--browser"):
            if has_eq:
                value = inline
                index += 1
            elif index + 1 < len(argv):
                value = argv[index + 1]
                index += 2
            else:
                raise ToolError("选项 %s 缺少取值" % (name,))

            if name == "--ui":
                options["ui"] = value.strip().lower()
            elif name == "--port":
                options["port"] = _parse_port(value)
            elif name == "--host":
                options["host"] = value.strip()
            else:
                options["browser"] = value.strip()
            continue

        if name == "--no-browser":
            options["no_browser"] = True
            index += 1
            continue

        if name in ("-h", "--help"):
            rest = ["help"]
            break

        raise ToolError("未知选项：%s" % (token,))

    return options, rest


def resolve_ui(options):
    """界面承载方式的优先级：命令行 > 环境变量 > 配置文件。"""
    if options.get("ui"):
        return options["ui"]
    env = (os.environ.get("TOOLBOX_UI") or "").strip().lower()
    if env:
        return env
    return str(config.get("ui") or "web").strip().lower()


# ----------------------------------------------------------------------
# Web 承载
# ----------------------------------------------------------------------
def _say(text=""):
    """往控制台输出一行并立即刷新。

    立即 flush 是为了避免"黑窗空白"的错觉 —— 用户双击启动时，
    必须先看到东西，才知道程序确实跑起来了。
    """
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def run_web(options):
    import secrets

    from web import launcher, router
    from web import server as web_server

    _say("")
    _say("  ToolBox 正在启动，请稍候…")
    _say("  Python : %s" % (sys.version.split()[0],))
    _say("  目录   : %s" % (os.path.dirname(_HERE) or _HERE,))

    token = secrets.token_urlsafe(24)
    ping_timeout = int(config.get("ping_timeout") or 90)

    app = router.Application(token)
    httpd = web_server.Server(
        router.build_handler(app),
        host=options["host"],
        port=options["port"],
        ping_timeout=ping_timeout,
    )
    app.server = httpd

    actual_port = httpd.start()
    url = "http://127.0.0.1:%d/" % (actual_port,)
    logs.log().info("服务已启动：%s" % (url,))

    _say("")
    _say("  ToolBox 已启动")
    _say("  访问地址：%s" % (url,))

    if options["no_browser"]:
        _say("  已按 --no-browser 跳过自动打开，请手动访问上面的地址")
        _say("  按 Ctrl+C 退出")
        _say("")
    else:
        _say("  正在查找浏览器…")
        mode = launcher.open_ui(url, config.get("window_size", ""),
                                options.get("browser", ""))
        if mode == "app":
            _say("  已用浏览器 --app 模式打开独立窗口（关闭窗口即退出）")
        elif mode == "browser":
            _say("  已用默认浏览器打开（未找到 Chromium 内核浏览器，窗口带地址栏）")
            _say("  关闭该标签页后程序会自动退出；也可按 Ctrl+C 退出")
        else:
            _say("  [!] 未能自动打开浏览器")
            _say("      可能是：没有 Chromium 内核浏览器 / 无图形会话 / 浏览器启动失败")
            _say("      请手动把上面的地址粘到浏览器里访问")
            _say("      排查：执行  python3 src/main.py doctor  查看浏览器探测结果")
            _say("  按 Ctrl+C 退出")
        _say("")

        if mode in ("app", "browser"):
            # 只有在浏览器真正打开后才启用心跳超时退出
            httpd.arm_watchdog()

    try:
        httpd.wait()
    except KeyboardInterrupt:
        pass

    _say("  已退出")
    return 0


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    try:
        options, rest = parse_args(argv)
    except ToolError as exc:
        print("参数错误：%s" % (exc,))
        print("")
        cli_mod.print_usage()
        return 2

    tools.register_all()

    # ---- 子命令 ----
    if rest:
        command, tail = rest[0], rest[1:]

        if command == "help":
            cli_mod.print_usage()
            print("")
            cli_mod.print_tools()
            return 0

        if command == "doctor":
            from web import doctor
            doctor.run()
            return 0

        if command in ("tools", "list-tools"):
            cli_mod.print_tools()
            return 0

        try:
            tool = registry.get(command)
        except ToolError as exc:
            print("错误：%s" % (exc,))
            print("")
            cli_mod.print_tools()
            return 2

        try:
            return tool.cli(tail)
        except ToolError as exc:
            print("错误：%s" % (exc,))
            return 1
        except KeyboardInterrupt:
            print("")
            return 130

    # ---- 界面承载 ----
    ui = resolve_ui(options)

    if ui in ("none",):
        options["no_browser"] = True
        return run_web(options)

    if ui == "web":
        return run_web(options)

    if ui == "cli":
        cli_mod.print_usage()
        print("")
        cli_mod.print_tools()
        print("")
        print("当前以 CLI 方式使用：python3 src/main.py <工具> <子命令> [参数]")
        return 0

    print("未知的界面模式：%s（可选 web / cli / none）" % (ui,))
    return 2


def entry():
    try:
        return main()
    except KeyboardInterrupt:
        print("")
        return 130
    except ToolBoxError as exc:
        logs.log().error("运行失败", exc)
        print("运行失败：%s" % (exc,))
        return 1
    except Exception as exc:                      # 兜底：绝不把 traceback 糊到用户脸上
        logs.log().error("未预期的错误", exc)
        print("发生未预期的错误：%s: %s" % (exc.__class__.__name__, exc))
        print("详细信息已写入日志目录，可执行 doctor 查看数据目录位置。")
        return 1


if __name__ == "__main__":
    sys.exit(entry())
