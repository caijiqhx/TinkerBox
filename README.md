# ToolBox

个人工具箱。本地 Web UI 承载，**纯 Python 标准库**，跨平台（Windows 开发 / aarch64 统信 UOS 运行）。

首版包含一个工具：**待办清单（TodoList）**。

---

## 待办清单

组织方式参考微软待办：

- **左栏分组**：我的一天 / 重要 / 已计划 / 全部任务 + 清单（默认「任务」+ 自定义）+ 已完成 / 回收站，每项带未完成计数
- **全部任务**：跨清单汇总所有未完成任务 —— 任务分散在多个清单时不用挨个点进去看
- **我的一天**：任务存的是一个日期，只有等于"今天"才出现在该视图 —— 所以每天自动清空，**不需要任何后台定时任务**
- **重要**：星标
- **已计划**：按到期日排序，并分组为 已过期 / 今天 / 明天 / 本周 / 以后
- **步骤**：任务可拆成子步骤，列表和详情里都显示 `2/5` 进度；**点步骤文字即可直接改**，打错字不必删掉重加
- **标签**：每条任务可加标签（最多 12 个），列表行显示前 3 个；**搜索会命中标签**
- **详情面板**：点任务行打开，可改标题、加步骤、设到期日、写备注、换所属清单。**按 Esc 收起面板**（焦点在输入框里时 Esc 是"放弃本次修改"，不会连带收起）
- **到期日快捷项**：**今天 / 明天**两个按钮，不用每次都去点日期选择器
- **清单**：点「新建清单」**不弹输入框**，直接建出「新清单 1」并**立刻进入改名状态**（想改就改，按 Esc 就用默认名）；之后切到该清单，**点标题也能改**。默认清单「任务」不可改名
- **搜索是全局的**：在任意视图下都能搜到全部任务（含步骤、标签与备注内容），不受当前视图限制，**命中的片段会高亮**
- **回收站**：**删除永远是软删除** —— 单条删除和「清理已完成」都会先把任务放进回收站，可在那里「恢复」或「彻底删除」，也能一键清空。回收站里的任务不出现在任何视图、计数和搜索结果里；里面的任务不能直接编辑，**先恢复再改**。默认保留 30 天，超期在保存时顺手清掉

数据存在 `data/todo.json`。旧版（v1 / v2）数据文件会被自动补齐字段，不需要手工迁移。

### 两道数据防线，各管一类事故

| | 管什么 | 在哪 |
|---|---|---|
| **自动备份**（`bak.1 … bak.5`） | 整个文件被写坏 / 被意外覆盖 / 断电 | `data/todo.json.bak.N` |
| **回收站** | 手滑删错了一条任务、误点了「清理已完成」 | 界面左栏「回收站」 |

**两者不能互相替代**：备份每次都跟着最新状态走，所以它救不了"删错一条"（任何后续操作都会把备份刷成"已删除"的版本）；而回收站救不了"文件本身被写坏"。所以两个都要有。

备份份数用 `data/config.json` 里的 `backup_keep` 调整，设 `0` 关闭；回收站保留天数用 `trash_keep_days`，设 `0` 表示永久保留。

**「已计划」里"本周"的口径**：一周以**周日结束**（后端 `model.week_end()`，唯一口径）。

---

## 快速开始

```bash
# Windows
run.bat

# Linux / 统信 UOS
./run.sh
```

启动脚本只负责**把服务拉起来**（默认不弹浏览器窗口），之后用浏览器访问
`http://127.0.0.1:8765` 即可 —— 建议存成书签。

想让启动时顺便弹出窗口，加 `--open`：

```bash
run.bat --open          # Windows
./run.sh --open         # Linux / 统信 UOS
```

（`--open` 会优先用浏览器 `--app` 模式打开无地址栏窗口；找不到 Chromium 内核浏览器时退化为普通标签页。）

### 运行方式：常驻

服务是**常驻**的 —— 关掉浏览器窗口后它继续留在后台，所以**一天只需要启动一次**：

```
早上点一次 run          → 服务起来（无窗口）
之后随时点浏览器书签     → 秒开（服务还在，不会重启）
晚上关机                → 服务自然结束
```

再次运行启动脚本**不会重复起服务**：它会先探测，发现已有实例就直接把地址打给你。

**黑窗可以直接关掉。** `run.bat` / `run.sh` 会把真正的服务放在一个**脱离终端的独立进程**里
（Windows 上走 `pythonw`，不附着任何控制台），启动脚本本身跑完就退出 ——
所以关掉那个终端窗口不会把服务带走。控制台里显示的启动结果只是反馈，
完整的运行输出在 `data/logs/service.out`。

**关闭服务**有三条路：

| 方式 | 适用场景 |
|---|---|
| 界面左下角「关闭服务」 | 界面还开着 |
| `run.bat stop` / `./run.sh stop` | 界面已经关了 |
| 连续 12 小时无请求自动退出 | 忘了关的兜底 |

**端口固定为 8765**，这样浏览器书签才能长期有效。若端口被别的程序占用，会**明确报错而不会偷偷换端口**——换端口只会让书签悄悄失效、而你不知道为什么。

### 其他用法

```bash
python3 src/main.py                        # 起服务（默认不弹浏览器）
python3 src/main.py --open                 # 起服务并自动打开浏览器窗口
python3 src/main.py status                 # 查看服务状态（端口、运行时长）
python3 src/main.py stop                   # 关闭后台服务
python3 src/main.py doctor                 # 环境自检（换机器后先跑这个）
python3 src/main.py help                   # 查看用法与工具列表
python3 src/main.py todo list              # 命令行使用待办清单
python3 src/main.py todo add "买牛奶" --due 2026-09-20
python3 src/main.py --no-browser           # 强制不打开浏览器（优先级高于 --open）
python3 src/main.py --detach               # 后台分离启动（run.bat / run.sh 默认走这条）
python3 src/main.py --force                # 忽略"已有实例在运行"，强行再起一个
TOOLBOX_UI=cli python3 src/main.py         # 强制 CLI（用于在当前机器上测降级路径）
```

### 可调配置

改 `data/config.json`（首次运行后自动生成）：

| 配置 | 默认 | 说明 |
|---|---|---|
| `port` | `8765` | 监听端口 |
| `keep_alive` | `true` | 关窗口后是否保留服务。改成 `false` 就回到"关窗口即退出"的老行为 |
| `idle_exit_hours` | `12` | 连续这么久没有任何请求就自动退出；`0` = 不限制 |
| `backup_keep` | `5` | 待办数据保留几份备份；`0` = 关闭备份 |
| `trash_keep_days` | `30` | 回收站保留多少天；`0` = 永久保留 |

还有一个**环境变量**（不是配置文件里的项）：

```bash
TOOLBOX_DATA_DIR=/tmp/toolbox-test python3 src/main.py
```

它整体改写数据目录，用途是**隔离测试** —— 例如跑冒烟脚本时不想碰真实待办。平时不需要设置。

运行信息（端口、进程号、实例标识）写在 `data/server.json`，服务正常退出时会自动清理。它只用于"重复点图标不要起第二个服务"这件事，删掉也不影响数据。

---

## 运行要求

**只有一条：目标机有 `python3`。**

不需要 pip、不需要联网、不需要 root、不需要任何第三方库。
（`tkinter` 不是必需项，缺失不影响运行 —— 它只是将来的可选增强。）

若需最低限度地使用，请确认：

```bash
python3 --version                    # Python 3.7 及以上
python3 -c "import http.server"      # 应当无输出
```

---

## 目录结构

```
ToolBox/
├─ src/
│  ├─ main.py            入口（Web UI / doctor / 工具子命令）
│  ├─ core/              契约层：Tool 基类、注册表、错误、路径
│  ├─ services/          公共服务：原子 JSON、配置、日志、平台差异
│  ├─ web/               承载层：HTTP 服务、路由、浏览器启动、doctor、静态前端
│  ├─ cli/               命令行的用法输出
│  └─ tools/todo/        待办清单（model / store / tool）
├─ tests/                单元测试（unittest，纯标准库）
├─ data/                 运行时数据：todo.json、config.json、logs/（不入库）
├─ run.sh / run.bat      启动脚本
└─ run-silent.vbs        Windows 无控制台窗口启动（给桌面快捷方式用）
```

**依赖方向严格单向**：`tools/*` → `core/` ← `web/`。

---

## 设计要点

**工具不感知 HTTP，也不感知 HTML。** 每个工具只暴露一组 `actions()`（入参 dict、出参可 JSON 序列化的结构），Web 路由层负责把请求映射到 action。

带来的好处：将来若要增加新的界面方式（例如 tkinter 承载层），或把工具搬到别的宿主上，**业务代码一行都不用改**。

**平台差异只允许出现在 `services/platform.py`。** 其余任何模块出现 `os.name` 之类的分支都视为设计违规 —— 这条纪律是跨平台确定性的工程保障。

**主题**：浅色以 Vue 官方文档配色为基准（品牌绿 `#42b883` + 深蓝 `#35495e`），深色用同色系的亮绿 `#42d392`。侧栏「主题」按钮循环切换 **浅色 → 深色 → 跟随系统**，偏好写入 `data/config.json`，重启后保持。

主题偏好由服务端注入 `<html data-theme-pref>`，并由 `<head>` 里的内联脚本在样式生效**之前**解析成 `data-theme` —— 所以打开页面时不会出现"先白后黑"的闪烁，也不需要写 `@media (prefers-color-scheme)`。配置接口只接受白名单内的键（`theme`、`window_size`），不会变成任意写入口。

**数据损坏不能让程序崩。** 读 JSON 一律降级处理：文件不存在、内容损坏、单条记录字段缺失，都在 `tools/todo/store.py` + `model.normalize()` 里被安全吸收。

**不调用浏览器原生弹窗。** 确认一律走外壳提供的 `ctx.confirm({...})`，返回 `Promise<boolean>`：

```js
ctx.confirm({ title: "删除任务", message: "删除「买牛奶」？",
              detail: "删除后无法撤销。", okText: "删除", danger: true })
   .then(function (ok) { if (ok) { /* ... */ } });
```

原生 `window.confirm` 有三个问题：样式跟主题无关、在 `--app` 窗口里会显示页面来源、且会阻塞整个页面。页内确认框就没有这些毛病 —— 支持 Esc 取消、回车确定、点遮罩取消、右上角 ✕，`danger: true` 时确定按钮渲染成红色。

---

## 新增一个工具

1. 在 `src/tools/` 下建包，实现 `Tool` 子类：

```python
from core.tool import Tool, ToolMeta

class MyTool(Tool):
    meta = ToolMeta(tid="mine", name="我的工具", desc="说明", icon="🔧", order=20)

    def actions(self):
        return {"hello": lambda payload: {"echo": payload}}
```

2. 在 `src/tools/__init__.py` 的 `register_all()` 里加一行 `registry.register(MyTool())`。
3. 前端在 `src/web/static/tools/` 加一个模块，用 `ToolBox.registerTool("mine", {render})` 注册，并在 `index.html` 里加一行 `<script>`。

**外壳与路由无需任何改动。**

---

## 测试

```bash
python3 -m unittest discover -s tests
```

---

## 部署到 aarch64 统信 UOS

```bash
# 1) 拷贝整个目录到家目录（离线环境用 U 盘）
cp -r ToolBox ~/

# 2) 自检
cd ~/ToolBox && python3 src/main.py doctor

# 3) 启动
./run.sh
```

### 固定到桌面 / 启动器

**Linux** —— 把下面内容存为 `~/.local/share/applications/toolbox.desktop`（路径需改成实际绝对路径）：

```ini
[Desktop Entry]
Type=Application
Name=工具箱
Exec=/home/<用户名>/ToolBox/run.sh
Icon=/home/<用户名>/ToolBox/assets/icon.png
Terminal=false
Categories=Utility;
```

**Windows** —— 右键 `run-silent.vbs` → 发送到 → 桌面快捷方式，再给快捷方式换图标即可（`run-silent.vbs` 用 `pythonw` 启动，不会弹出控制台黑窗口）。双击它只会**静默把服务拉起来**（没有任何窗口），然后点浏览器书签使用；只有启动失败时才会弹一个提示框。

---

## 已知边界

- **系统托盘**：Web UI 形态不支持。若将来确需，再考虑补一个 tkinter 承载层。
- **文件/目录选择器**：浏览器的安全限制使得页面拿不到本地路径，需要后端自建目录浏览接口。首版 TodoList 用不到，推迟到文件批处理工具时再做。
- **服务生命周期**：默认常驻，关窗口不关服务；退出只有「关闭服务」按钮 / `stop` / 空闲 12 小时三条路。把 `keep_alive` 改成 `false` 可回到"关窗口即退出"，那时才会启用 90 秒心跳超时兜底 —— 这个值刻意设得较大，因为浏览器会把后台标签页的定时器节流到约每分钟一次，设小了窗口一最小化就会被误杀。
