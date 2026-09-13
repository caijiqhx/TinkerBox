"""任务数据模型（v2）。

参考微软待办的组织方式：
- **清单（list）**：任务归属某个清单，至少有一个默认清单
- **重要（important）**：星标
- **我的一天（my_day）**：存日期字符串，只有等于"今天"的任务才出现在该视图 ——
  这样每天自动清空，不需要任何后台定时任务
- **到期日（due）**：日期字符串，用于"已计划"视图
- **步骤（steps）**：子任务，本任务内嵌
- 完成状态简化为 done / 未完成两种（对齐微软待办的单复选框）

全部字段用普通 dict 表示，与 JSON 同构。normalize_* 负责把从磁盘读到的、
可能不完整或被手工改坏的记录补齐 —— 这是"数据坏了也不能让程序崩"的第一道防线。
"""

from __future__ import annotations

import datetime
import uuid

from core.errors import ToolError

# ---------------------------------------------------------------- 常量

STATUS_TODO = "todo"
STATUS_DONE = "done"
STATUSES = (STATUS_TODO, STATUS_DONE)

DEFAULT_LIST_ID = "default"
DEFAULT_LIST_NAME = "任务"

#: 新建清单时的默认名（带上序号，见 next_list_name）
NEW_LIST_NAME = "新清单"

MAX_TITLE = 200
MAX_LIST_NAME = 40
MAX_TAGS = 12
MAX_STEPS = 50

#: 智能视图
VIEW_MY_DAY = "my_day"
VIEW_IMPORTANT = "important"
VIEW_PLANNED = "planned"
VIEW_COMPLETED = "completed"
VIEW_LIST = "list"
VIEWS = (VIEW_MY_DAY, VIEW_IMPORTANT, VIEW_PLANNED, VIEW_COMPLETED, VIEW_LIST)


# ---------------------------------------------------------------- 时间


def now_text():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_text():
    return datetime.date.today().isoformat()


def parse_date(value):
    """把 YYYY-MM-DD 解析成 date；非法返回 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    parts = text[:10].split("-")
    if len(parts) != 3:
        return None
    try:
        return datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (TypeError, ValueError):
        return None


def normalize_date(value):
    """规范化为 YYYY-MM-DD；非法一律返回空串（宁可为空，不可留下坏值）。"""
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else ""


# ---------------------------------------------------------------- 基础清洗


def _text(value, limit):
    text = str(value or "").strip()
    return text[:limit]


def clean_title(value):
    title = _text(value, MAX_TITLE)
    if not title:
        raise ToolError("标题不能为空")
    return title


def normalize_tags(tags):
    if tags is None:
        return []
    if isinstance(tags, str):
        tags = tags.replace("，", ",").replace("、", ",").split(",")
    if not isinstance(tags, (list, tuple)):
        raise ToolError("标签必须是列表，或逗号分隔的字符串")
    result = []
    for raw in tags:
        tag = str(raw).strip()
        if tag and tag not in result:
            result.append(tag)
    return result[:MAX_TAGS]


def as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


# ---------------------------------------------------------------- 构造


def make_list(name, order=0):
    name = _text(name, MAX_LIST_NAME)
    if not name:
        raise ToolError("清单名称不能为空")
    return {"id": uuid.uuid4().hex[:12], "name": name, "order": int(order or 0)}


def default_list():
    return {"id": DEFAULT_LIST_ID, "name": DEFAULT_LIST_NAME, "order": 0}


def next_list_name(existing_names):
    """给新清单取一个不重名的默认名字：新清单 1、新清单 2 …

    新建清单时不再让用户先弹框输名字 —— 先生成一个能用的名字，建完直接改名即可。
    编号取**最小的空缺**（删掉「新清单 1」后再建会补回 1），这样结果可预期。
    """
    taken = set(existing_names or [])
    index = 1
    while True:
        candidate = "%s %d" % (NEW_LIST_NAME, index)
        if candidate not in taken:
            return candidate
        index += 1


def make_step(title):
    title = _text(title, MAX_TITLE)
    if not title:
        raise ToolError("步骤内容不能为空")
    return {"id": uuid.uuid4().hex[:12], "title": title, "done": False}


def make_task(title, list_id=DEFAULT_LIST_ID, important=False,
              my_day="", due="", note="", tags=None, status=STATUS_TODO):
    stamp = now_text()
    return {
        "id": uuid.uuid4().hex[:12],
        "list_id": str(list_id or DEFAULT_LIST_ID),
        "title": clean_title(title),
        "status": status if status in STATUSES else STATUS_TODO,
        "important": as_bool(important),
        "my_day": normalize_date(my_day),
        "due": normalize_date(due),
        "note": str(note or "").strip(),
        "steps": [],
        "tags": normalize_tags(tags),
        "created": stamp,
        "updated": stamp,
        "done_at": "",
    }


# ---------------------------------------------------------------- 容错修复


def normalize_step(item):
    if not isinstance(item, dict):
        return None
    title = _text(item.get("title"), MAX_TITLE)
    if not title:
        return None
    return {
        "id": str(item.get("id") or uuid.uuid4().hex[:12]),
        "title": title,
        "done": as_bool(item.get("done")),
    }


def normalize_list(item, order=0):
    if not isinstance(item, dict):
        return None
    name = _text(item.get("name"), MAX_LIST_NAME)
    if not name:
        return None
    lid = str(item.get("id") or uuid.uuid4().hex[:12])
    if lid == DEFAULT_LIST_ID:
        return None                      # 默认清单由 store 统一补，不重复
    try:
        order = int(item.get("order", order))
    except (TypeError, ValueError):
        order = order
    return {"id": lid, "name": name, "order": order}


def normalize_task(item, valid_list_ids=None):
    """把任意输入修成合法任务；无法修复时返回 None（该条被丢弃）。"""
    if not isinstance(item, dict):
        return None

    title = _text(item.get("title"), MAX_TITLE)
    if not title:
        return None

    status = item.get("status")
    if status not in STATUSES:
        # 兼容 v1 的 "doing"，以及任何未知取值
        status = STATUS_TODO

    list_id = str(item.get("list_id") or DEFAULT_LIST_ID)
    if valid_list_ids is not None and list_id not in valid_list_ids:
        list_id = DEFAULT_LIST_ID

    steps = []
    raw_steps = item.get("steps")
    if isinstance(raw_steps, (list, tuple)):
        for raw in raw_steps[:MAX_STEPS]:
            step = normalize_step(raw)
            if step is not None:
                steps.append(step)

    try:
        tags = normalize_tags(item.get("tags"))
    except ToolError:
        tags = []

    stamp = str(item.get("created") or "") or now_text()

    return {
        "id": str(item.get("id") or uuid.uuid4().hex[:12]),
        "list_id": list_id,
        "title": title,
        "status": status,
        "important": as_bool(item.get("important")),
        "my_day": normalize_date(item.get("my_day")),
        "due": normalize_date(item.get("due")),
        "note": str(item.get("note") or ""),
        "steps": steps,
        "tags": tags,
        "created": stamp,
        "updated": str(item.get("updated") or "") or stamp,
        "done_at": str(item.get("done_at") or ""),
    }


def step_progress(task):
    """返回 (已完成步骤数, 总步骤数)。"""
    steps = task.get("steps") or []
    done = 0
    for step in steps:
        if step.get("done"):
            done += 1
    return done, len(steps)
