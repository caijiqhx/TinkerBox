"""Web UI 承载层。

只做三件事：起 HTTP 服务、把请求分发到工具 action、拉起浏览器。
业务逻辑一律不在这里出现。
"""

#: 身份标记 —— 用来确认"这个端口上跑的确实是 ToolBox"（见 instance.py）
APP_TAG = "tinkerbox"

__all__ = ["APP_TAG", "server", "router", "launcher", "doctor", "instance"]
