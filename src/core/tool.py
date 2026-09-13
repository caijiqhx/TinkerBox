"""工具契约。

关键设计：工具**不感知 HTTP，也不感知 HTML**。
每个工具只对外暴露一组 action（入参 dict、出参可 JSON 序列化的结构），
由承载层（web / cli）负责把外部请求映射到 action。

这样将来换 UI 承载方式（例如加 tkinter），业务代码一行都不用改。
"""

from __future__ import annotations

from core.errors import ToolError


class ToolMeta(object):
    """工具的元信息，供入口页 / 导航 / CLI 帮助渲染。"""

    def __init__(self, tid, name, desc="", icon="", order=100, icon_html=""):
        self.id = tid
        self.name = name
        self.desc = desc
        self.icon = icon
        self.order = order
        self.icon_html = icon_html   # 可选：内联 SVG，导航/入口页优先用它

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "desc": self.desc,
            "icon": self.icon,
            "icon_html": self.icon_html,
            "order": self.order,
        }

    def __repr__(self):
        return "<ToolMeta %s>" % self.id


class Tool(object):
    """所有工具子类的基类。"""

    #: 子类必须提供 ToolMeta 实例
    meta = None

    def actions(self):
        """返回 {action_name: callable(payload: dict) -> JSON 可序列化结果}。

        这是 UI 与业务之间**唯一**的接口。
        """
        return {}

    def cli(self, argv):
        """命令行子命令入口。默认不支持，子类按需覆写。

        返回进程退出码（int）。
        """
        raise ToolError("工具 '%s' 不支持命令行调用" % (self.meta.id,))

    # ------------------------------------------------------------------
    # 承载层统一入口
    # ------------------------------------------------------------------
    def call(self, action, payload):
        """查找并执行 action，做最基本的入参校验。"""
        if not action:
            raise ToolError("缺少操作名")
        handler = self.actions().get(action)
        if handler is None:
            raise ToolError("工具 '%s' 不支持操作：%s" % (self.meta.id, action))
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ToolError("请求体必须是 JSON 对象")
        return handler(payload)
