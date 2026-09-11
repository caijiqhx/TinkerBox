"""日志。

同时写文件与 stdout。**日志本身失败绝不允许影响主流程**，因此全部包在 try 里。
"""

from __future__ import annotations

import datetime
import traceback

from core import paths

_logger = None


class Logger(object):
    def __init__(self, directory):
        self.directory = directory
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def _emit(self, level, message):
        line = "[%s] %-5s %s" % (
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            level,
            message,
        )
        try:
            stamp = datetime.datetime.now().strftime("%Y-%m-%d")
            with open(str(self.directory / ("%s.log" % stamp)), "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            pass
        try:
            print(line)
        except Exception:
            pass

    def info(self, message):
        self._emit("INFO", message)

    def warn(self, message):
        self._emit("WARN", message)

    def error(self, message, exc=None):
        text = message
        if exc is not None:
            text = "%s | %s: %s" % (message, exc.__class__.__name__, exc)
            try:
                text += "\n" + "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )
            except Exception:
                pass
        self._emit("ERROR", text)


def log():
    global _logger
    if _logger is None:
        _logger = Logger(paths.logs_dir())
    return _logger
