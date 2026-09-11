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

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from core import registry                            # noqa: E402
from core.errors import NotFoundError, ToolError     # noqa: E402
from core.tool import Tool, ToolMeta                 # noqa: E402
from services import config, jsonio                  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
