#!/usr/bin/env python3
"""重新生成内置节假日数据 holidays.json。

什么时候跑：国务院办公厅每年 10-11 月发布下一年的放假安排后，跑一次更新内置数据
            （内网机器也可以只替换用户数据目录里的 holidays.json，不必跑本脚本）。

怎么跑：
    python build_holidays.py             # 联网抓 2007 年以来的官方数据（失败时用缓存）
    python build_holidays.py --offline   # 只用缓存（缓存放在系统临时目录）

数据来源
--------
* 2007 起：holiday-cn（github.com/NateScarlet/holiday-cn）—— 该项目每日抓取国务院公告，
  每个年份一个 JSON，带官方通知链接（papers），是目前最可靠的结构化来源。
* 2000-2006：没有结构化数据源，按国务院办公厅历年通知原文手工整理（见 MANUAL 的注释，
  每条都标了文号；这一时期的制度是"春节 / 五一 / 十一 三个黄金周 + 元旦"，没有清明/端午/中秋）。

口径（与项目里原有的 2026 数据逐条比对过，务必保持一致）
------------------------------------------------------------
* 假期段 = 通知给出的**完整放假区间**，含区间内的周末 —— 这样日历上连休是整块着色，
  "休 N 天"也等于连休天数。
* workdays 只放"本该休息却要上班"的**周末**。数据源里 isOffDay=false 还包含另一类
  ——假期过后"恢复正常上班"的日子（例：2020-02-03 周一，疫情延长春节后复工第一天），
  那种不能算调休，否则日历会在普通周一上错标「班」。
* 一律按**日期所属年份**归档。数据源按"文件标题年份"归档（12 月的日期可能来自下一年的
  文件），不转换的话，跨年那几天（如 12/31 属于次年元旦假期）在 12 月的日历里会漏标。
"""
import argparse
import collections
import json
import os
import sys
import tempfile
import urllib.request
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))      # src/ 进 sys.path
from tools.calendar import model                                # noqa: E402

REMOTE = "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/%d.json"
ONLINE_YEARS = range(2007, 2027)                                # 有结构化数据的年份

RENAME = {
    "\u201c\u4e94\u4e00\u201d": "劳动节",                       # “五一”
    "\u201c\u4e94\u4e00\u201d国际劳动节": "劳动节",              # “五一”国际劳动节
    "\u201c\u5341\u4e00\u201d": "国庆节",                        # “十一”
    "抗日战争暨世界反法西斯战争胜利70周年纪念日": "抗战胜利70周年",
}
MERGED_NAMES = {"国庆节、中秋节", "中秋节、国庆节"}              # 国庆与中秋撞车的写法
ORDER = ["元旦", "春节", "清明节", "劳动节", "端午节", "中秋节", "国庆节", "抗战胜利70周年"]


def rng(first, last):
    """闭区间 → 日期列表"""
    out, cur, end = [], date.fromisoformat(first), date.fromisoformat(last)
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


# ---------------------------------------------------------------- 2000-2006：按通知原文手工整理
# 2000  元旦：1999-12-31~2000-01-02 放假（1999-12-31 属上年，不收）；五一 / 国庆为 2000 年通知；
#       春节 2/5-2/11（初一至初七），2/12、2/13 上班（两个独立来源一致）
# 2001  国办发明电〔2001〕1 号（春节 / 五一 / 十一）；元旦据北京市政府办公厅通知
#       "1月1日放假1天，12月30、31日正常公休，1月2日上班"（新华社 / 中新网转载）
# 2002  国务院办公厅 2001 年 12 月通知（元旦 1/1-1/3、春节 2/12-2/18、五一 / 十一各 7 天）
# 2003  国办发明电〔2002〕27 号；※ 当年五一因非典实际执行有调整，此处按通知收录 5/1-5/7
# 2004  国办发明电〔2003〕53 号
# 2005  国办发明电〔2004〕52 号
# 2006  国办发明电〔2005〕35 号
MANUAL = {
    "2000": {
        "holidays": {"元旦": ["2000-01-01", "2000-01-02", "2000-12-30", "2000-12-31"],
                     "春节": rng("2000-02-05", "2000-02-11"),
                     "劳动节": rng("2000-05-01", "2000-05-07"),
                     "国庆节": rng("2000-10-01", "2000-10-07")},
        "workdays": ["2000-02-12", "2000-02-13", "2000-04-29", "2000-04-30",
                     "2000-09-30", "2000-10-08"],
    },
    "2001": {
        "holidays": {"元旦": ["2001-01-01"],
                     "春节": rng("2001-01-24", "2001-01-30"),
                     "劳动节": rng("2001-05-01", "2001-05-07"),
                     "国庆节": rng("2001-10-01", "2001-10-07")},
        "workdays": ["2001-01-20", "2001-01-21", "2001-04-28", "2001-04-29",
                     "2001-09-29", "2001-09-30", "2001-12-29", "2001-12-30"],
    },
    "2002": {
        "holidays": {"元旦": rng("2002-01-01", "2002-01-03"),
                     "春节": rng("2002-02-12", "2002-02-18"),
                     "劳动节": rng("2002-05-01", "2002-05-07"),
                     "国庆节": rng("2002-10-01", "2002-10-07")},
        "workdays": ["2002-02-09", "2002-02-10", "2002-04-27", "2002-04-28",
                     "2002-09-28", "2002-09-29"],
    },
    "2003": {
        "holidays": {"元旦": ["2003-01-01"],
                     "春节": rng("2003-02-01", "2003-02-07"),
                     "劳动节": rng("2003-05-01", "2003-05-07"),
                     "国庆节": rng("2003-10-01", "2003-10-07")},
        "workdays": ["2003-02-08", "2003-02-09", "2003-04-26", "2003-04-27",
                     "2003-09-27", "2003-09-28"],
    },
    "2004": {
        "holidays": {"元旦": ["2004-01-01"],
                     "春节": rng("2004-01-22", "2004-01-28"),
                     "劳动节": rng("2004-05-01", "2004-05-07"),
                     "国庆节": rng("2004-10-01", "2004-10-07")},
        "workdays": ["2004-01-17", "2004-01-18", "2004-05-08", "2004-05-09",
                     "2004-10-09", "2004-10-10"],
    },
    "2005": {
        "holidays": {"元旦": rng("2005-01-01", "2005-01-03"),
                     "春节": rng("2005-02-09", "2005-02-15"),
                     "劳动节": rng("2005-05-01", "2005-05-07"),
                     "国庆节": rng("2005-10-01", "2005-10-07")},
        "workdays": ["2005-02-05", "2005-02-06", "2005-04-30", "2005-05-08",
                     "2005-10-08", "2005-10-09", "2005-12-31"],
    },
    "2006": {
        "holidays": {"元旦": rng("2006-01-01", "2006-01-03"),
                     "春节": rng("2006-01-29", "2006-02-04"),
                     "劳动节": rng("2006-05-01", "2006-05-07"),
                     "国庆节": rng("2006-10-01", "2006-10-07")},
        "workdays": ["2006-01-28", "2006-02-05", "2006-04-29", "2006-04-30",
                     "2006-09-30", "2006-10-08", "2006-12-30", "2006-12-31"],
    },
}


def _opener():
    """绕过 http_proxy：内网机器常设代理，本机直连会被劫持（这个坑踩过）"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(year, cache_dir, offline=False):
    path = os.path.join(cache_dir, "%d.json" % year)
    if os.path.exists(path) and os.path.getsize(path) > 200:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    if offline:
        raise SystemExit("离线模式但缺缓存：%s" % path)
    url = REMOTE % year
    with _opener().open(url, timeout=30) as resp:
        blob = resp.read()
    data = json.loads(blob.decode("utf-8"))
    with open(path, "wb") as handle:
        handle.write(blob)
    print("  已下载 %d（%d 条）" % (year, len(data.get("days", []))))
    return data


def build_online(cache_dir, offline):
    raw_off, raw_work = [], set()
    for year in ONLINE_YEARS:
        for item in fetch(year, cache_dir, offline)["days"]:
            if item["isOffDay"]:
                raw_off.append((item["date"], item["name"]))
            else:
                raw_work.add(item["date"])
    off_dates = dict(raw_off)

    def is_off_day(iso):
        if iso in raw_work:
            return False
        if iso in off_dates:
            return True
        return date.fromisoformat(iso).weekday() >= 5

    def expand(days, year):
        """扩成"极大连续非工作日段"（连休里的周末也算），并裁掉越界年份"""
        out = set()
        for d in days:
            if not is_off_day(d):
                continue
            cur = end = date.fromisoformat(d)
            while is_off_day((cur - timedelta(days=1)).isoformat()):
                cur -= timedelta(days=1)
            while is_off_day((end + timedelta(days=1)).isoformat()):
                end += timedelta(days=1)
            x = cur
            while x <= end:
                if x.isoformat()[:4] == year:
                    out.add(x.isoformat())
                x += timedelta(days=1)
        return sorted(out)

    per_year = collections.defaultdict(lambda: {"off": collections.defaultdict(list), "work": []})
    no_expand = set()
    for iso, name in raw_off:
        year = iso[:4]
        if name in MERGED_NAMES:
            if model.lunar_festival(iso) == "中秋":
                nm = "中秋节"                      # 撞车年：中秋只占当天，否则会把整个国庆段吞掉
                no_expand.add((year, nm))
            else:
                nm = "国庆节"
        else:
            nm = RENAME.get(name, name)
        per_year[year]["off"][nm].append(iso)
    for iso in raw_work:
        per_year[iso[:4]]["work"].append(iso)

    result = {}
    for year in sorted(per_year):
        entry = per_year[year]
        holidays = {}
        for nm, days in entry["off"].items():
            seg = sorted(set(days)) if (year, nm) in no_expand else expand(days, year)
            if seg:
                holidays[nm] = seg
        ordered = {}
        for nm in ORDER:
            if nm in holidays:
                ordered[nm] = holidays[nm]
        for nm in holidays:
            if nm not in ordered:
                ordered[nm] = holidays[nm]
        item = {"holidays": ordered}
        workdays = sorted(d for d in set(entry["work"])
                          if date.fromisoformat(d).weekday() >= 5)
        if workdays:
            item["workdays"] = workdays
        if ordered or workdays:
            result[year] = item
    return result


def merge(online):
    result = {}
    for year, item in MANUAL.items():
        result[year] = {"holidays": dict(item["holidays"]), "workdays": list(item["workdays"])}
    for year, item in online.items():
        cur = result.setdefault(year, {})
        cur.setdefault("holidays", {}).update(item.get("holidays", {}))
        wl = cur.setdefault("workdays", [])
        for d in item.get("workdays", []):
            if d not in wl:
                wl.append(d)
        wl.sort()
    return result


def check(data):
    """自检：调休上班日必须是周末、不能跨年份、不能与放假日冲突"""
    problems = []
    for year, item in sorted(data.items()):
        work = set(item.get("workdays", []))
        for d in work:
            if date.fromisoformat(d).weekday() < 5:
                problems.append("%s 的调休上班日是工作日：%s" % (year, d))
            if d[:4] != year:
                problems.append("%s 里混入了别的年份：%s" % (year, d))
        for nm, days in sorted(item["holidays"].items()):
            for d in days:
                if d[:4] != year:
                    problems.append("%s/%s 混入别的年份：%s" % (year, nm, d))
                if d in work:
                    problems.append("%s 的 %s 与调休上班日冲突：%s" % (year, nm, d))
    return problems


def main():
    parser = argparse.ArgumentParser(description="重新生成内置节假日数据")
    parser.add_argument("--offline", action="store_true", help="只用缓存，不联网")
    parser.add_argument("--out", default=os.path.join(HERE, "holidays.json"))
    args = parser.parse_args()

    cache = os.path.join(tempfile.gettempdir(), "toolbox-holiday-cn")
    os.makedirs(cache, exist_ok=True)
    print("缓存目录：%s" % cache)

    data = merge(build_online(cache, args.offline))
    problems = check(data)
    if problems:
        for line in problems:
            print("✗ %s" % line)
        raise SystemExit("自检未通过，未写入文件")

    years = collections.OrderedDict((y, data[y]) for y in sorted(data))
    payload = collections.OrderedDict()
    payload["version"] = 1
    payload["source"] = ("2007-%d：holiday-cn（github.com/NateScarlet/holiday-cn，抓取国务院公告）；"
                         "2000-2006：按国务院办公厅历年通知原文整理（见 build_holidays.py 的 MANUAL）"
                         % max(ONLINE_YEARS))
    payload["note"] = ("按「日期所属年份」归档：12 月底若属于下一年的安排（如元旦假期跨年），仍归本年，"
                       "这样跨年那几天在 12 月的日历里也能正确标出。"
                       "2003 年五一因非典实际执行有调整，此处按当年通知收录（5/1-5/7）。")
    payload["years"] = years

    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("已写入 %s（%d 年，%.1f KB）"
          % (args.out, len(years), os.path.getsize(args.out) / 1024.0))


if __name__ == "__main__":
    main()
