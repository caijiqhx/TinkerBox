"""JSON 文件读写。

两条铁律：
1. **读**绝不抛异常 —— 文件不存在 / 内容损坏一律退化为默认值，不能让 UI 崩掉。
2. **写**必须原子 —— 先写同目录临时文件，再 os.replace 覆盖，
   避免断电或进程被杀时留下半个文件。
"""

from __future__ import annotations

import json
import os
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
