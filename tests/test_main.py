"""`--restart` 的编排测试。

重启 = 先把自家实例停干净、再走正常启动。这里不碰真实服务：
instance 那一层与启动函数全部打桩，只验证"顺序与刹车"是否正确 ——
最容易写错的是"停不掉还硬着头皮启动"（端口固定，那样必然撞端口）。

运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import main as main_mod                            # noqa: E402
from core.errors import ToolError                   # noqa: E402


class ParseArgsTest(unittest.TestCase):
    def test_restart_flag(self):
        options, rest = main_mod.parse_args(["--restart"])
        self.assertTrue(options["restart"])
        self.assertEqual(rest, [])

    def test_restart_combines_with_other_options(self):
        options, rest = main_mod.parse_args(["--restart", "--open", "--detach", "status"])
        self.assertTrue(options["restart"])
        self.assertTrue(options["open"])
        self.assertTrue(options["detach"])
        self.assertEqual(rest, ["status"])

    def test_default_is_off(self):
        options, _ = main_mod.parse_args([])
        self.assertFalse(options["restart"])

    def test_unknown_option_still_rejected(self):
        with self.assertRaises(ToolError):
            main_mod.parse_args(["--nope"])


class StopInstanceTest(unittest.TestCase):
    """stop_running_instance 的三种结果（stop 与 --restart 共用）。"""

    def _patch(self, record, shutdown=True, stopped=True):
        patches = [
            mock.patch("web.instance.find_running", return_value=(record, {})),
            mock.patch("web.instance.request_shutdown", return_value=shutdown),
            mock.patch("web.instance.wait_until_stopped", return_value=stopped),
            mock.patch("web.instance.clear_record"),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_nothing_running(self):
        self._patch(None)
        self.assertEqual(main_mod.stop_running_instance(), (True, None))

    def test_stopped(self):
        self._patch({"port": 8765, "instance": "abc", "pid": 4242})
        ok, message = main_mod.stop_running_instance()
        self.assertTrue(ok)
        self.assertIn("8765", message)

    def test_shutdown_request_not_delivered(self):
        self._patch({"port": 8765, "instance": "abc", "pid": 4242}, shutdown=False)
        ok, message = main_mod.stop_running_instance()
        self.assertFalse(ok)
        self.assertIn("没有送达", message)
        self.assertIn("4242", message)          # 要给出可手动结束的 pid

    def test_still_responding_after_request(self):
        self._patch({"port": 8765, "instance": "abc", "pid": 4242}, stopped=False)
        ok, message = main_mod.stop_running_instance()
        self.assertFalse(ok)
        self.assertIn("仍在响应", message)


class RestartFlowTest(unittest.TestCase):
    """main() 里的编排：停不掉就不能启动；停掉了才继续。"""

    def _run(self, stop_result, argv=None, ui="web"):
        with mock.patch.object(main_mod, "stop_running_instance", return_value=stop_result), \
             mock.patch.object(main_mod, "resolve_ui", return_value=ui), \
             mock.patch.object(main_mod, "run_web", return_value=0) as runner:
            code = main_mod.main(list(argv or ["--restart"]))
        return code, runner

    def test_failure_blocks_start(self):
        code, runner = self._run((False, "关闭请求没有送达（可手动结束进程 pid 1）"))
        self.assertEqual(code, 1)
        runner.assert_not_called()              # 关键：停不掉就不要启动

    def test_success_starts(self):
        code, runner = self._run((True, "已停止端口 8765 上的原有服务"))
        self.assertEqual(code, 0)
        runner.assert_called_once()

    def test_nothing_running_still_starts(self):
        code, runner = self._run((True, None))
        self.assertEqual(code, 0)
        runner.assert_called_once()

    def test_subcommands_do_not_trigger_restart(self):
        """`--restart status` 不该重启 —— 只有真正要启动时才重启。"""
        with mock.patch.object(main_mod, "stop_running_instance") as stop, \
             mock.patch.object(main_mod, "cmd_status", return_value=0):
            code = main_mod.main(["--restart", "status"])
        self.assertEqual(code, 0)
        stop.assert_not_called()

    def test_no_restart_flag_keeps_old_behaviour(self):
        with mock.patch.object(main_mod, "stop_running_instance") as stop, \
             mock.patch.object(main_mod, "resolve_ui", return_value="web"), \
             mock.patch.object(main_mod, "run_web", return_value=0):
            code = main_mod.main([])
        self.assertEqual(code, 0)
        stop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
