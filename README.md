# ToolBox

个人工具箱。本地 Web UI 承载，**纯 Python 标准库**，跨平台（Windows 开发 / aarch64 统信 UOS 运行）。

首版包含一个工具：**待办清单（TodoList）**。

---

## 待办清单

组织方式参考微软待办：

- **左栏分组**：我的一天 / 重要 / 已计划 + 清单（默认「任务」+ 自定义）+ 已完成，每项带未完成计数
- **我的一天**：任务存的是一个日期，只有等于"今天"才出现在该视图 —— 所以每天自动清空，**不需要任何后台定时任务**
- **重要**：星标
- **已计划**：按到期日排序，并分组为 已过期 / 今天 / 明天 / 本周 / 以后
- **步骤**：任务可拆成子步骤，列表和详情里都显示 `2/5` 进度
- **详情面板**：点任务行打开，可改标题、加步骤、设到期日（原生日期选择器）、写备注、换所属清单
- **搜索是全局的**：在任意视图下都能搜到全部任务（含步骤与备注内容），不受当前视图限制

数据存在 `data/todo.json`。旧版（v1）数据文件会被自动补齐字段，不需要手工迁移。

---

## 快速开始

```bash
# Windows
run.bat

# Linux / 统信 UOS
./run.sh
```

不加参数即启动 Web UI：程序会以浏览器的 `--app` 模式打开一个**无地址栏的独立窗口**，观感接近原生桌面应用；**关闭该窗口即退出程序**。

### 其他用法

```bash
python3 src/main.py doctor                 # 环境自检（换机器后先跑这个）
python3 src/main.py help                   # 查看用法与工具列表
python3 src/main.py todo list              # 命令行使用待办清单
python3 src/main.py todo add "买牛奶" --pri 1 --tag 生活
python3 src/main.py --no-browser           # 只起服务，手动访问打印出的地址
python3 src/main.py --port=8765            # 指定端口（默认 0 = 自动选空闲端口）
TOOLBOX_UI=cli python3 src/main.py        # 强制 CLI（用于在当前机器上测降级路径）
```

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

**Windows** —— 右键 `run-silent.vbs` → 发送到 → 桌面快捷方式，再给快捷方式换图标即可（`run-silent.vbs` 用 `pythonw` 启动，不会弹出控制台黑窗口）。

---

## 已知边界

- **系统托盘**：Web UI 形态不支持。若将来确需，再考虑补一个 tkinter 承载层。
- **文件/目录选择器**：浏览器的安全限制使得页面拿不到本地路径，需要后端自建目录浏览接口。首版 TodoList 用不到，推迟到文件批处理工具时再做。
- **退出机制**：关闭页面时通过 `sendBeacon` 通知服务退出（主路径）；另有心跳超时兜底（90 秒），该值刻意设置得较大 —— 浏览器会把后台标签页的定时器节流到约每分钟一次，设太小会导致窗口最小化时误退出。
