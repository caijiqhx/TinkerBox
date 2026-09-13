"""待办数据的持久化（v3）。

单文件 JSON + 原子写。文件不存在、内容损坏、记录字段缺失，
一律降级处理并保证程序能继续运行。

**回收站是一个独立的 `trash` 数组，而不是在任务上加"已删除"标记。**
理由：标记方案需要在视图筛选、计数、清单计数、统计、搜索、按 id 查找等
六处都补上过滤，漏掉任何一处就会出现"删了却还在"或"没删却不见了"；
独立数组则现有视图代码一行都不用改。

每次保存前会把上一版轮转成 `todo.json.bak.1 … .bak.N`（份数见配置
`backup_keep`，默认 5，设 0 关闭）。轮转有界，所以不需要手工清理；
它防的是"整个文件被写坏 / 被意外覆盖"这类事故，
而"删错了一条任务"由回收站负责 —— 两者互补。

v1 / v2 数据都会被自动补齐字段，不需要单独的迁移步骤。
"""

from __future__ import annotations

import datetime

from core import paths
from services import config, jsonio

from tools.todo import model

VERSION = 3

#: 回收站条目的默认保留天数（可被 config 里的 trash_keep_days 覆盖）
TRASH_KEEP_DAYS = 30


def file_path():
    return paths.state_file()


def path_text():
    return str(file_path())


def load():
    """读取全部数据，返回 {"version", "lists", "tasks", "trash"}，绝不抛异常。"""
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

    # ---- 回收站 ----
    trash = []
    raw_trash = raw.get("trash")
    if isinstance(raw_trash, (list, tuple)):
        for item in raw_trash:
            task = model.normalize_task(item, valid_ids)
            if task is None:
                continue
            if not task.get("deleted_at"):
                # 时间戳缺失就按"刚删"算，免得它一进来就被当成过期条目清掉
                task["deleted_at"] = model.now_text()
            trash.append(task)

    return {"version": VERSION, "lists": lists, "tasks": tasks, "trash": trash}


def save(data):
    payload = {
        "version": VERSION,
        "lists": [item for item in data.get("lists", []) if item.get("id") != model.DEFAULT_LIST_ID],
        "tasks": list(data.get("tasks", [])),
        "trash": prune_trash(data.get("trash", [])),
    }
    # 先留备份再覆盖：备份要的是"即将被覆盖的那一版"
    jsonio.rotate_backup(file_path(), config.get("backup_keep", 0) or 0)
    jsonio.write_json_atomic(file_path(), payload)
    return payload


def prune_trash(items, keep_days=None):
    """丢掉回收站里超过保留期的条目（keep_days <= 0 = 永久保留）。

    放在"保存时"顺手做，而不是"启动时扫一次" —— 常驻服务可能好几天都不重启，
    启动时清理等于长期不生效。这里多出来的成本只是一次列表遍历。
    """
    items = list(items or [])
    if keep_days is None:
        try:
            keep_days = int(config.get("trash_keep_days", TRASH_KEEP_DAYS))
        except (TypeError, ValueError):
            keep_days = TRASH_KEEP_DAYS
    if keep_days <= 0:
        return items

    deadline = datetime.datetime.now() - datetime.timedelta(days=keep_days)
    kept = []
    for item in items:
        removed = model.parse_stamp(item.get("deleted_at"))
        # 时间戳坏了就留着：宁可多留几条，也不能误删用户还想要的东西
        if removed is None or removed >= deadline:
            kept.append(item)
    return kept
