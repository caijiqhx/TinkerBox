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

    def test_items_carry_iso_week(self):
        v = model.month_view(2026, 9, today="2026-09-18")
        by_day = {i["day"]: i["week"] for i in v["items"]}
        self.assertEqual(by_day[1], 36)      # 2026-09-01 属于第 36 周
        self.assertEqual(by_day[7], 37)      # 周一换周
        self.assertEqual(by_day[30], 40)

    def test_week_is_uniform_within_a_row(self):
        # 日历按行显示一周，所以同一行内所有天的周号必须一致（前端取该行第一格即可）
        v = model.month_view(2026, 9, today="2026-09-18")
        lead = v["weekday0"]
        rows = {}
        for n, item in enumerate(v["items"]):
            rows.setdefault((lead + n) // 7, set()).add(item["week"])
        for row, weeks in rows.items():
            self.assertEqual(len(weeks), 1, "第 %d 行出现多个周号: %s" % (row, weeks))

    def test_week_across_year_boundary(self):
        # ISO 规则下 12 月底可能已经属于次年第 1 周，值直接跟标准库对齐
        v = model.month_view(2026, 12, today="2026-09-18")
        last = v["items"][-1]
        self.assertEqual(last["date"], "2026-12-31")
        self.assertEqual(last["week"], datetime.date(2026, 12, 31).isocalendar()[1])

    def test_items_carry_day_hint(self):
        v = model.month_view(2026, 9, today="2026-09-18")
        by_day = {i["day"]: i["hint"] for i in v["items"]}
        self.assertEqual(by_day[25], "中秋节 · 八月十五")   # 假期正日子（同名农历节日不重复写）
        self.assertEqual(by_day[26], "中秋节 · 八月十六")   # 假期里的其他天也说明在假期里
        self.assertEqual(by_day[20], "调休补班日 · 八月初十")
        self.assertEqual(by_day[17], "")                    # 普通工作日不提示

    def test_day_hint_merges_festival_and_term(self):
        v = model.month_view(2026, 6, today="2026-09-18")
        by_day = {i["day"]: i["hint"] for i in v["items"]}
        # 6/21 既是端午假期、又是夏至 —— 三样都该出现
        self.assertEqual(by_day[21], "端午节 · 夏至 · 五月初七")

    def test_day_hint_covers_lunar_new_year_eve(self):
        v = model.month_view(2026, 2, today="2026-09-18")
        by_day = {i["day"]: i["hint"] for i in v["items"]}
        self.assertEqual(by_day[16], "春节 · 除夕 · 腊月廿九")

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


class SolarTermTest(unittest.TestCase):
    """二十四节气（内置 1900-2100 压缩表，与 solarlunar 逐条核对过）。"""

    def test_known_terms_2026(self):
        self.assertEqual(model.solar_term("2026-01-05"), "小寒")
        self.assertEqual(model.solar_term("2026-02-04"), "立春")
        self.assertEqual(model.solar_term("2026-04-05"), "清明")
        self.assertEqual(model.solar_term("2026-06-21"), "夏至")
        self.assertEqual(model.solar_term("2026-08-07"), "立秋")
        self.assertEqual(model.solar_term("2026-12-22"), "冬至")

    def test_non_term_day_is_empty(self):
        self.assertEqual(model.solar_term("2026-01-01"), "")
        self.assertEqual(model.solar_term("2026-02-05"), "")

    def test_each_year_has_24_valid_days_in_month_order(self):
        # 每个节气都要落在合法日号上，且第 m 月的两个节气日号递增（小寒<大寒、立春<雨水…）
        for year in (1900, 1950, 2000, 2026, 2100):
            for n in range(1, 25, 2):
                first, second = model._term_day(year, n), model._term_day(year, n + 1)
                self.assertTrue(1 <= first < second <= 31, (year, n, first, second))

    def test_range_and_bad_input(self):
        self.assertEqual(model.solar_term("2101-01-01"), "")
        self.assertEqual(model.solar_term("1899-12-31"), "")
        self.assertEqual(model.solar_term("abc"), "")
        self.assertEqual(model.solar_term(""), "")


class LunarFestivalTest(unittest.TestCase):
    """农历传统节日（纯计算，不依赖任何外部数据）。"""

    def test_common_festivals_2026(self):
        self.assertEqual(model.lunar_festival("2026-01-26"), "腊八")     # 腊月初八
        self.assertEqual(model.lunar_festival("2026-02-17"), "春节")     # 正月初一
        self.assertEqual(model.lunar_festival("2026-03-03"), "元宵")     # 正月十五
        self.assertEqual(model.lunar_festival("2026-03-20"), "龙抬头")   # 二月初二
        self.assertEqual(model.lunar_festival("2026-06-19"), "端午")     # 五月初五
        self.assertEqual(model.lunar_festival("2026-08-19"), "七夕")     # 七月初七
        self.assertEqual(model.lunar_festival("2026-08-27"), "中元")     # 七月十五
        self.assertEqual(model.lunar_festival("2026-09-25"), "中秋")     # 八月十五
        self.assertEqual(model.lunar_festival("2026-10-18"), "重阳")     # 九月初九

    def test_new_years_eve_is_last_day_of_lunar_december(self):
        # 2026 腊月只有廿九 —— 除夕就是廿九，不是"三十"（这里按次日是初一判定）
        self.assertEqual(model.lunar_festival("2026-02-16"), "除夕")
        self.assertEqual(model.lunar_full("2026-02-16"), "腊月廿九")
        self.assertEqual(model.lunar_festival("2026-02-15"), "")        # 前一天不算

    def test_minor_new_year_covers_both_days(self):
        self.assertEqual(model.lunar_festival("2026-02-10"), "小年")     # 腊月廿三（北方）
        self.assertEqual(model.lunar_festival("2026-02-11"), "小年")     # 腊月廿四（南方）

    def test_ordinary_day_is_empty(self):
        self.assertEqual(model.lunar_festival("2026-02-12"), "")

    def test_leap_month_is_not_a_festival_day(self):
        # 2023 闰二月初一 ≠ 二月初二（龙抬头）；闰月不重复过节
        self.assertEqual(model.lunar_full("2023-03-22"), "闰二月初一")
        self.assertEqual(model.lunar_festival("2023-03-22"), "")

    def test_range_and_bad_input(self):
        self.assertEqual(model.lunar_festival("2101-01-01"), "")
        self.assertEqual(model.lunar_festival("1899-12-31"), "")
        self.assertEqual(model.lunar_festival("abc"), "")

    def test_month_view_carries_fest_and_term(self):
        feb = {i["day"]: i for i in model.month_view(2026, 2)["items"]}
        self.assertEqual(feb[16]["fest"], "除夕")
        self.assertEqual(feb[16]["term"], "")
        self.assertEqual(feb[4]["term"], "立春")
        self.assertEqual(feb[4]["fest"], "")
        # 3/20 春分与龙抬头同日：两个字段各自独立（展示时的优先级由前端决定）
        mar = {i["day"]: i for i in model.month_view(2026, 3)["items"]}
        self.assertEqual(mar[20]["term"], "春分")
        self.assertEqual(mar[20]["fest"], "龙抬头")


class FestivalDayTest(unittest.TestCase):
    """法定假期名只在"正日子"当天进格子（中秋三天不都写"中秋节"）。"""

    def test_solar_festivals_only_on_the_day(self):
        self.assertTrue(model.is_festival_day("2026-01-01", "元旦"))
        self.assertFalse(model.is_festival_day("2026-01-02", "元旦"))
        self.assertTrue(model.is_festival_day("2026-10-01", "国庆节"))
        self.assertFalse(model.is_festival_day("2026-10-03", "国庆节"))
        self.assertTrue(model.is_festival_day("2026-05-01", "劳动节"))
        self.assertFalse(model.is_festival_day("2026-05-05", "劳动节"))

    def test_lunar_festivals_only_on_the_day(self):
        self.assertTrue(model.is_festival_day("2026-09-25", "中秋节"))
        self.assertFalse(model.is_festival_day("2026-09-26", "中秋节"))
        self.assertFalse(model.is_festival_day("2026-09-27", "中秋节"))
        self.assertTrue(model.is_festival_day("2026-06-19", "端午节"))
        self.assertFalse(model.is_festival_day("2026-06-20", "端午节"))

    def test_spring_festival_anchors_on_lunar_new_year(self):
        # 正月初一才是"春节"；除夕和假期其余各天都不算
        self.assertTrue(model.is_festival_day("2026-02-17", "春节"))
        for day in ("2026-02-15", "2026-02-16", "2026-02-18", "2026-02-23"):
            self.assertFalse(model.is_festival_day(day, "春节"), day)

    def test_solar_term_named_festival_uses_term_day(self):
        # 清明节 = 清明节气当天（2026-04-05）；假期首日 4/4 不算
        self.assertTrue(model.is_festival_day("2026-04-05", "清明节"))
        self.assertFalse(model.is_festival_day("2026-04-04", "清明节"))

    def test_bad_input(self):
        self.assertFalse(model.is_festival_day("abc", "元旦"))
        self.assertFalse(model.is_festival_day("2026-01-01", ""))
        self.assertFalse(model.is_festival_day("2026-01-01", None))

    def test_month_view_marks_only_the_day(self):
        v = model.month_view(2026, 9, today="2026-09-14")
        got = {i["date"]: i["fest_day"] for i in v["items"] if i["status"] == "holiday"}
        self.assertEqual(got, {"2026-09-25": True,
                               "2026-09-26": False,
                               "2026-09-27": False})
        # 名字本身仍带着（供悬停提示说明"这几天是中秋假期"）
        names = set(i["name"] for i in v["items"] if i["status"] == "holiday")
        self.assertEqual(names, {"中秋节"})

    def test_month_view_fest_day_false_for_non_holidays(self):
        v = model.month_view(2026, 10, today="2026-09-14")
        self.assertFalse(any(i["fest_day"] for i in v["items"]
                             if i["status"] != "holiday"))

    def test_fallback_when_anchor_missing(self):
        # 罕见情况：假期里没有一天能对上节日（数据缺失 / 正日子落在邻月）→
        # 让月内第一天显示名字，总比整个假期一个名字都没有
        years = {"2026": {"holidays": {"国庆节": ["2026-08-30", "2026-08-31"]},
                          "workdays": []}}
        v = model.month_view(2026, 8, today="2026-09-14", years=years)
        got = {i["date"]: i["fest_day"] for i in v["items"] if i["status"] == "holiday"}
        self.assertEqual(got, {"2026-08-30": True, "2026-08-31": False})


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