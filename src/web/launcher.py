"""浏览器探测与 --app 启动。

优先用 Chromium 内核浏览器的 --app 模式：打开的是**无地址栏、无标签页**的
独立窗口，观感接近原生桌面应用；配合 .desktop / .lnk 图标即可"固定到桌面"。

退化顺序：--app  →  webbrowser.open（带地址栏）  →  手动打开提示
"""

from __future__ import annotations

import os
import webbrowser

from core import paths
from services import config, logs
from services import platform as plat


def pick_browser(explicit=""):
    """返回可用的浏览器可执行文件路径，找不到返回空串。"""
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        logs.log().warn("配置指定的浏览器不存在，改为自动探测：%s" % (explicit,))

    for candidate in plat.browser_candidates():
        if os.path.isfile(candidate):
            return candidate
    return ""


def open_ui(url, window_size="", browser_path=""):
    """打开 UI。返回实际采用的方式：app / browser / manual。"""
    if not plat.has_display():
        logs.log().warn("无图形环境，跳过打开浏览器。%s" % (plat.display_hint(),))
        return "manual"

    explicit = browser_path or config.get("browser_path", "")
    exe = pick_browser(explicit)

    if exe:
        args = [exe, "--app=" + url]
        if window_size:
            args.append("--window-size=" + str(window_size))
        # 独立的用户数据目录：不污染日常浏览器配置，也让窗口更"独立应用化"
        args.append("--user-data-dir=" + str(paths.browser_profile_dir()))
        try:
            plat.popen_detached(args)
            logs.log().info("已用 --app 模式启动：%s" % (exe,))
            return "app"
        except Exception as exc:
            logs.log().error("--app 启动失败，尝试退化方式", exc)

    try:
        if webbrowser.open(url):
            logs.log().info("已用默认浏览器打开（带地址栏）")
            return "browser"
    except Exception as exc:
        logs.log().error("webbrowser.open 失败", exc)

    return "manual"
