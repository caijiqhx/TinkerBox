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
import time

# 把 src/ 放到 sys.path 最前：源码直接运行与将来的打包（--paths src）都走同一套绝对导入
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from cli import cli as cli_mod                      # noqa: E402
from core import paths, registry                    # noqa: E402
from core.errors import ToolBoxError, ToolError     # noqa: E402
from services import config, logs                   # noqa: E402
from services import platform as plat               # noqa: E402
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
    options = {"ui": None, "port": None, "host": "127.0.0.1",
               "browser": "", "no_browser": False, "force": False,
               "detach": False}
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

        if name == "--force":
            # 忽略"已有实例在跑"，强行再起一个（换端口时才需要）
            options["force"] = True
            index += 1
            continue

        if name == "--detach":
            # 后台分离启动：服务跑在独立进程里，关掉终端不会带走它
            options["detach"] = True
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
#: 给用户看的启动命令写法（提示里复用）
RUN_CMD = "run.bat" if os.name == "nt" else "./run.sh"


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


def _human_duration(seconds):
    seconds = int(seconds or 0)
    if seconds < 60:
        return "%d 秒" % (seconds,)
    minutes = seconds // 60
    if minutes < 60:
        return "%d 分钟" % (minutes,)
    hours, rest = minutes // 60, minutes % 60
    if hours < 24:
        return ("%d 小时 %d 分钟" % (hours, rest)) if rest else ("%d 小时" % (hours,))
    return "%d 天 %d 小时" % (hours // 24, hours % 24)


def _open_browser_or_hint(url, window_size, options):
    """打开界面；失败时给出可执行的排查提示。返回实际采用的方式。"""
    from web import launcher

    _say("  正在查找浏览器…")
    mode = launcher.open_ui(url, window_size, options.get("browser", ""))

    if mode == "app":
        _say("  已用浏览器 --app 模式打开独立窗口")
    elif mode == "browser":
        _say("  已用默认浏览器打开（未找到 Chromium 内核浏览器，窗口带地址栏）")
    else:
        _say("  [!] 未能自动打开浏览器")
        _say("      可能是：没有 Chromium 内核浏览器 / 无图形会话 / 浏览器启动失败")
        _say("      请手动把上面的地址粘到浏览器里访问")
        _say("      排查：执行  %s doctor  查看浏览器探测结果" % (RUN_CMD,))
    return mode


def _resolve_port(options):
    port = options.get("port")
    if port is None:
        port = int(config.get("port") or 8765)
    return port


def run_detached(options):
    """后台分离启动：**服务跑在独立进程里，关掉终端不会带走它**。

    控制台只负责"反馈"，所以整个流程是：
      前台检查（是否已有实例 / 端口是否可用）→ 拉起分离子进程 → 等它就绪 → 打开界面 → 退出

    Windows 上这一步是必须的：cmd 关闭时会向同控制台的子进程发 CTRL_CLOSE_EVENT，
    普通子进程会被一起杀掉 —— 用户一关黑窗，常驻就无从谈起。
    """
    from web import instance

    port = _resolve_port(options)
    window_size = config.get("window_size", "")

    # ---------- 已经有一个实例在跑？直接打开界面 ----------
    if not options.get("force"):
        record, identity = instance.find_running()
        if record is not None:
            url = url_of(record["port"])
            _say("")
            _say("  工具箱服务已经在运行，直接为你打开界面")
            _say("  端口     : %d" % (record["port"],))
            _say("  已运行   : %s" % (_human_duration(identity.get("uptime")),))
            _say("")
            if options["no_browser"]:
                _say("  访问地址 : %s" % (url,))
            else:
                _open_browser_or_hint(url, window_size, options)
            return 0

    # 清掉可能残留的记录，免得子进程或被后续探测误导
    instance.clear_record()

    log_path = paths.logs_dir() / "service.out"
    child_args = [
        plat.background_python(),
        os.path.join(_HERE, "main.py"),
        "--force", "--no-browser",
        "--port=%d" % (port,),
    ]

    _say("")
    _say("  正在后台启动服务（端口 %d）…" % (port,))

    try:
        process = plat.spawn_background(child_args, log_path)
    except Exception as exc:
        logs.log().error("无法启动后台进程", exc)
        _say("  [错误] 无法启动后台进程：%s" % (exc,))
        return 1

    # ---------- 等它就绪：端口冲突之类的失败会在这里暴露出来 ----------
    deadline = time.time() + 20.0
    identity = None
    while time.time() < deadline:
        if process.poll() is not None:
            break                      # 子进程已经退出 → 启动失败，不必等满
        identity = instance.probe(port, timeout=1.0)
        if identity is not None:
            break
        time.sleep(0.3)

    if identity is None:
        logs.log().error("后台服务未能在端口 %d 上就绪" % (port,))
        _say("")
        _say("  [错误] 服务没能在端口 %d 上启动。" % (port,))
        _say("")
        _say("  最常见的原因是端口被占用了 —— 这里不会自动换端口，")
        _say("  因为浏览器书签里存的就是这个端口。")
        _say("  请关掉占用它的程序，或修改 %s 里的 port。" % (paths.config_file(),))
        _say("")
        _say("  详细输出：%s" % (log_path,))
        _say("  查看状态：%s status" % (RUN_CMD,))
        return 1

    url = url_of(port)
    _say("")
    _say("  服务已在后台运行")
    _say("  访问地址 : %s" % (url,))
    _say("  运行模式 : 常驻 —— **这个窗口可以直接关掉，服务不受影响**")
    _say("")
    _say("  关闭服务：界面左下角的「关闭服务」，或执行 %s stop" % (RUN_CMD,))
    _say("")

    if options["no_browser"]:
        _say("  已按 --no-browser 跳过自动打开，请手动访问上面的地址")
    else:
        _open_browser_or_hint(url, window_size, options)
    return 0


def run_web(options):
    import secrets

    from web import instance, router
    from web import server as web_server

    port = _resolve_port(options)
    keep_alive = bool(config.get("keep_alive", True))
    idle_hours = float(config.get("idle_exit_hours") or 0)
    window_size = config.get("window_size", "")

    # ---------------- 已经有一个实例在跑？直接复用 ----------------
    if not options.get("force"):
        record, identity = instance.find_running()
        if record is not None:
            url = "http://127.0.0.1:%d/" % (record["port"],)
            _say("")
            _say("  工具箱服务已经在运行，直接为你打开界面")
            _say("  端口     : %d" % (record["port"],))
            _say("  已运行   : %s" % (_human_duration(identity.get("uptime")),))
            _say("  访问地址 : %s" % (url,))
            _say("")
            if options["no_browser"]:
                _say("  已按 --no-browser 跳过自动打开")
            else:
                _open_browser_or_hint(url, window_size, options)
            return 0

    # ---------------- 启动新服务 ----------------
    _say("")
    _say("  工具箱正在启动，请稍候…")
    _say("  Python : %s" % (sys.version.split()[0],))

    token = secrets.token_urlsafe(24)
    app = router.Application(token)
    httpd = web_server.Server(
        router.build_handler(app),
        host=options["host"],
        port=port,
        keep_alive=keep_alive,
        idle_timeout=(idle_hours * 3600.0) if idle_hours > 0 else 0,
        ping_timeout=int(config.get("ping_timeout") or 90),
    )
    app.server = httpd

    try:
        actual_port = httpd.start()
    except OSError as exc:
        _say("")
        _say("  [错误] 端口 %d 用不了：%s" % (port, exc))
        _say("")
        _say("  这里**不会**自动换一个端口 —— 你的浏览器书签里存的是这个端口，")
        _say("  悄悄换掉只会让书签失效、而且你不知道为什么。")
        _say("")
        _say("  请关掉占用该端口的程序，或者修改下面这个文件里的 port 后重试：")
        _say("    %s" % (paths.config_file(),))
        _say("")
        return 1

    instance.write_record(actual_port, httpd.instance_id, httpd.started_text())
    logs.log().info("服务已启动：%s（keep_alive=%s, idle_exit=%s h）"
                    % (url_of(actual_port), keep_alive, idle_hours))

    url = url_of(actual_port)
    _say("")
    _say("  工具箱已启动")
    _say("  访问地址 : %s" % (url,))
    _say("  运行模式 : %s" % (
        "常驻 —— 关掉窗口后服务继续留在后台" if keep_alive else "跟随窗口 —— 关掉窗口即退出",))
    if idle_hours > 0:
        _say("  空闲退出 : 连续 %.0f 小时没有任何请求则自动关闭" % (idle_hours,))
    _say("")
    _say("  建议把上面的地址存成浏览器书签，以后点书签就能直接打开。")
    _say("  关闭服务：界面左下角的「关闭服务」，或执行 %s stop" % (RUN_CMD,))
    _say("")

    mode = "manual"
    if options["no_browser"]:
        _say("  已按 --no-browser 跳过自动打开，请手动访问上面的地址")
    else:
        mode = _open_browser_or_hint(url, window_size, options)

    if not keep_alive and mode in ("app", "browser"):
        # 跟随窗口模式：只有浏览器真的打开了才开始计时
        httpd.arm_watchdog()

    try:
        httpd.wait()
    except KeyboardInterrupt:
        pass

    instance.clear_record()
    _say("")
    _say("  服务已关闭")
    return 0


def url_of(port):
    return "http://127.0.0.1:%d/" % (port,)


# ----------------------------------------------------------------------
# status / stop
# ----------------------------------------------------------------------
def cmd_status():
    from web import instance

    record, identity = instance.find_running()
    if record is None:
        _say("工具箱服务：未在运行")
        stale = instance.read_record()
        if stale is not None:
            _say("  （发现一条残留记录，指向端口 %d，但那里没有响应 —— 已清理）"
                 % (stale["port"],))
            instance.clear_record()
        return 1

    idle = identity.get("idle_exit_hours") or 0
    _say("工具箱服务：运行中")
    _say("  端口     : %d" % (record["port"],))
    _say("  访问地址 : http://127.0.0.1:%d/" % (record["port"],))
    _say("  启动时间 : %s" % (record["started"] or identity.get("started") or "-",))
    _say("  已运行   : %s" % (_human_duration(identity.get("uptime")),))
    _say("  运行模式 : %s" % ("常驻（关窗口不退出）" if identity.get("keep_alive")
                              else "跟随窗口（关窗口即退出）",))
    _say("  空闲退出 : %s" % ("不限制" if not idle else "%.0f 小时无请求" % (idle,),))
    _say("  进程号   : %s" % (record.get("pid") or "-",))
    _say("  数据文件 : %s" % (paths.state_file(),))
    return 0


def cmd_stop():
    from web import instance

    record, _identity = instance.find_running()
    if record is None:
        _say("工具箱服务未在运行")
        instance.clear_record()
        return 1

    _say("正在关闭端口 %d 上的服务…" % (record["port"],))
    if not instance.request_shutdown(record["port"], record["instance"]):
        _say("[!] 关闭请求没有送达")
        if record.get("pid"):
            _say("    可以手动结束该进程：pid %s" % (record["pid"],))
        return 1

    if instance.wait_until_stopped(record["port"]):
        instance.clear_record()
        _say("服务已关闭")
        return 0

    _say("[!] 请求已发出，但服务仍在响应")
    if record.get("pid"):
        _say("    可手动结束该进程：pid %s" % (record["pid"],))
    return 1


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

        if command in ("status", "state"):
            return cmd_status()

        if command in ("stop", "shutdown"):
            return cmd_stop()

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

    if ui == "none":
        options["no_browser"] = True
        ui = "web"

    if ui == "web":
        if options.get("detach"):
            return run_detached(options)
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
