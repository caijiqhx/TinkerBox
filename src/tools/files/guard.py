"""文件浏览的路径安全策略。

这是整个工具**唯一的边界**所在 —— 任何要访问的路径都必须先过这里。
它做三件事：

1. **不越出已授权位置** —— 请求路径 realpath 之后必须落在用户显式添加过的
   目录之内。符号链接因此自动受限：一个指向范围外的链接，解析后就不在
   范围内了，不需要单独处理链接类型。
2. **拒绝伪文件系统** —— `/proc`、`/sys`、`/dev` 列目录要么毫无意义，要么会
   把请求挂死（读 `/dev/zero` 永不返回）。
3. **统一成绝对真实路径** —— 靠 normpath + realpath 消掉 `..`、重复斜杠、
   符号链接造成的"同一条路径多种写法"。**否则前缀比较能被轻易绕过**：
   `/home/u/x/../../etc` 这种字符串看起来在根内，实际不是。

为什么要有"边界"（用户本来也能手输任意路径）：它约束的是**浏览过程**，
防止从某个链接或 `..` 悄悄滑出用户选定的范围；同时它也是将来做文件批处理
（要写文件）的必要基础。
"""

from __future__ import annotations

import os

from services import platform


def key(path):
    """比较用的键：Windows 上路径大小写不敏感，必须按同一口径比较。

    否则 `C:\\Users\\qhx` 与 `c:\\users\\qhx` 会被判成两个不同位置，
    同一个目录能被添加两次、边界比较也会失效。
    """
    text = str(path)
    return text if platform.is_case_sensitive() else text.lower()


def normalize(path):
    """规范化成绝对路径（展开 `~`，不做存在性检查）。"""
    text = str(path or "").strip()
    if not text:
        return ""
    try:
        return os.path.normpath(os.path.abspath(os.path.expanduser(text)))
    except (OSError, ValueError):
        return ""


def real(path):
    """解析符号链接后的真实路径（路径不存在时退回规范化结果）。"""
    target = normalize(path)
    if not target:
        return ""
    try:
        return os.path.realpath(target)
    except (OSError, ValueError):
        return target


def within(path, root):
    """path 是否等于 root 或位于 root 之内。两者都应是已 realpath 的路径。"""
    path_key, root_key = key(path), key(root)
    if not path_key or not root_key:
        return False
    if path_key == root_key:
        return True
    if not root_key.endswith(os.sep):
        root_key += os.sep
    return path_key.startswith(root_key)


def pseudo_reason(path):
    """落在伪文件系统里就返回原因文本，否则返回空串。"""
    target = real(path)
    for prefix in platform.pseudo_filesystems():
        if within(target, real(prefix)):
            return "不支持浏览系统目录：%s" % (prefix,)
    return ""


def pick(path, roots):
    """在已授权位置里找能容纳 path 的那个。

    返回 `(真实路径, 命中的位置)`；不合法时返回 `("", "")`。
    """
    if not path or not roots:
        return "", ""
    target = real(path)
    for root in roots:
        root_real = real(root)
        if root_real and within(target, root_real):
            return target, root_real
    return "", ""


def resolve(path, roots, kind=None):
    """完整校验，返回 `(真实路径, 错误文本)`；错误文本非空表示不可用。

    `kind`：None 不检查 / `"dir"` 要求是目录 / `"file"` 要求是普通文件。
    """
    if not str(path or "").strip():
        return "", "缺少路径"
    if not roots:
        return "", "还没有添加任何位置，请先添加一个文件夹"

    reason = pseudo_reason(path)
    if reason:
        return "", reason

    target, _root = pick(path, roots)
    if not target:
        return "", "该路径不在已添加的位置之内"

    if not os.path.exists(target):
        return "", "路径不存在：%s" % (target,)

    if kind == "dir" and not os.path.isdir(target):
        return "", "不是文件夹：%s" % (target,)
    if kind == "file" and not os.path.isfile(target):
        # 目录、设备节点、管道一律不当普通文件对待
        return "", "不是普通文件：%s" % (target,)

    return target, ""
