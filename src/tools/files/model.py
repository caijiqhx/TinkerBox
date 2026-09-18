"""文件浏览的展示逻辑：条目结构、排序、格式化、"能不能打开"的判定。

纯数据加工 —— 不做路径安全判断（在 `guard.py`），不碰持久化（`store.py`），
也不直接读目录（在 `tool.py`）。
"""

from __future__ import annotations

import datetime
import os

#: 允许"用系统默认程序打开"的扩展名。**白名单**：未列出的一律拒绝。
#:
#: 只放"数据型"文件。可执行体与脚本 —— `.sh` / `.desktop` / `.bat` / `.cmd` /
#: `.exe` / `.lnk` / `.ps1` / `.vbs` / `.jar` … —— **一律不在其中**：这个动作由
#: 接口触发，能打开脚本就等于把"任意代码执行"暴露给了接口。未列入的文件
#: 仍然可以在文件管理器里打开（工具提供了那个出口），所以不会把人堵死。
#:
#: `.wps` / `.et` / `.dps` 是**故意**放进去的：它们正是"交给系统里的 WPS 打开"。
OPENABLE_EXTS = frozenset([
    # 文档
    "doc", "docx", "docm", "dot", "dotx", "rtf", "odt", "pdf", "tex",
    "xls", "xlsx", "xlsm", "xlt", "xltx", "csv", "tsv", "ods",
    "ppt", "pptx", "pptm", "pot", "potx", "odp",
    "wps", "et", "dps",
    # 纯文本与配置
    "txt", "md", "markdown", "log", "json", "xml", "yaml", "yml",
    "ini", "cfg", "conf",
    # 图片
    "png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "ico", "tif", "tiff", "heic",
    # 音视频
    "mp3", "wav", "flac", "m4a", "aac", "ogg", "opus",
    "mp4", "mkv", "avi", "mov", "wmv", "webm", "m4v",
    # 压缩包与电子书
    "zip", "7z", "rar", "tar", "gz", "bz2", "xz", "epub", "mobi",
    # 网页：交给默认浏览器打开本地文件。file:// 页面拿不到本服务的令牌，
    # 也没有同源关系，因此不构成回打接口的风险。
    "html", "htm",
])

#: 单次返回的最大条目数。目录里几万个文件时一次全给前端会直接卡死。
LIST_LIMIT = 2000

#: 支持的排序键
SORTS = ("name", "size", "time")


def extension(name):
    """扩展名（小写、不含点）。没有扩展名、或形如 `.bashrc` 的隐藏文件返回空串。"""
    base = os.path.basename(str(name or ""))
    dot = base.rfind(".")
    if dot <= 0:
        return ""
    return base[dot + 1:].lower()


def can_open(path):
    """是否允许"用系统默认程序打开"。"""
    return extension(path) in OPENABLE_EXTS


def human_size(size):
    """字节数 → 人看的文本。`None`（目录或读不到）返回空串。"""
    if size is None:
        return ""
    try:
        size = int(size)
    except (TypeError, ValueError):
        return ""
    if size < 0:
        return ""
    if size < 1024:
        return "%d B" % size
    value = float(size)
    unit = "KB"
    for unit in ("KB", "MB", "GB", "TB", "PB"):
        value /= 1024.0
        if value < 1024 or unit == "PB":
            break
    if value < 10:
        return "%.2f %s" % (value, unit)
    if value < 100:
        return "%.1f %s" % (value, unit)
    return "%.0f %s" % (value, unit)


def stamp_text(mtime):
    """时间戳 → `YYYY-MM-DD HH:MM`；拿到坏值返回空串而不抛异常。"""
    if mtime is None:
        return ""
    try:
        moment = datetime.datetime.fromtimestamp(float(mtime))
    except (TypeError, ValueError, OSError, OverflowError):
        return ""
    return moment.strftime("%Y-%m-%d %H:%M")


def clean_text(value):
    """把可能含"代理转义"的文件名转成能安全 JSON 序列化的文本。

    返回 `(文本, 是否干净)`。

    Linux 的文件名允许任意字节，Python 用 surrogateescape 把它解成含
    U+DC80~U+DCFF 的字符串 —— 这类字符串 `json.dumps` 会直接抛
    UnicodeEncodeError。**一个名字奇怪的文件就能让整个目录列不出来**，
    所以必须在这里降级成"能显示、但可能带问号"的文本，并告诉调用方它不可回传。
    """
    text = str(value)
    try:
        text.encode("utf-8")
        return text, True
    except UnicodeEncodeError:
        repaired = text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
        return repaired, False


def make_entry(name, path, is_dir, is_link, stat_result=None,
               stat_error="", link_escapes=False):
    """构造交给前端的条目结构。

    `stat_result` 为 None 表示拿不到元信息（无权限、恰好被删掉…）。这时**仍然
    把条目列出来** —— "有个文件的属性读不到"比"整个目录打不开"有用得多。

    `link_escapes` 表示这是指向已授权范围之外的符号链接：照样列出来（用户得
    知道有这么个东西），但标记成不可进入、不可打开。
    """
    safe_name, name_clean = clean_text(name)
    safe_path, path_clean = clean_text(path)
    usable = name_clean and path_clean and not link_escapes

    size, mtime = None, None
    if stat_result is not None:
        try:
            if not is_dir:
                size = int(stat_result.st_size)
            mtime = float(stat_result.st_mtime)
        except (TypeError, ValueError, OverflowError):
            size, mtime = None, None

    ext = extension(name)
    return {
        "name": safe_name,
        "path": safe_path if usable else "",
        "dir": bool(is_dir),
        "link": bool(is_link),
        "escapes": bool(link_escapes),
        "size": size,
        "size_text": human_size(size),
        "mtime": mtime,
        "mtime_text": stamp_text(mtime),
        "ext": ext,
        "openable": (not is_dir) and (ext in OPENABLE_EXTS) and usable,
        "broken": not name_clean,
        "error": stat_error,
    }


def dirs_first(items):
    """把目录排到前面（稳定排序，组内保持原有顺序）。"""
    return sorted(items, key=lambda item: 0 if item.get("dir") else 1)


def sort_items(items, sort_key="name", desc=False):
    """排序。**目录永远排在前面** —— 跟文件管理器一致，翻目录时更可预期。

    实现是"先按主键排、再稳定地按目录分组"，所以目录内部也保持主键顺序。
    """
    if sort_key not in SORTS:
        sort_key = "name"

    if sort_key == "size":
        key_func = lambda item: item.get("size") if item.get("size") is not None else -1
    elif sort_key == "time":
        key_func = lambda item: item.get("mtime") if item.get("mtime") is not None else -1.0
    else:
        key_func = lambda item: str(item.get("name") or "").lower()

    return dirs_first(sorted(items, key=key_func, reverse=bool(desc)))
