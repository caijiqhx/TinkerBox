"""待办数据的持久化（v2）。

单文件 JSON + 原子写。文件不存在、内容损坏、记录字段缺失，
一律降级处理并保证程序能继续运行。

v1 数据（只有 tasks、没有 list_id / steps / important / my_day / due）会被
model.normalize_task 自动补齐，不需要单独的迁移步骤。
"""

from __future__ import annotations

from core import paths
from services import jsonio

from tools.todo import model

VERSION = 2


def file_path():
    return paths.state_file()


def path_text():
    return str(file_path())


def load():
    """读取全部数据，返回 {"version", "lists", "tasks"}，绝不抛异常。"""
    raw = jsonio.read_json(file_path(), None)
    if not isinstance(raw, dict):
        raw = {}

    # ---- 清单 ----
    lists = []
    raw_lists = raw.get("lists")
    if isinstance(raw_lists, (list, tuple)):
        order = 1
        for item in raw_lists:
            parsed = model.normalize_list(item, order)
            if parsed is not None:
                lists.append(parsed)
                order += 1
    lists.sort(key=lambda item: (item.get("order", 0), item.get("name") or ""))

    # 默认清单始终存在，且排在最前
    lists.insert(0, model.default_list())
    valid_ids = set(item["id"] for item in lists)

    # ---- 任务 ----
    tasks = []
    raw_tasks = raw.get("tasks")
    if isinstance(raw_tasks, (list, tuple)):
        for item in raw_tasks:
            task = model.normalize_task(item, valid_ids)
            if task is not None:
                tasks.append(task)

    return {"version": VERSION, "lists": lists, "tasks": tasks}


def save(data):
    payload = {
        "version": VERSION,
        "lists": [item for item in data.get("lists", []) if item.get("id") != model.DEFAULT_LIST_ID],
        "tasks": list(data.get("tasks", [])),
    }
    jsonio.write_json_atomic(file_path(), payload)
    return payload
