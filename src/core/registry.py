"""工具注册表。

新增一个工具 = 在 tools/ 下建一个包 + 在 tools/__init__.py 里 register 一行，
外壳与路由**零改动**。
"""

from __future__ import annotations

from core.errors import NotFoundError

_TOOLS = []
_INDEX = {}


def register(tool):
    """注册一个工具实例，返回它本身（便于链式书写）。"""
    meta = getattr(tool, "meta", None)
    if meta is None:
        raise ValueError("工具必须提供 meta")
    if meta.id in _INDEX:
        raise ValueError("工具 id 重复：%s" % (meta.id,))
    _TOOLS.append(tool)
    _INDEX[meta.id] = tool
    return tool


def all_tools():
    """按 order、id 排序返回全部工具实例。"""
    return sorted(_TOOLS, key=lambda t: (t.meta.order, t.meta.id))


def list_meta():
    """返回全部工具的元信息（供 /api/tools 使用）。"""
    return [t.meta.to_dict() for t in all_tools()]


def get(tid):
    tool = _INDEX.get(tid)
    if tool is None:
        raise NotFoundError("工具不存在：%s" % (tid,))
    return tool


def clear():
    """仅供测试使用。"""
    del _TOOLS[:]
    _INDEX.clear()
