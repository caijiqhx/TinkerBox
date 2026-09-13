"""HTTP 路由与 action 分发。

承载层的全部职责：
1. 把 HTTP 请求翻译成 `工具.call(action, payload)`
2. 把结果/异常翻译成统一的 JSON 响应
3. 做本机服务必需的安全校验

业务代码一行都不在这里。
"""

from __future__ import annotations

import hmac
import json
import mimetypes
import os
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs

from core import paths, registry
from core.errors import ToolError
from services import config, logs
from web import APP_TAG

MAX_BODY = 1024 * 1024          # 1 MB
TOKEN_HEADER = "X-Toolbox-Token"
TOKEN_PLACEHOLDER = "__TOKEN_PLACEHOLDER__"
THEME_PLACEHOLDER = "__THEME_PREF_PLACEHOLDER__"

#: 主题取值白名单
THEMES = ("light", "dark", "auto")

#: 允许前端写入的配置项白名单 —— 配置接口不能变成任意写入口
WRITABLE_CONFIG = ("theme", "window_size")

_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]")

# 显式声明，避免 Windows 上 mimetypes 受注册表影响把 .js 猜成 text/plain
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


class Application(object):
    def __init__(self, token, server=None):
        self.token = token
        self.server = server
        self.static_root = os.path.realpath(str(paths.static_dir()))

    # ------------------------------------------------------------------
    # 安全
    # ------------------------------------------------------------------
    def host_ok(self, headers):
        """校验 Host，阻断 DNS rebinding。"""
        host = (headers.get("Host") or "").strip().lower()
        if not host:
            return False
        if host.startswith("["):
            hostname = host.split("]")[0] + "]"
        else:
            hostname = host.split(":")[0]
        return hostname in _LOCAL_HOSTS

    def origin_ok(self, headers):
        """校验 Origin，阻断跨站请求。"""
        origin = headers.get("Origin")
        if not origin:
            return True
        tail = origin.split("://")[-1]
        host_part = tail.split("/")[0].split(":")[0].strip().lower()
        return host_part in _LOCAL_HOSTS

    def token_ok(self, headers, query=""):
        """校验令牌。

        header 是常规方式；查询串 ?t= 是为了页面关闭时的 sendBeacon ——
        beacon 无法自定义请求头，只能把令牌放在 URL 上。
        """
        given = headers.get(TOKEN_HEADER) or ""
        if not given and query:
            given = parse_qs(query).get("t", [""])[0]
        try:
            return hmac.compare_digest(given.encode("utf-8"), self.token.encode("utf-8"))
        except Exception:
            return False

    def identity(self):
        if self.server is None:
            return {"app": APP_TAG, "instance": "", "port": 0}
        return self.server.identity()

    def instance_ok(self, query):
        """用实例标识校验「stop 命令」发来的关闭请求。

        stop 在进程外运行、拿不到页面令牌，所以改用 server.json 里的实例标识。
        两者的信任级别相同 —— 能读到 server.json 的人本来就能直接结束该进程。
        """
        given = parse_qs(query).get("i", [""])[0]
        server = self.server
        if server is None or not given:
            return False
        try:
            return hmac.compare_digest(given.encode("utf-8"),
                                       server.instance_id.encode("utf-8"))
        except Exception:
            return False

    # ------------------------------------------------------------------
    def theme_pref(self):
        """读取已保存的主题偏好，非法值一律退回 auto。"""
        value = str(config.get("theme") or "auto").strip().lower()
        return value if value in THEMES else "auto"

    def index_html(self):
        target = os.path.join(self.static_root, "index.html")
        try:
            with open(target, "r", encoding="utf-8") as handle:
                html = handle.read()
        except OSError:
            return "<h1>ToolBox</h1><p>静态资源缺失：web/static/index.html</p>"
        # 主题在服务端注入，页面渲染时就已经是对的颜色，不会闪一下白/黑
        html = html.replace(THEME_PLACEHOLDER, self.theme_pref())
        return html.replace(TOKEN_PLACEHOLDER, self.token)


def build_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ToolBox"
        sys_version = ""

        def log_message(self, fmt, *args):        # 静音默认访问日志
            return

        # ---------------- 响应 ----------------
        def _send(self, status, payload, content_type):
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                if self.command != "HEAD" and payload:
                    self.wfile.write(payload)
            except Exception:
                pass

        def _json(self, status, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _ok(self, data=None):
            self._json(200, {"ok": True, "data": data})

        def _fail(self, message):
            self._json(200, {"ok": False, "error": message})

        # ---------------- 请求体 ----------------
        def _read_body(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                length = 0
            if length <= 0:
                return {}
            if length > MAX_BODY:
                raise ToolError("请求体过大（上限 1 MB）")
            raw = self.rfile.read(length)
            if not raw:
                return {}
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                raise ToolError("请求体不是合法 JSON")
            if not isinstance(data, dict):
                raise ToolError("请求体必须是 JSON 对象")
            return data

        # ---------------- 入口 ----------------
        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def _handle(self, method):
            try:
                if not app.host_ok(self.headers):
                    self._json(403, {"ok": False, "error": "Host 校验失败"})
                    return
                if not app.origin_ok(self.headers):
                    self._json(403, {"ok": False, "error": "来源校验失败"})
                    return

                path, _, query = self.path.partition("?")

                # 任何请求都算"有人在用"，空闲退出依据的是这个
                if app.server is not None:
                    app.server.note_activity()

                if path in ("/", "/index.html"):
                    self._send(200, app.index_html(), "text/html; charset=utf-8")
                    return
                if path == "/favicon.ico":
                    self._send(204, b"", "image/x-icon")
                    return
                if path.startswith("/static/"):
                    self._serve_static(path[len("/static/"):])
                    return

                # ---- 下面两个端点不走令牌校验 ----
                # /api/identity：新启动的进程要能探测到老进程，而它不知道老进程的令牌
                if path == "/api/identity" and method == "GET":
                    self._ok(app.identity())
                    return
                # /api/shutdown：stop 命令用 server.json 里的实例标识校验
                if path == "/api/shutdown" and method == "POST":
                    if not app.instance_ok(query):
                        self._json(403, {"ok": False, "error": "实例校验失败"})
                        return
                    self._ok({"bye": True})
                    if app.server is not None:
                        app.server.request_shutdown()
                    return

                if path.startswith("/api/"):
                    if not app.token_ok(self.headers, query):
                        self._json(403, {"ok": False, "error": "令牌校验失败，请重新打开页面"})
                        return
                    body = self._read_body() if method == "POST" else {}
                    self._api(method, path, body)
                    return

                self._json(404, {"ok": False, "error": "未知路径：%s" % path})
            except ToolError as exc:
                self._fail(str(exc))
            except Exception as exc:
                logs.log().error("请求处理异常 %s %s" % (method, self.path), exc)
                self._fail("服务内部错误：%s: %s" % (exc.__class__.__name__, exc))

        # ---------------- 静态资源 ----------------
        def _serve_static(self, relative):
            relative = relative.split("?")[0]
            target = os.path.realpath(
                os.path.join(app.static_root, relative.replace("/", os.sep))
            )
            if not (target == app.static_root
                    or target.startswith(app.static_root + os.sep)):
                self._json(404, {"ok": False, "error": "路径非法"})
                return
            if not os.path.isfile(target):
                self._json(404, {"ok": False, "error": "文件不存在：%s" % relative})
                return
            ext = os.path.splitext(target)[1].lower()
            ctype = _CONTENT_TYPES.get(ext) or mimetypes.guess_type(target)[0] \
                or "application/octet-stream"
            try:
                with open(target, "rb") as handle:
                    data = handle.read()
            except OSError as exc:
                self._json(404, {"ok": False, "error": str(exc)})
                return
            self._send(200, data, ctype)

        # ---------------- API ----------------
        def _api(self, method, path, body):
            if path == "/api/tools" and method == "GET":
                self._ok({"tools": registry.list_meta()})
                return

            if path == "/api/doctor" and method == "GET":
                from web import doctor
                info = doctor.collect()
                self._ok({"info": info, "text": doctor.render(info)})
                return

            if path == "/api/config" and method == "GET":
                self._ok({"config": {k: config.get(k) for k in WRITABLE_CONFIG}})
                return

            if path == "/api/config" and method == "POST":
                updates = body.get("payload")
                if not isinstance(updates, dict):
                    self._fail("payload 必须是对象")
                    return
                saved = {}
                for key, value in updates.items():
                    if key not in WRITABLE_CONFIG:
                        continue
                    if key == "theme":
                        value = str(value).strip().lower()
                        if value not in THEMES:
                            raise ToolError("主题取值非法：%s" % (value,))
                    config.set_value(key, value)
                    saved[key] = value
                self._ok({"saved": saved})
                return

            if path == "/api/ping" and method == "POST":
                if app.server is not None:
                    app.server.note_ping()
                self._ok({"time": time.time()})
                return

            if path == "/api/status" and method == "GET":
                data = dict(app.identity())
                data.pop("instance", None)          # 页面不需要知道实例标识
                self._ok(data)
                return

            if path == "/api/quit" and method == "POST":
                # 界面上的「关闭服务」按钮 —— 无论哪种模式都真的关掉
                self._ok({"bye": True})
                if app.server is not None:
                    app.server.request_shutdown()
                return

            if path == "/api/bye" and method == "POST":
                # 页面关闭时由 sendBeacon 触发。
                # 常驻模式下**关窗口不等于关服务**，所以这里什么都不做，
                # 只把 keep_alive 回给前端，让它知道服务还活着。
                server = app.server
                if server is None or server.keep_alive:
                    self._ok({"bye": True, "keep_alive": True})
                    return
                self._ok({"bye": True, "keep_alive": False})
                server.request_shutdown()
                return

            if path.startswith("/api/tool/") and method == "POST":
                parts = path[len("/api/tool/"):].split("/")
                if len(parts) != 2 or not parts[0] or not parts[1]:
                    self._fail("路径格式应为 /api/tool/<工具>/<操作>")
                    return
                payload = body.get("payload")
                if payload is None:
                    payload = {}
                if not isinstance(payload, dict):
                    self._fail("payload 必须是对象")
                    return
                tool = registry.get(parts[0])
                self._ok(tool.call(parts[1], payload))
                return

            self._json(404, {"ok": False, "error": "未知接口：%s" % path})

    return Handler
