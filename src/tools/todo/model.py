"""任务数据模型（v2）。

参考微软待办的组织方式：
- **清单（list）**：任务归属某个清单，至少有一个默认清单
- **重要（important）**：星标
- **我的一天（my_day）**：存加入时的日期，只要**不晚于今天且未完成**就出现在该视图 ——
  昨天没做完的今天自动延续，不需要任何后台定时任务
- **到期日（due）**：日期字符串，用于"已计划"视图
- **步骤（steps）**：子任务，本任务内嵌
- 完成状态简化为 done / 未完成两种（对齐微软待办的单复选框）

全部字段用普通 dict 表示，与 JSON 同构。normalize_* 负责把从磁盘读到的、
可能不完整或被手工改坏的记录补齐 —— 这是"数据坏了也不能让程序崩"的第一道防线。
"""

from __future__ import annotations

import calendar
import datetime
import uuid

from core.errors import ToolError

# ---------------------------------------------------------------- 常量

STATUS_TODO = "todo"
STATUS_DONE = "done"
STATUSES = (STATUS_TODO, STATUS_DONE)

#: 重复周期。none = 不重复（默认）
REPEAT_NONE = "none"
REPEAT_DAILY = "daily"
REPEAT_WEEKLY = "weekly"
REPEAT_MONTHLY = "monthly"
REPEATS = (REPEAT_NONE, REPEAT_DAILY, REPEAT_WEEKLY, REPEAT_MONTHLY)

#: 界面上给用户看的周期名
REPEAT_LABELS = {
    REPEAT_NONE: "不重复",
    REPEAT_DAILY: "每天",
    REPEAT_WEEKLY: "每周",
    REPEAT_MONTHLY: "每月",
}

DEFAULT_LIST_ID = "default"
#: 默认清单名。定位是"未分类任务的兜底容器"（新建任务默认落点、
#: 删清单/恢复任务的收容所），不叫「任务」以免和"全部任务"视图混淆。
DEFAULT_LIST_NAME = "未分类"

#: 新建清单时的默认名（带上序号，见 next_list_name）
NEW_LIST_NAME = "新清单"

MAX_TITLE = 200
MAX_LIST_NAME = 40
MAX_TAGS = 12
MAX_STEPS = 50

#: 智能视图
VIEW_ALL = "all"
VIEW_MY_DAY = "my_day"
VIEW_IMPORTANT = "important"
VIEW_PLANNED = "planned"
VIEW_COMPLETED = "completed"
VIEW_LIST = "list"
VIEW_TRASH = "trash"
VIEWS = (VIEW_ALL, VIEW_MY_DAY, VIEW_IMPORTANT, VIEW_PLANNED,
         VIEW_COMPLETED, VIEW_LIST, VIEW_TRASH)


# ---------------------------------------------------------------- 时间


def now_text():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_text():
    return datetime.date.today().isoformat()


def is_in_my_day(task, today=None):
    """任务是否当前可见于「我的一天」。

    my_day 保存的是"加入那天"的日期；只要它**不晚于今天**且任务未完成，
    就持续可见 —— 昨天没做完的今天还在（微软待办行为，不用每天重新点 ☀）。
    重复任务完成时会把这个字段推到未来，未来日期不算可见，
    所以"今天勾掉 → 今天消失"依然成立。
    """
    today = today or datetime.date.today()
    mark = parse_date(task.get("my_day"))
    if mark is None:
        return False
    return mark <= today


def week_end(today=None):
    """今天所在周的周日。

    「已计划」分组和"到期日快捷项"共用这一个函数 —— 否则两处各写一遍，
    迟早出现"点本周末得到的那天，跟已计划里本周末分组对不上"的怪事。
    """
    today = today or datetime.date.today()
    return today + datetime.timedelta(days=(6 - today.weekday()))


def due_presets(today=None):
    """到期日的快捷选项：只有「今天」和「明天」。

    日期由**后端**算、随 board 一起发给前端渲染 ——
    同一份口径不在两个语言里各写一遍，既能被单元测试覆盖，也不会两边漂移。
    """
    today = today or datetime.date.today()
    return [
        {"label": "今天", "value": today.isoformat()},
        {"label": "明天", "value": (today + datetime.timedelta(days=1)).isoformat()},
    ]


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


def parse_stamp(value):
    """解析 now_text() 写出的时间戳；非法返回 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    for fmt, size in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.datetime.strptime(text[:size], fmt)
        except ValueError:
            continue
    return None


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


# ---------------------------------------------------------------- 重复周期


def normalize_repeat(value):
    """把任意输入规范成 repeat 取值；非法一律回落为"不重复"。"""
    text = str(value or "").strip().lower()
    if text not in REPEATS:
        return REPEAT_NONE
    return text


def advance_date(day, repeat):
    """把日期推后一个周期。

    月末防溢出：1月31日 + 每月 → 2月28/29日，而不是 3月3日。
    这比"直接加 31 天"更符合直觉 —— 用户要的是"下个月的这一天"。
    """
    day = day or datetime.date.today()
    if repeat == REPEAT_DAILY:
        return day + datetime.timedelta(days=1)
    if repeat == REPEAT_WEEKLY:
        return day + datetime.timedelta(days=7)
    if repeat == REPEAT_MONTHLY:
        year = day.year + (day.month // 12)
        month = (day.month % 12) + 1
        last = calendar.monthrange(year, month)[1]
        return datetime.date(year, month, min(day.day, last))
    return day


def defer_repeat(task, today=None):
    """把重复任务"顺延"到下一周期，返回顺延后的任务。

    完成一个重复任务时调用：不生成新卡、卡片本身循环使用。
    规则（全部在同一处，避免口径漂移）：
    - 锚点：有 due 且 due >= 今天（还没到计划日）→ 从 **due** 推一周期。
      提前完成（如周一做完周五的例会）不应改变下次计划日期；
      due 已过期 → 从**今天**推，让它补上进度而不是越拖越远；
      没有 due 的重复任务（"每天喝水"）→ 从今天推并补一个 due，
      否则它没有"下次哪天"可言，顺延就失去意义；
    - my_day 同向推一周期（基准取今天）：例行任务做完了，
      下一周期自动回到"我的一天"；my_day 永为"今天"或过期值，取今天最干净；
    - 步骤重置为未勾选、状态回未完成 —— 每个周期重新打卡。
    """
    today = today or datetime.date.today()
    repeat = normalize_repeat(task.get("repeat"))
    if repeat == REPEAT_NONE:
        return task

    due = parse_date(task.get("due"))
    if due is not None and due >= today:
        anchor = due
    else:
        anchor = today
    task["due"] = advance_date(anchor, repeat).isoformat()

    if task.get("my_day"):
        task["my_day"] = advance_date(today, repeat).isoformat()
    task["status"] = STATUS_TODO
    task["done_at"] = ""
    for step in task.get("steps") or []:
        step["done"] = False
    task["updated"] = now_text()
    return task


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
              my_day="", due="", note="", tags=None, status=STATUS_TODO,
              repeat=REPEAT_NONE):
    stamp = now_text()
    return {
        "id": uuid.uuid4().hex[:12],
        "list_id": str(list_id or DEFAULT_LIST_ID),
        "title": clean_title(title),
        "status": status if status in STATUSES else STATUS_TODO,
        "important": as_bool(important),
        "my_day": normalize_date(my_day),
        "due": normalize_date(due),
        "repeat": normalize_repeat(repeat),
        "note": str(note or "").strip(),
        "steps": [],
        "tags": normalize_tags(tags),
        "created": stamp,
        "updated": stamp,
        "done_at": "",
        "deleted_at": "",          # 非空 = 在回收站里（时间戳）
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
        "repeat": normalize_repeat(item.get("repeat")),
        "note": str(item.get("note") or ""),
        "steps": steps,
        "tags": tags,
        "created": stamp,
        "updated": str(item.get("updated") or "") or stamp,
        "done_at": str(item.get("done_at") or ""),
        "deleted_at": str(item.get("deleted_at") or ""),
    }


def step_progress(task):
    """返回 (已完成步骤数, 总步骤数)。"""
    steps = task.get("steps") or []
    done = 0
    for step in steps:
        if step.get("done"):
            done += 1
    return done, len(steps)
