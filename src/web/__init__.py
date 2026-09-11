"""Web UI 承载层。

只做三件事：起 HTTP 服务、把请求分发到工具 action、拉起浏览器。
业务逻辑一律不在这里出现。
"""

__all__ = ["server", "router", "launcher", "doctor"]
