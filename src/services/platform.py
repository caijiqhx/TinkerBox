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
