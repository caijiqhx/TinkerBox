"""待办清单工具核心逻辑测试（v2：清单 / 步骤 / 重要 / 我的一天 / 到期日）。

运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import datetime
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from core.errors import ToolError                    # noqa: E402
from services import jsonio                          # noqa: E402
from tools.todo import model, store                  # noqa: E402
from tools.todo.tool import TodoTool                 # noqa: E402


def _today(offset=0):
    return (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()


class TodoToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="toolbox-todo-")
        self._original = store.file_path
        store.file_path = lambda: os.path.join(self.tmp, "todo.json")
        self.tool = TodoTool()

    def tearDown(self):
        store.file_path = self._original
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- 基础
    def test_board_defaults_to_my_day_and_is_empty(self):
        board = self.tool.act_board({})
        self.assertEqual(board["view"], "my_day")
        self.assertEqual(board["shown"], 0)
        self.assertEqual(board["groups"], [])
        self.assertEqual(board["stats"]["total"], 0)

    def test_add_requires_title(self):
        with self.assertRaises(ToolError):
            self.tool.act_add({"title": "   "})

    def test_default_list_always_exists(self):
        board = self.tool.act_board({})
        # 默认清单（未分类）排在最后
        self.assertEqual(board["lists"][-1]["id"], model.DEFAULT_LIST_ID)
        self.assertEqual(board["lists"][-1]["name"], model.DEFAULT_LIST_NAME)

    def test_task_goes_to_default_list(self):
        self.tool.act_add({"title": "买牛奶"})
        board = self.tool.act_board({"view": "list"})
        self.assertEqual(len(board["groups"][0]["tasks"]), 1)
        default = [i for i in board["lists"] if i["id"] == model.DEFAULT_LIST_ID][0]
        self.assertEqual(default["count"], 1)

    # ---------------------------------------------------------------- 视图
    def test_add_in_view_sets_context(self):
        self.tool.act_add({"title": "A", "view": "my_day"})
        self.tool.act_add({"title": "B", "view": "important"})
        self.tool.act_add({"title": "C", "view": "planned"})

        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 1)
        self.assertEqual(self.tool.act_board({"view": "important"})["shown"], 1)
        self.assertEqual(self.tool.act_board({"view": "planned"})["shown"], 1)

        planned = self.tool.act_board({"view": "planned"})["groups"][0]["tasks"][0]
        self.assertEqual(planned["title"], "C")
        self.assertEqual(planned["due"], _today(0))

    def test_add_rejected_in_history_views(self):
        """已完成 / 回收站是"看历史"的视图：往里加任务不会出现在列表里，
        用户会以为没加上。转到这两个视图添加必须被拒绝。"""
        for view in ("completed", "trash"):
            with self.assertRaises(ToolError):
                self.tool.act_add({"title": "看不到的任务", "view": view})

    def test_my_day_carries_over_unfinished(self):
        task = self.tool.act_add({"title": "今天的事"})["task"]
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 0)

        self.tool.act_toggle_my_day({"id": task["id"]})
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 1)

        # 昨天加入、今天未完成 —— 应当**继续可见**（自动延续，不用每天重新点 ☀）
        data = store.load()
        data["tasks"][0]["my_day"] = _today(-1)
        store.save(data)
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 1)
        self.assertEqual(self.tool.act_board({"view": "my_day"})["views"]["my_day"], 1)

    def test_my_day_no_carry_over_if_not_marked(self):
        # my_day 为空 = 从未加入 → 不出现在「我的一天」
        task = self.tool.act_add({"title": "没加进今天"})["task"]
        self.assertEqual(task["my_day"], "")
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 0)

    def test_my_day_carry_over_toggle_removes(self):
        # 延续中的任务（my_day 是昨天）再点 ☀ → 移出（清空），而不是继续"加入今天"
        task = self.tool.act_add({"title": "延续任务"})["task"]
        data = store.load()
        data["tasks"][0]["my_day"] = _today(-1)
        store.save(data)
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 1)

        self.tool.act_toggle_my_day({"id": task["id"]})
        self.assertEqual(store.load()["tasks"][0]["my_day"], "")
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 0)

    def test_my_day_toggle_rejoins_today(self):
        # 移出后再点 ☀ → 重新加入（my_day 回到今天）
        task = self.tool.act_add({"title": "加回来"})["task"]
        self.tool.act_toggle_my_day({"id": task["id"]})
        self.tool.act_toggle_my_day({"id": task["id"]})
        self.tool.act_toggle_my_day({"id": task["id"]})
        self.assertEqual(store.load()["tasks"][0]["my_day"], _today(0))
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 1)

    def test_completed_view_and_toggle(self):
        task = self.tool.act_add({"title": "倒垃圾"})["task"]
        self.assertEqual(self.tool.act_board({"view": "completed"})["shown"], 0)

        self.tool.act_toggle({"id": task["id"]})
        self.assertEqual(self.tool.act_board({"view": "completed"})["shown"], 1)
        self.assertEqual(self.tool.act_board({"view": "list"})["shown"], 0)

        self.tool.act_toggle({"id": task["id"]})
        self.assertEqual(self.tool.act_board({"view": "completed"})["shown"], 0)
        self.assertEqual(self.tool.act_board({"view": "list"})["shown"], 1)

    # ---------------------------------------------------------------- 重复任务（顺延）
    def _make_repeat(self, title, repeat, due="", my_day=""):
        task = self.tool.act_add({"title": title, "repeat": repeat})["task"]
        if due or my_day:
            fields = {}
            if due:
                fields["due"] = due
            if my_day:
                fields["my_day"] = my_day
            self.tool.act_update({"id": task["id"], "fields": fields})
        return task

    def test_repeat_daily_defer_to_tomorrow(self):
        task = self._make_repeat("喝水", "daily", due=_today(0))
        result = self.tool.act_toggle({"id": task["id"]})

        self.assertEqual(result["deferred_to"], _today(1))
        self.assertEqual(result["task"]["status"], "todo")
        # 重复任务永不进已完成视图
        self.assertEqual(self.tool.act_board({"view": "completed"})["shown"], 0)
        # 仍然在已计划里，归到「明天」组
        groups = self.tool.act_board({"view": "planned"})["groups"]
        self.assertIn("明天", [g["label"] for g in groups])

    def test_repeat_never_shows_in_completed_view(self):
        # 无论完成多少次，重复任务始终是未完成，不进已完成视图
        task = self._make_repeat("周例会", "weekly", due=_today(0))
        self.tool.act_toggle({"id": task["id"]})
        self.tool.act_toggle({"id": task["id"]})
        self.assertEqual(self.tool.act_board({"view": "completed"})["shown"], 0)
        self.assertEqual(self.tool.act_board({"view": "planned"})["shown"], 1)

    def test_repeat_without_due_anchors_to_today(self):
        # "每天喝水"没有到期日：完成时自动补 due = 今天 + 一周期
        task = self._make_repeat("喝水", "monthly")
        result = self.tool.act_toggle({"id": task["id"]})
        self.assertEqual(result["task"]["due"],
                         model.advance_date(datetime.date.today(), "monthly").isoformat())

    def test_repeat_advance_crosses_month_boundary(self):
        # 1月31日 + 每月 → 2月28/29，而不是 3月3日
        self.assertEqual(
            model.advance_date(datetime.date(2026, 1, 31), "monthly"),
            datetime.date(2026, 2, 28))
        self.assertEqual(
            model.advance_date(datetime.date(2024, 1, 31), "monthly"),
            datetime.date(2024, 2, 29))          # 闰年
        # 每周固定 +7 天
        self.assertEqual(
            model.advance_date(datetime.date(2026, 9, 13), "weekly"),
            datetime.date(2026, 9, 20))

    def test_repeat_resets_steps_on_defer(self):
        task = self._make_repeat("健身", "daily", due=_today(0))
        added = self.tool.act_add_step({"id": task["id"], "title": "深蹲"})
        step_id = added["step"]["id"]
        self.tool.act_toggle_step({"id": task["id"], "step_id": step_id})
        self.assertTrue(store.load()["tasks"][0]["steps"][0]["done"])

        self.tool.act_toggle({"id": task["id"]})
        self.assertFalse(store.load()["tasks"][0]["steps"][0]["done"])

    def test_repeat_my_day_defers_to_next_period(self):
        task = self._make_repeat("日报", "daily", due="", my_day=_today(0))
        result = self.tool.act_toggle({"id": task["id"]})
        self.assertEqual(result["task"]["my_day"], _today(1))
        # 今天不再出现在「我的一天」
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 0)

    def test_repeat_cancel_toggle_is_pure_restore(self):
        # 普通任务：取消完成（done→todo）就是单纯恢复，没有任何顺延副作用
        task = self.tool.act_add({"title": "普通任务"})["task"]
        self.tool.act_toggle({"id": task["id"]})          # done
        self.tool.act_toggle({"id": task["id"]})          # 取消完成
        reloaded = store.load()["tasks"][0]
        self.assertEqual(reloaded["status"], "todo")
        # 重复任务本身永远到不了 done 状态，toggle 只有"完成→顺延"一个方向
        repeat = self._make_repeat("每日打卡", "daily", due=_today(0))
        self.tool.act_toggle({"id": repeat["id"]})
        self.tool.act_toggle({"id": repeat["id"]})
        self.assertEqual(store.load()["tasks"][1]["status"], "todo")

    def test_repeat_early_completion_keeps_due_anchor(self):
        # 提前完成：due 还在未来（下周），顺延应从 due 推，不改变原计划节奏
        task = self._make_repeat("例会", "weekly", due=_today(7))
        self.tool.act_toggle({"id": task["id"]})
        self.assertEqual(store.load()["tasks"][0]["due"], _today(14))

    def test_repeat_bulk_done_defers_too(self):
        # 批量完成对重复任务同样顺延（与单条勾选一致，否则批量操作会把
        # 重复任务"真正完成"，破坏"永不进已完成视图"的不变式）
        task = self._make_repeat("喝水", "daily", due=_today(0))
        result = self.tool.act_bulk({
            "ids": [task["id"]], "op": "done", "value": True})
        self.assertEqual(result["changed"], 1)
        self.assertEqual(store.load()["tasks"][0]["status"], "todo")
        self.assertEqual(store.load()["tasks"][0]["due"], _today(1))
        self.assertEqual(self.tool.act_board({"view": "completed"})["shown"], 0)

    def test_update_status_done_defers_repeat(self):
        # update 直接改 status=done 与勾选走同一路径：重复任务顺延而非完成
        task = self._make_repeat("周报", "weekly", due=_today(0))
        self.tool.act_update({"id": task["id"], "fields": {"status": "done"}})
        reloaded = store.load()["tasks"][0]
        self.assertEqual(reloaded["status"], "todo")
        self.assertEqual(reloaded["due"], _today(7))
        self.assertEqual(self.tool.act_board({"view": "completed"})["shown"], 0)

    def test_repeat_normalize_handles_bad_input(self):
        self.assertEqual(model.normalize_repeat(""), "none")
        self.assertEqual(model.normalize_repeat("DAILY"), "daily")
        self.assertEqual(model.normalize_repeat("每周"), "none")     # 非法的回落
        self.assertEqual(model.normalize_repeat("monthly"), "monthly")

    def test_repeat_roundtrip_through_store(self):
        task = self._make_repeat("打卡", "daily", due=_today(0))
        # 模拟重载：save/load 一遭后 repeat 字段仍在
        data = store.load()
        store.save(data)
        reloaded = store.load()["tasks"][0]
        self.assertEqual(reloaded["repeat"], "daily")

    def test_view_counts(self):
        a = self.tool.act_add({"title": "A"})["task"]
        b = self.tool.act_add({"title": "B"})["task"]
        self.tool.act_toggle_important({"id": a["id"]})
        self.tool.act_toggle_my_day({"id": b["id"]})
        self.tool.act_update({"id": a["id"], "fields": {"due": _today(3)}})

        counts = self.tool.act_board({})["views"]
        self.assertEqual(counts["my_day"], 1)
        self.assertEqual(counts["important"], 1)
        self.assertEqual(counts["planned"], 1)
        self.assertEqual(counts["completed"], 0)

        self.tool.act_toggle({"id": a["id"]})
        counts = self.tool.act_board({})["views"]
        self.assertEqual(counts["completed"], 1)
        self.assertEqual(counts["important"], 0)      # 已完成不再计入
        self.assertEqual(counts["planned"], 0)

    def test_planned_grouping(self):
        self.tool.act_update({"id": self.tool.act_add({"title": "过期"})["task"]["id"],
                              "fields": {"due": _today(-2)}})
        self.tool.act_add({"title": "今天做", "view": "planned"})
        self.tool.act_update({"id": self.tool.act_add({"title": "明天"})["task"]["id"],
                              "fields": {"due": _today(1)}})
        self.tool.act_update({"id": self.tool.act_add({"title": "很久以后"})["task"]["id"],
                              "fields": {"due": _today(90)}})

        groups = self.tool.act_board({"view": "planned"})["groups"]
        labels = [g["label"] for g in groups]
        self.assertEqual(labels[0], "已过期")
        self.assertIn("今天", labels)
        self.assertIn("明天", labels)
        self.assertIn("以后", labels)

        overdue = [g for g in groups if g["key"] == "overdue"][0]
        self.assertEqual([t["title"] for t in overdue["tasks"]], ["过期"])

    def test_important_tasks_sort_first(self):
        self.tool.act_add({"title": "普通一"})
        starred = self.tool.act_add({"title": "重要的"})["task"]
        self.tool.act_toggle_important({"id": starred["id"]})

        tasks = self.tool.act_board({"view": "list"})["groups"][0]["tasks"]
        self.assertEqual(tasks[0]["title"], "重要的")

    def test_keyword_search_is_global(self):
        """搜索是全局的：即使在「我的一天」视图里，也能搜到别处的任务。"""
        task = self.tool.act_add({"title": "写方案"})["task"]
        self.tool.act_add_step({"id": task["id"], "title": "调研竞品"})
        self.tool.act_update({"id": task["id"], "fields": {"note": "月底前交"}})

        self.assertEqual(self.tool.act_board({})["view"], "my_day")
        self.assertEqual(self.tool.act_board({"keyword": "竞品"})["shown"], 1)
        self.assertEqual(self.tool.act_board({"keyword": "月底"})["shown"], 1)
        self.assertEqual(self.tool.act_board({"keyword": "不存在"})["shown"], 0)

        # 搜索时标题应变成搜索提示
        self.assertTrue(self.tool.act_board({"keyword": "竞品"})["title"].startswith("搜索："))

    # ---------------------------------------------------------------- 步骤
    def test_steps_lifecycle(self):
        task = self.tool.act_add({"title": "搬家"})["task"]
        task = self.tool.act_add_step({"id": task["id"], "title": "找搬家公司"})["task"]
        task = self.tool.act_add_step({"id": task["id"], "title": "打包行李"})["task"]
        self.assertEqual(model.step_progress(task), (0, 2))

        # 步骤按输入顺序追加在末尾
        self.assertEqual([s["title"] for s in task["steps"]],
                         ["找搬家公司", "打包行李"])

        step_id = task["steps"][0]["id"]
        task = self.tool.act_toggle_step({"id": task["id"], "step_id": step_id})["task"]
        self.assertEqual(model.step_progress(task), (1, 2))

        task = self.tool.act_update_step(
            {"id": task["id"], "step_id": step_id, "title": "打包行李（已改）"})["task"]
        self.assertEqual(task["steps"][0]["title"], "打包行李（已改）")

        task = self.tool.act_remove_step({"id": task["id"], "step_id": step_id})["task"]
        self.assertEqual(len(task["steps"]), 1)

    def test_step_errors(self):
        task = self.tool.act_add({"title": "T"})["task"]
        with self.assertRaises(ToolError):
            self.tool.act_add_step({"id": task["id"], "title": " "})
        with self.assertRaises(ToolError):
            self.tool.act_toggle_step({"id": task["id"], "step_id": "not-exist"})

    # ---------------------------------------------------------------- 清单
    def test_list_crud_and_move(self):
        created = self.tool.act_add_list({"name": "工作"})["list"]

        def by_name(name):
            return [i for i in self.tool.act_board({})["lists"] if i["name"] == name][0]

        board = self.tool.act_board({})
        self.assertEqual(len(board["lists"]), 2)
        self.assertEqual(by_name("工作")["name"], "工作")

        self.tool.act_add({"title": "周报", "list_id": created["id"]})
        board = self.tool.act_board({"view": "list", "list_id": created["id"]})
        self.assertEqual(board["shown"], 1)
        self.assertEqual(board["title"], "工作")
        self.assertEqual(by_name("工作")["count"], 1)

        self.tool.act_rename_list({"list_id": created["id"], "name": "工作事务"})
        self.assertEqual(by_name("工作事务")["name"], "工作事务")

        result = self.tool.act_remove_list({"list_id": created["id"]})
        self.assertEqual(result["moved"], 1)
        board = self.tool.act_board({})
        self.assertEqual(len(board["lists"]), 1)
        # 任务被移回默认清单而不是被删掉
        self.assertEqual(board["lists"][0]["count"], 1)

    def test_list_guards(self):
        with self.assertRaises(ToolError):
            self.tool.act_add_list({"name": ""})
        with self.assertRaises(ToolError):
            self.tool.act_add_list({"name": model.DEFAULT_LIST_NAME})
        with self.assertRaises(ToolError):
            self.tool.act_remove_list({"list_id": model.DEFAULT_LIST_ID})
        with self.assertRaises(ToolError):
            self.tool.act_rename_list({"list_id": model.DEFAULT_LIST_ID, "name": "改名"})

    def test_rename_list_rejects_duplicate_but_allows_self(self):
        self.tool.act_add_list({"name": "工作"})
        second = self.tool.act_add_list({"name": "生活"})["list"]

        with self.assertRaises(ToolError):
            self.tool.act_rename_list({"list_id": second["id"], "name": "工作"})
        # 改成自己原本的名字不算重名（前端的 onblur 会走到这里）
        kept = self.tool.act_rename_list({"list_id": second["id"], "name": "生活"})
        self.assertEqual(kept["list"]["name"], "生活")

    def test_add_list_without_name_gets_default(self):
        """不传名字时自动取名 —— 界面靠这个做到"新建清单不弹输入框"。"""
        first = self.tool.act_add_list({})["list"]
        self.assertEqual(first["name"], model.NEW_LIST_NAME + " 1")
        second = self.tool.act_add_list({})["list"]
        self.assertEqual(second["name"], model.NEW_LIST_NAME + " 2")
        third = self.tool.act_add_list({})["list"]
        self.assertEqual(third["name"], model.NEW_LIST_NAME + " 3")

        # 编号取最小空缺：删掉「新清单 2」后再建，补回 2 而不是 4
        self.tool.act_remove_list({"list_id": second["id"]})
        refill = self.tool.act_add_list({})["list"]
        self.assertEqual(refill["name"], model.NEW_LIST_NAME + " 2")

        # "不传名字"与"传了空名字"是两回事：后者仍然是错误
        with self.assertRaises(ToolError):
            self.tool.act_add_list({"name": "   "})

    def test_update_step_title(self):
        task = self.tool.act_add({"title": "T"})["task"]
        step = self.tool.act_add_step({"id": task["id"], "title": "原步骤"})["step"]

        updated = self.tool.act_update_step(
            {"id": task["id"], "step_id": step["id"], "title": "改过的步骤"})
        self.assertEqual(updated["task"]["steps"][0]["title"], "改过的步骤")

        with self.assertRaises(ToolError):
            self.tool.act_update_step(
                {"id": task["id"], "step_id": step["id"], "title": "   "})

    def test_tags_are_normalized_and_searchable(self):
        task = self.tool.act_add({"title": "买年货"})["task"]

        # 逗号分隔的字符串也接受，并自动去重
        updated = self.tool.act_update(
            {"id": task["id"], "fields": {"tags": "生活, 采购, 生活"}})["task"]
        self.assertEqual(updated["tags"], ["生活", "采购"])

        # 搜索能命中标签（这也是标签唯一的价值所在）
        self.assertEqual(self.tool.act_board({"keyword": "采购"})["shown"], 1)

        # 超过上限的部分被截断
        many = ["t%d" % (i,) for i in range(model.MAX_TAGS + 5)]
        updated = self.tool.act_update({"id": task["id"], "fields": {"tags": many}})["task"]
        self.assertEqual(len(updated["tags"]), model.MAX_TAGS)

        # 空数组 = 清空
        updated = self.tool.act_update({"id": task["id"], "fields": {"tags": []}})["task"]
        self.assertEqual(updated["tags"], [])

    def test_tags_survive_restart(self):
        task = self.tool.act_add({"title": "带标签"})["task"]
        self.tool.act_update({"id": task["id"], "fields": {"tags": ["a", "b"]}})

        fresh = TodoTool()
        found = fresh.act_board({"view": "list"})["groups"][0]["tasks"][0]
        self.assertEqual(found["tags"], ["a", "b"])

    def test_update_rejects_unknown_field(self):
        task = self.tool.act_add({"title": "T"})["task"]
        with self.assertRaises(ToolError):
            self.tool.act_update({"id": task["id"], "fields": {"evil": 1}})

    def test_update_rejects_empty_title(self):
        task = self.tool.act_add({"title": "有效"})["task"]
        with self.assertRaises(ToolError):
            self.tool.act_update({"id": task["id"], "fields": {"title": ""}})

    def test_update_rejects_unknown_list(self):
        task = self.tool.act_add({"title": "T"})["task"]
        with self.assertRaises(ToolError):
            self.tool.act_update({"id": task["id"], "fields": {"list_id": "nope"}})

    def test_remove_and_clear_done(self):
        first = self.tool.act_add({"title": "一"})["task"]
        self.tool.act_add({"title": "二"})
        self.assertEqual(self.tool.act_remove({"id": first["id"]})["removed"], first["id"])
        self.assertEqual(self.tool.act_board({})["stats"]["total"], 1)

        second = self.tool.act_board({"view": "list"})["groups"][0]["tasks"][0]
        self.tool.act_toggle({"id": second["id"]})
        self.assertEqual(self.tool.act_clear_done({})["removed"], 1)
        self.assertEqual(self.tool.act_board({})["stats"]["total"], 0)

    def test_save_keeps_rotating_backups(self):
        """每次保存前留一份上一版，且份数有界 —— 这是"整个文件被写坏"的兜底。"""
        for index in range(1, 4):
            self.tool.act_add({"title": "第 %d 条" % (index,)})

        names = sorted(n for n in os.listdir(self.tmp) if ".bak." in n)
        self.assertEqual(names, ["todo.json.bak.1", "todo.json.bak.2"])

        # bak.1 = 覆盖前那一版（2 条），bak.2 = 更早那一版（1 条）
        newest = jsonio.read_json(jsonio.backup_path(store.file_path(), 1))
        older = jsonio.read_json(jsonio.backup_path(store.file_path(), 2))
        self.assertEqual(len(newest["tasks"]), 2)
        self.assertEqual(len(older["tasks"]), 1)

    def test_backup_files_do_not_break_load(self):
        """备份文件与主文件同目录，不能干扰正常读取。"""
        self.tool.act_add({"title": "一"})
        self.tool.act_add({"title": "二"})
        self.assertEqual(self.tool.act_board({})["stats"]["total"], 2)

    def test_due_presets_are_today_and_tomorrow(self):
        """用固定日期校验，免得结果随"今天是星期几"变化。"""
        presets = model.due_presets(datetime.date(2026, 9, 13))
        self.assertEqual([p["label"] for p in presets], ["今天", "明天"])
        self.assertEqual(presets[0]["value"], "2026-09-13")
        self.assertEqual(presets[1]["value"], "2026-09-14")

        # 跨月也要对
        presets = model.due_presets(datetime.date(2026, 9, 30))
        self.assertEqual(presets[1]["value"], "2026-10-01")

    def test_week_end_matches_planned_grouping(self):
        """「已计划」里"本周"的上界就是 model.week_end()，后端只此一份口径。"""
        # 周日：本周日就是今天；周一与周六：都指向同一个周日
        self.assertEqual(model.week_end(datetime.date(2026, 9, 13)).isoformat(), "2026-09-13")
        self.assertEqual(model.week_end(datetime.date(2026, 9, 14)).isoformat(), "2026-09-20")
        self.assertEqual(model.week_end(datetime.date(2026, 9, 19)).isoformat(), "2026-09-20")

        task = self.tool.act_add({"title": "本周内"})["task"]
        self.tool.act_update({"id": task["id"],
                              "fields": {"due": model.week_end().isoformat()}})
        groups = dict((g["key"], g["tasks"])
                      for g in self.tool.act_board({"view": "planned"})["groups"])
        landed = [key for key, items in groups.items()
                  if task["id"] in [t["id"] for t in items]]
        # 今天正好是周日时"本周日"就是今天，会落 today 桶；其余星期落 week 桶
        self.assertEqual(len(landed), 1, landed)
        self.assertIn(landed[0], ("today", "week"), landed)

    # ---------------------------------------------------------------- 全部任务
    def test_all_view_spans_lists_and_excludes_completed(self):
        work = self.tool.act_add_list({"name": "工作"})["list"]
        first = self.tool.act_add({"title": "默认清单里的"})["task"]
        self.tool.act_add({"title": "工作清单里的", "list_id": work["id"]})

        board = self.tool.act_board({"view": "all"})
        titles = sorted(t["title"] for g in board["groups"] for t in g["tasks"])
        self.assertEqual(titles, ["工作清单里的", "默认清单里的"])
        self.assertEqual(board["views"]["all"], 2)

        # 完成的不算在「任务」里（那是「已完成」视图的事）
        self.tool.act_toggle({"id": first["id"]})
        board = self.tool.act_board({"view": "all"})
        self.assertEqual([t["title"] for g in board["groups"] for t in g["tasks"]],
                         ["工作清单里的"])
        self.assertEqual(board["views"]["all"], 1)
        self.assertEqual(board["views"]["completed"], 1)

    # ---------------------------------------------------------------- 回收站
    def test_remove_goes_to_trash(self):
        task = self.tool.act_add({"title": "手滑删掉的"})["task"]
        self.tool.act_remove({"id": task["id"]})

        board = self.tool.act_board({"view": "all"})
        self.assertEqual(board["shown"], 0)
        self.assertEqual(board["stats"]["total"], 0)
        self.assertEqual(board["views"]["trash"], 1)

        trash = self.tool.act_board({"view": "trash"})
        self.assertEqual(trash["shown"], 1)
        self.assertEqual(trash["groups"][0]["tasks"][0]["title"], "手滑删掉的")
        self.assertTrue(trash["groups"][0]["tasks"][0]["deleted_at"])

    def test_trashed_task_is_invisible_everywhere(self):
        task = self.tool.act_add({"title": "找得到的名字"})["task"]
        self.tool.act_toggle_important({"id": task["id"]})
        self.tool.act_update({"id": task["id"],
                              "fields": {"my_day": _today(), "due": _today(1),
                                         "tags": ["标记"]}})
        self.tool.act_remove({"id": task["id"]})

        for view in ("all", "my_day", "important", "planned", "completed"):
            board = self.tool.act_board({"view": view})
            ids = [t["id"] for g in board["groups"] for t in g["tasks"]]
            self.assertNotIn(task["id"], ids, view)

        # 清单计数、搜索都不该把它算进来
        self.assertEqual(self.tool.act_board({"view": "list"})["lists"][0]["count"], 0)
        self.assertEqual(self.tool.act_board({"keyword": "找得"})["shown"], 0)
        self.assertEqual(self.tool.act_board({"keyword": "标记"})["shown"], 0)

    def test_restore_puts_it_back_where_it_was(self):
        work = self.tool.act_add_list({"name": "工作"})["list"]
        task = self.tool.act_add({"title": "还要用", "list_id": work["id"]})["task"]
        self.tool.act_remove({"id": task["id"]})

        restored = self.tool.act_restore({"id": task["id"]})["task"]
        self.assertEqual(restored["list_id"], work["id"])
        self.assertEqual(restored["deleted_at"], "")

        board = self.tool.act_board({"view": "all"})
        self.assertEqual(board["shown"], 1)
        self.assertEqual(board["views"]["trash"], 0)

    def test_restore_falls_back_when_original_list_is_gone(self):
        work = self.tool.act_add_list({"name": "临时"})["list"]
        task = self.tool.act_add({"title": "孤儿", "list_id": work["id"]})["task"]
        self.tool.act_remove({"id": task["id"]})
        self.tool.act_remove_list({"list_id": work["id"]})

        restored = self.tool.act_restore({"id": task["id"]})["task"]
        self.assertEqual(restored["list_id"], model.DEFAULT_LIST_ID)

    def test_purge_and_empty_trash_are_permanent(self):
        first = self.tool.act_add({"title": "一"})["task"]
        second = self.tool.act_add({"title": "二"})["task"]
        self.tool.act_remove({"id": first["id"]})
        self.tool.act_remove({"id": second["id"]})

        self.assertEqual(self.tool.act_purge({"id": first["id"]})["purged"], first["id"])
        self.assertEqual(self.tool.act_board({"view": "trash"})["shown"], 1)

        self.assertEqual(self.tool.act_empty_trash({})["removed"], 1)
        self.assertEqual(self.tool.act_board({"view": "trash"})["shown"], 0)

        # 彻底删掉之后就找不回来了
        with self.assertRaises(ToolError):
            self.tool.act_restore({"id": first["id"]})
        with self.assertRaises(ToolError):
            self.tool.act_purge({"id": second["id"]})

    def test_clear_done_also_goes_to_trash(self):
        task = self.tool.act_add({"title": "完成的"})["task"]
        self.tool.act_toggle({"id": task["id"]})
        self.tool.act_clear_done({})

        self.assertEqual(self.tool.act_board({"view": "all"})["stats"]["total"], 0)
        self.assertEqual(self.tool.act_board({"view": "trash"})["shown"], 1)

    def test_trash_survives_restart(self):
        task = self.tool.act_add({"title": "重启后还在回收站"})["task"]
        self.tool.act_remove({"id": task["id"]})

        fresh = TodoTool()
        trash = fresh.act_board({"view": "trash"})
        self.assertEqual(trash["groups"][0]["tasks"][0]["title"], "重启后还在回收站")

    def test_prune_trash_respects_retention(self):
        old = {"id": "old", "title": "老条目", "deleted_at": "2000-01-01 00:00:00"}
        recent = {"id": "new", "title": "刚删的", "deleted_at": model.now_text()}

        kept = store.prune_trash([old, recent], 30)
        self.assertEqual([t["id"] for t in kept], ["new"])

        # 时间戳坏了就留着 —— 宁可多留，不可误删
        broken = {"id": "bad", "title": "时间戳坏了", "deleted_at": "不是时间"}
        self.assertEqual(len(store.prune_trash([broken], 30)), 1)

        # 0 = 永久保留
        self.assertEqual(len(store.prune_trash([old, recent], 0)), 2)

    def test_v2_data_without_trash_still_loads(self):
        jsonio.write_json_atomic(store.file_path(), {
            "version": 2,
            "lists": [],
            "tasks": [{"id": "a1", "title": "老任务"}],
        })
        data = store.load()
        self.assertEqual(data["trash"], [])
        self.assertEqual([t["title"] for t in data["tasks"]], ["老任务"])

    def test_bad_trash_entries_are_dropped(self):
        jsonio.write_json_atomic(store.file_path(), {
            "version": 3, "lists": [], "tasks": [],
            "trash": [{"id": "x"}, {"id": "y", "title": "有效"}, "不是对象"],
        })
        trash = store.load()["trash"]
        self.assertEqual([t["title"] for t in trash], ["有效"])
        self.assertTrue(trash[0]["deleted_at"])       # 缺时间戳的按"刚删"补上

    # ---------------------------------------------------------------- 批量操作
    def _make(self, *titles):
        return [self.tool.act_add({"title": t})["task"] for t in titles]

    def _titles(self, view="all"):
        return [t["title"] for g in self.tool.act_board({"view": view})["groups"]
                for t in g["tasks"]]

    def test_bulk_done_sets_explicit_value(self):
        ids = [t["id"] for t in self._make("甲", "乙", "丙")]
        result = self.tool.act_bulk({"ids": ids, "op": "done", "value": True})
        self.assertEqual(result["changed"], 3)
        self.assertEqual(self._titles("completed"), ["甲", "乙", "丙"])

        # 再标一次：已经是目标状态，changed 归零（说明是"设值"不是"切换"）
        again = self.tool.act_bulk({"ids": ids, "op": "done", "value": True})
        self.assertEqual(again["changed"], 0)

        # 混合状态下用"取消完成"，只动那些确实是完成的
        self.tool.act_toggle({"id": ids[0]})
        back = self.tool.act_bulk({"ids": ids, "op": "done", "value": False})
        self.assertEqual(back["changed"], 2)
        self.assertEqual(self._titles("completed"), [])

    def _days(self):
        return [x["my_day"] for g in self.tool.act_board({"view": "my_day"})["groups"]
                for x in g["tasks"]]

    def test_bulk_important_and_my_day(self):
        ids = [t["id"] for t in self._make("甲", "乙")]
        self.tool.act_bulk({"ids": ids, "op": "important", "value": True})
        self.assertEqual(self.tool.act_board({"view": "important"})["shown"], 2)

        # 已经重要的那条不该被重复计数
        self.tool.act_toggle_important({"id": ids[0]})
        result = self.tool.act_bulk({"ids": ids, "op": "important", "value": True})
        self.assertEqual(result["changed"], 1)

        self.tool.act_bulk({"ids": ids, "op": "my_day", "value": True})
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 2)
        self.assertEqual(self._days(), [_today(), _today()])

        self.tool.act_bulk({"ids": ids, "op": "my_day", "value": False})
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 0)

    def test_bulk_move_to_list(self):
        target = self.tool.act_add_list({"name": "工作"})["list"]
        ids = [t["id"] for t in self._make("甲", "乙")]
        result = self.tool.act_bulk({"ids": ids, "op": "move", "value": target["id"]})
        self.assertEqual(result["changed"], 2)
        # 「全部任务」是跨清单汇总，所以要看具体的清单视图
        self.assertEqual(self._titles({"view": "list", "list_id": model.DEFAULT_LIST_ID}), [])
        moved = self.tool.act_board({"view": "list", "list_id": target["id"]})
        self.assertEqual([t["title"] for g in moved["groups"] for t in g["tasks"]],
                         ["甲", "乙"])

        # 已经是目标清单：不算改动
        again = self.tool.act_bulk({"ids": ids, "op": "move", "value": target["id"]})
        self.assertEqual(again["changed"], 0)

    def test_bulk_remove_goes_to_trash(self):
        ids = [t["id"] for t in self._make("甲", "乙", "丙")]
        result = self.tool.act_bulk({"ids": ids[:2], "op": "remove"})
        self.assertEqual(result["changed"], 2)
        self.assertEqual(self._titles(), ["丙"])
        self.assertEqual(self._titles("trash"), ["甲", "乙"])

    def test_bulk_ignores_unknown_ids(self):
        ids = [t["id"] for t in self._make("甲")]
        result = self.tool.act_bulk({"ids": ids + ["不存在", ids[0]], "op": "done",
                                     "value": True})
        self.assertEqual(result["selected"], 1)      # 重复 id 已去重
        self.assertEqual(result["changed"], 1)

    def test_bulk_all_ids_gone_is_not_an_error(self):
        self._make("甲")
        result = self.tool.act_bulk({"ids": ["早就没了"], "op": "done", "value": True})
        self.assertEqual(result["selected"], 0)

    def test_bulk_validates_target_list_even_when_nothing_selected(self):
        """清单校验要在"选中集为空就返回"之前 —— 否则调用方的 bug 会被静默吞掉。"""
        self._make("甲")
        with self.assertRaises(ToolError):
            self.tool.act_bulk({"ids": ["早就没了"], "op": "move", "value": "没这个清单"})

    def test_bulk_writes_file_once(self):
        """批量必须一次读写 —— 否则 N 条就是 N 次全量写盘。"""
        ids = [t["id"] for t in self._make("甲", "乙", "丙", "丁", "戊")]
        calls = []
        original = store.save

        def counting(data):
            calls.append(1)
            return original(data)

        store.save = counting
        try:
            self.tool.act_bulk({"ids": ids, "op": "done", "value": True})
        finally:
            store.save = original
        self.assertEqual(len(calls), 1)

    def test_bulk_guards(self):
        ids = [t["id"] for t in self._make("甲")]
        with self.assertRaises(ToolError):
            self.tool.act_bulk({"ids": ids, "op": "不存在"})
        with self.assertRaises(ToolError):
            self.tool.act_bulk({"ids": ids, "op": ""})
        with self.assertRaises(ToolError):
            self.tool.act_bulk({"ids": "不是列表", "op": "done"})
        with self.assertRaises(ToolError):
            self.tool.act_bulk({"ids": [], "op": "done"})
        with self.assertRaises(ToolError):
            self.tool.act_bulk({"ids": ["  "], "op": "done"})
        with self.assertRaises(ToolError):
            self.tool.act_bulk({"ids": ids, "op": "move", "value": "没有这个清单"})
        with self.assertRaises(ToolError):
            self.tool.act_bulk({"ids": ["x%d" % i for i in range(600)], "op": "done"})

    def test_bulk_cannot_touch_trash(self):
        """回收站里的任务不能被批量操作碰到（它们不在 tasks 里）。"""
        ids = [t["id"] for t in self._make("甲")]
        self.tool.act_remove({"id": ids[0]})
        result = self.tool.act_bulk({"ids": ids, "op": "important", "value": True})
        self.assertEqual(result["selected"], 0)
        self.assertEqual(self._titles("trash"), ["甲"])

    def test_reorder_lists(self):
        first = self.tool.act_add_list({"name": "甲"})["list"]
        second = self.tool.act_add_list({"name": "乙"})["list"]
        third = self.tool.act_add_list({"name": "丙"})["list"]

        def names():
            return [i["name"] for i in self.tool.act_board({})["lists"]]

        self.assertEqual(names(), ["甲", "乙", "丙", "未分类"])

        self.tool.act_reorder_lists({"ids": [third["id"], first["id"], second["id"]]})
        self.assertEqual(names(), ["丙", "甲", "乙", "未分类"])

        # 默认清单永远排最后，塞进去也不参与排序
        self.tool.act_reorder_lists(
            {"ids": [model.DEFAULT_LIST_ID, second["id"], third["id"], first["id"]]})
        self.assertEqual(names(), ["乙", "丙", "甲", "未分类"])

        # 没提到的清单按原相对顺序接在后面（前端顺序过期时也不会乱）
        self.tool.act_reorder_lists({"ids": [first["id"]]})
        self.assertEqual(names(), ["甲", "乙", "丙", "未分类"])

        # 不存在的 id 直接忽略，不报错
        self.tool.act_reorder_lists({"ids": ["不存在", second["id"]]})
        self.assertEqual(names(), ["乙", "甲", "丙", "未分类"])

        with self.assertRaises(ToolError):
            self.tool.act_reorder_lists({"ids": "不是列表"})

    def test_reorder_keeps_tasks_in_their_lists(self):
        first = self.tool.act_add_list({"name": "甲"})["list"]
        second = self.tool.act_add_list({"name": "乙"})["list"]
        task = self.tool.act_add({"title": "在甲里", "list_id": first["id"]})["task"]

        self.tool.act_reorder_lists({"ids": [second["id"], first["id"]]})
        stored = self.tool.act_board({"view": "list", "list_id": first["id"]})
        self.assertEqual([t["id"] for g in stored["groups"] for t in g["tasks"]],
                         [task["id"]])

    def test_reorder_survives_restart(self):
        first = self.tool.act_add_list({"name": "甲"})["list"]
        second = self.tool.act_add_list({"name": "乙"})["list"]
        self.tool.act_reorder_lists({"ids": [second["id"], first["id"]]})

        fresh = TodoTool()
        self.assertEqual([i["name"] for i in fresh.act_board({})["lists"]],
                         ["乙", "甲", "未分类"])

    def test_unknown_task_id(self):
        with self.assertRaises(ToolError):
            self.tool.act_toggle({"id": "not-exist"})

    # ---------------------------------------------------------------- 持久化
    def test_persistence_roundtrip(self):
        task = self.tool.act_add({"title": "重启后还在"})["task"]
        self.tool.act_add_step({"id": task["id"], "title": "步骤一"})
        self.tool.act_add_list({"name": "工作"})

        fresh = TodoTool()
        board = fresh.act_board({"view": "list"})
        tasks = board["groups"][0]["tasks"]
        self.assertEqual(tasks[0]["title"], "重启后还在")
        self.assertEqual(tasks[0]["steps"][0]["title"], "步骤一")
        self.assertEqual([i["name"] for i in board["lists"]],
                         ["工作", model.DEFAULT_LIST_NAME])

    def test_missing_file_returns_empty(self):
        data = store.load()
        self.assertEqual(data["tasks"], [])
        self.assertEqual(len(data["lists"]), 1)

    def test_corrupted_file_returns_empty(self):
        with open(store.path_text(), "w", encoding="utf-8") as handle:
            handle.write("{ 这不是合法 JSON")
        self.assertEqual(store.load()["tasks"], [])

    def test_v1_data_is_migrated(self):
        """v1 只有 title/status/priority/tags，读出来应当自动补齐 v2 字段。"""
        jsonio.write_json_atomic(store.path_text(), {
            "version": 1,
            "tasks": [
                {"id": "aaa", "title": "旧任务", "status": "doing",
                 "priority": 2, "tags": ["旧"]},
            ],
        })
        data = store.load()
        task = data["tasks"][0]
        self.assertEqual(task["title"], "旧任务")
        self.assertEqual(task["status"], model.STATUS_TODO)    # doing 已废弃
        self.assertEqual(task["list_id"], model.DEFAULT_LIST_ID)
        self.assertFalse(task["important"])
        self.assertEqual(task["my_day"], "")
        self.assertEqual(task["due"], "")
        self.assertEqual(task["steps"], [])
        self.assertEqual(task["tags"], ["旧"])

    def test_damaged_records_are_dropped_not_fatal(self):
        jsonio.write_json_atomic(store.path_text(), {
            "version": 2,
            "lists": [{"id": "work", "name": "工作"}, "不是对象", {"name": ""}],
            "tasks": [
                {"title": "正常"},
                {"title": ""},
                "整条是字符串",
                {"title": "坏字段", "due": "2026-13-45", "important": "yes",
                 "steps": ["不是对象", {"title": "有效步骤"}]},
                {"title": "指向不存在的清单", "list_id": "ghost"},
            ],
        })
        data = store.load()
        self.assertEqual([t["title"] for t in data["tasks"]],
                         ["正常", "坏字段", "指向不存在的清单"])
        self.assertEqual(len(data["lists"]), 2)                # 默认 + 工作

        broken = data["tasks"][1]
        self.assertEqual(broken["due"], "")                    # 非法日期被清空
        self.assertTrue(broken["important"])
        self.assertEqual([s["title"] for s in broken["steps"]], ["有效步骤"])
        self.assertEqual(data["tasks"][2]["list_id"], model.DEFAULT_LIST_ID)

    # ---------------------------------------------------------------- CLI
    def test_cli_commands(self):
        self.tool.act_add({"title": "命令行可见"})
        self.assertEqual(self.tool.cli(["list", "-a"]), 0)
        self.assertEqual(self.tool.cli(["add", "新任务"]), 0)
        self.assertEqual(self.tool.cli(["where"]), 0)
        self.assertEqual(self.tool.cli(["help"]), 0)

        tasks = self.tool.act_board({"view": "list"})["groups"][0]["tasks"]
        task_id = tasks[0]["id"]
        self.assertEqual(self.tool.cli(["star", task_id]), 0)
        self.assertEqual(self.tool.cli(["today", task_id]), 0)
        self.assertEqual(self.tool.cli(["done", task_id]), 0)

        done = [t for t in self.tool.act_board({"view": "completed"})["groups"][0]["tasks"]]
        self.assertEqual([t["id"] for t in done], [task_id])

        self.assertEqual(self.tool.cli(["undone", task_id]), 0)
        self.assertEqual(self.tool.act_board({"view": "completed"})["shown"], 0)

        self.assertEqual(self.tool.cli(["rm", task_id]), 0)

    def test_cli_unknown_command(self):
        self.assertEqual(self.tool.cli(["nope"]), 2)


if __name__ == "__main__":
    unittest.main()
