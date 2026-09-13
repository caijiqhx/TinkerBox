"""平台差异 —— 全项目**唯一**允许出现平台分支的地方。

其余任何模块都不得出现 os.name / sys.platform / std::os 之类的判断。
这条纪律是"跨平台确定性"的工程保障：平台差异全部收口在这里，改动可控。
"""

from __future__ import annotations

import os
import subprocess
import sys

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"

# Chromium 内核优先 —— 它们是唯一支持 --app（无地址栏独立窗口）的一类
_LINUX_BROWSERS = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "microsoft-edge",
    "microsoft-edge-stable",
    "uos-browser",
    "deepin-browser",
    "brave-browser",
    "browser",
    "360browser",
    "qihoo-browser",
)

_WINDOWS_BROWSERS = (
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
)


def browser_candidates():
    """按优先级返回候选浏览器可执行文件路径（只列候选，不保证存在）。"""
    candidates = []

    if IS_WINDOWS:
        for raw in _WINDOWS_BROWSERS:
            expanded = os.path.expandvars(raw)
            if expanded != raw and expanded not in candidates:
                candidates.append(expanded)
        for name in ("chrome.exe", "msedge.exe"):
            for folder in os.environ.get("PATH", "").split(os.pathsep):
                if folder:
                    path = os.path.join(folder, name)
                    if path not in candidates:
                        candidates.append(path)
        return candidates

    for name in _LINUX_BROWSERS:
        for folder in os.environ.get("PATH", "").split(os.pathsep):
            if not folder:
                continue
            path = os.path.join(folder, name)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                if path not in candidates:
                    candidates.append(path)
    return candidates


def has_display():
    """是否存在可用的图形环境。"""
    if IS_WINDOWS or IS_MACOS:
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def display_hint():
    if IS_WINDOWS or IS_MACOS:
        return ""
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return "未检测到 DISPLAY / WAYLAND_DISPLAY，当前可能是无图形会话（如纯 SSH 终端）"
    return ""


def is_case_sensitive():
    """文件系统是否区分大小写。

    首版 TodoList 用不到，为将来的文件批处理（FileBatch）预留：
    Windows 上 a.txt -> A.txt 是合法改名，Linux 上会与自身冲突。
    """
    if IS_WINDOWS or IS_MACOS:
        return False
    return True


def allow_address_reuse():
    """绑定监听端口时是否启用地址复用（SO_REUSEADDR）。

    POSIX：**启用**。它只影响 TIME_WAIT 的残留连接，能让服务在重启后立刻
           重新绑定同一端口，不会与"端口已被占用"混淆。

    Windows：**必须关闭**。Windows 的 SO_REUSEADDR 语义不同 —— 它允许两个
           进程绑同一个端口，于是"端口被占用"根本检测不出来：我们会悄悄
           绑上一个别人正在用的端口，而报错分支永远不会触发。
    """
    return not IS_WINDOWS


def popen_detached(args):
    """启动一个脱离当前进程的 GUI 子进程。"""
    if IS_WINDOWS:
        return subprocess.Popen(args, close_fds=True)
    return subprocess.Popen(
        args,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def background_python():
    """跑后台服务用的解释器。

    Windows 上优先用 `pythonw.exe`：它是 GUI 子系统程序，**永远不附着控制台**，
    比只靠 DETACHED_PROCESS 又稳一层（双重保险：即使标志位没生效，
    pythonw 也不会因为关掉黑窗而收到 CTRL_CLOSE_EVENT）。
    """
    if IS_WINDOWS:
        candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.isfile(candidate):
            return candidate
    return sys.executable


def spawn_background(args, log_path=None):
    """把进程彻底从当前终端分离出去，返回 Popen 对象。

    **这是"服务常驻"的前提。** Windows 上关闭控制台窗口会向同控制台的
    所有子进程发送 CTRL_CLOSE_EVENT —— 普通子进程会被一起杀掉，
    用户一关黑窗服务就没了。所以必须用 DETACHED_PROCESS 让子进程
    不与任何控制台绑定。

    POSIX 下用 start_new_session 达到同样效果（脱离会话、不接收 SIGHUP）。
    """
    out = None
    if log_path is not None:
        try:
            directory = os.path.dirname(str(log_path))
            if directory:
                os.makedirs(directory, exist_ok=True)
            out = open(str(log_path), "ab")
        except OSError:
            out = None

    stdout = out if out is not None else subprocess.DEVNULL
    stderr = subprocess.STDOUT if out is not None else subprocess.DEVNULL

    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": stdout,
        "stderr": stderr,
        "close_fds": True,
    }
    if IS_WINDOWS:
        flags = 0
        for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
            flags |= getattr(subprocess, name, 0)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True

    process = subprocess.Popen(args, **kwargs)
    if out is not None:
        out.close()          # 子进程已持有自己的句柄，父进程这份可以关掉
    return process


def open_in_file_manager(path):
    """在系统文件管理器中定位目标文件。返回是否成功。"""
    target = str(path)
    try:
        if IS_WINDOWS:
            popen_detached(["explorer", "/select,", target])
        elif IS_MACOS:
            popen_detached(["open", "-R", target])
        else:
            popen_detached(["xdg-open", os.path.dirname(target) or "."])
        return True
    except Exception:
        return False
