"""HTTP 服务生命周期。

- 绑定回环地址，端口传 0 由系统分配（避免冲突、避免局域网暴露）
- 心跳看门狗：只有在**成功拉起浏览器之后**才启用，
  这样"关掉 --app 窗口 → 程序自动退出"，体验贴近原生应用。
"""

from __future__ import annotations

import threading
import time
from http.server import ThreadingHTTPServer

from services import logs


class Server(object):
    def __init__(self, handler_class, host="127.0.0.1", port=0, ping_timeout=90):
        self.handler_class = handler_class
        self.host = host
        self.port = port
        self.ping_timeout = ping_timeout

        self.actual_port = None
        self._httpd = None
        self._thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_ping = 0.0
        self._ping_seen = False
        self._armed = False

    # ------------------------------------------------------------------
    def start(self):
        self._httpd = ThreadingHTTPServer((self.host, self.port), self.handler_class)
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

    # ------------------------------------------------------------------
    def note_ping(self):
        with self._lock:
            self._ping_seen = True
            self._last_ping = time.time()

    def arm_watchdog(self):
        """成功打开浏览器后调用，开始计时。"""
        with self._lock:
            self._armed = True
            self._last_ping = time.time()

    def _watchdog(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(1.0)
            if self._stop_event.is_set():
                return
            with self._lock:
                armed, seen, last = self._armed, self._ping_seen, self._last_ping
            if armed and seen and (time.time() - last) > self.ping_timeout:
                logs.log().info("前端心跳超时（> %s 秒），自动退出" % (self.ping_timeout,))
                self.shutdown()
                return

    # ------------------------------------------------------------------
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
