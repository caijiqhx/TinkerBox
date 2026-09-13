"""业务工具包。

新增一个工具只需两步：
1. 在 tools/ 下建一个包，实现 Tool 子类
2. 在本文件的 register_all() 里加一行 registry.register(...)

外壳与路由无需任何改动。
"""

from __future__ import annotations

from core import registry

_registered = False


def register_all():
    """注册全部工具。重复调用是安全的。"""
    global _registered
    if _registered:
        return registry.all_tools()

    from tools.calendar.tool import CalendarTool
    from tools.todo.tool import TodoTool

    registry.register(TodoTool())
    registry.register(CalendarTool())

    _registered = True
    return registry.all_tools()
