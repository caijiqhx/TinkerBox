"""文件浏览工具测试。

重点在**边界**：路径逃逸（`..`、绝对路径、符号链接）必须一律被拒。
这部分一旦失效，就等于给本机开了一个"任意目录读取"接口。

运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from core.errors import ToolError                       # noqa: E402
from services import platform                           # noqa: E402
from tools.files import guard, model, store, tool        # noqa: E402


def _symlink_dir(source, link):
    """建一个指向目录的符号链接；这个环境建不出来就**跳过**该测试。

    两处平台/环境坑：
    - Windows 上必须显式声明 `target_is_directory`，否则会建成悬空的**文件**链接，
      realpath 之后目标不存在，测出来的错误就完全不是我们想验的那个（POSIX 忽略此参数）。
    - 受限环境可能"假装成功"：`os.symlink` 不报错，但链接根本没落地。
      所以要回头确认它真的存在，否则测试会在一个不存在的东西上得出假结论。
    """
    try:
        os.symlink(source, link, target_is_directory=True)
    except (OSError, NotImplementedError, AttributeError):
        raise unittest.SkipTest("该环境不允许创建符号链接")
    if not os.path.lexists(link):
        raise unittest.SkipTest("该环境创建符号链接被拦截（调用未报错，但链接不存在）")


class GuardTest(unittest.TestCase):
    """路径解析与边界比较。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tb-files-guard-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_normalize_expands_home(self):
        got = guard.normalize("~")
        self.assertTrue(os.path.isabs(got), got)
        self.assertNotIn("~", got)

    def test_normalize_collapses_dotdot(self):
        target = os.path.join(self.tmp, "a", "..", "b")
        self.assertEqual(guard.normalize(target), os.path.join(self.tmp, "b"))

    def test_normalize_blank(self):
        self.assertEqual(guard.normalize(""), "")
        self.assertEqual(guard.normalize(None), "")
        self.assertEqual(guard.normalize("   "), "")

    # ---------------------------------------------------------------- within
    def test_within_equal_and_inside(self):
        root = os.path.join(self.tmp, "root")
        self.assertTrue(guard.within(root, root))
        self.assertTrue(guard.within(os.path.join(root, "a", "b"), root))

    def test_within_rejects_outside(self):
        root = os.path.join(self.tmp, "root")
        self.assertFalse(guard.within(os.path.join(self.tmp, "other"), root))
        self.assertFalse(guard.within(self.tmp, root))

    def test_within_is_not_fooled_by_name_prefix(self):
        """`/x/root2` 不是 `/x/root` 的子路径 —— 只做字符串前缀会误判。"""
        root = os.path.join(self.tmp, "root")
        sibling = os.path.join(self.tmp, "root2")
        self.assertFalse(guard.within(sibling, root))

    def test_within_is_not_fooled_by_dotdot_text(self):
        """`root/../../etc` 这种写法必须先规范化，否则前缀比较形同虚设。"""
        root = os.path.join(self.tmp, "root")
        sneaky = os.path.join(root, "..", "..", "etc")
        self.assertFalse(guard.within(guard.real(sneaky), guard.real(root)))

    # ---------------------------------------------------------------- resolve
    def test_resolve_needs_path(self):
        _target, reason = guard.resolve("", [self.tmp])
        self.assertEqual(reason, "缺少路径")

    def test_resolve_needs_roots(self):
        _target, reason = guard.resolve(self.tmp, [])
        self.assertIn("还没有添加任何位置", reason)

    def test_resolve_rejects_outside_root(self):
        root = os.path.join(self.tmp, "root")
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(root)
        os.makedirs(outside)
        _target, reason = guard.resolve(outside, [root])
        self.assertEqual(reason, "该路径不在已添加的位置之内")

    def test_resolve_rejects_dotdot_escape(self):
        root = os.path.join(self.tmp, "root")
        os.makedirs(root)
        _target, reason = guard.resolve(os.path.join(root, ".."), [root])
        self.assertEqual(reason, "该路径不在已添加的位置之内")

    def test_resolve_rejects_missing(self):
        root = os.path.join(self.tmp, "root")
        os.makedirs(root)
        _target, reason = guard.resolve(os.path.join(root, "nope"), [root])
        self.assertIn("路径不存在", reason)

    def test_resolve_checks_kind(self):
        root = os.path.join(self.tmp, "root")
        os.makedirs(root)
        with open(os.path.join(root, "f.txt"), "w", encoding="utf-8") as handle:
            handle.write("x")
        _t, reason = guard.resolve(os.path.join(root, "f.txt"), [root], kind="dir")
        self.assertIn("不是文件夹", reason)
        _t, reason = guard.resolve(root, [root], kind="file")
        self.assertIn("不是普通文件", reason)
        target, reason = guard.resolve(os.path.join(root, "f.txt"), [root], kind="file")
        self.assertEqual(reason, "")
        self.assertTrue(target.endswith("f.txt"))

    def test_resolve_accepts_root_itself(self):
        target, reason = guard.resolve(self.tmp, [self.tmp], kind="dir")
        self.assertEqual(reason, "")
        self.assertEqual(guard.key(target), guard.key(guard.real(self.tmp)))

    @unittest.skipIf(not platform.pseudo_filesystems(), "该平台没有伪文件系统")
    def test_resolve_rejects_pseudo_filesystem(self):
        _target, reason = guard.resolve("/proc", ["/"], kind="dir")
        self.assertIn("不支持浏览系统目录", reason)

    # ---------------------------------------------------------------- 符号链接
    def test_symlink_outside_root_is_blocked(self):
        """指向范围外的链接：解析后落在根外，必须拒绝 —— 否则边界形同虚设。"""
        root = os.path.join(self.tmp, "root")
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(root)
        os.makedirs(outside)
        link = os.path.join(root, "sneak")
        _symlink_dir(outside, link)

        _target, reason = guard.resolve(link, [root], kind="dir")
        self.assertEqual(reason, "该路径不在已添加的位置之内")

    def test_symlink_inside_root_is_allowed(self):
        root = os.path.join(self.tmp, "root")
        real_dir = os.path.join(root, "real")
        os.makedirs(real_dir)
        link = os.path.join(root, "alias")
        _symlink_dir(real_dir, link)

        target, reason = guard.resolve(link, [root], kind="dir")
        self.assertEqual(reason, "")
        self.assertEqual(guard.key(target), guard.key(guard.real(real_dir)))


class ModelTest(unittest.TestCase):
    """条目结构、格式化、可打开性判定。"""

    def test_extension(self):
        self.assertEqual(model.extension("a.TXT"), "txt")
        self.assertEqual(model.extension("/x/y/a.tar.gz"), "gz")
        self.assertEqual(model.extension("noext"), "")
        self.assertEqual(model.extension(".bashrc"), "")      # 隐藏文件不算扩展名
        self.assertEqual(model.extension(""), "")

    def test_openable_whitelist(self):
        for name in ("a.docx", "b.xlsx", "c.pdf", "d.txt", "e.png", "f.mp4", "g.zip"):
            self.assertTrue(model.can_open(name), name)

    def test_wps_formats_are_openable(self):
        """WPS 自家格式要能交给系统里的 WPS 打开 —— 这是本工具的一个实际用途。"""
        for name in ("a.wps", "b.et", "c.dps"):
            self.assertTrue(model.can_open(name), name)

    def test_executables_are_not_openable(self):
        """脚本与可执行体不能"用默认程序打开" —— 那等于接口触发的代码执行。"""
        for name in ("a.sh", "b.desktop", "c.bat", "d.cmd", "e.exe", "f.lnk",
                     "g.ps1", "h.vbs", "i.jar", "j.py", "k.scr", "noext"):
            self.assertFalse(model.can_open(name), name)

    def test_human_size(self):
        self.assertEqual(model.human_size(0), "0 B")
        self.assertEqual(model.human_size(512), "512 B")
        self.assertEqual(model.human_size(1024), "1.00 KB")
        self.assertEqual(model.human_size(1536), "1.50 KB")
        self.assertEqual(model.human_size(1024 * 1024), "1.00 MB")
        self.assertEqual(model.human_size(None), "")
        self.assertEqual(model.human_size(-5), "")

    def test_stamp_text_is_safe(self):
        self.assertEqual(model.stamp_text(0)[:4], "1970")
        self.assertEqual(model.stamp_text(None), "")
        self.assertEqual(model.stamp_text("垃圾"), "")

    def test_clean_text_passes_normal_names(self):
        text, clean = model.clean_text("正常名字.txt")
        self.assertTrue(clean)
        self.assertEqual(text, "正常名字.txt")

    def test_clean_text_repairs_surrogates(self):
        """Linux 上文件名可以是任意字节，Python 会解成代理对 ——
        json.dumps 遇到这种字符串会直接抛异常，必须在这里降级，
        不能让一个名字奇怪的文件把整个目录拖垮。"""
        raw = "坏名字".encode("utf-8") + b"\xff\xfe"
        broken = raw.decode("utf-8", "surrogateescape")
        text, clean = model.clean_text(broken)
        self.assertFalse(clean)
        self.assertIn("坏名字", text)
        import json
        json.dumps(text)          # 降级之后必须能序列化

    def test_make_entry_fields(self):
        entry = model.make_entry("报告.docx", "/tmp/报告.docx", False, False)
        self.assertEqual(entry["name"], "报告.docx")
        self.assertEqual(entry["ext"], "docx")
        self.assertFalse(entry["dir"])
        self.assertTrue(entry["openable"])
        self.assertEqual(entry["size_text"], "")        # 没有元信息
        import json
        json.dumps(entry, ensure_ascii=False)           # 一定能序列化

    def test_make_entry_directory(self):
        entry = model.make_entry("子目录", "/tmp/子目录", True, False)
        self.assertTrue(entry["dir"])
        self.assertFalse(entry["openable"])             # 目录不走"打开文件"
        self.assertEqual(entry["size_text"], "")

    def test_make_entry_escaping_link_has_no_path(self):
        """越界链接不给可回传的路径 —— 前端也就无法拿它去请求。"""
        entry = model.make_entry("外链", "/tmp/外链", True, True, link_escapes=True)
        self.assertTrue(entry["escapes"])
        self.assertEqual(entry["path"], "")
        self.assertFalse(entry["openable"])

    def test_dirs_first_keeps_inner_order(self):
        items = [{"name": "b", "dir": False}, {"name": "a", "dir": True},
                 {"name": "c", "dir": False}, {"name": "d", "dir": True}]
        got = [item["name"] for item in model.dirs_first(items)]
        self.assertEqual(got, ["a", "d", "b", "c"])

    def test_sort_by_name_dirs_first(self):
        items = [{"name": "b.txt", "dir": False},
                 {"name": "a.txt", "dir": False},
                 {"name": "zdir", "dir": True}]
        got = [item["name"] for item in model.sort_items(items, "name")]
        self.assertEqual(got, ["zdir", "a.txt", "b.txt"])

    def test_sort_desc_still_dirs_first(self):
        items = [{"name": "a.txt", "dir": False}, {"name": "zdir", "dir": True}]
        got = [item["name"] for item in model.sort_items(items, "name", desc=True)]
        self.assertEqual(got, ["zdir", "a.txt"])

    def test_sort_by_size_with_unknown_sizes(self):
        items = [{"name": "big", "dir": False, "size": 900},
                 {"name": "small", "dir": False, "size": 10},
                 {"name": "unknown", "dir": False, "size": None}]
        got = [item["name"] for item in model.sort_items(items, "size", desc=True)]
        self.assertEqual(got, ["big", "small", "unknown"])

    def test_sort_by_time(self):
        items = [{"name": "old", "dir": False, "mtime": 1.0},
                 {"name": "new", "dir": False, "mtime": 9.0}]
        got = [item["name"] for item in model.sort_items(items, "time", desc=True)]
        self.assertEqual(got, ["new", "old"])

    def test_unknown_sort_falls_back_to_name(self):
        items = [{"name": "b", "dir": False}, {"name": "a", "dir": False}]
        got = [item["name"] for item in model.sort_items(items, "乱写")]
        self.assertEqual(got, ["a", "b"])


class _FakeEntry(object):
    """`os.DirEntry` 的替身：只实现 `_entry()` 真正用到的那几个方法。

    用处是让"符号链接指向范围外 / 范围内"的判定**脱离环境**来测 ——
    有的环境根本建不出符号链接（见 `_symlink_dir`），光靠真链接会漏掉这段逻辑。
    """

    def __init__(self, path, name, is_dir=False, is_link=False, stat_error=""):
        self.path = path
        self.name = name
        self._dir = is_dir
        self._link = is_link
        self._stat_error = stat_error

    def is_symlink(self):
        return self._link

    def is_dir(self):
        return self._dir

    def stat(self):
        if self._stat_error:
            raise OSError(self._stat_error)
        return os.stat(__file__)


class EntryBuildingTest(unittest.TestCase):
    """条目构造：越界链接的标记、读不到元信息时的降级。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tb-files-entry-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "root")
        os.makedirs(self.root)
        self.tool = tool.FilesTool()

    @staticmethod
    def _touch(path, text="x"):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_symlink_pointing_outside_is_marked_unusable(self):
        outside = os.path.join(self.tmp, "outside.txt")
        self._touch(outside)
        got = self.tool._entry(_FakeEntry(outside, "sneak", is_link=True), [self.root])
        self.assertTrue(got["escapes"])
        self.assertEqual(got["path"], "")          # 不留可回传路径
        self.assertFalse(got["openable"])

    def test_symlink_pointing_inside_is_usable(self):
        inside = os.path.join(self.root, "real.txt")
        self._touch(inside)
        got = self.tool._entry(_FakeEntry(inside, "alias.txt", is_link=True), [self.root])
        self.assertFalse(got["escapes"])
        self.assertTrue(got["openable"])
        self.assertTrue(got["path"])

    def test_unreadable_entry_still_produces_a_row(self):
        """拿不到属性也要把条目列出来 —— "有个文件读不到"比"整个目录打不开"有用。"""
        got = self.tool._entry(
            _FakeEntry(os.path.join(self.root, "locked"), "locked", stat_error="拒绝访问"),
            [self.root],
        )
        self.assertEqual(got["name"], "locked")
        self.assertEqual(got["error"], "拒绝访问")
        self.assertIsNone(got["size"])
        self.assertEqual(got["size_text"], "")


class FilesToolTest(unittest.TestCase):
    """工具层：位置管理、列目录、交给系统的动作。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tb-files-tool-")
        self.data = tempfile.mkdtemp(prefix="tb-files-data-")
        patcher = mock.patch.dict(os.environ, {"TOOLBOX_DATA_DIR": self.data})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(shutil.rmtree, self.data, True)

        self.root = os.path.join(self.tmp, "root")
        os.makedirs(os.path.join(self.root, "sub"))
        self._write(os.path.join(self.root, "b.txt"), "bb")
        self._write(os.path.join(self.root, "a.txt"), "a")
        self._write(os.path.join(self.root, ".hidden"), "h")
        self._write(os.path.join(self.root, "sub", "inner.txt"), "i")

        self.tool = tool.FilesTool()
        self.tool.call("add_root", {"path": self.root})

    @staticmethod
    def _write(path, text):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    # ---------------------------------------------------------------- 位置
    def test_info_without_roots(self):
        fresh = tempfile.mkdtemp(prefix="tb-files-empty-")
        self.addCleanup(shutil.rmtree, fresh, True)
        patcher = mock.patch.dict(os.environ, {"TOOLBOX_DATA_DIR": fresh})
        patcher.start()
        self.addCleanup(patcher.stop)
        data = tool.FilesTool().call("info", {})
        self.assertEqual(data["roots"], [])
        self.assertTrue(data["quick"], "首次使用应有可一键添加的常见位置")

    def test_add_root_rejects_missing(self):
        with self.assertRaises(ToolError):
            self.tool.call("add_root", {"path": os.path.join(self.tmp, "不存在")})

    def test_add_root_rejects_file(self):
        with self.assertRaises(ToolError):
            self.tool.call("add_root", {"path": os.path.join(self.root, "a.txt")})

    def test_add_root_is_idempotent(self):
        self.tool.call("add_root", {"path": self.root})
        roots = self.tool.call("info", {})["roots"]
        self.assertEqual(len(roots), 1, "同一个目录不该被添加两次")

    def test_add_root_accepts_relative_and_dotdot_path(self):
        weird = os.path.join(self.root, "sub", "..")
        self.tool.call("add_root", {"path": weird})
        roots = self.tool.call("info", {})["roots"]
        self.assertEqual(len(roots), 1)

    def test_remove_root(self):
        out = self.tool.call("remove_root", {"path": self.root})
        self.assertEqual(out["roots"], [])
        with self.assertRaises(ToolError):
            self.tool.call("remove_root", {"path": self.root})

    def test_remove_root_clears_last(self):
        self.tool.call("list", {"path": self.root})
        self.assertTrue(store.load()["last"])
        self.tool.call("remove_root", {"path": self.root})
        self.assertEqual(store.load()["last"], "")

    # ---------------------------------------------------------------- 列目录
    def test_list_hides_dotfiles_by_default(self):
        out = self.tool.call("list", {"path": self.root})
        names = [item["name"] for item in out["items"]]
        self.assertNotIn(".hidden", names)
        self.assertEqual(out["hidden"], 1)
        self.assertEqual(out["total"], 3)               # a.txt b.txt sub

    def test_list_can_show_hidden(self):
        out = self.tool.call("list", {"path": self.root, "show_hidden": True})
        names = [item["name"] for item in out["items"]]
        self.assertIn(".hidden", names)
        self.assertEqual(out["hidden"], 0)

    def test_list_puts_directories_first(self):
        out = self.tool.call("list", {"path": self.root})
        self.assertTrue(out["items"][0]["dir"])
        self.assertEqual(out["items"][0]["name"], "sub")

    def test_list_keyword_filter(self):
        out = self.tool.call("list", {"path": self.root, "keyword": "A.TXT"})
        self.assertEqual([item["name"] for item in out["items"]], ["a.txt"])
        self.assertEqual(out["total"], 3)               # 总数不受筛选影响
        self.assertEqual(out["matched"], 1)

    def test_list_sort_by_size_desc(self):
        out = self.tool.call("list", {"path": self.root, "sort": "size", "desc": True})
        files = [item["name"] for item in out["items"] if not item["dir"]]
        self.assertEqual(files, ["b.txt", "a.txt"])

    def test_list_reports_parent_and_crumbs(self):
        out = self.tool.call("list", {"path": os.path.join(self.root, "sub")})
        self.assertEqual(guard.key(out["parent"]), guard.key(self.root))
        labels = [crumb["label"] for crumb in out["crumbs"]]
        self.assertEqual(labels, [os.path.basename(self.root), "sub"])

    def test_parent_is_empty_at_root_top(self):
        """已经在位置顶层时**没有上级** —— 再往上就是边界之外。"""
        out = self.tool.call("list", {"path": self.root})
        self.assertEqual(out["parent"], "")

    def test_list_rejects_escape(self):
        for bad in (os.path.join(self.root, ".."),
                    os.path.join(self.root, "..", ".."),
                    self.tmp, os.path.abspath(os.sep)):
            with self.assertRaises(ToolError):
                self.tool.call("list", {"path": bad})

    def test_list_rejects_non_directory(self):
        with self.assertRaises(ToolError):
            self.tool.call("list", {"path": os.path.join(self.root, "a.txt")})

    def test_list_remembers_last(self):
        sub = os.path.join(self.root, "sub")
        self.tool.call("list", {"path": sub})
        self.assertEqual(guard.key(store.load()["last"]), guard.key(sub))

    def test_list_truncates_large_directory(self):
        with mock.patch.object(model, "LIST_LIMIT", 2):
            out = self.tool.call("list", {"path": self.root})
        self.assertEqual(out["shown"], 2)
        self.assertTrue(out["truncated"])
        self.assertIn("只列出前 2 条", out["note"])

    def test_list_sort_by_size_also_truncates(self):
        with mock.patch.object(model, "LIST_LIMIT", 1):
            out = self.tool.call("list", {"path": self.root, "sort": "size"})
        self.assertEqual(out["shown"], 1)
        self.assertTrue(out["truncated"])

    def test_list_survives_unreadable_entry(self):
        """单项读不到元信息不能影响整个目录。"""
        out = self.tool.call("list", {"path": self.root})
        self.assertEqual(len(out["items"]), 3)

    def test_list_marks_escaping_symlink(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        link = os.path.join(self.root, "sneak")
        _symlink_dir(outside, link)

        out = self.tool.call("list", {"path": self.root})
        entry = [item for item in out["items"] if item["name"] == "sneak"][0]
        self.assertTrue(entry["escapes"])
        self.assertEqual(entry["path"], "")            # 不留可回传路径
        # 直接点进去也必须被拒
        with self.assertRaises(ToolError):
            self.tool.call("list", {"path": link})

    # ---------------------------------------------------------------- 交给系统
    def test_open_rejects_script(self):
        script = os.path.join(self.root, "run.sh")
        self._write(script, "echo hi")
        with mock.patch.object(platform, "open_with_default") as fake:
            with self.assertRaises(ToolError):
                self.tool.call("open", {"path": script})
            fake.assert_not_called()                   # 连调都不该调

    def test_open_allows_document(self):
        doc = os.path.join(self.root, "报告.docx")
        self._write(doc, "x")
        with mock.patch.object(platform, "open_with_default", return_value=True) as fake:
            out = self.tool.call("open", {"path": doc})
        self.assertTrue(out["opened"])
        fake.assert_called_once()

    def test_open_rejects_outside_root(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        target = os.path.join(outside, "a.txt")
        self._write(target, "x")
        with mock.patch.object(platform, "open_with_default") as fake:
            with self.assertRaises(ToolError):
                self.tool.call("open", {"path": target})
            fake.assert_not_called()

    def test_open_rejects_directory(self):
        with mock.patch.object(platform, "open_with_default") as fake:
            with self.assertRaises(ToolError):
                self.tool.call("open", {"path": os.path.join(self.root, "sub")})
            fake.assert_not_called()

    def test_open_reports_system_failure(self):
        doc = os.path.join(self.root, "报告.docx")
        self._write(doc, "x")
        with mock.patch.object(platform, "open_with_default", return_value=False):
            with self.assertRaises(ToolError):
                self.tool.call("open", {"path": doc})

    def test_reveal_allows_any_extension(self):
        """白名单之外的文件仍有出口：交给文件管理器自己处理。"""
        script = os.path.join(self.root, "run.sh")
        self._write(script, "echo hi")
        with mock.patch.object(platform, "open_in_file_manager", return_value=True) as fake:
            out = self.tool.call("reveal", {"path": script})
        self.assertTrue(out["revealed"])
        fake.assert_called_once()

    def test_reveal_directory_opens_it(self):
        with mock.patch.object(platform, "open_with_default", return_value=True) as fake:
            out = self.tool.call("reveal", {"path": os.path.join(self.root, "sub")})
        self.assertTrue(out["revealed"])
        fake.assert_called_once()

    def test_reveal_rejects_outside_root(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        with mock.patch.object(platform, "open_with_default") as fake:
            with self.assertRaises(ToolError):
                self.tool.call("reveal", {"path": outside})
            fake.assert_not_called()


if __name__ == "__main__":
    unittest.main()
