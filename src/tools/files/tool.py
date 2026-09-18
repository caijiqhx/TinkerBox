"""文件浏览工具：action 定义。

这一层**完全不感知 HTTP 和 HTML**，与 tools/todo、tools/calendar 契约一致。

**唯一的边界**在 `guard.resolve`：所有被访问的路径都必须落在用户自己添加过的
位置之内，且不能是伪文件系统。任何 action 都不许绕过它。

提供的 action：
- `info`         `{}`                              位置清单 + 常见位置快捷入口
- `add_root`     `{path}`                          添加一个可浏览位置
- `remove_root`  `{path}`                          移除一个位置
- `list`         `{path, sort, desc, keyword, show_hidden}`  列目录（只读）
- `open`         `{path}`                          用系统默认程序打开（白名单）
- `reveal`       `{path}`                          在系统文件管理器里打开 / 定位
"""

from __future__ import annotations

import os

from core.errors import ToolError
from core.tool import Tool, ToolMeta
from services import platform

from tools.files import guard, model, store


def _os_error_text(exc, fallback):
    """OSError 的说明文本。

    ⚠️ `strerror` **经常是空的**（只有 args[0] 的异常、或某些带文件名的错误），
    直接用它会让所有失败都退化成同一句"无法读取属性"，把真正的原因丢掉 ——
    所以它为空时改用 `str(exc)`。
    """
    text = getattr(exc, "strerror", None) or ""
    if not text:
        text = str(exc).strip()
    return text or fallback


class FilesTool(Tool):
    meta = ToolMeta(
        tid="files",
        name="文件浏览",
        desc="查看目录里的文件信息。位置由你自己指定，只读、不改动任何文件。",
        icon="🗂",
        icon_html='<svg viewBox="0 0 16 16" class="ic" width="16" height="16" fill="none" '
                  'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
                  'stroke-linejoin="round"><path d="M1.9 4.3h4.2l1.3 1.7h6.7v6.1a1 1 0 0 1-1 1'
                  'H2.9a1 1 0 0 1-1-1z"/></svg>',
        order=30,
    )

    def actions(self):
        return {
            "info": self.act_info,
            "add_root": self.act_add_root,
            "remove_root": self.act_remove_root,
            "list": self.act_list,
            "open": self.act_open,
            "reveal": self.act_reveal,
        }

    # ------------------------------------------------------------------
    # 位置管理
    # ------------------------------------------------------------------
    def act_info(self, payload):
        """位置清单 + "可以一键添加"的常见位置。

        常见位置里**已经添加过的就不再出现** —— 同一个目录给两个入口没有意义。
        首次使用时列表是空的，界面会引导用户从这些快捷入口添加，或者手输路径。
        """
        data = store.load()
        seen = set(item["path"] for item in data["roots"])
        seen_key = set(guard.key(item["path"]) for item in data["roots"])

        quick = []
        for group in (platform.home_dirs(), platform.volume_roots()):
            for item in group:
                if item["path"] in seen or guard.key(item["path"]) in seen_key:
                    continue
                seen.add(item["path"])
                seen_key.add(guard.key(item["path"]))
                quick.append({"label": item["label"], "path": item["path"]})

        return {
            "roots": data["roots"],
            "quick": quick,
            "last": data["last"],
            # 前端比较路径时要跟后端同一口径（Windows 不区分大小写、Linux 区分）
            "case_sensitive": platform.is_case_sensitive(),
            "store": store.path_text(),
        }

    def act_add_root(self, payload):
        raw = str(payload.get("path") or "").strip()
        if not raw:
            raise ToolError("请提供一个文件夹路径")

        target = guard.real(raw)
        if not os.path.isdir(target):
            raise ToolError("不是一个存在的文件夹：%s" % (guard.normalize(raw) or raw,))
        reason = guard.pseudo_reason(target)
        if reason:
            raise ToolError(reason)

        data = store.load()
        known = set(guard.key(item["path"]) for item in data["roots"])
        if guard.key(target) not in known:
            data["roots"].append({"path": target, "label": store.default_label(target)})
            store.save(data)
        return {"roots": store.load()["roots"], "added": target}

    def act_remove_root(self, payload):
        raw = str(payload.get("path") or "").strip()
        if not raw:
            raise ToolError("请提供一个位置路径")
        target = guard.key(guard.real(raw))

        data = store.load()
        kept = [item for item in data["roots"] if guard.key(item["path"]) != target]
        if len(kept) == len(data["roots"]):
            raise ToolError("这个位置不在列表里")

        data["roots"] = kept
        if guard.key(data.get("last")) == target:
            data["last"] = ""
        store.save(data)
        return {"roots": store.load()["roots"]}

    # ------------------------------------------------------------------
    # 列目录
    # ------------------------------------------------------------------
    def act_list(self, payload):
        """列出一个目录的内容（**只读**，不返回任何文件内容）。"""
        data = store.load()
        roots = [item["path"] for item in data["roots"]]

        target, reason = guard.resolve(payload.get("path"), roots, kind="dir")
        if reason:
            raise ToolError(reason)

        keyword = str(payload.get("keyword") or "").strip().lower()
        show_hidden = bool(payload.get("show_hidden"))
        desc = bool(payload.get("desc"))
        sort_key = str(payload.get("sort") or "name")
        if sort_key not in model.SORTS:
            sort_key = "name"

        try:
            entries = list(os.scandir(target))
        except OSError as exc:
            raise ToolError("无法读取该目录：%s" % (_os_error_text(exc, "未知原因"),))

        total, hidden, matched = 0, 0, []
        for entry in entries:
            if not show_hidden and entry.name.startswith("."):
                hidden += 1
                continue
            total += 1
            if keyword and keyword not in entry.name.lower():
                continue
            matched.append(entry)

        if sort_key == "name":
            # 按名字排序不需要读元信息 —— 先排序再截断，大目录里省掉几万次 stat
            matched.sort(key=lambda item: item.name.lower(), reverse=desc)
            items = [self._entry(item, roots) for item in matched[:model.LIST_LIMIT]]
            items = model.dirs_first(items)
        else:
            # 按大小 / 时间排序必须先有元信息，只能全量算完再截断
            items = [self._entry(item, roots) for item in matched]
            items = model.sort_items(items, sort_key, desc)[:model.LIST_LIMIT]

        note = ""
        if len(matched) > model.LIST_LIMIT:
            note = "条目较多，只列出前 %d 条。用筛选缩小范围可看全。" % (model.LIST_LIMIT,)

        root_hit = guard.pick(target, roots)[1]
        self._remember_last(data, target)

        return {
            "path": target,
            "root": root_hit,
            "crumbs": self._crumbs(target, root_hit),
            "parent": self._parent(target, root_hit),
            "items": items,
            "total": total,                 # 不含隐藏项（除非打开了显示隐藏）
            "matched": len(matched),        # 关键词过滤之后
            "shown": len(items),            # 实际返回
            "truncated": len(matched) > len(items),
            "hidden": hidden,
            "limit": model.LIST_LIMIT,
            "sort": sort_key,
            "desc": desc,
            "show_hidden": show_hidden,
            "keyword": keyword,
            "note": note,
            "store": store.path_text(),
        }

    def _entry(self, entry, roots):
        """把一个目录项转成前端要的结构。

        **任何单项失败都不能影响整个目录**：拿不到元信息就留空并记下原因，
        条目照样列出来。
        """
        try:
            is_link = entry.is_symlink()
        except OSError:
            is_link = False
        try:
            is_dir = entry.is_dir()
        except OSError:
            is_dir = False

        info, error = None, ""
        try:
            info = entry.stat()
        except OSError as exc:
            error = _os_error_text(exc, "无法读取属性")

        # 指向已授权范围之外的符号链接：列出来（用户得知道有这么个东西），
        # 但标记成不可进入、不可打开
        escapes = False
        if is_link:
            escapes = not guard.pick(entry.path, roots)[0]

        return model.make_entry(entry.name, entry.path, is_dir, is_link,
                                info, error, escapes)

    def _crumbs(self, target, root):
        """面包屑：从所在位置起、逐段到当前目录。每段都带可回跳的路径。"""
        root = root or target
        crumbs = [{"label": store.default_label(root), "path": root}]
        if guard.key(target) == guard.key(root):
            return crumbs

        relative = target[len(root):].lstrip("\\/") if len(target) > len(root) else ""
        current = root
        for part in [piece for piece in relative.replace("\\", "/").split("/") if piece]:
            current = os.path.join(current, part)
            crumbs.append({"label": part, "path": current})
        return crumbs

    def _parent(self, target, root):
        """上级目录。已经在位置顶层时返回空串 —— **不能再往上**，那是边界。"""
        root = root or target
        if guard.key(target) == guard.key(root):
            return ""
        parent = os.path.dirname(target.rstrip("\\/")) or target
        if not guard.within(guard.real(parent), guard.real(root)):
            return ""
        return parent

    def _remember_last(self, data, target):
        """记下这次浏览的目录，下次进工具直接回到这里。

        写的是几十字节的小文件，且只在目录真的变了才写。记不住位置不是错误，
        **绝不能因此让列目录失败**。
        """
        if guard.key(data.get("last")) == guard.key(target):
            return
        try:
            data["last"] = target
            store.save(data)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # 交给系统
    # ------------------------------------------------------------------
    def act_open(self, payload):
        """用系统默认程序打开一个文件。

        ⚠️ 这个动作让服务进程去启动本机程序，所以两道闸门缺一不可：
        ① 路径必须在已添加的位置之内（`guard.resolve`）；
        ② 扩展名必须在白名单里（`model.can_open`）—— 脚本与可执行体一律拒绝，
           否则等于把"任意代码执行"暴露给接口。
        """
        roots = [item["path"] for item in store.load()["roots"]]
        target, reason = guard.resolve(payload.get("path"), roots, kind="file")
        if reason:
            raise ToolError(reason)

        if not model.can_open(target):
            ext = model.extension(target)
            raise ToolError(
                "出于安全考虑，不能直接打开%s文件。可以改用「在文件管理器中打开」。"
                % ((" .%s " % ext) if ext else "无扩展名的",)
            )

        if not platform.open_with_default(target):
            raise ToolError("没能调起系统默认程序，可以改用「在文件管理器中打开」")
        return {"opened": True, "path": target}

    def act_reveal(self, payload):
        """交给系统文件管理器：目录 → 打开它；文件 → 定位并选中它。

        这是给白名单之外的文件留的**出口** —— 所以任何扩展名都可以走这里，
        不受 `OPENABLE_EXTS` 限制。
        """
        roots = [item["path"] for item in store.load()["roots"]]
        target, reason = guard.resolve(payload.get("path"), roots)
        if reason:
            raise ToolError(reason)

        if os.path.isdir(target):
            ok = platform.open_with_default(target)       # 目录 → 文件管理器打开它
        else:
            ok = platform.open_in_file_manager(target)    # 文件 → 定位并选中
        if not ok:
            raise ToolError("没能调起系统文件管理器")
        return {"revealed": True, "path": target}

    # ------------------------------------------------------------------
    # 命令行
    # ------------------------------------------------------------------
    def cli(self, argv):
        raise ToolError("文件浏览暂不支持命令行调用，请在 Web 界面使用")
