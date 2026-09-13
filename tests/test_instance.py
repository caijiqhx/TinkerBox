"""服务实例识别测试。

这一层负责"重复点图标不要起第二个服务"，其中最容易出错的是
/api/identity 响应的解包 —— 接口统一返回 {"ok": true, "data": {...}}，
早期实现直接在顶层找 app 字段，导致永远认不出自己的服务。

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

from core import paths                             # noqa: E402
from web import APP_TAG, instance                  # noqa: E402


class ParseIdentityTest(unittest.TestCase):
    def test_envelope_is_unwrapped(self):
        body = json.dumps({"ok": True, "data": {"app": APP_TAG, "instance": "abc"}})
        self.assertEqual(instance.parse_identity(body)["instance"], "abc")

    def test_bare_object_also_accepted(self):
        body = json.dumps({"app": APP_TAG, "instance": "abc"})
        self.assertEqual(instance.parse_identity(body)["instance"], "abc")

    def test_other_application_is_rejected(self):
        body = json.dumps({"ok": True, "data": {"app": "something-else"}})
        self.assertIsNone(instance.parse_identity(body))

    def test_non_json_is_rejected(self):
        self.assertIsNone(instance.parse_identity("<html>502 Bad Gateway</html>"))

    def test_json_but_not_object_is_rejected(self):
        self.assertIsNone(instance.parse_identity("[1, 2, 3]"))

    def test_error_response_is_rejected(self):
        body = json.dumps({"ok": False, "error": "未知接口"})
        self.assertIsNone(instance.parse_identity(body))


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="toolbox-inst-")
        self._original = paths.server_file
        paths.server_file = lambda: os.path.join(self.tmp, "server.json")

    def tearDown(self):
        paths.server_file = self._original
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_returns_none(self):
        self.assertIsNone(instance.read_record())

    def test_roundtrip(self):
        instance.write_record(8765, "abc123", "2026-09-13 10:00:00")
        record = instance.read_record()
        self.assertEqual(record["port"], 8765)
        self.assertEqual(record["instance"], "abc123")
        self.assertEqual(record["started"], "2026-09-13 10:00:00")
        self.assertEqual(record["pid"], os.getpid())

    def test_clear(self):
        instance.write_record(8765, "abc123", "x")
        instance.clear_record()
        self.assertIsNone(instance.read_record())

    def test_clear_is_safe_when_absent(self):
        instance.clear_record()
        instance.clear_record()
        self.assertIsNone(instance.read_record())

    def test_corrupted_file_returns_none(self):
        with open(paths.server_file(), "w", encoding="utf-8") as handle:
            handle.write("{ 不是合法 JSON")
        self.assertIsNone(instance.read_record())

    def test_bad_port_rejected(self):
        for bad in ("abc", None, 0, 99999, -1):
            with open(paths.server_file(), "w", encoding="utf-8") as handle:
                json.dump({"port": bad, "instance": "x"}, handle)
            self.assertIsNone(instance.read_record(), "port=%r 应被拒绝" % (bad,))

    def test_missing_instance_rejected(self):
        with open(paths.server_file(), "w", encoding="utf-8") as handle:
            json.dump({"port": 8765}, handle)
        self.assertIsNone(instance.read_record())

    def test_stale_record_yields_no_running_instance(self):
        """有记录但端口上没人应答 → 视为没有运行中的实例。"""
        # 选一个几乎不可能被占用的端口，避免误连到别人的服务
        instance.write_record(1, "abc123", "x")
        record, identity = instance.find_running()
        self.assertIsNone(record)
        self.assertIsNone(identity)

    def test_probe_nothing_listening(self):
        self.assertIsNone(instance.probe(1, timeout=0.3))

    def test_probe_rejects_foreign_service(self):
        """端口上跑着别的 HTTP 服务时不能被误判成自己。"""
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                body = json.dumps({"hello": "world"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        httpd = HTTPServer(("127.0.0.1", 0), Handler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever)
        thread.daemon = True
        thread.start()
        try:
            self.assertIsNone(instance.probe(port, timeout=1.5))
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
