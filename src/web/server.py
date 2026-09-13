"""HTTP 服务生命周期。

两种运行模式：

**常驻模式（keep_alive = True，默认）**
    关掉浏览器窗口后服务继续留着，一天只需要点一次 run。
    退出只有三条路：界面上的「关闭服务」/ `stop` 命令 / 空闲超时。

**跟随窗口模式（keep_alive = False）**
    回到早期行为：关窗口即退出，并用心跳超时兜底。

另：绑定回环地址；端口来自配置（固定），方便书签稳定指向。
"""

from __future__ import annotations

import datetime
import secrets
import threading
import time
from http.server import ThreadingHTTPServer

from services import logs
from services import platform as plat
from web import APP_TAG


class _HTTPServer(ThreadingHTTPServer):
    # 平台决定是否启用地址复用 —— Windows 上必须关闭，
    # 否则两个进程能绑同一端口，"端口被占用"就检测不出来了。
    allow_reuse_address = plat.allow_address_reuse()


class Server(object):
    def __init__(self, handler_class, host="127.0.0.1", port=0,
                 keep_alive=True, idle_timeout=0, ping_timeout=90):
        self.handler_class = handler_class
        self.host = host
        self.port = port
        self.keep_alive = bool(keep_alive)
        self.idle_timeout = int(idle_timeout or 0)      # 秒；0 = 不限制
        self.ping_timeout = ping_timeout

        self.actual_port = None
        self.instance_id = secrets.token_hex(8)
        self.started_at = time.time()

        self._httpd = None
        self._thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_activity = time.time()
        self._last_ping = 0.0
        self._ping_seen = False
        self._armed = False

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------
    def start(self):
        """绑定端口并开始服务。端口被占用会抛 OSError，由调用方决定怎么提示。"""
        self._httpd = _HTTPServer((self.host, self.port), self.handler_class)
        self._httpd.daemon_threads = True
        self.actual_port = self._httpd.server_address[1]

        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        name="toolbox-http")
        self._thread.daemon = True
        self._thread.start()

        watchdog = threading.Thread(target=self._watchdog, name="toolbox-watchdog")
        watchdog.daemon = True
        watchdog.start()
        return self.actual_port

    def url(self, path="/"):
        return "http://127.0.0.1:%d%s" % (self.actual_port, path)

    def wait(self):
        """阻塞主线程直到收到退出信号。"""
        try:
            while not self._stop_event.is_set():
                time.sleep(0.3)
        except KeyboardInterrupt:
            logs.log().info("收到 Ctrl+C，正在退出")
        finally:
            self.shutdown()

    def request_shutdown(self):
        """供请求处理线程调用：另起线程关闭，避免在 handler 内阻塞。"""
        threading.Thread(target=self.shutdown, name="toolbox-shutdown").start()

    def shutdown(self):
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            try:
                self._httpd.server_close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 活动追踪
    # ------------------------------------------------------------------
    def note_activity(self):
        """任何一次请求都算活动 —— 空闲退出依据的是"还有没有人在用"。"""
        with self._lock:
            self._last_activity = time.time()

    def note_ping(self):
        with self._lock:
            self._ping_seen = True
            self._last_ping = time.time()
            self._last_activity = time.time()

    def arm_watchdog(self):
        """只在成功打开浏览器之后调用（跟随窗口模式才需要）。"""
        with self._lock:
            self._armed = True
            self._last_ping = time.time()

    def _watchdog(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(1.0)
            if self._stop_event.is_set():
                return

            now = time.time()
            with self._lock:
                idle = now - self._last_activity
                armed, seen, last_ping = self._armed, self._ping_seen, self._last_ping

            # 空闲超时：常驻模式的"忘了关"兜底，任何时候都生效
            if self.idle_timeout and idle > self.idle_timeout:
                logs.log().info("空闲 %.1f 小时无任何请求，自动退出" % (idle / 3600.0,))
                self.shutdown()
                return

            # 心跳超时：仅在"跟随窗口"模式下用于判断窗口是否已经关掉
            if not self.keep_alive and armed and seen \
                    and (now - last_ping) > self.ping_timeout:
                logs.log().info("前端心跳超时（> %s 秒），自动退出" % (self.ping_timeout,))
                self.shutdown()
                return

    # ------------------------------------------------------------------
    # 身份信息
    # ------------------------------------------------------------------
    def started_text(self):
        return datetime.datetime.fromtimestamp(self.started_at) \
            .strftime("%Y-%m-%d %H:%M:%S")

    def uptime(self):
        return max(0, int(time.time() - self.started_at))

    def identity(self):
        """供 /api/identity 与 /api/status 使用。"""
        return {
            "app": APP_TAG,
            "instance": self.instance_id,
            "port": self.actual_port,
            "started": self.started_text(),
            "uptime": self.uptime(),
            "keep_alive": self.keep_alive,
            "idle_exit_hours": (self.idle_timeout / 3600.0) if self.idle_timeout else 0,
        }
