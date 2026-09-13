"""核心契约层与公共服务层的测试。

运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from core import paths                              # noqa: E402
from core import registry                            # noqa: E402
from core.errors import NotFoundError, ToolError     # noqa: E402
from core.tool import Tool, ToolMeta                 # noqa: E402
from services import config, jsonio                  # noqa: E402
import main                                          # noqa: E402


class _DemoTool(Tool):
    meta = ToolMeta(tid="demo", name="示例", desc="测试用", order=5)

    def actions(self):
        return {
            "echo": lambda payload: {"got": payload},
            "boom": self._boom,
        }

    @staticmethod
    def _boom(payload):
        raise ToolError("故意失败")


class RegistryTest(unittest.TestCase):
    def setUp(self):
        registry.clear()

    def tearDown(self):
        registry.clear()

    def test_register_and_get(self):
        tool = registry.register(_DemoTool())
        self.assertIs(registry.get("demo"), tool)
        self.assertEqual([m["id"] for m in registry.list_meta()], ["demo"])

    def test_duplicate_id_rejected(self):
        registry.register(_DemoTool())
        with self.assertRaises(ValueError):
            registry.register(_DemoTool())

    def test_tool_without_meta_rejected(self):
        class NoMeta(Tool):
            pass
        with self.assertRaises(ValueError):
            registry.register(NoMeta())

    def test_unknown_tool(self):
        with self.assertRaises(NotFoundError):
            registry.get("nope")

    def test_sorted_by_order(self):
        other = _DemoTool()
        other.meta = ToolMeta(tid="aaa", name="先", order=1)
        registry.register(_DemoTool())
        registry.register(other)
        self.assertEqual([m["id"] for m in registry.list_meta()], ["aaa", "demo"])


class ToolContractTest(unittest.TestCase):
    def setUp(self):
        self.tool = _DemoTool()

    def test_call_dispatches(self):
        self.assertEqual(self.tool.call("echo", {"a": 1}), {"got": {"a": 1}})

    def test_call_defaults_empty_payload(self):
        self.assertEqual(self.tool.call("echo", None), {"got": {}})

    def test_call_rejects_non_dict_payload(self):
        with self.assertRaises(ToolError):
            self.tool.call("echo", ["不是对象"])

    def test_call_unknown_action(self):
        with self.assertRaises(ToolError):
            self.tool.call("no-such-action", {})

    def test_business_error_propagates(self):
        with self.assertRaises(ToolError):
            self.tool.call("boom", {})

    def test_cli_unsupported_by_default(self):
        with self.assertRaises(ToolError):
            self.tool.cli([])


class JsonIoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="toolbox-json-")
        self.path = os.path.join(self.tmp, "a.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_roundtrip_keeps_chinese(self):
        jsonio.write_json_atomic(self.path, {"标题": "买牛奶"})
        with open(self.path, "r", encoding="utf-8") as handle:
            raw = handle.read()
        self.assertIn("买牛奶", raw)                 # 不能被转义成 \uXXXX
        self.assertEqual(jsonio.read_json(self.path), {"标题": "买牛奶"})

    def test_missing_file_returns_default(self):
        self.assertEqual(jsonio.read_json(self.path, {"fallback": True}),
                         {"fallback": True})

    def test_corrupted_file_returns_default(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{{{")
        self.assertIsNone(jsonio.read_json(self.path))

    def test_write_creates_missing_directory(self):
        nested = os.path.join(self.tmp, "a", "b", "c.json")
        jsonio.write_json_atomic(nested, [1, 2, 3])
        self.assertEqual(jsonio.read_json(nested), [1, 2, 3])

    def test_overwrite_is_complete(self):
        jsonio.write_json_atomic(self.path, {"a": "很长的内容" * 50})
        jsonio.write_json_atomic(self.path, {"a": "短"})
        self.assertEqual(jsonio.read_json(self.path), {"a": "短"})
        # 同目录不应残留临时文件
        leftovers = [n for n in os.listdir(self.tmp) if n.startswith(".tmp-")]
        self.assertEqual(leftovers, [])

    def test_written_text_is_valid_json(self):
        jsonio.write_json_atomic(self.path, {"k": [1, {"n": None}]})
        with open(self.path, "r", encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {"k": [1, {"n": None}]})


class BackupRotationTest(unittest.TestCase):
    """备份轮转：份数有界（不需要手工清理），关掉时不留文件。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="toolbox-bak-")
        self.path = os.path.join(self.tmp, "a.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, value):
        jsonio.write_json_atomic(self.path, {"v": value})

    def _backup(self, index):
        return jsonio.read_json(jsonio.backup_path(self.path, index))

    def test_no_backup_when_target_missing(self):
        self.assertEqual(jsonio.rotate_backup(self.path, 3), 0)

    def test_newest_is_index_1_and_oldest_is_dropped(self):
        # 与 store.save 的用法一致：先轮转（留上一版），再写新内容
        for step in range(1, 6):
            jsonio.rotate_backup(self.path, 3)
            self._write(step)

        self.assertEqual(jsonio.read_json(self.path), {"v": 5})
        self.assertEqual(self._backup(1), {"v": 4})
        self.assertEqual(self._backup(2), {"v": 3})
        self.assertEqual(self._backup(3), {"v": 2})
        self.assertIsNone(self._backup(4))        # 超出上限的直接丢弃

    def test_keep_zero_disables_backup(self):
        self._write(1)
        self.assertEqual(jsonio.rotate_backup(self.path, 0), 0)
        self.assertIsNone(self._backup(1))

    def test_non_numeric_keep_is_treated_as_off(self):
        self._write(1)
        self.assertEqual(jsonio.rotate_backup(self.path, "五个"), 0)

    def test_backup_keeps_chinese_readable(self):
        jsonio.write_json_atomic(self.path, {"标题": "买牛奶"})
        jsonio.rotate_backup(self.path, 1)
        with open(jsonio.backup_path(self.path, 1), "r", encoding="utf-8") as handle:
            self.assertIn("买牛奶", handle.read())


class DataDirOverrideTest(unittest.TestCase):
    """TOOLBOX_DATA_DIR 用来做隔离测试 —— 跑冒烟时不必碰真实数据。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="toolbox-datadir-")
        self._original = os.environ.get("TOOLBOX_DATA_DIR")

    def tearDown(self):
        if self._original is None:
            os.environ.pop("TOOLBOX_DATA_DIR", None)
        else:
            os.environ["TOOLBOX_DATA_DIR"] = self._original
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_env_override_wins(self):
        os.environ["TOOLBOX_DATA_DIR"] = self.tmp
        self.assertEqual(str(paths.data_dir()), str(Path(self.tmp)))
        self.assertEqual(str(paths.state_file()),
                         str(Path(self.tmp) / "todo.json"))

    def test_missing_directory_is_created(self):
        nested = os.path.join(self.tmp, "a", "b")
        os.environ["TOOLBOX_DATA_DIR"] = nested
        self.assertEqual(str(paths.data_dir()), str(Path(nested)))
        self.assertTrue(os.path.isdir(nested))

    def test_blank_value_falls_back_to_project_data(self):
        os.environ["TOOLBOX_DATA_DIR"] = "   "
        self.assertEqual(paths.data_dir(), paths.project_root() / "data")


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="toolbox-cfg-")
        self._original = config._path
        config._path = lambda: os.path.join(self.tmp, "config.json")
        config.reload()

    def tearDown(self):
        config._path = self._original
        config.reload()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_defaults(self):
        self.assertEqual(config.get("ui"), "web")
        self.assertEqual(config.get("theme"), "auto")

    def test_lifecycle_defaults(self):
        """常驻模式相关默认值 —— 改这些会影响"一天只启动一次"的行为。"""
        self.assertEqual(config.get("port"), 8765)
        self.assertTrue(config.get("keep_alive"))
        self.assertEqual(config.get("idle_exit_hours"), 12)

    def test_backup_default_is_on(self):
        self.assertEqual(config.get("backup_keep"), 5)

    def test_set_then_reload_persists(self):
        config.set_value("theme", "dark")
        config.reload()
        self.assertEqual(config.get("theme"), "dark")

    def test_missing_file_falls_back_to_defaults(self):
        # 尚未写过任何配置时，仍应拿到默认值而不是报错
        self.assertEqual(config.get("theme"), "auto")
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, "config.json")))

    def test_unknown_key_returns_none(self):
        self.assertIsNone(config.get("no-such-key"))

    def test_corrupted_config_falls_back_to_defaults(self):
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as handle:
            handle.write("这不是 JSON")
        config.reload()
        self.assertEqual(config.get("theme"), "auto")


class LaunchOptionsTest(unittest.TestCase):
    """启动参数：默认**不**弹浏览器窗口，只有 --open 才弹。

    日常用法是点浏览器书签，启动脚本只负责把服务拉起来 ——
    每次双击都弹窗反而是干扰，所以默认值必须是 False。
    """

    def test_default_does_not_open_browser(self):
        options, rest = main.parse_args([])
        self.assertEqual(rest, [])
        self.assertFalse(main.want_browser(options))

    def test_open_flag_enables_browser(self):
        options, rest = main.parse_args(["--open"])
        self.assertTrue(main.want_browser(options))
        self.assertEqual(rest, [])

    def test_no_browser_wins_over_open(self):
        options, _rest = main.parse_args(["--open", "--no-browser"])
        self.assertFalse(main.want_browser(options))

    def test_ui_none_does_not_open_browser(self):
        options, _rest = main.parse_args(["--ui=none"])
        self.assertEqual(options["ui"], "none")
        self.assertFalse(main.want_browser(options))

    def test_open_before_command_is_global(self):
        options, rest = main.parse_args(["--open", "status"])
        self.assertTrue(main.want_browser(options))
        self.assertEqual(rest, ["status"])

    def test_options_after_command_are_not_global(self):
        # 工具子命令的内容不能被当成全局选项吞掉
        options, rest = main.parse_args(["todo", "add", "--open"])
        self.assertFalse(main.want_browser(options))
        self.assertEqual(rest, ["todo", "add", "--open"])


if __name__ == "__main__":
    unittest.main()
