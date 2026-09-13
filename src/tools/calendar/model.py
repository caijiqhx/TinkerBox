"""日历工具 —— 纯数据层。

只负责"给一个日期，说它是节假日 / 调休 / 周末 / 工作日"，以及按月生成视图数据。
**不感知 HTTP 与 HTML**（与 tools/todo 的契约一致）。

数据来源：`tools/calendar/holidays.json`（内置，随程序走）。
- 内置的是国务院已发布的年份安排（目前 2026）。
- 用户可在数据目录放 `holidays.json` 覆盖/补充 —— 内网机器换年份只需
  替换这一个文件，不用重装程序。
- 查询某天：先看内置 + 用户数据里有没有配置，没有则按星期推算（周六/周日 = 休，
  其余 = 工作）。所以无数据的年份也能正常显示，只是没有节假日标注。

返回的状态只有四态：
- "holiday"  法定节假日（如 国庆节），带节日名
- "workday"  调休补班日（周六/周日要上班）
- "weekend"  普通周末（周六/周日，不在节假日配置里）
- "workday"  普通工作日
"""

from __future__ import annotations

import calendar
import datetime
import os

from core import paths
from services import jsonio

# ---------- 农历 ----------
#: 农历 1900-2100 压缩表（社区通用表，与 solarlunar 等实现一致）。
#: 编码：低 4 位 = 闰月（0 表示该年无闰月）；bit4-15 表示 12 个月大小（1=30 天，0=29 天）；
#:       bit16 = 闰月大小（0=29 天，1=30 天）。
_LUNAR_INFO = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,  # 1900-1909
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,  # 1910-1919
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,  # 1920-1929
    0x06566, 0x0d4a0, 0x0ea50, 0x06e95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,  # 1930-1939
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,  # 1940-1949
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5b0, 0x14573, 0x052b0, 0x0a9a8, 0x0e950, 0x06aa0,  # 1950-1959
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,  # 1960-1969
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b6a0, 0x195a6,  # 1970-1979
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,  # 1980-1989
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x05ac0, 0x0ab60, 0x096d5, 0x092e0,  # 1990-1999
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,  # 2000-2009
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,  # 2010-2019
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,  # 2020-2029
    0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,  # 2030-2039
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,  # 2040-2049
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06b20, 0x1a6c4, 0x0aae0,  # 2050-2059
    0x092e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,  # 2060-2069
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,  # 2070-2079
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,  # 2080-2089
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a4d0, 0x0d150, 0x0f252,  # 2090-2099
    0x0d520,                                                                                  # 2100
]

#: 农历月名（索引 0 不用；1=正月 … 12=腊月）
_LUNAR_MONTHS = ("", "正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊")
#: 农历日名的十位（1=十，2=廿）与个位数字
_LUNAR_DAY_TENS = ("初", "十", "廿", "卅")
_LUNAR_DIGITS = ("日", "一", "二", "三", "四", "五", "六", "七", "八", "九")


def _leap_month(ly):
    """农历年份的闰月（0 表示无闰月）。"""
    return _LUNAR_INFO[ly - 1900] & 0xF


def _leap_days(ly):
    """闰月天数（无闰月返回 0）。"""
    if not _leap_month(ly):
        return 0
    return 30 if (_LUNAR_INFO[ly - 1900] & 0x10000) else 29


def _month_days(ly, lm):
    """农历 ly 年 lm 月（非闰月）天数。"""
    return 30 if (_LUNAR_INFO[ly - 1900] & (0x10000 >> lm)) else 29


def _lunar_year_days(ly):
    """农历 ly 年一整年的总天数。"""
    info = _LUNAR_INFO[ly - 1900]
    total = 348
    bit = 0x8000
    while bit > 0x8:
        if info & bit:
            total += 1
        bit >>= 1
    return total + _leap_days(ly)


def _solar2lunar(year, month, day):
    """公历 → 农历 (年, 月, 日, 是否闰月)。越界/非法返回 None。"""
    try:
        days = (datetime.date(year, month, day) - datetime.date(1900, 1, 31)).days
    except ValueError:
        return None
    if days < 0:
        return None

    # 1) 定位农历年：从 1900 起逐年代扣
    ly = 1900
    while ly <= 2100 and days > 0:
        ydays = _lunar_year_days(ly)
        days -= ydays
        ly += 1
    if days < 0:
        days += ydays
        ly -= 1
    if not 1900 <= ly <= 2100:
        return None

    # 2) 定位农历月（闰月插在相应月份之后）
    leap = _leap_month(ly)
    is_leap = False
    lm = 1
    while lm <= 12 and days > 0:
        if leap and lm == leap + 1 and not is_leap:
            lm -= 1
            is_leap = True
            mdays = _leap_days(ly)
        else:
            mdays = _month_days(ly, lm)
        if is_leap and lm == leap + 1:
            is_leap = False
        days -= mdays
        lm += 1
    if days == 0 and leap and lm == leap + 1:
        if is_leap:
            is_leap = False
        else:
            is_leap = True
            lm -= 1
    if days < 0:
        days += mdays
        lm -= 1
    return ly, lm, days + 1, is_leap


def _lunar_day_cn(lda):
    """农历日 → 汉字（初一 … 三十）。"""
    if lda == 10:
        return "初十"
    if lda == 20:
        return "二十"
    if lda == 30:
        return "三十"
    return _LUNAR_DAY_TENS[lda // 10] + _LUNAR_DIGITS[lda % 10]


def lunar_str(day):
    """公历日期（'YYYY-MM-DD'）→ 农历展示文本。

    每月初一显示月名（正月 / 闰二月 …），其余显示日名（初二 / 十五 / 廿九）。
    支持 1900-01-31 ~ 2100-12-31，越界或非法日期返回空串（前端不显示）。
    """
    try:
        y, m, d = (int(x) for x in day.split("-"))
    except (ValueError, AttributeError):
        return ""
    if not (1900 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31):
        return ""
    got = _solar2lunar(y, m, d)
    if got is None:
        return ""
    _lyr, lmo, lda, is_leap = got
    if lda == 1:
        return ("闰" if is_leap else "") + _LUNAR_MONTHS[lmo] + "月"
    return _lunar_day_cn(lda)


#: 内置数据文件（随程序包走）
_BUNDLED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holidays.json")

#: 用户数据目录里的覆盖文件（内网换年份只需替换这个）
USER_FILE = "holidays.json"

#: 业务状态（也是前端渲染的依据）
HOLIDAY = "holiday"      # 法定节假日（带节日名）
ADJUST = "workday"       # 调休补班日（周六/周日上班）
WEEKEND = "weekend"      # 普通周末
WORK = "work"            # 普通工作日


def _load_bundled():
    """读取内置数据；损坏/缺失时返回空结构，绝不抛异常。"""
    raw = jsonio.read_json(_BUNDLED, None)
    if not isinstance(raw, dict):
        return {}
    years = raw.get("years")
    return years if isinstance(years, dict) else {}


def _load_user():
    """读取用户数据目录的覆盖文件；不存在时返回空结构。"""
    path = paths.data_dir() / USER_FILE
    raw = jsonio.read_json(path, None)
    if not isinstance(raw, dict):
        return {}
    years = raw.get("years")
    return years if isinstance(years, dict) else {}


def load_years():
    """合并内置 + 用户数据，用户优先。返回 {年份: {...}}。"""
    merged = {}
    bundled = _load_bundled()
    for year, data in bundled.items():
        merged[year] = data
    for year, data in _load_user().items():
        merged[year] = data
    return merged


def _set_for_day(years, day):
    """返回某天所在的 {节日名: [日期...]} 中的条目，供快速查找。"""
    year = day[:4]
    data = years.get(year) or {}
    holidays = data.get("holidays") if isinstance(data, dict) else None
    if not isinstance(holidays, dict):
        return {}
    return holidays


def day_status(day, years=None):
    """判断单个日期（'YYYY-MM-DD'）的业务状态。

    返回 {"status": <四态之一>, "name": <节日名 or None>}。
    """
    if years is None:
        years = load_years()
    year = day[:4]
    data = years.get(year) or {}

    holidays = data.get("holidays") if isinstance(data, dict) else {}
    if isinstance(holidays, dict):
        for name, days in holidays.items():
            if isinstance(days, list) and day in days:
                return {"status": HOLIDAY, "name": name}

    workdays = data.get("workdays") if isinstance(data, dict) else []
    if isinstance(workdays, list) and day in workdays:
        return {"status": ADJUST, "name": "调休"}

    try:
        date = datetime.date.fromisoformat(day)
    except ValueError:
        return {"status": WORK, "name": None}
    if date.weekday() >= 5:      # 周六(5)/周日(6)
        return {"status": WEEKEND, "name": None}
    return {"status": WORK, "name": None}


def month_view(year, month, today=None, years=None):
    """生成某年某月的整月视图数据（供前端直接渲染）。

    返回：
    {
      "year": int, "month": int,
      "year_month": "2026-09",
      "weekday0": 0,            # 月份第一天是周几（0=周一 … 6=周日）
      "days": 28..31,           # 本月天数
      "today": "YYYY-MM-DD" or null,   # 若该月含今天
      "items": [ {"day": 8, "date": "2026-09-08", "status": "work", "name": null,
                  "lunar": "八月十二"}, ... ],      # lunar：农历文本，空串=不显示
      "overview": {             # 月份概览
        "holidays": 3, "adjusts": 1,
        "holiday_names": [{"name": "中秋节", "days": 3}],
        "holiday_span": [25, 27], "adjust_span": [20],
      }
    }
    """
    if years is None:
        years = load_years()
    try:
        year = int(year)
        month = int(month)
        days_in_month = calendar.monthrange(year, month)[1]
    except (TypeError, ValueError):
        return None
    if not 1 <= month <= 12:
        return None
    if not 1900 <= year <= 2400:
        return None

    first = datetime.date(year, month, 1)
    today_text = today or datetime.date.today().isoformat()

    items = []
    for day in range(1, days_in_month + 1):
        date = datetime.date(year, month, day)
        iso = date.isoformat()
        status = day_status(iso, years)
        items.append({
            "day": day,
            "date": iso,
            "status": status["status"],
            "name": status["name"],
            "lunar": lunar_str(iso),
        })

    # 月份概览：本月节假日 / 调休 数量与跨度（跨月假日两侧都只算本月的天数）
    overview = {
        "holidays": 0, "holiday_names": [], "adjusts": 0,
        "holiday_span": [], "adjust_span": [],
    }
    holiday_days = [i["day"] for i in items if i["status"] == HOLIDAY]
    if holiday_days:
        overview["holidays"] = len(holiday_days)
        _first, _last = holiday_days[0], holiday_days[-1]
        overview["holiday_span"] = [_first, _last]
        counts = {}
        for i in items:
            if i["status"] == HOLIDAY and i["name"]:
                counts[i["name"]] = counts.get(i["name"], 0) + 1
        for nm, cnt in sorted(counts.items(), key=lambda kv: -kv[1]):
            overview["holiday_names"].append({"name": nm, "days": cnt})
    overall = [i["day"] for i in items if i["status"] == ADJUST]
    if overall:
        overview["adjust_span"] = [overall[0], overall[-1]]
        overview["adjusts"] += len(overall)

    return {
        "year": year,
        "month": month,
        "year_month": "%04d-%02d" % (year, month),
        "weekday0": first.weekday(),     # 0=周一
        "days": days_in_month,
        "today": today_text if today_text[:7] == ("%04d-%02d" % (year, month)) else None,
        "items": items,
        "overview": overview,
    }