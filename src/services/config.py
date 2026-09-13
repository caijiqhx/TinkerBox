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

    # ---- 服务生命周期 ----
    # 固定端口：因为浏览器书签里含端口，随机端口会让书签失效。
    # 端口被占用时不会静默换端口，而是明确报错。
    "port": 8765,
    # True = 关掉浏览器窗口后服务继续驻留（一天点一次 run 即可）
    # False = 回到"关窗口即退出"的老行为
    "keep_alive": True,
    # 连续这么多小时没有任何请求就自动退出，0 = 不限制。
    # 纯粹是"忘了关"的兜底；正常使用不会触发。
    "idle_exit_hours": 12,

    # 心跳（仅在 keep_alive = False 时用于判断窗口是否已关闭）。
    # 超时值必须足够大 —— 浏览器会把后台标签页的定时器节流到约每分钟一次。
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
