"""服务实例的运行信息与探测。

解决的问题：**重复点图标不要起第二个服务。**

做法：
1. 服务启动后把 {port, pid, instance, started} 写到 <数据目录>/server.json
2. 下次点图标时先读这个文件，再向那个端口请求 /api/identity
3. 返回的身份标识与文件里一致 → 确认是"我自己的服务" → 直接复用，不重复启动

只靠文件不够（进程可能已经死了、文件可能是残留的），所以**文件 + 实际探测**两条一起用。

探测端点 /api/identity 不需要令牌 —— 因为新进程不知道旧进程的令牌。
它只暴露"这里跑着一个 ToolBox 和它的实例标识"，本机任何进程都能读到同样的信息
（server.json 本身就是明文文件），因此不构成额外的信息泄露。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from core import paths
from services import jsonio
from web import APP_TAG

PROBE_TIMEOUT = 1.5
SHUTDOWN_TIMEOUT = 3.0


def _local_opener():
    """一个**显式绕过代理**的 opener。

    目标永远是 127.0.0.1，走代理既没有意义、还会失败 ——
    内网机器上经常设着 http_proxy，若不绕过，实例探测会直接失灵。
    """
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


# ---------------------------------------------------------------- 运行记录


def record_path():
    return paths.server_file()


def read_record():
    """读取运行记录；文件缺失或内容不可信时返回 None。"""
    data = jsonio.read_json(record_path(), None)
    if not isinstance(data, dict):
        return None
    try:
        port = int(data.get("port"))
    except (TypeError, ValueError):
        return None
    if not (1 <= port <= 65535):
        return None
    instance_id = str(data.get("instance") or "")
    if not instance_id:
        return None
    return {
        "port": port,
        "pid": data.get("pid"),
        "instance": instance_id,
        "started": str(data.get("started") or ""),
    }


def write_record(port, instance_id, started):
    payload = {
        "app": APP_TAG,
        "port": int(port),
        "pid": os.getpid(),
        "instance": instance_id,
        "started": started,
    }
    jsonio.write_json_atomic(record_path(), payload)
    return payload


def clear_record():
    try:
        os.remove(str(record_path()))
    except OSError:
        pass


# ---------------------------------------------------------------- 探测


def parse_identity(body_text):
    """从 /api/identity 的响应文本里解析身份信息。

    接口统一返回 {"ok": true, "data": {...}}，这里做一次解包，
    同时兼容直接返回裸对象的情况。不是我们的服务则返回 None。
    """
    try:
        data = json.loads(body_text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    payload = data.get("data")
    if not isinstance(payload, dict):
        payload = data
    if payload.get("app") != APP_TAG:
        return None
    return payload


def probe(port, timeout=PROBE_TIMEOUT):
    """向指定端口请求 /api/identity。不是我们的服务（或连不上）则返回 None。"""
    url = "http://127.0.0.1:%d/api/identity" % (int(port),)
    try:
        with _local_opener().open(url, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except Exception:
        return None
    return parse_identity(body)


def find_running():
    """查找正在运行的自有实例。

    返回 (record, identity)：
      - 找到 → (运行记录, 身份信息)
      - 没找到 → (None, None)
    """
    record = read_record()
    if record is None:
        return None, None

    identity = probe(record["port"])
    if identity is None:
        return None, None
    if str(identity.get("instance") or "") != record["instance"]:
        # 端口上跑着别的东西，或残留记录指向了错误目标
        return None, None
    return record, identity


def request_shutdown(port, instance_id, timeout=SHUTDOWN_TIMEOUT):
    """请求指定实例关闭自己。

    这里用 server.json 里的 instance 值校验，而不是页面令牌 ——
    `stop` 命令在进程外运行，拿不到令牌。两者的信任级别相同
    （能读 server.json 的人本来就能直接结束该进程）。
    """
    url = "http://127.0.0.1:%d/api/shutdown?i=%s" % (
        int(port), urllib.parse.quote(str(instance_id)))
    try:
        request = urllib.request.Request(url, data=b"{}", method="POST")
        request.add_header("Content-Type", "application/json")
        with _local_opener().open(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        return bool(data.get("ok"))
    except Exception:
        return False


def wait_until_stopped(port, attempts=25, interval=0.2):
    """等待服务真正退出（用于 stop 命令给用户一个准确的结果）。"""
    for _ in range(attempts):
        if probe(port) is None:
            return True
        time.sleep(interval)
    return False
