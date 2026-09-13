"""待办清单工具：action 定义 + 命令行入口。

这一层**完全不感知 HTTP 和 HTML** —— 无论是 Web UI 还是将来的其他承载方式，
调用的都是同一批 action。

组织方式参考微软待办：
  左栏 = 智能视图（我的一天 / 重要 / 已计划 / 已完成）+ 清单（默认「任务」+ 自定义）
  右侧 = 该视图下的任务；点开任务看步骤、备注、到期日
"""

from __future__ import annotations

import datetime

from core.errors import ToolError
from core.tool import Tool, ToolMeta

from tools.todo import model, store

#: 可被 update 修改的字段
UPDATABLE = ("title", "note", "due", "my_day", "important", "list_id", "tags",
             "status", "repeat")

#: 批量操作支持的动作（值都表示"设成什么"，而不是"切换" ——
#: 一批任务里有的已完成有的没完成时，"切换"的语义是不确定的）
BULK_OPS = ("done", "important", "my_day", "move", "remove")

#: 单次批量的上限。不是性能考虑（几百条也就是一次全量写），
#: 而是防手滑：全选之后误点删除时，回收站里一次涌入几千条很难收拾。
MAX_BULK = 500


class TodoTool(Tool):
    meta = ToolMeta(
        tid="todo",
        name="待办清单",
        desc="参考微软待办：我的一天、重要星标、步骤拆解、到期日与多清单。",
        icon="✓",
        order=10,
    )

    # ==================================================================
    # 内部工具
    # ==================================================================
    @staticmethod
    def _find_task(tasks, task_id):
        wanted = str(task_id or "").strip()
        if not wanted:
            raise ToolError("缺少任务 id")
        for task in tasks:
            if task.get("id") == wanted:
                return task
        raise ToolError("找不到该任务：%s" % (wanted,))

    @staticmethod
    def _find_list(lists, list_id):
        wanted = str(list_id or "").strip()
        for item in lists:
            if item.get("id") == wanted:
                return item
        return None

    @staticmethod
    def _find_step(task, step_id):
        wanted = str(step_id or "").strip()
        if not wanted:
            raise ToolError("缺少步骤 id")
        for step in task.get("steps") or []:
            if step.get("id") == wanted:
                return step
        raise ToolError("找不到该步骤：%s" % (wanted,))

    @staticmethod
    def _sort_key(task):
        # 重要的靠前；其次按到期日（无到期日的排最后）；再按创建时间
        return (
            0 if task.get("important") else 1,
            task.get("due") or "9999-99-99",
            task.get("created") or "",
        )

    @staticmethod
    def _stats(tasks):
        done = 0
        for task in tasks:
            if task.get("status") == model.STATUS_DONE:
                done += 1
        return {"total": len(tasks), "active": len(tasks) - done, "done": done}

    @staticmethod
    def _view_counts(tasks, trash=None):
        counts = {"all": 0, "my_day": 0, "important": 0, "planned": 0,
                  "completed": 0, "trash": len(trash or [])}
        for task in tasks:
            if task.get("status") == model.STATUS_DONE:
                counts["completed"] += 1
                continue
            counts["all"] += 1
            if model.is_in_my_day(task):
                counts["my_day"] += 1
            if task.get("important"):
                counts["important"] += 1
            if task.get("due"):
                counts["planned"] += 1
        return counts

    @classmethod
    def _lists_with_counts(cls, lists, tasks):
        counts = {}
        for task in tasks:
            if task.get("status") == model.STATUS_DONE:
                continue
            key = task.get("list_id") or model.DEFAULT_LIST_ID
            counts[key] = counts.get(key, 0) + 1
        result = []
        for item in lists:
            result.append({
                "id": item["id"],
                "name": item["name"],
                "order": item.get("order", 0),
                "count": counts.get(item["id"], 0),
            })
        return result

    def _select(self, tasks, view, list_id, keyword):
        # 搜索是**全局**的（微软待办也是这个行为）：
        # 否则用户在「我的一天」里搜别处的任务会搜不到，很反直觉。
        if keyword:
            chosen = [t for t in tasks if self._match(t, keyword)]
            chosen.sort(key=self._search_key)
            return chosen

        if view == model.VIEW_COMPLETED:
            chosen = [t for t in tasks if t.get("status") == model.STATUS_DONE]
        elif view == model.VIEW_ALL:
            # 所有未完成任务，跨清单 —— 任务分散在多个清单时不用挨个点
            chosen = [t for t in tasks if t.get("status") != model.STATUS_DONE]
        elif view == model.VIEW_MY_DAY:
            chosen = [t for t in tasks
                      if t.get("status") != model.STATUS_DONE
                      and model.is_in_my_day(t)]
        elif view == model.VIEW_IMPORTANT:
            chosen = [t for t in tasks
                      if t.get("status") != model.STATUS_DONE and t.get("important")]
        elif view == model.VIEW_PLANNED:
            chosen = [t for t in tasks
                      if t.get("status") != model.STATUS_DONE and t.get("due")]
        else:                                   # 清单视图只显示未完成
            chosen = [t for t in tasks
                      if t.get("status") != model.STATUS_DONE
                      and (t.get("list_id") or model.DEFAULT_LIST_ID) == list_id]

        if view == model.VIEW_COMPLETED:
            chosen.sort(key=lambda t: t.get("done_at") or "", reverse=True)
        else:
            chosen.sort(key=self._sort_key)
        return chosen

    @staticmethod
    def _search_key(task):
        return (0 if task.get("status") != model.STATUS_DONE else 1,) \
            + TodoTool._sort_key(task)

    @staticmethod
    def _match(task, keyword):
        if keyword in (task.get("title") or "").lower():
            return True
        if keyword in (task.get("note") or "").lower():
            return True
        for tag in task.get("tags") or []:
            if keyword in str(tag).lower():
                return True
        for step in task.get("steps") or []:
            if keyword in (step.get("title") or "").lower():
                return True
        return False

    def _group(self, tasks, view, searching):
        """统一返回 groups 结构，前端可以无差别渲染。"""
        if view == model.VIEW_PLANNED and not searching:
            return self._planned_groups(tasks)
        if not tasks:
            return []
        return [{"key": "all", "label": "", "tasks": tasks}]

    @staticmethod
    def _planned_groups(tasks):
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        week_end = model.week_end(today)          # 与到期日快捷项共用同一口径

        buckets = [
            ("overdue", "已过期", []),
            ("today", "今天", []),
            ("tomorrow", "明天", []),
            ("week", "本周", []),
            ("later", "以后", []),
        ]
        index = dict((key, bucket) for key, _, bucket in buckets)

        for task in tasks:
            due = model.parse_date(task.get("due"))
            if due is None:
                key = "later"
            elif due < today:
                key = "overdue"
            elif due == today:
                key = "today"
            elif due == tomorrow:
                key = "tomorrow"
            elif due <= week_end:
                key = "week"
            else:
                key = "later"
            index[key].append(task)

        return [{"key": key, "label": label, "tasks": items}
                for key, label, items in buckets if items]

    @staticmethod
    def _set_status(task, status):
        if status not in model.STATUSES:
            raise ToolError("状态非法：%s" % (status,))
        task["status"] = status
        task["done_at"] = model.now_text() if status == model.STATUS_DONE else ""

    @staticmethod
    def _complete(task):
        """完成一条任务。所有完成路径（单条勾选 / 批量完成 / update status）都走这里。

        重复任务"完成"即顺延：不生成新卡、卡片回到未完成、到期日推到下一周期
        （defer_repeat 内部已处理 due/my_day/步骤重置/状态回滚）。
        普通任务才真正标记为已完成 —— 这样重复任务永远不会出现在「已完成」视图。
        返回 True 表示发生了顺延（调用方据此决定要不要给用户反馈）。
        """
        if model.normalize_repeat(task.get("repeat")) != model.REPEAT_NONE:
            model.defer_repeat(task)
            return True
        TodoTool._set_status(task, model.STATUS_DONE)
        return False

    @staticmethod
    def _touch(task):
        task["updated"] = model.now_text()

    def _persist(self, data):
        store.save(data)

    # ==================================================================
    # 视图
    # ==================================================================
    def act_board(self, payload):
        data = store.load()
        lists, tasks = data["lists"], data["tasks"]
        trash = data.get("trash") or []

        view = str(payload.get("view") or model.VIEW_MY_DAY).strip()
        if view not in model.VIEWS:
            view = model.VIEW_MY_DAY

        list_id = str(payload.get("list_id") or model.DEFAULT_LIST_ID).strip()
        if self._find_list(lists, list_id) is None:
            list_id = model.DEFAULT_LIST_ID

        keyword = str(payload.get("keyword") or "").strip().lower()
        title = ""

        if view == model.VIEW_TRASH:
            # 回收站是另一份数据，不走 _select（那边的任务是"活的"）
            selected = sorted(trash, key=lambda t: t.get("deleted_at") or "", reverse=True)
            groups = [{"key": "all", "label": "", "tasks": selected}] if selected else []
        else:
            selected = self._select(tasks, view, list_id, keyword)
            groups = self._group(selected, view, bool(keyword))
            if view == model.VIEW_LIST:
                item = self._find_list(lists, list_id)
                title = item["name"] if item else model.DEFAULT_LIST_NAME
            if keyword:
                title = "搜索：%s" % (keyword,)

        return {
            "view": view,
            "list_id": list_id,
            "title": title,
            "today": model.today_text(),
            "presets": model.due_presets(),        # 到期日快捷项（口径在 model 里统一）
            "lists": self._lists_with_counts(lists, tasks),
            "views": self._view_counts(tasks, trash),
            "groups": groups,
            "shown": len(selected),
            "stats": self._stats(tasks),
            "store": store.path_text(),
        }

    # ==================================================================
    # 任务增删改
    # ==================================================================
    def act_add(self, payload):
        data = store.load()
        view = str(payload.get("view") or "").strip()

        # 已完成 / 回收站是"看历史"的视图：往里添加的任务不会出现在当前列表里，
        # 用户会以为没加上（任务其实加进了默认清单）。直接拒绝，把错误说清楚。
        if view in (model.VIEW_COMPLETED, model.VIEW_TRASH):
            raise ToolError("这个视图是看历史的，不能在这里添加任务，请切换到其他视图")

        list_id = str(payload.get("list_id") or model.DEFAULT_LIST_ID).strip()
        if self._find_list(data["lists"], list_id) is None:
            list_id = model.DEFAULT_LIST_ID

        extra = {
            "repeat": model.normalize_repeat(payload.get("repeat")),
        }
        if view == model.VIEW_MY_DAY:
            extra["my_day"] = model.today_text()
        elif view == model.VIEW_IMPORTANT:
            extra["important"] = True
        elif view == model.VIEW_PLANNED:
            extra["due"] = model.normalize_date(payload.get("due")) or model.today_text()

        task = model.make_task(payload.get("title"), list_id, **extra)
        data["tasks"].append(task)
        self._persist(data)
        return {"task": task}

    def act_update(self, payload):
        data = store.load()
        task = self._find_task(data["tasks"], payload.get("id"))

        fields = payload.get("fields")
        if fields is None:
            fields = {}
        if not isinstance(fields, dict):
            raise ToolError("fields 必须是对象")

        unknown = [k for k in fields if k not in UPDATABLE]
        if unknown:
            raise ToolError("不支持的字段：%s" % (", ".join(sorted(unknown)),))

        if "title" in fields:
            task["title"] = model.clean_title(fields.get("title"))
        if "note" in fields:
            task["note"] = str(fields.get("note") or "").strip()
        if "due" in fields:
            task["due"] = model.normalize_date(fields.get("due"))
        if "repeat" in fields:
            task["repeat"] = model.normalize_repeat(fields.get("repeat"))
        if "my_day" in fields:
            task["my_day"] = model.normalize_date(fields.get("my_day"))
        if "important" in fields:
            task["important"] = model.as_bool(fields.get("important"))
        if "tags" in fields:
            task["tags"] = model.normalize_tags(fields.get("tags"))
        if "list_id" in fields:
            wanted = str(fields.get("list_id") or "").strip()
            if self._find_list(data["lists"], wanted) is None:
                raise ToolError("清单不存在：%s" % (wanted,))
            task["list_id"] = wanted
        if "status" in fields:
            wanted = str(fields.get("status") or "").strip()
            if wanted == model.STATUS_DONE:
                # 与勾选完成同一路径：重复任务在这里同样顺延，不会变成"已完成"
                self._complete(task)
            else:
                self._set_status(task, wanted)

        self._touch(task)
        self._persist(data)
        return {"task": task}

    def act_toggle(self, payload):
        data = store.load()
        task = self._find_task(data["tasks"], payload.get("id"))
        target = model.STATUS_TODO if task.get("status") == model.STATUS_DONE \
            else model.STATUS_DONE

        # 取消完成（done→todo）是**单纯恢复**，不顺延 —— 否则用户想撤销
        # 一个误勾时，顺延会把任务日期推走，造成二次破坏。
        deferred = None
        if target == model.STATUS_TODO:
            self._set_status(task, model.STATUS_TODO)
        else:
            deferred = self._complete(task) and task.get("due")

        self._touch(task)
        self._persist(data)
        result = {"task": task}
        if deferred:
            # 顺延后卡片仍处于未完成，没有这个提示用户会以为没勾上
            result["deferred_to"] = deferred
        return result

    def act_toggle_important(self, payload):
        data = store.load()
        task = self._find_task(data["tasks"], payload.get("id"))
        task["important"] = not task.get("important")
        self._touch(task)
        self._persist(data)
        return {"task": task}

    def act_toggle_my_day(self, payload):
        """加入 / 移出「我的一天」。

        加入 = 把 my_day 设为今天；移出 = 清空。
        判断"当前是否在"用可见性（is_in_my_day，含昨天遗留的任务），
        而不是 `my_day == today` —— 否则昨天没做完的任务，今天看到的是
        ☀ 已点亮（可见），却因为 my_day 是昨天而把"点亮"误判成"未加入"，
        点一下它不会被移出，反而把标记更新成今天，永远移不出去。
        """
        data = store.load()
        task = self._find_task(data["tasks"], payload.get("id"))
        if model.is_in_my_day(task):
            task["my_day"] = ""
        else:
            task["my_day"] = model.today_text()
        self._touch(task)
        self._persist(data)
        return {"task": task}

    @staticmethod
    def _to_trash(trash, tasks):
        """把要删的任务打上删除时间并挪进回收站。

        所有删除路径（单条删除、清理已完成）都走这里 ——
        "删除"在这个工具里永远是软删除，彻底清除只能从回收站里显式做。
        """
        stamp = model.now_text()
        for task in tasks:
            task["deleted_at"] = stamp
            trash.append(task)
        return len(tasks)

    def act_remove(self, payload):
        data = store.load()
        task = self._find_task(data["tasks"], payload.get("id"))
        data["tasks"] = [t for t in data["tasks"] if t.get("id") != task.get("id")]
        self._to_trash(data["trash"], [task])
        self._persist(data)
        return {"removed": task.get("id")}

    def act_clear_done(self, payload):
        data = store.load()
        done = [t for t in data["tasks"] if t.get("status") == model.STATUS_DONE]
        data["tasks"] = [t for t in data["tasks"] if t.get("status") != model.STATUS_DONE]
        self._to_trash(data["trash"], done)
        self._persist(data)
        return {"removed": len(done)}

    def act_bulk(self, payload):
        """批量操作多条任务，**一次读写**。

        为什么不让前端循环调用单条 action：N 条就是 N 次全量写盘 + N 次全量刷新，
        而且中途哪一次失败，数据会停在"改了一半"的状态。

        语义要点：
        - 所有 op 都是"设成指定值"而不是"切换"，见 BULK_OPS 的注释；
        - 找不到的 id 直接忽略（可能刚被别处删掉），不算错误；
        - 回收站里的任务不在 data["tasks"] 里，天然不会被批量操作碰到。
        """
        op = str(payload.get("op") or "").strip()
        if op not in BULK_OPS:
            raise ToolError("不支持的批量操作：%s" % (op or "(空)",))

        raw = payload.get("ids")
        if not isinstance(raw, (list, tuple)):
            raise ToolError("ids 必须是列表")

        wanted = []
        for value in raw:
            key = str(value or "").strip()
            if key and key not in wanted:
                wanted.append(key)
        if not wanted:
            raise ToolError("没有选中任何任务")
        if len(wanted) > MAX_BULK:
            raise ToolError("一次最多处理 %d 条" % (MAX_BULK,))

        value = payload.get("value")
        target = str(value or "").strip() if op == "move" else ""

        data = store.load()
        # 清单校验必须放在"选中集为空就直接返回"之前 ——
        # 否则传了不存在的清单、又恰好选中集为空时会被静默吞掉，
        # 调用方会以为移动成功了。
        if op == "move" and self._find_list(data["lists"], target) is None:
            raise ToolError("清单不存在：%s" % (target,))

        tasks = [t for t in data["tasks"] if t.get("id") in wanted]
        if not tasks:
            # 选中的都被删掉了：当作无事发生，不报错（前端会刷新成最新状态）
            return {"op": op, "changed": 0, "selected": 0}

        changed = 0

        if op == "remove":
            data["tasks"] = [t for t in data["tasks"] if t.get("id") not in wanted]
            changed = self._to_trash(data["trash"], tasks)
        elif op == "move":
            for task in tasks:
                if (task.get("list_id") or model.DEFAULT_LIST_ID) != target:
                    task["list_id"] = target
                    self._touch(task)
                    changed += 1
        elif op == "done":
            want = model.as_bool(value)
            target = model.STATUS_DONE if want else model.STATUS_TODO
            for task in tasks:
                if task.get("status") != target:
                    if target == model.STATUS_DONE:
                        self._complete(task)   # 重复任务批量完成也顺延，不进已完成
                    else:
                        self._set_status(task, target)
                    self._touch(task)
                    changed += 1
        elif op == "important":
            want = model.as_bool(value)
            for task in tasks:
                if bool(task.get("important")) != want:
                    task["important"] = want
                    self._touch(task)
                    changed += 1
        elif op == "my_day":
            want = model.as_bool(value)
            mark = model.today_text() if want else ""
            for task in tasks:
                if (task.get("my_day") or "") != mark:
                    task["my_day"] = mark
                    self._touch(task)
                    changed += 1

        self._persist(data)
        return {"op": op, "changed": changed, "selected": len(tasks)}

    # ==================================================================
    # 步骤
    # ==================================================================
    def act_add_step(self, payload):
        data = store.load()
        task = self._find_task(data["tasks"], payload.get("id"))
        steps = task.setdefault("steps", [])
        if len(steps) >= model.MAX_STEPS:
            raise ToolError("单个任务最多 %d 个步骤" % (model.MAX_STEPS,))
        step = model.make_step(payload.get("title"))
        # 追加在末尾：用户是按"先做什么后做什么"的顺序输入步骤的，
        # 插到最前面会把顺序颠倒过来
        steps.append(step)
        self._touch(task)
        self._persist(data)
        return {"task": task, "step": step}

    def act_toggle_step(self, payload):
        data = store.load()
        task = self._find_task(data["tasks"], payload.get("id"))
        step = self._find_step(task, payload.get("step_id"))
        step["done"] = not step.get("done")
        self._touch(task)
        self._persist(data)
        return {"task": task}

    def act_update_step(self, payload):
        data = store.load()
        task = self._find_task(data["tasks"], payload.get("id"))
        step = self._find_step(task, payload.get("step_id"))
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ToolError("步骤内容不能为空")
        step["title"] = title[:model.MAX_TITLE]
        self._touch(task)
        self._persist(data)
        return {"task": task}

    def act_remove_step(self, payload):
        data = store.load()
        task = self._find_task(data["tasks"], payload.get("id"))
        step = self._find_step(task, payload.get("step_id"))
        task["steps"] = [s for s in (task.get("steps") or []) if s.get("id") != step["id"]]
        self._touch(task)
        self._persist(data)
        return {"task": task}

    # ==================================================================
    # 清单
    # ==================================================================
    def act_add_list(self, payload):
        data = store.load()
        raw = payload.get("name")
        if raw is None:
            # 不给名字 = 自动取一个不重名的默认名（界面用它来"建完直接改名"）。
            # 传了空字符串仍视为错误，避免静默改名带来的意外。
            name = model.next_list_name([i["name"] for i in data["lists"]])
        else:
            name = str(raw).strip()
            if not name:
                raise ToolError("清单名称不能为空")
        for item in data["lists"]:
            if item["name"] == name:
                raise ToolError("已存在同名清单：%s" % (name,))
        order = 1 + max([int(i.get("order", 0)) for i in data["lists"]] or [0])
        item = model.make_list(name, order)
        data["lists"].append(item)
        self._persist(data)
        return {"list": item}

    def act_rename_list(self, payload):
        data = store.load()
        item = self._find_list(data["lists"], payload.get("list_id"))
        if item is None:
            raise ToolError("清单不存在")
        if item["id"] == model.DEFAULT_LIST_ID:
            raise ToolError("默认清单「%s」不可重命名" % (model.DEFAULT_LIST_NAME,))
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ToolError("清单名称不能为空")
        name = name[:model.MAX_LIST_NAME]
        # 与 add_list 保持一致：不允许重名，否则左栏会出现两个看不出区别的清单
        for other in data["lists"]:
            if other["id"] != item["id"] and other["name"] == name:
                raise ToolError("已存在同名清单：%s" % (name,))
        item["name"] = name
        self._persist(data)
        return {"list": item}

    def act_reorder_lists(self, payload):
        """按给定顺序重排**自定义**清单。

        只接受"要排在前面的那批 id"，其余按原相对顺序接在后面 ——
        这样即使前端传来的顺序已经过期（比如别处刚建/删了一个清单），也不会出错。
        默认清单永远排第一，不参与排序。
        """
        data = store.load()
        raw = payload.get("ids")
        if not isinstance(raw, (list, tuple)):
            raise ToolError("ids 必须是列表")

        wanted = []
        for value in raw:
            key = str(value or "").strip()
            if key and key != model.DEFAULT_LIST_ID and key not in wanted:
                wanted.append(key)

        ordered = []
        for key in wanted:
            item = self._find_list(data["lists"], key)
            if item is not None:
                ordered.append(item)
        for item in data["lists"]:
            if item["id"] != model.DEFAULT_LIST_ID and item not in ordered:
                ordered.append(item)

        for index, item in enumerate(ordered, start=1):
            item["order"] = index
        self._persist(data)
        return {"lists": self._lists_with_counts(ordered, data["tasks"])}

    def act_remove_list(self, payload):
        """删除清单；其中的任务移回默认清单，避免误删数据。"""
        data = store.load()
        list_id = str(payload.get("list_id") or "").strip()
        if list_id == model.DEFAULT_LIST_ID:
            raise ToolError("默认清单不可删除")
        item = self._find_list(data["lists"], list_id)
        if item is None:
            raise ToolError("清单不存在")

        moved = 0
        for task in data["tasks"]:
            if (task.get("list_id") or model.DEFAULT_LIST_ID) == list_id:
                task["list_id"] = model.DEFAULT_LIST_ID
                moved += 1
        data["lists"] = [i for i in data["lists"] if i["id"] != list_id]
        self._persist(data)
        return {"removed": list_id, "moved": moved}

    # ==================================================================
    # 回收站
    # ==================================================================
    @staticmethod
    def _find_trashed(trash, task_id):
        wanted = str(task_id or "").strip()
        if not wanted:
            raise ToolError("缺少任务 id")
        for task in trash:
            if task.get("id") == wanted:
                return task
        raise ToolError("回收站里找不到该任务：%s" % (wanted,))

    def act_restore(self, payload):
        """从回收站恢复一条。原清单若已被删掉，就落回默认清单。"""
        data = store.load()
        trash = data["trash"]
        task = self._find_trashed(trash, payload.get("id"))

        if self._find_list(data["lists"], task.get("list_id")) is None:
            task["list_id"] = model.DEFAULT_LIST_ID
        task["deleted_at"] = ""
        trash.remove(task)
        data["tasks"].append(task)
        self._persist(data)
        return {"task": task}

    def act_purge(self, payload):
        """从回收站彻底删除一条 —— 不可恢复。"""
        data = store.load()
        task = self._find_trashed(data["trash"], payload.get("id"))
        data["trash"] = [t for t in data["trash"] if t.get("id") != task["id"]]
        self._persist(data)
        return {"purged": task["id"]}

    def act_empty_trash(self, payload):
        """清空回收站 —— 不可恢复。"""
        data = store.load()
        removed = len(data["trash"])
        data["trash"] = []
        self._persist(data)
        return {"removed": removed}

    # ==================================================================
    def act_stats(self, payload):
        data = store.load()
        return {
            "stats": self._stats(data["tasks"]),
            "views": self._view_counts(data["tasks"]),
            "store": store.path_text(),
        }

    def actions(self):
        return {
            "board": self.act_board,
            "add": self.act_add,
            "update": self.act_update,
            "toggle": self.act_toggle,
            "toggle_important": self.act_toggle_important,
            "toggle_my_day": self.act_toggle_my_day,
            "remove": self.act_remove,
            "clear_done": self.act_clear_done,
            "bulk": self.act_bulk,
            "add_step": self.act_add_step,
            "toggle_step": self.act_toggle_step,
            "update_step": self.act_update_step,
            "remove_step": self.act_remove_step,
            "add_list": self.act_add_list,
            "rename_list": self.act_rename_list,
            "reorder_lists": self.act_reorder_lists,
            "remove_list": self.act_remove_list,
            "restore": self.act_restore,
            "purge": self.act_purge,
            "empty_trash": self.act_empty_trash,
            "stats": self.act_stats,
        }

    # ==================================================================
    # 命令行
    # ==================================================================
    def cli(self, argv):
        if not argv:
            return self._cli_list([])

        command, rest = argv[0], argv[1:]
        table = {
            "list": self._cli_list, "ls": self._cli_list,
            "add": self._cli_add,
            "done": self._cli_done,
            "undone": self._cli_undone,
            "star": self._cli_star,
            "today": self._cli_today,
            "rm": self._cli_remove, "del": self._cli_remove,
            "clear": self._cli_clear,
            "where": self._cli_where,
            "help": self._cli_help, "-h": self._cli_help, "--help": self._cli_help,
        }
        handler = table.get(command)
        if handler is None:
            print("未知命令：%s" % (command,))
            self._cli_help([])
            return 2
        return handler(rest)

    def _cli_list(self, argv):
        view, list_id, keyword, index = model.VIEW_MY_DAY, model.DEFAULT_LIST_ID, "", 0
        while index < len(argv):
            token = argv[index]
            if token in ("-a", "--all"):
                view = model.VIEW_LIST
            elif token in ("-i", "--important"):
                view = model.VIEW_IMPORTANT
            elif token in ("-p", "--planned"):
                view = model.VIEW_PLANNED
            elif token in ("-d", "--done"):
                view = model.VIEW_COMPLETED
            else:
                keyword = token if not keyword else keyword + " " + token
            index += 1

        data = self.act_board({"view": view, "list_id": list_id, "keyword": keyword})
        total = 0
        for group in data["groups"]:
            if group["label"]:
                print("[%s]" % (group["label"],))
            for task in group["tasks"]:
                total += 1
                mark = "[x]" if task["status"] == model.STATUS_DONE else "[ ]"
                star = "*" if task["important"] else " "
                due = task["due"] or "----------"
                done_steps, all_steps = model.step_progress(task)
                progress = ("  %d/%d" % (done_steps, all_steps)) if all_steps else ""
                print("  %s%s %s  %-10s %s%s"
                      % (mark, star, task["id"], due, task["title"], progress))
        if not total:
            print("（这个视图里没有任务）")
        stats = data["stats"]
        print("--- 显示 %d 项 | 全部 %d 项：未完成 %d，已完成 %d"
              % (total, stats["total"], stats["active"], stats["done"]))
        return 0

    def _cli_add(self, argv):
        words, due, index = [], "", 0
        while index < len(argv):
            token = argv[index]
            if token in ("-d", "--due") and index + 1 < len(argv):
                due = argv[index + 1]
                index += 2
            else:
                words.append(token)
                index += 1
        title = " ".join(words).strip()
        if not title:
            print("用法：todo add <标题> [--due 2026-09-20]")
            return 2
        task = self.act_add({"title": title, "due": due})["task"]
        print("已添加  %s  %s" % (task["id"], task["title"]))
        return 0

    def _cli_done(self, argv):
        return self._cli_set_status(argv, model.STATUS_DONE, "已完成")

    def _cli_undone(self, argv):
        return self._cli_set_status(argv, model.STATUS_TODO, "已恢复未完成")

    def _cli_set_status(self, argv, status, label):
        if not argv:
            print("用法：todo %s <id>"
                  % ("done" if status == model.STATUS_DONE else "undone",))
            return 2
        task = self.act_update({"id": argv[0], "fields": {"status": status}})["task"]
        print("%s  %s" % (label, task["title"]))
        return 0

    def _cli_star(self, argv):
        if not argv:
            print("用法：todo star <id>")
            return 2
        task = self.act_toggle_important({"id": argv[0]})["task"]
        print("%s重要  %s" % ("已标记为" if task["important"] else "已取消", task["title"]))
        return 0

    def _cli_today(self, argv):
        if not argv:
            print("用法：todo today <id>")
            return 2
        task = self.act_toggle_my_day({"id": argv[0]})["task"]
        inside = task["my_day"] == model.today_text()
        print("%s「我的一天」  %s" % ("已加入" if inside else "已移出", task["title"]))
        return 0

    def _cli_remove(self, argv):
        if not argv:
            print("用法：todo rm <id>")
            return 2
        print("已删除  %s" % (self.act_remove({"id": argv[0]})["removed"],))
        return 0

    def _cli_clear(self, argv):
        print("已清理 %d 项已完成任务" % (self.act_clear_done({})["removed"],))
        return 0

    def _cli_where(self, argv):
        print("数据文件：%s" % (store.path_text(),))
        return 0

    def _cli_help(self, argv):
        print("待办清单（todo）命令：")
        print("  list [关键词] [-a|-i|-p|-d]")
        print("        默认显示「我的一天」；-a 任务清单  -i 重要  -p 已计划  -d 已完成")
        print("  add <标题> [--due 2026-09-20]")
        print("  done <id>      切换完成状态")
        print("  undone <id>    同上（别名，便于表达意图）")
        print("  star <id>      切换重要星标")
        print("  today <id>     加入 / 移出「我的一天」")
        print("  rm <id>        删除")
        print("  clear          清理全部已完成")
        print("  where          显示数据文件位置")
        return 0
