"""文件浏览的位置清单（持久化）。

**只存"用户显式添加过的目录"和上次浏览的位置** —— 不存任何文件内容、
不做索引，所以这个文件永远只有几十字节，不需要考虑清理。

为什么单独一个文件、而不是塞进 `config.json`：config 里的项是全局设置
（端口、主题…），而"我允许浏览哪些目录"是这个工具自己的数据，
跟待办的 `todo.json` 同一性质 —— 按项目约定，存储访问收口在工具自己的
store 里，将来换存储后端只改这一个文件。
"""

from __future__ import annotations

import os

from core import paths
from services import jsonio

from tools.files import guard

VERSION = 1


def file_path():
    return paths.data_dir() / "files.json"


def path_text():
    return str(file_path())


def default_label(path):
    """位置的默认名字：取目录名；根目录这种没有名字的就用路径本身。"""
    text = str(path or "").rstrip("\\/")
    if not text:
        return str(path or "")
    return os.path.basename(text) or text


def load():
    """读位置清单，返回 `{"version", "roots", "last"}`，**绝不抛异常**。

    读失败、内容损坏、记录字段缺失一律降级成空清单 —— 不能让 UI 崩掉。
    """
    raw = jsonio.read_json(file_path(), None)
    if not isinstance(raw, dict):
        raw = {}

    roots, seen = [], set()
    raw_roots = raw.get("roots")
    if isinstance(raw_roots, (list, tuple)):
        for item in raw_roots:
            if isinstance(item, dict):
                path = str(item.get("path") or "").strip()
                label = str(item.get("label") or "").strip()
            elif isinstance(item, str):
                path, label = item.strip(), ""
            else:
                continue
            if not path or path in seen:
                continue
            seen.add(path)
            roots.append({"path": path, "label": label or default_label(path)})

    last = str(raw.get("last") or "").strip()
    if last:
        # 上次浏览的通常是**子目录**，所以判定是"落在某个位置之内"，
        # 而不是"等于某个位置" —— 后者会把记下来的子目录每次都清掉，
        # "下次进来回到原处"就永远失效。
        inside = False
        for item in roots:
            if guard.within(last, item["path"]):
                inside = True
                break
        if not inside:
            last = ""
    return {"version": VERSION, "roots": roots, "last": last}


def save(data):
    payload = {
        "version": VERSION,
        "roots": [
            {"path": item.get("path"), "label": item.get("label")}
            for item in data.get("roots", [])
            if isinstance(item, dict) and item.get("path")
        ],
        "last": str(data.get("last") or ""),
    }
    jsonio.write_json_atomic(file_path(), payload)
    return payload
