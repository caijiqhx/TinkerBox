# ToolBox 设计方案

> 个人工具箱 · 本地 Web UI 承载 · 纯标准库 · 跨平台（Windows 开发 / aarch64 UOS 运行）
>
> **当前工具：待办清单（TodoList）+ 日历（Calendar）** —— 首版从 TodoList 起步，架构保留多工具扩展能力。

---

## 0. 设计前提（硬约束）

| 约束 | 内容 | 原因 |
|---|---|---|
| **运行环境** | 目标机为 aarch64 UOS，**仅能确定有 python3** | 环境无法预先探测 |
| **功能范围** | **当前：待办清单 + 日历**（首版只做 TodoList，架构保留多工具扩展能力） | 逐步增量，非一次性排期 |
| **依赖策略** | **纯标准库**，零第三方依赖 | 引入 C 扩展库会把跨平台问题重新带回来 |
| **语言版本** | 兼容 **Python 3.7**（目标机可能是 3.7.x） | 源码运行，版本由目标机决定 |
| **交付形态** | 源码目录 + 启动脚本，**不打包** | 用户已确认接受源码运行 |
| **UI 承载** | **本地 Web UI**（浏览器 `--app` 模式呈现） | 依赖 `http.server`（核心标准库）+ 系统浏览器（桌面版必备） |
| **UI 可替换** | 承载层与业务逻辑解耦 | 将来若要补 tkinter 承载层，业务代码零改动 |

### Python 3.7 兼容清单

- 文件头统一加 `from __future__ import annotations`（3.7 即支持）
- **禁用**：海象运算符 `:=`（3.8+）、f-string `=` 调试语法（3.8+）、`X | None`（3.10+）、内置泛型 `list[str]`（3.9+）
- **可用**：`dataclasses`、`pathlib`、`json`、`http.server`、`f-string`（3.6+）、`typing.Optional/List/Dict`

---

## 1. 需求覆盖性

| 需求 | Web UI 覆盖度 | 说明 |
|---|---|---|
| 总体入口页 → 跳转工具页 | ✅ 完全胜任 | 网页导航是这个形态的天然强项 |
| TodoList 增删改查 | ✅ 完全胜任 | 列表/表单/行内编辑都是 Web 常规能力 |
| 日历（月历 / 节假日 / 农历） | ✅ 完全胜任 | 纯前端网格渲染，数据全部内置、离线可用 |
| **中文输入** | ✅ **优于 Tkinter** | 走浏览器输入法，无需处理 XIM/fcitx |
| 固定到桌面/启动器 | ✅ 胜任 | `.desktop` 图标 + `--app` 无地址栏窗口 |
| 界面美观度 | ✅ 优于 Tkinter | HTML/CSS 表现力远超 Tk |
| **系统原生文件对话框** | ⚠️ 需自建 | 现有工具**用不到**，推迟到 filebatch |
| 系统托盘常驻 | ❌ 不支持 | 若将来必需，才需要考虑 tkinter 承载层 |

**结论**：现有工具（待办清单 / 日历）的全部需求 Web UI 均可覆盖，**GUI 承载层不做**。

### 入口页

**入口页始终显示**，不做自适应隐藏——它是工具箱的固定"门面"，即使当前只有一个工具也保留，位置固定、心智稳定。启动后落在入口页，点击工具卡片跳转到工具页。

> 备选方案（工具数 = 1 时直达工具页）已评估并**放弃**：入口页常显的行为更可预期，且将来加工具时不会出现"入口页突然冒出来"的突变。

---

## 2. 架构总览

```
┌─────────────────────────────────────────────┐
│  浏览器（--app 模式窗口）                     │
│  index.html + app.js + style.css            │
└──────────────────┬──────────────────────────┘
                   │  JSON over HTTP (127.0.0.1 + token)
┌──────────────────▼──────────────────────────┐
│  web/  承载层                                │
│  server.py router.py instance.py launcher.py │
│  doctor.py                                   │
└──────────────────┬──────────────────────────┘
                   │  统一 action 分发（与协议无关）
┌──────────────────▼──────────────────────────┐
│  core/  契约层                               │
│  Tool 基类 · 注册表 · ToolError · paths      │
└──────┬───────────────────────────┬──────────┘
       │                           │
┌──────▼────────┐          ┌───────▼──────────┐
│  services/    │          │  tools/          │
│ 配置 存储 日志 │          │  todo / calendar │
│  平台差异      │          │  （各自 model+   │
│               │          │   tool，互不依赖）│
└───────────────┘          └──────────────────┘
```

**依赖方向严格单向**：`tools/*` → `core/` ← `web/`；`tools/*` 与 `services/` 必须能独立于 UI 运行。

**核心设计点**：工具**不感知 HTTP，也不感知 HTML**。每个工具只对外暴露一组 `action` 函数（入参 dict、出参 JSON 可序列化）。Web 路由层负责把 HTTP 请求映射到 action。将来加 tkinter 承载层或加新工具，都只在这两侧改动。

> 保留注册表机制（而非直接把 TodoList 写死在外壳里）的成本几乎为零，但换来"加工具=加一行注册"的扩展性。这是本方案唯一一处"为未来留口子"的地方。

---

## 3. 目录结构

```
ToolBox/
├─ DESIGN.md
├─ README.md
├─ .gitattributes            # 行尾固化（*.bat / *.vbs = CRLF）
├─ run.sh                    # Linux 启动脚本
├─ run.bat                   # Windows 启动脚本
├─ run-silent.vbs            # Windows 静默启动（无窗口、无浏览器，失败才提示）
├─ src/
│  ├─ main.py                # 唯一入口（含 --detach / stop / status 等子命令）
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ tool.py             # Tool 基类 + ToolMeta（含 icon_html 内联 SVG）
│  │  ├─ registry.py         # 工具注册表
│  │  ├─ errors.py           # ToolError / 统一错误
│  │  └─ paths.py            # 跨平台路径（配置/数据目录，支持 TOOLBOX_DATA_DIR 覆盖）
│  ├─ services/
│  │  ├─ __init__.py
│  │  ├─ jsonio.py           # 原子 JSON 读写 + 备份轮转
│  │  ├─ config.py           # 全局配置
│  │  ├─ logs.py             # 日志
│  │  └─ platform.py         # 平台差异【全项目唯一允许平台分支处】
│  ├─ web/
│  │  ├─ __init__.py
│  │  ├─ server.py           # ThreadingHTTPServer 封装
│  │  ├─ router.py           # 路由 + action 分发 + token 校验
│  │  ├─ instance.py         # 常驻实例探测（幂等启动 / stop / status）
│  │  ├─ launcher.py         # 浏览器探测与 --app 启动
│  │  ├─ doctor.py           # 环境自检报告
│  │  └─ static/
│  │     ├─ index.html
│  │     ├─ app.js
│  │     ├─ style.css
│  │     ├─ ui/
│  │     │  └─ datepicker.js # 日期选择浮层（外壳级通用小部件，工具经 ctx.pickDate 调用）
│  │     └─ tools/
│  │        ├─ todo.js       # 待办清单前端模块
│  │        └─ calendar.js   # 日历前端模块
│  ├─ cli/
│  │  └─ cli.py              # CLI 承载层（保底，100% 可用）
│  └─ tools/
│     ├─ __init__.py         # register_all()：注册全部工具
│     ├─ todo/
│     │  ├─ __init__.py
│     │  ├─ model.py         # Task 数据结构 + 视图/日期口径
│     │  ├─ store.py         # data/todo.json 原子读写（含回收站）
│     │  └─ tool.py          # Tool 实现（actions + cli）
│     └─ calendar/
│        ├─ __init__.py
│        ├─ model.py         # 月视图 / 农历（1900-2100）/ 节假日状态
│        ├─ tool.py          # Tool 实现（actions；无 CLI）
│        └─ holidays.json    # 内置节假日数据（离线可用）
├─ data/                     # 运行时数据（配置、todo.json、日志）
└─ tests/                    # test_todo / test_calendar / test_core / test_instance
```

`services/tasks.py`（后台长任务）首版**不实现** —— TodoList 无耗时操作。等将来做文件批处理时再加。

---

## 4. 契约层设计（core/）

### 4.1 Tool 基类

```python
# core/tool.py
class ToolMeta:
    def __init__(self, tid, name, desc="", icon="", order=100):
        self.id, self.name, self.desc, self.icon, self.order = ...

class Tool(object):
    meta = None                      # 子类必须提供 ToolMeta

    def actions(self):
        """返回 {action_name: callable(payload: dict) -> JSON可序列化结果}
        这是 UI 与业务之间唯一的接口。"""
        return {}

    def cli(self, argv):
        """可选：命令行子命令入口，返回退出码。默认不支持。"""
        raise ToolError("该工具不支持命令行调用")
```

**约定**：
- action 入参一律是 `dict`，出参必须可 JSON 序列化（`dict` / `list` / 基本类型）
- 业务失败一律抛 `ToolError(message)`，由承载层统一转成错误响应
- action **不得**直接操作 UI、不得长时间阻塞（长任务将来走 `services/tasks.py`）

### 4.2 工具注册表

```python
# core/registry.py
_REGISTRY = []
def register(tool_instance): ...
def all_tools(): return sorted(_REGISTRY, key=lambda t: t.meta.order)
def get(tid): ...
```

新增工具 = 在 `tools/` 下建一个包 + 在 `tools/__init__.py` 里注册一行，**外壳与路由零改动**。

---

## 5. Web 承载层设计（web/）

### 5.1 服务

- `http.server.ThreadingHTTPServer` + 自定义 `BaseHTTPRequestHandler`
- **只绑定 `127.0.0.1`**；端口**固定 8765** —— 用户靠浏览器书签进来，随机端口会让书签失效。
  被占用时**明确报错，绝不静默换端口**（静默换掉只会让书签悄悄失效、用户还不知道为什么）
- 全部 API 走 JSON，响应统一包装：`{"ok": true, "data": ...}` / `{"ok": false, "error": "..."}`

### 5.2 路由

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回 `index.html`（注入 token） |
| GET | `/static/<path>` | 静态资源（限白名单，防目录穿越；`Cache-Control: no-store`） |
| GET | `/api/tools` | 工具清单（id/name/desc/icon/icon_html），供导航 / 入口页渲染 |
| POST | `/api/tool/<tid>/<action>` | body: `{"payload": {...}}` → 分发到 `tools.get(tid).actions()[action]` |
| GET | `/api/doctor` | 环境自检报告 |
| POST | `/api/ping` | 前端心跳（活动时间统计；常驻模式下不因此退出） |
| GET | `/api/identity` | **免 token** 的只读探测：确认"是不是我自己的服务"（幂等启动用） |
| POST | `/api/shutdown?i=<instance>` | 供 `stop` 子命令关闭服务（进程外拿不到页面 token，改用实例标识校验） |
| GET | `/api/status` | 运行时长 / 端口 / 是否常驻（侧栏小字用，带 token） |
| POST | `/api/quit` | 页面「关闭服务」按钮 |
| POST | `/api/bye` | 窗口关闭信号（`sendBeacon`，走 `?t=` 查询参数传 token）；**常驻模式下不关服务** |

### 5.3 安全（必做，不是可选项）

本机服务有一个真实风险：**用户浏览器里的任意网页都能向 `127.0.0.1:<port>` 发请求**。防护三条：

1. **启动时生成随机 token**，从 `index.html` 注入前端；之后所有 `/api/*` 请求必须带 `X-Toolbox-Token` 头，服务端用 `hmac.compare_digest` 比对
2. **校验 `Host` 头**，只接受 `127.0.0.1` / `localhost`
3. **校验 `Origin` 头**（若存在），来源必须是自身地址

只监听回环地址 + 上述校验，即满足个人工具的安全边界。

### 5.4 生命周期

**服务寿命与窗口寿命解耦** —— 用户日常只做一个动作：**点一次 run，当天一直驻留**。

- **启动（幂等）**：先探测是否已有自有实例在跑（读 `data/server.json` + 请求 `/api/identity` 确认身份）；
  有则**只打开界面、不重复起服务**；没有才拉起服务
- **服务跑在分离进程里**（`--detach`）：Windows 用 `DETACHED_PROCESS` + `pythonw.exe`，POSIX 用
  `start_new_session`。否则**关掉启动脚本的黑窗会连带杀掉服务**，常驻就无从谈起
- **三个人工/自动出口**：界面「关闭服务」/ 命令行 `stop` / **空闲 12 小时自动退出**
- **重启（`--restart`）**：先停掉自有实例、**等它让出端口**，再按原方式启动 —— 端口是固定的，
  不等旧进程退出就启动必然撞端口。停止这一步与 `stop` 子命令**共用同一段实现**
  （`find_running` → `request_shutdown` → `wait_until_stopped`），停不掉时**直接报错返回**，
  不继续启动。`--restart status` 这类子命令**不触发**重启（只有真要启动时才重启）。
  与 `--force` 的区别：`--force` 是"无视已有实例、硬起一个"，只在换端口时有意义
- **关窗口 ≠ 退出服务**：前端 `pagehide` 发 `/api/bye`，但**是否因此退出由服务端按 `keep_alive` 判断**
  （`keep_alive=false` 可回退到"关窗口即退"）
- 心跳间隔 15 秒、超时 90 秒（必须大于浏览器对后台标签的节流周期，否则窗口一最小化就被误杀）

### 5.5 浏览器探测与 `--app` 启动（launcher.py）

按优先级探测，命中即用：

1. **Chromium 内核（支持 `--app`）**
   - Linux：`chromium`、`chromium-browser`、`google-chrome`、`microsoft-edge`、`uos-browser`、`browser`、`360browser`、`qihoo-browser`
   - Windows：`chrome.exe`、`msedge.exe`（含常见安装路径）
2. **退化为 `webbrowser.open(url)`**（Firefox 等，会有地址栏，观感下降但可用）
3. **都没有** → 打印 URL 让用户手动打开

启动参数：`--app=<url> --window-size=1200,800 --user-data-dir=<独立目录>`
> `--user-data-dir` 单独指定，避免污染用户日常浏览器配置，也让 `--app` 窗口更"独立应用化"。

**无图形环境判断**：`DISPLAY` 与 `WAYLAND_DISPLAY` 均未设置 → 不起浏览器，提示改用 CLI 或 `--no-browser`。

**默认不自动打开浏览器**（与直觉相反，但实战结论）：用户日常的主路径其实是**点浏览器书签**，
启动脚本只负责把服务拉起来。所以"打开浏览器"做成**显式开关 `--open`**，默认只打印地址；
`--no-browser` 保留为语义明确的显式否定，优先级高于 `--open`。

### 5.6 前端（static/，无框架手写）

- `index.html`：外壳容器（侧栏 + 内容区 + 弹窗 + 确认框），启动时由服务端注入 token 与主题偏好
- `app.js`
  - `GET /api/tools` 渲染侧栏导航与入口页卡片（工具图标优先用 `icon_html` 内联 SVG，回退文本 `icon`）
  - hash 路由：`#/<工具 id>`；**路由解析只认路径部分**，`?` 后的参数（如 `#/todo?due=...`）由各工具自行读取
  - 统一封装 `callTool(tool, action, payload)` / `apiGet` / `apiPost`：自动带 token、自动解包
    `{ok,data,error}`、统一错误提示
  - 对外提供 `ctx`（`el` / `callTool` / `toast` / `confirm` / `openModal` / `clear` / `dialogOpen` / `pickDate` …）
  - 主题三态（浅色 / 深色 / 跟随系统）；侧栏底部显示服务状态小字
- `tools/todo.js`、`tools/calendar.js`：各自 IIFE，导出 `window.ToolBox.registerTool(id, {render})`；
  **只调 action，不写业务规则**；跨工具联动也是调对方的 action（如日历调 `todo.due_map`）
- `ui/datepicker.js`：**外壳级通用小部件**（日期选择浮层），替代浏览器原生 `<input type="date">`。
  工具通过 `ctx.pickDate({ value, anchor, onPick })` 调用，不直接依赖该模块（缺席也不崩）。
  自绘的理由：原生弹层样式不跟主题、滚动翻月不受控，且"点日期即确认关闭"是写死的行为插不进「确定」
- `style.css`：手写 CSS 变量做主题（`:root[data-theme=...]`），深浅两套

---

## 6. 服务层设计（services/）

| 模块 | 职责 | 关键点 |
|---|---|---|
| `jsonio.py` | JSON 原子读写 + 备份轮转 | 写临时文件 → `os.fsync` → `os.replace()`；**写前先把旧版轮转成 `.bak.N`**；读失败给默认值，不崩 |
| `config.py` | 全局配置 | 存 `data/config.json`；`get/set` 与默认值合并。已有：`port` / `keep_alive` / `idle_exit_hours` / `backup_keep` / `trash_keep_days` |
| `logs.py` | 日志 | 写 `data/logs/`，按日切分；UI 异常单独记录；后台服务输出落 `data/logs/service.out` |
| `platform.py` | 平台差异**唯一出口** | 见下 |

**`platform.py` 是全项目唯一允许出现平台分支的地方**：

```python
IS_WINDOWS = os.name == "nt"

def browser_candidates():     # 浏览器候选列表（按平台返回，Chromium 内核优先）
def has_display():            # 是否有图形环境
def is_case_sensitive():      # Windows 不区分大小写；Linux 区分（为将来 filebatch 预留）
def allow_address_reuse():    # Windows 必须返回 False（否则两个进程能绑同一端口）
def spawn_background(...)     # 分离进程启动（DETACHED_PROCESS / start_new_session）
def background_python():      # Windows 优先 pythonw.exe（GUI 子系统，不附着控制台）
def open_in_file_manager(path)
```

数据目录的选址（项目内 `data/` 优先，不可写时退回用户目录；`TOOLBOX_DATA_DIR` 可整体覆盖）放在 `core/paths.py`，与平台行为分开。

---

## 7. 入口设计（main.py）

```bash
python3 src/main.py                     # 默认：起服务（不弹浏览器窗口，用书签访问）；已是常驻则只开界面
python3 src/main.py --open              # 起服务并自动打开浏览器窗口
python3 src/main.py --ui=cli            # 强制 CLI（TOOLBOX_UI=cli 亦可）
python3 src/main.py --ui=none --port=8765   # 只起服务，不开浏览器
python3 src/main.py --no-browser        # 强制不打开浏览器（优先级高于 --open）
python3 src/main.py --detach            # 分离进程启动（拉起后台服务后前台立即退出，黑窗可关）
python3 src/main.py status              # 查看服务是否在跑（端口 / 运行时长）
python3 src/main.py stop                # 关闭正在跑的服务
python3 src/main.py doctor              # 环境自检并打印报告
python3 src/main.py todo list           # 直接调工具的 CLI 子命令
python3 src/main.py todo add "买牛奶"
```

**默认不弹浏览器窗口**：日常用法是点浏览器书签，启动脚本只负责把服务拉起来；
每次双击都弹窗纯属干扰。需要弹窗时显式加 `--open`。

**`--ui` / `TOOLBOX_UI` 的用途**：让你**在 Windows 开发机上就能测完所有承载路径**，不必真去找缺组件的机器。

**doctor 输出内容**：Python 版本与架构 · 关键标准库模块可用性 · 浏览器探测结果 · `DISPLAY`/`WAYLAND_DISPLAY` · 数据目录路径与可写性 · 推荐承载方式。

---

## 8. 工具设计

> 8.1–8.5 描述 **TodoList**（第一个、也是最完整的工具）；8.6 简述**日历**。

### 8.1 数据模型

任务直接用**普通 dict**表示（不用 dataclass）——它与 JSON 天然同构，省掉一层序列化往返，读写不易出错：

```python
# tools/todo/model.py  make_task() 的产物（字段与实际实现一致）
{
    "id":         "a1b2c3d4e5f6",   # uuid4 前 12 位
    "list_id":    "default",         # 所属清单；default = 兜底清单「未分类」
    "title":      "买牛奶",
    "status":     "todo",            # todo | done
    "important":  False,             # 星标（重要视图）
    "my_day":     "",                # 加入「我的一天」那天（YYYY-MM-DD）；空 = 未加入
    "due":        "",                # 到期日（YYYY-MM-DD）；空 = 无
    "repeat":     "none",            # none | daily | weekly | monthly
    "note":       "",
    "steps":      [],                # [{id, title, done}]，最多 50 步
    "tags":       [],                # 字符串列表，最多 12 个
    "created":    "2026-09-11 21:50:00",
    "updated":    "2026-09-11 21:50:00",
    "done_at":    "",                # 空串表示未完成
    "deleted_at": "",                # 非空 = 在回收站（软删除，保留 30 天）
}
```

> 「我的一天」靠 `my_day <= 今天 且未完成` 判定（不是等于今天），所以**不需要任何后台定时任务**，
> 昨天没做完的今天自动还在；重复任务完成时顺延，`my_day` 被推到下一周期、当天自然消失。
> 手动排序键为 `(星标, order, 到期日, 创建)`；任务**不做**手动拖拽排序（与自动排序互斥）。

### 8.2 持久化

- 单文件 `data/todo.json`，**原子写**（临时文件 → `os.replace`）
- 结构：`{"version": 1, "tasks": [...]}`（带 version 便于将来迁移）
- 读取容错：文件不存在 / 内容损坏 → 返回空列表并记录日志，**不抛异常、不崩 UI**

### 8.3 actions

统一入口 `board`（读）+ 一组写动作。`board` 一次返回视图所需的全部数据，前端不做二次拼装。

| action | payload | 说明 |
|---|---|---|
| `board` | `{view, list_id, keyword, due}` | 视图/筛选/分组/计数/统计一次给全。`view` ∈ all / my_day / important / planned / completed / list / trash / day |
| `due_map` | `{year, month}`（可选） | 按到期日聚合 `{pending, done}`，供日历格子叠加显示 |
| `add` | `{title, view, list_id, due, repeat}` | 在「我的一天 / 重要 / 已计划 / 某天待办」视图里添加会自动补齐对应字段 |
| `update` | `{id, fields}` | 改标题 / 到期日 / 备注 / 标签 / 所属清单 / 重复 |
| `toggle` | `{id}` | 切换完成态；重复任务完成即顺延（返回 `deferred_to`） |
| `toggle_important` / `toggle_my_day` | `{id}` | 星标 / 加入我的一天 |
| `remove` / `clear_done` | `{id}` / `{}` | **软删除** → 进回收站 |
| `bulk` | `{ids, op, value}` | 批量（设成指定值语义），一次读写 |
| `add_step` / `toggle_step` / `update_step` / `remove_step` | `{id, ...}` | 步骤增删改 |
| `add_list` / `rename_list` / `reorder_lists` / `remove_list` | `{...}` | 清单增删改与拖拽排序 |
| `restore` / `purge` / `empty_trash` | `{id}` / `{}` | 回收站：恢复 / 彻底删 / 清空 |

### 8.4 前端要点

- **顶部工具栏**（只创建一次，避免刷新时输入框失焦）：添加框（回车即加，按当前视图自动补齐字段）+ 全局搜索（命中标题/备注/标签/步骤，片段高亮）+「多选」
- **左栏**：我的一天 / 重要 / 已计划 / 已完成 / 任务 + 清单（自定义 + 兜底的「未分类」），回收站沉底；
  清单可**拖拽排序**、可**置顶/删除**、**点标题即可改名**
- **列表**：行首勾选切换完成态（多选模式下换成"选择框"）；行内显示星标/☀/重复/步骤进度/到期日/标签 chip；
  **点步骤文字直接改**；「已计划」按 已过期/今天/明天/本周/以后 分组
- **某天待办**（从日历跳入的临时视图）：跨清单、含已完成，分「未完成 / 已完成」两组，每条标出来源清单
- **详情面板**：标题 / 步骤 / 标记 / 到期日（快捷项「今天」「明天」）/ 备注 / 所属清单 / 重复；**Esc 收起**
- **批量操作**：多选后标记完成 / 标为重要 / 加入我的一天 / 移到清单 / 删除，另有全选
- **不调用浏览器原生弹窗**：确认框由外壳提供 `ctx.confirm`
- **中文输入**：浏览器原生支持，无需额外处理

### 8.5 CLI

```bash
python3 src/main.py todo list              # 默认「我的一天」；-a 全部 -i 重要 -p 已计划 -d 已完成
python3 src/main.py todo add "买牛奶" --due 2026-09-20
python3 src/main.py todo done <id>         # undone <id> 同义
python3 src/main.py todo star <id>         # 切换星标
python3 src/main.py todo today <id>        # 加入 / 移出「我的一天」
python3 src/main.py todo rm <id>
python3 src/main.py todo clear             # 清理全部已完成
python3 src/main.py todo where             # 显示数据文件位置
```

作用有两个：① 图形环境不可用时的保底；② **在 Windows 上验证核心逻辑不需要开浏览器**，调试更快。
（**日历工具不提供 CLI** —— 它本身就是纯展示。）

### 8.6 日历工具（简述）

与 TodoList 并列的第二个工具（`tools/calendar/`），同样是"只暴露 action"：

- **数据全内置、彻底离线**：`holidays.json`（节假日 / 调休，覆盖 **2000-2026**）+ 1900-2100 农历表 + 1900-2100 二十四节气表。
  农历传统节日（元宵 / 龙抬头 / 七夕 / 中元 / 重阳 / 腊八 / 小年 / 除夕）由农历**纯计算**得出，不需要外部数据。
  `build_holidays.py` 是生成脚本（2007 起从 holiday-cn 抓的国务院公告 + 2000-2006 按通知原文手工整理的表），
  每年国务院发下一年安排后跑一次即可；跑完自带自检（调休日必须是周末、不得跨年、不得与放假日冲突）
- **数据按"日期所属年份"归档**（不是按通知的年份）：12 月底若属于下一年的元旦假期，仍记在本年，
  否则翻到 12 月会漏标那几天
- **用户数据目录里的 `holidays.json` 按条目合并**（同名假期整条覆盖、workdays 取并集），
  不是整年替换 —— 否则"只想补一天"会静默丢掉内置那一年的其余安排。
  内网机器补年份只需放这个文件，**不用重装程序**
- `month` action 返回整月网格（周一开头；每格带 状态[节假日/调休/周末/工作日] / 节日名 /
  ISO 周号 / 农历（短形式 + 完整形式）/ 农历节日 / 节气 / 是否今天）和月份概览（本月节假日、调休天数与跨度），
  外加**干支纪年**（`ganzhi`，如「丙午马年」）。干支是**纯计算**（序号 = (年 - 4) % 60，公元 4 年为甲子），
  不需要数据表。两处口径**故意不同**：
  - `month_view` 看的是"这个月里经历了什么" → 口径为**农历年**（正月初一换年），且用**区间**求值，
    跨农历年的月份给两段（「乙巳蛇年 → 丙午马年」）—— 公历月与农历年天然错位，单点求值会写错；
    区间判定依赖农历表，表范围外（1900-01-31 之前、2100 之后）返回空串，前端不显示
  - `year` 看的是"这一年叫什么年" → 直接用该年春节起的干支（「丙午马年」），不带跨年箭头，
    也不依赖农历表。**无数据的年份退化为纯公历**，不报错
- **格子里"当天是什么日子"的展示规则**：格子那一行只放一个（假日名 / 农历节日 / 节气 / 农历日）；
  有农历节日 / 节气时用它**顶替**农历日，法定假期名只在**正日子**当天进格子（`fest_day`，
  如中秋只在中秋节那天，其余天进悬停提示），正日子当天也不再叠农历日 —— 完整农历始终在悬停提示里。
  国务院数据把整个假期挂同一个名字，直接显示会像是放了三次中秋
- **与待办联动**：前端调 `todo.due_map` 取当天待办数叠加到格子（未完成/已完成分开），
  点某天跳 `#/todo?due=YYYY-MM-DD`（跨清单的「某天待办」视图）
- 联动取数失败（如 todo 工具缺席）时**退化成纯日历**，不影响主功能
- **年度视图**：`year` action 一次返回 12 个月的月视图（约 70KB，本地一次请求足够）。
  前端一屏铺 12 张月份卡片（每格只标假期 / 调休 / 周末 / 今天，具体日子放悬停提示），
  点某天 → 切回月视图、跳到该月并选中那天；年度视图**不做待办计数**（那要 12 次请求，小格也放不下）

---

## 9. Windows 上的测试方案（重要）

**结论：除 3 项配置级内容外，全部可在 Windows 上完整测试。因此「固定到桌面」建议保留、现在就做。**

### 9.1 能完整验证的

| 项 | Windows 上怎么测 | 与 Linux 的差异 |
|---|---|---|
| `--app` 无地址栏窗口 | Chrome / Edge 都支持 `--app=` | 无差异 |
| 浏览器探测与启动逻辑 | 探测 `chrome.exe` / `msedge.exe` | 仅候选列表不同 |
| 心跳自动退出 | 完全一致 | 无差异 |
| token / Host / Origin 安全校验 | 完全一致（同为 localhost 模型） | 无差异 |
| Web 服务、路由、action 分发 | 完全一致（纯标准库） | 无差异 |
| 持久化、原子写 | 完全一致 | 路径不同，由 `platform.py` 收口 |
| **桌面图标启动** | 用 `.lnk` 快捷方式（右键 `run.bat` → 发送到桌面） | 等价于 `.desktop` |
| **无控制台黑窗启动** | 用 `pythonw.exe` 启动 | Linux 无此问题 |
| 自定义图标 | `.ico` | Linux 用 `.png` |

### 9.2 无法在 Windows 上验证的（仅 3 项，都是配置级）

1. **`.desktop` 文件语法本身** —— 纯文本格式，可静态检查；写错概率极低
2. **Linux 浏览器名字列表**（`uos-browser` 等）—— 已在 `platform.py` 里做成列表，目标机上补一个名字即可
3. **`gio trash` / 回收站** —— **与 TodoList 无关**，本项目首版用不到

### 9.3 建议的落地方式

先在 Windows 上把「桌面快捷方式」做通（`.lnk` + `pythonw` + 自定义图标），同时**把 `.desktop` 文件按模板一并写好放进仓库**。到目标机后跑一次 `doctor`，按报出的浏览器名字微调列表即可。**额外成本几乎为零。**

> 备选验证手段：Windows 11 的 WSLg 可以运行 Linux GUI 程序，理论上能在 WSL 里 `gtk-launch` 测 `.desktop`。但需要另装浏览器且是 x86_64 架构，收益不抵成本，**不建议**。

---

## 10. 启动与部署

### run.sh（Linux）

```sh
#!/bin/sh
cd "$(dirname "$0")" || exit 1
exec python3 src/main.py "$@"
```

### run.bat（Windows）

```bat
@echo off
cd /d "%~dp0"
python src\main.py %*
```

### 部署到 UOS aarch64

```bash
# 1) 拷贝源码目录到家目录（离线环境用 U 盘）
cp -r ToolBox ~/
# 2) 跑自检看报告
cd ~/ToolBox && python3 src/main.py doctor
# 3) 启动
./run.sh
```

**前置条件只有一条**：目标机有 `python3`。不需要 pip、不需要联网、不需要 root、不需要任何第三方库。

### 固定到桌面

**Linux（`.desktop`，提前写好，到目标机微调）**

```ini
# ~/.local/share/applications/toolbox.desktop
[Desktop Entry]
Type=Application
Name=工具箱
Exec=/home/<user>/ToolBox/run.sh
Icon=/home/<user>/ToolBox/assets/icon.png
Terminal=false
Categories=Utility;
```

**Windows（`.lnk`，现在就能测）**

1. 右键 `run.bat` → 发送到 → 桌面快捷方式
2. 快捷方式属性 → 改图标为 `assets\icon.ico`
3. 把目标改为 `pythonw.exe src\main.py`（去掉控制台黑窗）

> `Exec=` 与 `Icon=` 必须写绝对路径。
> 注：`assets/`（图标）目前**未入库**，需要时自行放置 `icon.ico`（Windows）/ `icon.png`（Linux）；
> 不放也不影响功能，只是快捷方式用默认图标。

---

## 11. 风险与对策

| 风险 | 对策 |
|---|---|
| 浏览器不支持 `--app` | 降级为 `webbrowser.open`（有地址栏但可用）；再不行手开 URL |
| 目标机无图形环境 | `doctor` 报告 + 自动建议 CLI 承载；TodoList 有完整 CLI 可用 |
| 端口冲突 | **固定端口 + 明确报错**（绝不静默换端口，否则书签失效）；配合 `server.json` + `/api/identity` 做幂等启动 |
| 关掉启动窗口把服务带走 | 服务跑在**分离进程**（`DETACHED_PROCESS` + `pythonw.exe` / `start_new_session`） |
| 服务进程残留 | 空闲 12 小时自动退 + `stop` 子命令 + 界面「关闭服务」 |
| Windows `SO_REUSEADDR` 让两个进程绑同一端口 | 平台判断，**Windows 关闭 `allow_reuse_address`**（否则"端口被占用"分支永不触发） |
| 本机探测被 `http_proxy` 劫持 | `build_opener(ProxyHandler({}))` 显式绕过代理（内网机器常设代理） |
| 本机 CSRF | token + Host/Origin 校验（见 5.3） |
| 目标机 Python 版本过低 | 全局 3.7 兼容编码约定 + `doctor` 首行报告版本 |
| 中文输入 | 走浏览器，无需处理（相对 Tkinter 是优势） |

---

## 12. 开发里程碑

> 下表是**首版立项时的计划**，仅作历史记录；后续功能（多清单 / 到期日 / 重复任务 / 回收站 /
> 常驻服务 / 日历 / 日历联动等）都是在 M1–M4 之后增量做的，详见 §14 与 README。

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **M1** | 骨架 + `main.py` + `doctor` + Web 服务 + 入口页 + todo 空白页 | 浏览器打开能看到导航与 todo 页；`doctor` 报告完整 |
| **M2** | TodoList 完整功能（actions + 前端模块 + 持久化 + CLI） | 增删改查/完成态/过滤/中文输入均正常；重启后数据还在 |
| **M3** | 桌面启动（`run.sh` / `run.bat` / `.lnk` / `.desktop` / 图标） | Windows 上点桌面图标能无黑窗启动并打开 `--app` 窗口 |
| **M4** | 部署到目标机 | `doctor` 通过，浏览器名列表按需微调，`.desktop` 生效 |

**M1 + M2 是关键路径**——它们验证「UI 承载 ↔ action 契约 ↔ 持久化」这条主干。

---

## 13. 后续规划（首版不做）

架构已为以下工具预留扩展位，届时**只需新增 `tools/<name>/` 并在 `tools/__init__.py` 注册一行**：

- **filebatch（文件/批量处理）** —— 移植现有 PowerRename（Rust 版）的骨架：`rules` / `transform` / `preview` / `apply` / `fs_tree` / `list_io`
  - 两阶段改名（先临时名再目标名，防 A↔B 互换）
  - 冲突检测需覆盖：重名 · 非法字符 · Windows 保留名 · 结尾点/空格 · **大小写敏感差异（Linux 区分，Windows 不区分）**
  - 删除走回收站，永不硬删；操作可撤销
  - 前端需要文件/目录选择器 → 补 `POST /api/fs/list` + 目录树组件
- **doc（文档处理）** —— 只做「纯文件层」：docx/xlsx = zip + XML，用 `zipfile` + `xml.etree` 解析与比对，**不依赖任何 Office 自动化**
- **tkinter 承载层** —— 仅当确认目标机有 tkinter 且确实需要系统托盘时再做

---

## 14. 已确认的范围决策

> 下表是**当前实际状态**（含实现过程中变更的决策），不是首版立项时的样子。

| 事项 | 决定 |
|---|---|
| 项目名 | **ToolBox** |
| 现有工具 | **待办清单 + 日历**（保留注册表机制：加工具 = 新增 `tools/<name>/` + 注册一行） |
| 入口页 | **始终显示**，不做自适应隐藏 |
| 到期日 | **已实现**：`due` 字段 + 「已计划」视图 + 从日历跳入的「某天待办」。**系统提醒/通知不做**（避免引入后台定时任务） |
| 多清单 / 分类 | **已实现**：自定义清单 + 拖拽排序 + 置顶；兜底清单「未分类」固定排最后 |
| 重复任务 | **已实现**：每天 / 每周 / 每月，完成即**顺延**（同一张卡循环，不生成新卡）；自定义周期（每 2 天 / 每工作日）**暂缓** |
| 我的一天 | **已实现**：`my_day <= 今天 且未完成` 即可见，昨天没做完的自动延续 |
| 回收站 / 自动备份 | **已实现**：软删除 + 30 天回收站；写盘前备份轮转（防文件级损坏）。两者互补，都要有 |
| 任务拖拽排序 | **不做**（与自动排序互斥，用户已否） |
| 撤销（Undo） | **不做**（用户已否） |
| 标签筛选 | **暂缓**（标签本身已支持，只是还没有"按标签过滤"的入口） |
| 固定到桌面 | **做**，Windows 上先用 `.lnk` 验证，`.desktop` 模板一并入库 |
| 系统托盘 / 开机自启 | **不做** |
| 文件/目录选择器 | **不需要**（现有工具用不到），推迟到 filebatch |
| 常驻服务 | 固定端口 + 幂等启动（点一次 run 当天一直驻留），空闲 12 小时自动退出 |
