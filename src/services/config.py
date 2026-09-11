"""全局配置。

存储位置：<数据目录>/config.json
读取时与默认值合并，因此新增配置项不会让旧配置文件失效。
"""

from __future__ import annotations

from core import paths
from services import jsonio

DEFAULTS = {
    "ui": "web",                 # web | cli | none
    "theme": "auto",             # light | dark | auto（跟随系统）
    "browser_path": "",          # 指定浏览器可执行文件；空 = 自动探测
    "window_size": "1200,800",   # --app 窗口尺寸
    # 退出机制：① 页面关闭时 sendBeacon 到 /api/bye，立即退出（主路径）
    #           ② 心跳超时兜底。超时值必须足够大 —— 浏览器会把后台标签页的
    #              定时器节流到约每分钟一次，设太小会导致窗口最小化时误退出。
    "ping_interval": 15,
    "ping_timeout": 90,
}

_cache = None


def _path():
    return paths.config_file()


def load():
    global _cache
    if _cache is None:
        data = jsonio.read_json(_path(), {})
        if not isinstance(data, dict):
            data = {}
        merged = dict(DEFAULTS)
        merged.update(data)
        _cache = merged
    return _cache


def reload():
    global _cache
    _cache = None
    return load()


def get(key, default=None):
    value = load().get(key, DEFAULTS.get(key, default))
    return value


def set_value(key, value):
    cfg = load()
    cfg[key] = value
    jsonio.write_json_atomic(_path(), cfg)
    return cfg
