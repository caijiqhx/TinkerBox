"""日历工具核心逻辑测试。

运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import datetime
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from core.errors import ToolError                # noqa: E402
from services import jsonio                      # noqa: E402
from tools.calendar import model, tool           # noqa: E402


def _today(offset=0):
    return (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()


class DayStatusTest(unittest.TestCase):
    """单日四态判定（数据来自内置 holidays.json，2026）。"""

    def test_holiday(self):
        self.assertEqual(model.day_status("2026-01-01")["status"], model.HOLIDAY)
        self.assertEqual(model.day_status("2026-01-01")["name"], "元旦")
        self.assertEqual(model.day_status("2026-02-15")["name"], "春节")
        self.assertEqual(model.day_status("2026-10-01")["name"], "国庆节")

    def test_adjust_workday(self):
        # 调休补班日：周六/周日要上班
        self.assertEqual(model.day_status("2026-02-14")["status"], model.ADJUST)
        self.assertEqual(model.day_status("2026-02-14")["name"], "调休")
        self.assertTrue(model.day_status("2026-02-14")["status"] == model.ADJUST)
        self.assertEqual(model.day_status("2026-10-10")["status"], model.ADJUST)
        self.assertEqual(model.day_status("2026-01-04")["status"], model.ADJUST)

    def test_weekend(self):
        # 2026-03-07 是周六（无调休）
        self.assertEqual(model.day_status("2026-03-07")["status"], model.WEEKEND)
        self.assertEqual(model.day_status("2026-03-08")["status"], model.WEEKEND)

    def test_work(self):
        self.assertEqual(model.day_status("2026-03-10")["status"], model.WORK)
        self.assertEqual(model.day_status("2026-03-10")["name"], None)

    def test_unknown_year_defaults_to_calendar(self):
        # 没有数据的年份：按星期推（周末 = 休，其余 = 工作），不报错、无节日名
        s = model.day_status("2030-06-03")   # 周一
        self.assertEqual(s["status"], model.WORK)
        s = model.day_status("2030-06-01")   # 周六
        self.assertEqual(s["status"], model.WEEKEND)


class MonthViewTest(unittest.TestCase):
    def test_february_2026(self):
        v = model.month_view(2026, 2)
        self.assertEqual(v["year"], 2026)
        self.assertEqual(v["month"], 2)
        self.assertEqual(v["days"], 28)
        self.assertEqual(v["weekday0"], 6)    # 2026-02-01 是周日？查 weekday()：周日=6
        # 春节 2/15-23
        holiday_days = [i["day"] for i in v["items"] if i["status"] == model.HOLIDAY]
        self.assertEqual(holiday_days, list(range(15, 24)))
        # 调休：2/14、2/28
        adjust = [i["day"] for i in v["items"] if i["status"] == model.ADJUST]
        self.assertEqual(adjust, [14, 28])

    def test_february_2026_weekday0(self):
        import datetime as dt
        d = dt.date(2026, 2, 1)
        self.assertEqual(d.weekday(), 6)     # 周日
        v = model.month_view(2026, 2)
        self.assertEqual(v["weekday0"], 6)

    def test_month_with_today(self):
        now = datetime.date.today()
        v = model.month_view(now.year, now.month)
        self.assertIsNotNone(v["today"])
        self.assertEqual(v["today"], now.isoformat())

    def test_month_without_today(self):
        now = datetime.date.today()
        # 上一个月的今天（若有），一般不含今天
        if now.month == 1:
            v = model.month_view(now.year - 1, 12)
        else:
            v = model.month_view(now.year, now.month - 1)
        self.assertIsNone(v["today"])

    def test_invalid_args(self):
        self.assertIsNone(model.month_view(2026, 13))
        self.assertIsNone(model.month_view(2026, 0))
        self.assertIsNone(model.month_view(2026, "x"))
        self.assertIsNone(model.month_view("x", 1))


class CalendarToolTest(unittest.TestCase):
    def setUp(self):
        self.tool = tool.CalendarTool()

    def test_month_action(self):
        res = self.tool.call("month", {"year": 2026, "month": 9})
        view = res["view"]
        self.assertEqual(view["year_month"], "2026-09")
        self.assertEqual(len(view["items"]), 30)
        # 9 月有中秋（25-27）与国庆调休（9/20）
        names = [i["name"] for i in view["items"] if i["name"]]
        self.assertIn("中秋节", names)

    def test_month_action_defaults_to_today(self):
        now = datetime.date.today()
        res = self.tool.call("month", {})
        view = res["view"]
        self.assertEqual(view["year"], now.year)
        self.assertEqual(view["month"], now.month)

    def test_year_action(self):
        res = self.tool.call("year", {"year": 2026})
        self.assertEqual(res["year"], 2026)
        self.assertEqual(len(res["months"]), 12)

    def test_year_action_defaults_to_today(self):
        res = self.tool.call("year", {})
        self.assertEqual(res["year"], datetime.date.today().year)

    def test_invalid_month_raises_tool_error(self):
        with self.assertRaises(ToolError):
            self.tool.call("month", {"year": 2026, "month": 13})

    def test_cli_not_supported(self):
        with self.assertRaises(ToolError):
            self.tool.cli(["month"])


if __name__ == "__main__":
    unittest.main()