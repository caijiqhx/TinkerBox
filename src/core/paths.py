"""路径定义（全项目唯一的路径来源）。

设计要点：
- 源码根目录通过 __file__ 推导，不依赖当前工作目录 —— 这是"从 Windows 搬到
  Linux 最容易翻车"的地方，必须由这里统一收口。
- 数据目录优先放在项目内的 data/，这样整个目录拷贝走时数据跟着走；
  若项目目录不可写（如放在只读介质上），自动退回用户数据目录。
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "ToolBox"


def project_root():
    # src/core/paths.py -> src/core -> src -> 项目根
    return Path(__file__).resolve().parents[2]


def src_dir():
    return project_root() / "src"


def static_dir():
    return src_dir() / "web" / "static"


def assets_dir():
    return project_root() / "assets"


def _user_data_dir():
    home = Path.home()
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        return (Path(base) / APP_NAME) if base else (home / APP_NAME)
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) / APP_NAME) if base else (home / ".local" / "share" / APP_NAME)


def data_dir():
    """运行时数据目录：项目内 data/ 优先，不可写则退回用户目录。"""
    candidate = project_root() / "data"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        if os.access(str(candidate), os.W_OK):
            return candidate
    except OSError:
        pass
    fallback = _user_data_dir()
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return fallback


def state_file():
    return data_dir() / "todo.json"


def config_file():
    return data_dir() / "config.json"


def logs_dir():
    return data_dir() / "logs"


def browser_profile_dir():
    return data_dir() / "browser-profile"
