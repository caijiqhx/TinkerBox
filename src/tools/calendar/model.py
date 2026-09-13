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
      "items": [ {"day": 8, "date": "2026-09-08", "status": "work", "name": null}, ... ]
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
        })

    return {
        "year": year,
        "month": month,
        "year_month": "%04d-%02d" % (year, month),
        "weekday0": first.weekday(),     # 0=周一
        "days": days_in_month,
        "today": today_text if today_text[:7] == ("%04d-%02d" % (year, month)) else None,
        "items": items,
    }