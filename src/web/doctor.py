"""环境自检（doctor）。

目的：**不必提前猜目标机环境**。在目标机上跑一次就能得到完整报告 ——
Python 版本、架构、关键标准库可用性、浏览器、图形环境、数据目录。
"""

from __future__ import annotations

import importlib
import os
import platform as sysinfo
import sys

from core import paths
from services import config
from services import platform as plat

#: 本项目运行所依赖的标准库模块。tkinter 不在其中 —— 它是可选增强项。
REQUIRED_MODULES = (
    "http.server",
    "json",
    "hmac",
    "threading",
    "zipfile",
    "xml.etree.ElementTree",
    "webbrowser",
)

OPTIONAL_MODULES = (
    "tkinter",     # 可选：将来若要做 tkinter 承载层
    "sqlite3",     # 可选：将来数据量大了可换
    "curses",      # 可选：TUI 保底
)


def _try_import(name):
    try:
        importlib.import_module(name)
        return True, ""
    except Exception as exc:
        return False, exc.__class__.__name__


def _scan(names):
    result = []
    for name in names:
        ok, err = _try_import(name)
        result.append({"name": name, "ok": ok, "err": err})
    return result


def collect():
    """收集环境信息，返回结构化 dict。"""
    required = _scan(REQUIRED_MODULES)
    optional = _scan(OPTIONAL_MODULES)

    browsers = [p for p in plat.browser_candidates() if os.path.isfile(p)]
    data_dir = paths.data_dir()

    return {
        "python": sys.version.split()[0],
        "python_full": sys.version.replace("\n", " "),
        "bits": 64 if sys.maxsize > 2 ** 32 else 32,
        "machine": sysinfo.machine(),
        "system": sysinfo.system(),
        "release": sysinfo.release(),
        "executable": sys.executable,
        "required": required,
        "optional": optional,
        "browsers": browsers,
        "has_display": plat.has_display(),
        "display_hint": plat.display_hint(),
        "data_dir": str(data_dir),
        "data_writable": os.access(str(data_dir), os.W_OK),
        "config_file": str(paths.config_file()),
        "config_exists": os.path.isfile(str(paths.config_file())),
        "is_windows": plat.IS_WINDOWS,
        "recommended_ui": _recommend(browsers),
    }


def _recommend(browsers):
    if browsers and plat.has_display():
        return "web"
    if plat.has_display():
        return "web（浏览器需自行打开 URL）"
    return "cli"


def render(info):
    """把结构化信息渲染成可读文本。"""
    lines = []
    add = lines.append

    add("=" * 58)
    add(" ToolBox 环境自检报告")
    add("=" * 58)

    add("")
    add("[运行环境]")
    add("  Python 版本 : %s (%d bit)" % (info["python"], info["bits"]))
    add("  Python 路径 : %s" % (info["executable"],))
    add("  操作系统    : %s %s" % (info["system"], info["release"]))
    add("  CPU 架构    : %s" % (info["machine"],))
    add("  平台分支    : %s" % ("Windows" if info["is_windows"] else "类 Unix",))

    add("")
    add("[必需标准库]  —— 任一缺失都会影响运行")
    for item in info["required"]:
        add("  %s %s%s" % ("[ OK ]" if item["ok"] else "[FAIL]",
                           item["name"],
                           "" if item["ok"] else "  (%s)" % item["err"]))

    add("")
    add("[可选模块]  —— 缺失不影响首版运行")
    for item in info["optional"]:
        add("  %s %s%s" % ("[ OK ]" if item["ok"] else "[ -- ]",
                           item["name"],
                           "" if item["ok"] else "  (未安装/不可用)"))

    add("")
    add("[图形环境]")
    add("  有图形会话  : %s" % ("是" if info["has_display"] else "否"))
    if info["display_hint"]:
        add("  提示        : %s" % (info["display_hint"],))
    add("  浏览器      : %s" % ("未找到" if not info["browsers"] else ""))
    for path in info["browsers"]:
        add("                - %s" % (path,))

    add("")
    add("[数据目录]")
    add("  位置        : %s" % (info["data_dir"],))
    add("  可写        : %s" % ("是" if info["data_writable"] else "否(!)",))
    add("  配置文件    : %s%s" % (info["config_file"],
                                  "" if info["config_exists"] else "  (尚未创建)"))

    add("")
    add("[结论]")
    add("  推荐承载方式: %s" % (info["recommended_ui"],))
    if not all(i["ok"] for i in info["required"]):
        add("  [!] 存在必需模块缺失，请检查上面的 [FAIL] 项")
    elif not info["browsers"]:
        add("  [!] 未探测到浏览器：UI 仍会启动，请手动访问打印出的 URL")
    else:
        add("  [OK] 环境满足运行要求，直接执行即可：python3 src/main.py")

    add("")
    add("=" * 58)
    add(" 数据目录：%s" % (info["data_dir"],))
    add("=" * 58)
    return "\n".join(lines)


def run(stream=None):
    """自检并以文本形式输出。返回结构化 info。"""
    info = collect()
    text = render(info)
    if stream is None:
        stream = sys.stdout
    try:
        stream.write(text + "\n")
    except Exception:
        pass
    return info
