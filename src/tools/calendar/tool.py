"""日历工具：action 定义。

这一层**完全不感知 HTTP 和 HTML** —— 承载层（web/cli）通过 call(action, payload)
调用，与 tools/todo 的契约完全一致。

提供的 action：
- month   {year, month}  返回某年某月的整月视图数据（含每天状态、节日名、今天）
- year    {year}         返回某年 12 个月的月视图（前端的"年度视图"用）
"""

from __future__ import annotations

from core.errors import ToolError
from core.tool import Tool, ToolMeta

from tools.calendar import model


class CalendarTool(Tool):
    meta = ToolMeta(
        tid="calendar",
        name="日历",
        desc="带节假日与调休标注的月历。数据内置，离线可用。",
        icon="▦",
        order=20,
    )

    def actions(self):
        return {
            "month": self.act_month,
            "year": self.act_year,
        }

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def act_month(self, payload):
        """返回某年某月的整月视图数据。

        payload: {"year": 2026, "month": 9}   （缺省时用当前月份）
        """
        year = payload.get("year")
        month = payload.get("month")
        if year is None or month is None:
            import datetime
            now = datetime.date.today()
            year = year if year is not None else now.year
            month = month if month is not None else now.month
        view = model.month_view(year, month)
        if view is None:
            raise ToolError("日历参数无效：year=%r month=%r" % (year, month))
        return {"view": view}

    def act_year(self, payload):
        """返回某年每个月的月视图（供前端的"年度视图"一次拿全年）。"""
        year = payload.get("year")
        if year is None:
            import datetime
            year = datetime.date.today().year
        try:
            year = int(year)
        except (TypeError, ValueError):
            raise ToolError("年份无效：%r" % (year,))
        months = []
        years = model.load_years()      # 读一次给 12 个月复用：否则每次 month_view 都会重读数据文件
        for month in range(1, 13):
            view = model.month_view(year, month, years=years)
            if view is None:
                continue
            months.append(view)
        # 整年的干支：按农历年判定，跨农历年时给出两段（如「乙巳蛇年 → 丙午马年」）
        return {"year": year,
                "ganzhi": model.ganzhi_span("%04d-01-01" % year, "%04d-12-31" % year),
                "months": months}

    # ------------------------------------------------------------------
    # 命令行
    # ------------------------------------------------------------------
    def cli(self, argv):
        raise ToolError("日历工具暂不支持命令行调用，请在 Web 界面使用")