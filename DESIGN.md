# ToolBox 设计方案

> 个人工具箱 · 本地 Web UI 承载 · 纯标准库 · 跨平台（Windows 开发 / aarch64 UOS 运行）
>
> **首版功能范围：仅 TodoList 一个工具。**

---

## 0. 设计前提（硬约束）

| 约束 | 内容 | 原因 |
|---|---|---|
| **运行环境** | 目标机为 aarch64 UOS，**仅能确定有 python3** | 环境无法预先探测 |
| **功能范围** | **首版只做 TodoList**（架构保留多工具扩展能力） | 用户已收窄 |
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
| **中文输入** | ✅ **优于 Tkinter** | 走浏览器输入法，无需处理 XIM/fcitx |
| 固定到桌面/启动器 | ✅ 胜任 | `.desktop` 图标 + `--app` 无地址栏窗口 |
| 界面美观度 | ✅ 优于 Tkinter | HTML/CSS 表现力远超 Tk |
| **系统原生文件对话框** | ⚠️ 需自建 | 首版 TodoList **用不到**，可推迟 |
| 系统托盘常驻 | ❌ 不支持 | 若将来必需，才需要考虑 tkinter 承载层 |

**结论**：TodoList 的全部需求 Web UI 均可覆盖，**GUI 承载层不做**。

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
│  server.py  router.py  launcher.py  doctor.py│
└──────────────────┬──────────────────────────┘
                   │  统一 action 分发（与协议无关）
┌──────────────────▼──────────────────────────┐
│  core/  契约层                               │
│  Tool 基类 · 注册表 · ToolError · paths      │
└──────┬───────────────────────────┬──────────┘
       │                           │
┌──────▼────────┐          ┌───────▼──────────┐
│  services/    │          │  tools/          │
│  配置 存储 任务 │          │  todo            │
│ 日志 平台差异  │          │                  │
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
├─ run.sh                    # Linux 启动脚本
├─ run.bat                   # Windows 启动脚本
├─ src/
│  ├─ main.py                # 唯一入口
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ tool.py             # Tool 基类 + ToolMeta
│  │  ├─ registry.py         # 工具注册表
│  │  ├─ errors.py           # ToolError / 统一错误
│  │  └─ paths.py            # 跨平台路径（配置/数据目录）
│  ├─ services/
│  │  ├─ __init__.py
│  │  ├─ jsonio.py           # 原子 JSON 读写
│  │  ├─ config.py           # 全局配置
│  │  ├─ logs.py             # 日志
│  │  └─ platform.py         # 平台差异【全项目唯一允许平台分支处】
│  ├─ web/
│  │  ├─ __init__.py
│  │  ├─ server.py           # ThreadingHTTPServer 封装
│  │  ├─ router.py           # 路由 + action 分发 + token 校验
│  │  ├─ launcher.py         # 浏览器探测与 --app 启动
│  │  ├─ doctor.py           # 环境自检报告
│  │  └─ static/
│  │     ├─ index.html
│  │     ├─ app.js
│  │     ├─ style.css
│  │     └─ tools/
│  │        └─ todo.js       # TodoList 前端模块
│  ├─ cli/
│  │  └─ cli.py              # CLI 承载层（保底，100% 可用）
│  └─ tools/
│     ├─ __init__.py         # 注册工具（目前只有 todo）
│     └─ todo/
│        ├─ __init__.py
│        ├─ model.py         # Task 数据结构
│        ├─ store.py         # data/todo.json 原子读写
│        └─ tool.py          # Tool 实现（actions + cli）
├─ data/                     # 运行时数据（配置、todo.json、日志）
├─ tests/
└─ assets/                   # 图标（.ico / .png）
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
- **绑定 `127.0.0.1`，端口传 `0` 让系统动态分配**（避免冲突、避免局域网暴露），启动后读回实际端口
- 全部 API 走 JSON，响应统一包装：`{"ok": true, "data": ...}` / `{"ok": false, "error": "..."}`

### 5.2 路由

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回 `index.html`（注入 token） |
| GET | `/static/<path>` | 静态资源（限白名单，防目录穿越） |
| GET | `/api/tools` | 工具清单（id/name/desc/icon），供导航 / 入口页渲染 |
| POST | `/api/tool/<tid>/<action>` | body: `{"payload": {...}}` → 分发到 `tools.get(tid).actions()[action]` |
| GET | `/api/doctor` | 环境自检报告 |
| POST | `/api/ping` | 前端心跳，用于「关窗口即退出」 |
| POST | `/api/quit` | 主动退出 |

### 5.3 安全（必做，不是可选项）

本机服务有一个真实风险：**用户浏览器里的任意网页都能向 `127.0.0.1:<port>` 发请求**。防护三条：

1. **启动时生成随机 token**，从 `index.html` 注入前端；之后所有 `/api/*` 请求必须带 `X-Toolbox-Token` 头，服务端用 `hmac.compare_digest` 比对
2. **校验 `Host` 头**，只接受 `127.0.0.1` / `localhost`
3. **校验 `Origin` 头**（若存在），来源必须是自身地址

只监听回环地址 + 上述校验，即满足个人工具的安全边界。

### 5.4 生命周期

- **启动**：起服务 → 探测浏览器 → 用 `--app` 打开 → 主线程等待退出信号
- **退出**（两条并行）
  - 前端每 3 秒 `POST /api/ping`；服务端超过 10 秒未收到心跳 → 自动 shutdown（**关掉 `--app` 窗口即退，体验贴近原生应用**）
  - 页面提供「退出」按钮 → `POST /api/quit`
- **残留进程**：`KeyboardInterrupt` / `SIGTERM` 均走统一清理，避免端口与进程残留

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

### 5.6 前端（static/，无框架手写）

- `index.html`：入口页容器 + 左侧导航容器 + 右侧内容容器
- `app.js`
  - 启动时 `GET /api/tools` 渲染导航；按"工具数 > 1"规则决定是否显示入口页
  - hash 路由 `#/todo`，切换时调用对应工具模块的 `render(container, api)`
  - `api` 对象封装 `fetch`：自动带 token、自动解包 `{ok,data,error}`、统一错误提示
  - 心跳定时器
- `tools/todo.js`：导出 `render(container, api)`；只调 action，不写业务规则
- `style.css`：手写 CSS 变量做主题，深浅色可选

---

## 6. 服务层设计（services/）

| 模块 | 职责 | 关键点 |
|---|---|---|
| `jsonio.py` | JSON 原子读写 | 写临时文件 → `os.replace()` 覆盖；读失败给默认值，不崩 |
| `config.py` | 全局配置 | 存 `data/config.json`；`get/set` 与默认值合并 |
| `logs.py` | 日志 | 写 `data/logs/`，按日切分；UI 异常单独记录 |
| `platform.py` | 平台差异**唯一出口** | 见下 |

**`platform.py` 是全项目唯一允许出现平台分支的地方**：

```python
IS_WINDOWS = os.name == "nt"

def browser_candidates():   # 浏览器候选列表（按平台返回，Chromium 内核优先）
def has_display():          # 是否有图形环境
def is_case_sensitive():    # Windows 不区分大小写；Linux 区分（为将来 filebatch 预留）
def open_in_file_manager(path)
```

数据目录的选址（项目内 `data/` 优先，不可写时退回用户目录）放在 `core/paths.py`，与平台行为分开。

---

## 7. 入口设计（main.py）

```bash
python3 src/main.py                     # 默认：起服务（不弹浏览器窗口，用书签访问）
python3 src/main.py --open              # 起服务并自动打开浏览器窗口
python3 src/main.py --ui=cli            # 强制 CLI（TOOLBOX_UI=cli 亦可）
python3 src/main.py --ui=none --port=8765   # 只起服务，不开浏览器
python3 src/main.py --no-browser        # 强制不打开浏览器（优先级高于 --open）
python3 src/main.py doctor              # 环境自检并打印报告
python3 src/main.py todo list           # 直接调工具的 CLI 子命令
python3 src/main.py todo add "买牛奶"
```

**默认不弹浏览器窗口**：日常用法是点浏览器书签，启动脚本只负责把服务拉起来；
每次双击都弹窗纯属干扰。需要弹窗时显式加 `--open`。

**`--ui` / `TOOLBOX_UI` 的用途**：让你**在 Windows 开发机上就能测完所有承载路径**，不必真去找缺组件的机器。

**doctor 输出内容**：Python 版本与架构 · 关键标准库模块可用性 · 浏览器探测结果 · `DISPLAY`/`WAYLAND_DISPLAY` · 数据目录路径与可写性 · 推荐承载方式。

---

## 8. TodoList 设计

### 8.1 数据模型

任务直接用**普通 dict**表示（不用 dataclass）——它与 JSON 天然同构，省掉一层序列化往返，读写不易出错：

```python
# tools/todo/model.py
{
    "id":       "a1b2c3d4e5f6",   # uuid4 前 12 位
    "title":    "买牛奶",
    "status":   "todo",            # todo | doing | done
    "priority": 0,                 # 0 普通 / 1 重要 / 2 紧急
    "tags":     [],                # 字符串列表
    "note":     "",
    "created":  "2026-09-11 21:50:00",
    "updated":  "2026-09-11 21:50:00",
    "done_at":  "",                # 空串表示未完成
}
```

> 首版**不含到期日期与提醒**（用户已确认不做）；也**不做多清单**（暂用单列表 + 标签，多清单后续再说）。

### 8.2 持久化

- 单文件 `data/todo.json`，**原子写**（临时文件 → `os.replace`）
- 结构：`{"version": 1, "tasks": [...]}`（带 version 便于将来迁移）
- 读取容错：文件不存在 / 内容损坏 → 返回空列表并记录日志，**不抛异常、不崩 UI**

### 8.3 actions

| action | payload | 返回 |
|---|---|---|
| `list` | `{"filter": "all\|todo\|doing\|done", "keyword": ""}` | `{"tasks": [...], "stats": {...}}` |
| `add` | `{"title": "...", "priority": 0, "tags": []}` | 新建 Task |
| `update` | `{"id": "...", "fields": {...}}` | 更新后的 Task |
| `toggle` | `{"id": "..."}` | 更新后的 Task |
| `remove` | `{"id": "..."}` | `{"removed": "id"}` |
| `stats` | `{}` | 各状态计数 |

### 8.4 前端要点

- 顶部输入框：**回车即添加**（最高频操作要最顺手）
- 列表：复选框切换完成态 · 双击行内编辑 · 删除需一次确认
- 分组：进行中 / 已完成；支持按优先级排序
- 过滤：全部 / 未完成 / 已完成 + 关键词搜索
- **中文输入**：浏览器原生支持，无需额外处理

### 8.5 CLI

```bash
python3 src/main.py todo list
python3 src/main.py todo add "买牛奶"
python3 src/main.py todo done <id>
python3 src/main.py todo rm <id>
```

作用有两个：① 图形环境不可用时的保底；② **在 Windows 上验证核心逻辑不需要开浏览器**，调试更快。

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

---

## 11. 风险与对策

| 风险 | 对策 |
|---|---|
| 浏览器不支持 `--app` | 降级为 `webbrowser.open`（有地址栏但可用）；再不行手开 URL |
| 目标机无图形环境 | `doctor` 报告 + 自动建议 CLI 承载；TodoList 有完整 CLI 可用 |
| 端口冲突 | 端口传 `0`，由系统分配 |
| 服务进程残留 | 前端心跳超时自动退出 + 退出按钮 + `SIGTERM` 清理 |
| 本机 CSRF | token + Host/Origin 校验（见 5.3） |
| 目标机 Python 版本过低 | 全局 3.7 兼容编码约定 + `doctor` 首行报告版本 |
| 中文输入 | 走浏览器，无需处理（相对 Tkinter 是优势） |

---

## 12. 开发里程碑

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

| 事项 | 决定 |
|---|---|
| 项目名 | **ToolBox** |
| 首版功能范围 | **仅 TodoList**（保留注册表机制以便扩展） |
| 入口页 | **始终显示**，不做自适应隐藏 |
| 到期日期 / 提醒 | **不做**（避免引入后台定时任务） |
| 多清单 / 分类 | **不做**，暂用单列表 + 标签；后续可考虑 |
| 固定到桌面 | **做**，Windows 上先用 `.lnk` 验证，`.desktop` 模板一并入库 |
| 文件/目录选择器 | 首版**不需要**（TodoList 用不到），推迟到 filebatch |
