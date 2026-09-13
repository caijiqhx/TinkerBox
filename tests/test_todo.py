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
        self.assertEqual(board["lists"][0]["id"], model.DEFAULT_LIST_ID)
        self.assertEqual(board["lists"][0]["name"], model.DEFAULT_LIST_NAME)

    def test_task_goes_to_default_list(self):
        self.tool.act_add({"title": "买牛奶"})
        board = self.tool.act_board({"view": "list"})
        self.assertEqual(len(board["groups"][0]["tasks"]), 1)
        self.assertEqual(board["lists"][0]["count"], 1)

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

    def test_my_day_only_shows_today(self):
        task = self.tool.act_add({"title": "今天的事"})["task"]
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 0)

        self.tool.act_toggle_my_day({"id": task["id"]})
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 1)

        # 手工把日期改成昨天 —— 应当自动"过期"出「我的一天」
        data = store.load()
        data["tasks"][0]["my_day"] = _today(-1)
        store.save(data)
        self.assertEqual(self.tool.act_board({"view": "my_day"})["shown"], 0)

    def test_completed_view_and_toggle(self):
        task = self.tool.act_add({"title": "倒垃圾"})["task"]
        self.assertEqual(self.tool.act_board({"view": "completed"})["shown"], 0)

        self.tool.act_toggle({"id": task["id"]})
        self.assertEqual(self.tool.act_board({"view": "completed"})["shown"], 1)
        self.assertEqual(self.tool.act_board({"view": "list"})["shown"], 0)

        self.tool.act_toggle({"id": task["id"]})
        self.assertEqual(self.tool.act_board({"view": "completed"})["shown"], 0)
        self.assertEqual(self.tool.act_board({"view": "list"})["shown"], 1)

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
        board = self.tool.act_board({})
        self.assertEqual(len(board["lists"]), 2)
        self.assertEqual(board["lists"][1]["name"], "工作")

        self.tool.act_add({"title": "周报", "list_id": created["id"]})
        board = self.tool.act_board({"view": "list", "list_id": created["id"]})
        self.assertEqual(board["shown"], 1)
        self.assertEqual(board["title"], "工作")
        self.assertEqual(board["lists"][1]["count"], 1)

        self.tool.act_rename_list({"list_id": created["id"], "name": "工作事务"})
        self.assertEqual(self.tool.act_board({})["lists"][1]["name"], "工作事务")

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
                         [model.DEFAULT_LIST_NAME, "工作"])

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
