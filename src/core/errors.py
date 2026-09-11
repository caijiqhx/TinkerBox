"""统一异常定义。

约定：所有可以"展示给用户"的业务失败都抛 ToolError；
承载层（web / cli）统一捕获并转成用户可读的信息，不打印 traceback。
"""

from __future__ import annotations


class ToolBoxError(Exception):
    """本项目所有异常的基类。"""


class ToolError(ToolBoxError):
    """工具业务错误：消息可直接展示给用户。"""


class NotFoundError(ToolError):
    """请求的资源不存在（工具 id、action 名、任务 id 等）。"""


class ConfigError(ToolBoxError):
    """配置读写异常（通常由调用方降级处理）。"""
