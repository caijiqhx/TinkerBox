"""JSON 文件读写。

两条铁律：
1. **读**绝不抛异常 —— 文件不存在 / 内容损坏一律退化为默认值，不能让 UI 崩掉。
2. **写**必须原子 —— 先写同目录临时文件，再 os.replace 覆盖，
   避免断电或进程被杀时留下半个文件。

另外提供"有限份数的备份轮转"：覆盖前把原文件留一份，编号越大越旧，
超出上限的直接丢弃 —— 这样备份永远是有界的，不需要用户手工清理。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile


def read_json(path, default=None):
    """读取 JSON。任何失败都返回 default。"""
    try:
        with open(str(path), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (IOError, OSError):
        return default
    except ValueError:          # json.JSONDecodeError 是 ValueError 的子类
        return default


def write_json_atomic(path, data):
    """原子写入 JSON（UTF-8，不转义中文，缩进 2）。"""
    target = str(path)
    directory = os.path.dirname(target)
    if directory:
        os.makedirs(directory, exist_ok=True)

    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=directory or None)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise
    return target


# ---------------------------------------------------------------- 备份轮转


def backup_path(path, index):
    """第 index 份备份的文件名（1 = 最新）。"""
    return "%s.bak.%d" % (str(path), int(index))


def rotate_backup(path, keep):
    """把当前文件轮转成 `<path>.bak.1` … `<path>.bak.<keep>`。

    1 是最新的一份、编号越大越旧，超出 keep 的直接丢弃。
    **必须在写入新内容之前调用** —— 它保存的是"即将被覆盖的那一版"。

    返回实际留存的份数：0 表示原文件不存在，或 keep <= 0（关闭备份）。
    任何失败都只是少一份备份，绝不能让保存本身失败。
    """
    target = str(path)
    try:
        keep = int(keep)
    except (TypeError, ValueError):
        keep = 0
    if keep <= 0 or not os.path.isfile(target):
        return 0

    _remove_quietly(backup_path(target, keep))          # 最老的先丢
    for index in range(keep - 1, 0, -1):
        source = backup_path(target, index)
        if os.path.isfile(source):
            _replace_quietly(source, backup_path(target, index + 1))
    try:
        shutil.copy2(target, backup_path(target, 1))
    except (IOError, OSError):
        return 0
    return 1


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _replace_quietly(source, destination):
    try:
        os.replace(source, destination)
    except OSError:
        pass
