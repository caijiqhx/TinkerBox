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


class LunarTest(unittest.TestCase):
    """农历转换（内置 1900-2100 表）。"""

    def test_day_name(self):
        # 非初一：显示日名（初一以外不加月名）
        self.assertEqual(model.lunar_str("2026-09-25"), "十五")    # 中秋节
        self.assertEqual(model.lunar_str("2026-06-19"), "初五")    # 端午节
        self.assertEqual(model.lunar_str("2026-01-01"), "十三")    # 冬月十三

    def test_first_day_shows_month_name(self):
        # 每月初一显示月名；2026-02-17 是丙午年正月初一（春节）
        self.assertEqual(model.lunar_str("2026-02-17"), "正月")
        self.assertEqual(model.lunar_str("2024-02-10"), "正月")
        self.assertEqual(model.lunar_str("2025-02-28"), "二月")
        self.assertEqual(model.lunar_str("2023-03-22"), "闰二月")  # 2023 闰二月初一

    def test_spring_festival_eve(self):
        # 除夕前后：2026-02-16 除夕(廿九)，2/15 廿八
        self.assertEqual(model.lunar_str("2026-02-16"), "廿九")
        self.assertEqual(model.lunar_str("2026-02-15"), "廿八")
        self.assertEqual(model.lunar_str("2026-02-17"), "正月")

    def test_range_edges(self):
        # 数据表支持 1900-01-31 ~ 2100-12-31
        self.assertEqual(model.lunar_str("1900-01-31"), "正月")
        self.assertEqual(model.lunar_str("2100-12-31"), "腊月")
        # 越界 / 非法输入返回空串（前端不显示）
        self.assertEqual(model.lunar_str("1899-12-31"), "")
        self.assertEqual(model.lunar_str("2101-01-01"), "")
        self.assertEqual(model.lunar_str("not-a-date"), "")
        self.assertEqual(model.lunar_str(""), "")

    def test_leap_month_sequence(self):
        # 2023 闰二月：闰二月初一在 3/22，正月最后一天是 2/19
        self.assertEqual(model.lunar_str("2023-02-19"), "廿九")
        self.assertEqual(model.lunar_str("2023-02-20"), "二月")
        self.assertEqual(model.lunar_str("2023-03-22"), "闰二月")

    def test_month_view_items_include_lunar(self):
        v = model.month_view(2026, 2)
        by_day = {i["day"]: i["lunar"] for i in v["items"]}
        self.assertEqual(by_day[17], "正月")
        self.assertEqual(by_day[16], "廿九")
        self.assertEqual(by_day[15], "廿八")
        # 每一天都有农历文本（2000-2100 内）
        self.assertTrue(all(i["lunar"] for i in v["items"]))

    def test_month_view_items_include_full_lunar(self):
        """格子放不下完整农历，但悬停提示要用它（八月初三而不是"初三"）。"""
        v = model.month_view(2026, 9)
        by_day = {i["day"]: i["lunar_full"] for i in v["items"]}
        self.assertEqual(by_day[25], "八月十五")     # 中秋
        self.assertEqual(by_day[1], "七月二十")
        # 完整农历始终"月+日"，不会像 lunar 那样在初一只给月名
        v2 = model.month_view(2026, 2)
        feb = {i["day"]: i["lunar_full"] for i in v2["items"]}
        self.assertEqual(feb[17], "正月初一")
        self.assertTrue(all(i["lunar_full"] for i in v2["items"]))


class LunarFullTest(unittest.TestCase):
    """完整农历（月 + 日），供悬停提示使用。"""

    def test_always_includes_month_name(self):
        # 与 lunar_str 的差别：初一时不再是光秃秃的"正月"，而是"正月初一"
        self.assertEqual(model.lunar_full("2026-02-17"), "正月初一")
        self.assertEqual(model.lunar_str("2026-02-17"), "正月")
        # 普通日子同样带月名
        self.assertEqual(model.lunar_full("2026-02-18"), "正月初二")
        self.assertEqual(model.lunar_full("2026-09-25"), "八月十五")   # 中秋
        self.assertEqual(model.lunar_full("2026-06-19"), "五月初五")   # 端午
        self.assertEqual(model.lunar_full("2026-01-01"), "冬月十三")

    def test_leap_month(self):
        self.assertEqual(model.lunar_full("2023-03-22"), "闰二月初一")
        self.assertEqual(model.lunar_full("2023-03-23"), "闰二月初二")

    def test_range_edges_and_bad_input(self):
        self.assertEqual(model.lunar_full("1900-01-31"), "正月初一")
        self.assertEqual(model.lunar_full("2100-12-31"), "腊月初一")
        self.assertEqual(model.lunar_full("2101-01-01"), "")     # 越界
        self.assertEqual(model.lunar_full("1899-12-31"), "")
        self.assertEqual(model.lunar_full("abc"), "")            # 非法
        self.assertEqual(model.lunar_full(""), "")


class OverviewTest(unittest.TestCase):
    """月份概览（节假日 / 调休 数量与跨度）。"""

    def test_february_2026(self):
        v = model.month_view(2026, 2)
        ov = v["overview"]
        self.assertEqual(ov["holidays"], 9)                    # 春节 2/15-23
        self.assertEqual(ov["adjusts"], 2)                     # 调休 2/14、2/28
        self.assertEqual(ov["holiday_span"], [15, 23])
        self.assertEqual(ov["adjust_span"], [14, 28])
        self.assertEqual(ov["holiday_names"][0]["name"], "春节")
        self.assertEqual(ov["holiday_names"][0]["days"], 9)

    def test_january_2026(self):
        v = model.month_view(2026, 1)
        ov = v["overview"]
        self.assertEqual(ov["holidays"], 3)                    # 元旦 1/1-3
        self.assertEqual(ov["adjusts"], 1)                     # 补班 1/4
        self.assertEqual(ov["adjust_span"], [4, 4])            # 单天也按 [首, 末]
        self.assertEqual(ov["holiday_names"][0]["name"], "元旦")

    def test_cross_month_holiday_counts_local_days(self):
        # 国庆 2026-10-01~07 全在 10 月内；另有 10/10 补班。
        v = model.month_view(2026, 10)
        ov = v["overview"]
        self.assertEqual(ov["holidays"], 7)
        self.assertEqual(ov["adjusts"], 1)                     # 10/10 国庆调休
        self.assertEqual(ov["adjust_span"], [10, 10])

    def test_month_without_holidays(self):
        v = model.month_view(2026, 7)
        ov = v["overview"]
        self.assertEqual(ov["holidays"], 0)
        self.assertEqual(ov["adjusts"], 0)
        self.assertEqual(ov["holiday_names"], [])
        self.assertEqual(ov["holiday_span"], [])
        self.assertEqual(ov["adjust_span"], [])


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