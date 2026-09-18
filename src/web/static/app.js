/* ToolBox 前端外壳
 *
 * 职责：导航 / 路由 / API 调用 / 提示与弹窗 / 心跳。
 * 业务逻辑一律不在这里 —— 每个工具注册自己的 render(container, ctx)。
 *
 * 语法上刻意保守（ES5 + 模板字符串），以兼容信创环境里内核较老的国产浏览器。
 */
(function (window, document) {
  "use strict";

  var TOKEN = window.__TOOLBOX_TOKEN__ || "";
  var tools = [];
  var registry = {};
  var heartbeatTimer = null;
  var saidGoodbye = false;

  /* ================= DOM 工具 ================= */

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      for (var key in attrs) {
        if (!Object.prototype.hasOwnProperty.call(attrs, key)) { continue; }
        var value = attrs[key];
        if (value === null || value === undefined) { continue; }
        if (key === "class") { node.className = value; }
        else if (key === "text") { node.textContent = String(value); }
        else if (key === "html") { node.innerHTML = value; }
        else if (key.indexOf("on") === 0 && typeof value === "function") {
          node.addEventListener(key.slice(2).toLowerCase(), value);
        } else { node.setAttribute(key, String(value)); }
      }
    }
    appendChildren(node, children);
    return node;
  }

  function appendChildren(node, children) {
    if (children === null || children === undefined) { return; }
    if (typeof children === "string" || typeof children === "number") {
      node.appendChild(document.createTextNode(String(children)));
      return;
    }
    if (children instanceof Array) {
      for (var i = 0; i < children.length; i++) { appendChildren(node, children[i]); }
      return;
    }
    if (children.nodeType) { node.appendChild(children); }
  }

  function clear(node) {
    while (node.firstChild) { node.removeChild(node.firstChild); }
  }

  function mainNode() { return document.getElementById("main"); }

  /* ================= 提示 / 弹窗 ================= */

  var toastTimer = null;

  function toast(message, isError) {
    var box = document.getElementById("toast");
    box.textContent = message;
    box.className = "toast show" + (isError ? " error" : "");
    if (toastTimer) { clearTimeout(toastTimer); }
    toastTimer = setTimeout(function () { box.className = "toast"; },
                            isError ? 4500 : 2200);
  }

  function openModal(title, content) {
    document.getElementById("modal-title").textContent = title;
    var body = document.getElementById("modal-body");
    clear(body);
    if (typeof content === "string") {
      body.appendChild(el("pre", { text: content }));
    } else if (content) {
      body.appendChild(content);
    }
    document.getElementById("modal").className = "modal";
  }

  function closeModal() {
    document.getElementById("modal").className = "modal hidden";
  }

  /* ---- 应用内确认框（替代 window.confirm）----
     浏览器原生弹窗有三个问题：样式跟主题无关、在 --app 窗口里会显示页面来源、
     而且它阻塞整个页面。这里做成页内对话框，返回 Promise<boolean>。 */
  var confirmResolve = null;

  function confirmDialog(options) {
    options = options || {};
    return new Promise(function (resolve) {
      confirmResolve = resolve;

      document.getElementById("confirm-title").textContent = options.title || "确认";

      var body = document.getElementById("confirm-body");
      clear(body);
      body.appendChild(el("div", { class: "confirm-text", text: options.message || "" }));
      if (options.detail) {
        body.appendChild(el("div", { class: "confirm-detail", text: options.detail }));
      }

      var ok = document.getElementById("confirm-ok");
      ok.textContent = options.okText || "确定";
      ok.className = "btn " + (options.danger ? "danger-solid" : "primary");
      document.getElementById("confirm-cancel").textContent = options.cancelText || "取消";

      document.getElementById("confirm").className = "modal";
      ok.focus();
    });
  }

  function confirmOpen() {
    return document.getElementById("confirm").className.indexOf("hidden") < 0;
  }

  /* 有对话框开着时，工具层的快捷键必须让位 ——
     否则在确认框里按 Esc 会同时把背后的详情面板也收起来。 */
  function dialogOpen() {
    return confirmOpen()
      || document.getElementById("modal").className.indexOf("hidden") < 0;
  }

  function settleConfirm(result) {
    if (!confirmOpen()) { return; }        // Esc 与点击可能先后到达，只认第一次
    document.getElementById("confirm").className = "modal hidden";
    var resolve = confirmResolve;
    confirmResolve = null;
    if (resolve) { resolve(result); }
  }

  /* ================= 自绘提示：接管 title =================

     原生 tooltip 由系统/浏览器绘制：页面切深色它仍是系统色（跟不了主题），
     还有 0.5~1 秒延迟、位置固定在指针右下（靠窗口右边会被裁）、
     在 --app 窗口里显示为系统气泡，且样式完全改不了（title 没有 CSS 接口）。

     做法：在 document 上做事件委托 —— 指针进入带 title 的元素时把文本取走、
     摘掉 title（不摘浏览器照样弹原生框），改用这层自绘提示显示。
     好处：工具模块一行都不用改，**以后新写的 title 也自动生效**。

     TIP_OPTIONS 是程序内开关（不进 config.json、也不做界面开关），方便按需调整：
     enabled 设 false 即可整体退回浏览器原生提示。 */
  var TIP_OPTIONS = {
    enabled: true,   /* 总开关：false = 完全用回浏览器原生 tooltip */
    delay: 350,      /* 悬停多久才浮现（ms）；原生框也有延迟，太快会"扫过一排疯狂闪现" */
    gap: 8,          /* 提示与元素之间的间距（px） */
    edge: 6          /* 与视口边缘至少留出的距离（px） */
  };

  var tipNode = null, tipTimer = null, tipOwner = null;

  function initTooltip() {
    if (!TIP_OPTIONS.enabled) { return; }   /* 关掉时完全不接管，title 原样交给浏览器 */
    tipNode = document.getElementById("tip");
    if (!tipNode) { return; }

    document.addEventListener("mouseover", onTipEnter, true);
    document.addEventListener("mouseout", onTipLeave, true);
    document.addEventListener("focusin", onTipEnter, true);
    document.addEventListener("focusout", onTipLeave, true);
    document.addEventListener("click", hideTip, true);
    document.addEventListener("scroll", hideTip, true);   /* 捕获：也能收到内层滚动容器 */
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { hideTip(); }
    });
  }

  /* 原生 tooltip 会向上找最近的带 title 的祖先元素 —— 这里保持同样口径，
     否则"行里的小图标没 title、行本身有"时会读不到。 */
  function tipHost(node) {
    var depth = 0;
    while (node && node.nodeType === 1 && depth < 8) {
      if (node.getAttribute("title") || node.getAttribute("data-tip")) { return node; }
      node = node.parentNode;
      depth += 1;
    }
    return null;
  }

  /* 取走文本：摘掉 title（否则原生框照弹）、留一份到 data-tip（下次直接用），
     并把内容补进 aria-label —— 纯图标按钮的唯一说明就是它。 */
  function takeTipText(host) {
    var text = host.getAttribute("title");
    if (text) {
      host.setAttribute("data-tip", text);
      host.removeAttribute("title");
      if (!host.getAttribute("aria-label")) {
        host.setAttribute("aria-label", text);
      }
      return text;
    }
    return host.getAttribute("data-tip") || "";
  }

  function onTipEnter(event) {
    var host = tipHost(event.target);
    if (!host || host === tipOwner) { return; }   /* 在同一元素内部移动，不重来 */
    var text = takeTipText(host);
    if (!text) { return; }
    tipOwner = host;
    if (tipTimer) { clearTimeout(tipTimer); }
    tipTimer = setTimeout(function () {
      tipTimer = null;
      showTip(host, text);
    }, TIP_OPTIONS.delay);
  }

  /* 指针仍在同一元素（含其子元素）内时不隐藏，否则行内小图标之间移动会闪 */
  function onTipLeave(event) {
    if (!tipOwner) { return; }
    var to = event.relatedTarget;
    if (to && tipOwner.contains && tipOwner.contains(to)) { return; }
    hideTip();
  }

  function hideTip() {
    if (tipTimer) { clearTimeout(tipTimer); tipTimer = null; }
    tipOwner = null;
    if (tipNode) {
      tipNode.textContent = "";
      tipNode.className = "tip hidden";
    }
  }

  function showTip(host, text) {
    if (!host || host !== tipOwner || !tipNode) { return; }
    tipNode.textContent = text;
    tipNode.className = "tip";
    if (!host.getBoundingClientRect) { return; }   /* DOM 桩环境：不定位，退化为居中默认 */

    var box = host.getBoundingClientRect();
    var w = tipNode.offsetWidth || 0;
    var h = tipNode.offsetHeight || 0;
    var vw = window.innerWidth || 0;
    var vh = window.innerHeight || 0;

    /* 默认在元素下方居中；下面放不下就翻到上方；左右再夹进视口 */
    var left = box.left + box.width / 2 - w / 2;
    var top = box.bottom + TIP_OPTIONS.gap;
    if (vh && top + h > vh - TIP_OPTIONS.edge) {
      top = box.top - h - TIP_OPTIONS.gap;
    }
    if (vw && left + w > vw - TIP_OPTIONS.edge) { left = vw - w - TIP_OPTIONS.edge; }
    if (left < TIP_OPTIONS.edge) { left = TIP_OPTIONS.edge; }
    if (top < TIP_OPTIONS.edge) { top = TIP_OPTIONS.edge; }

    tipNode.style.left = Math.round(left) + "px";
    tipNode.style.top = Math.round(top) + "px";
  }

  /* ================= API ================= */

  function request(method, path, payload) {
    var options = { method: method, headers: { "X-Toolbox-Token": TOKEN } };
    if (payload !== undefined && payload !== null) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify({ payload: payload });
    }
    return fetch(path, options).then(function (resp) {
      return resp.text().then(function (text) {
        var data = null;
        try { data = JSON.parse(text); } catch (e) { data = null; }
        if (!data) {
          throw new Error("服务返回了非 JSON 响应（HTTP " + resp.status + "）");
        }
        if (!data.ok) { throw new Error(data.error || "请求失败"); }
        return data.data;
      });
    });
  }

  function apiGet(path) { return request("GET", path, null); }
  function apiPost(path, payload) { return request("POST", path, payload || {}); }

  function callTool(toolId, action, payload) {
    return request("POST",
      "/api/tool/" + encodeURIComponent(toolId) + "/" + encodeURIComponent(action),
      payload || {});
  }

  /* ================= 路由 ================= */

  function currentKey() {
    var hash = window.location.hash || "#/";
    hash = hash.replace(/^#/, "");
    hash = hash.split("?")[0];
    if (hash === "" || hash === "/") { return "/"; }
    if (hash.charAt(0) !== "/") { hash = "/" + hash; }
    hash = hash.replace(/\/+$/, "");
    return hash === "" ? "/" : hash;
  }

  function setActiveNav(key) {
    var items = document.querySelectorAll(".nav-item");
    for (var i = 0; i < items.length; i++) {
      var route = items[i].getAttribute("data-route");
      items[i].className = (route === key) ? "nav-item active" : "nav-item";
    }
  }

  function findTool(id) {
    for (var i = 0; i < tools.length; i++) {
      if (tools[i].id === id) { return tools[i]; }
    }
    return null;
  }

  function emptyBlock(text, icon) {
    return el("div", { class: "empty" }, [
      el("span", { class: "empty-icon", text: icon || "◌" }),
      el("div", { text: text })
    ]);
  }

  function pageHead(title, desc) {
    return el("div", { class: "page-head" }, [
      el("h1", { class: "page-title", text: title }),
      el("p", { class: "page-desc", text: desc || "" })
    ]);
  }

  function navIcon(tool) {
    var span = el("span", { class: "nav-icon" });
    if (tool.icon_html) {
      span.innerHTML = tool.icon_html;
    } else {
      span.textContent = tool.icon || "◆";
    }
    return span;
  }

  function renderNav() {
    var nav = document.getElementById("nav");
    while (nav.children.length > 1) { nav.removeChild(nav.lastChild); }
    for (var i = 0; i < tools.length; i++) {
      (function (tool) {
        nav.appendChild(el("a", {
          class: "nav-item",
          href: "#/" + tool.id,
          "data-route": "/" + tool.id
        }, [
          navIcon(tool),
          el("span", { text: tool.name })
        ]));
      })(tools[i]);
    }
  }

  function cardIcon(tool) {
    var span = el("span", { class: "card-icon" });
    if (tool.icon_html) {
      span.innerHTML = tool.icon_html;
      span.classList.add("svg");
    } else {
      span.textContent = tool.icon || "◆";
    }
    return span;
  }

  function renderHome() {
    var main = mainNode();
    clear(main);
    main.appendChild(pageHead("工具箱", "选择一个工具开始使用。"));

    if (!tools.length) {
      main.appendChild(emptyBlock("还没有注册任何工具"));
      return;
    }

    var grid = el("div", { class: "cards" });
    for (var i = 0; i < tools.length; i++) {
      (function (tool) {
        grid.appendChild(el("button", {
          class: "card",
          onclick: function () { window.location.hash = "#/" + tool.id; }
        }, [
          cardIcon(tool),
          el("div", { class: "card-name", text: tool.name }),
          el("div", { class: "card-desc", text: tool.desc || "" })
        ]));
      })(tools[i]);
    }
    main.appendChild(grid);
  }

  function renderTool(id) {
    var main = mainNode();
    clear(main);

    var meta = findTool(id) || { name: id, desc: "" };
    main.appendChild(pageHead(meta.name, meta.desc));

    var mod = registry[id];
    if (!mod || typeof mod.render !== "function") {
      main.appendChild(emptyBlock("工具「" + id + "」尚未提供前端界面", "⚠"));
      return;
    }

    var body = el("div", { class: "page-body" });
    main.appendChild(body);
    try {
      mod.render(body, ctx);
    } catch (err) {
      body.appendChild(emptyBlock("界面渲染失败：" + err.message, "⚠"));
      if (window.console) { window.console.error(err); }
    }
  }

  function route() {
    var key = currentKey();
    setActiveNav(key);
    if (key === "/") { renderHome(); return; }
    renderTool(key.slice(1));
  }

  /* ================= 环境自检 / 退出 ================= */

  function showDoctor() {
    openModal("环境自检", "正在检测…");
    apiGet("/api/doctor").then(function (data) {
      openModal("环境自检", (data && data.text) || "无报告内容");
    }).catch(function (err) {
      openModal("环境自检", "检测失败：" + err.message);
    });
  }

  function quitApp() {
    confirmDialog({
      title: "关闭服务",
      message: "确定要关闭工具箱服务吗？",
      detail: "关闭后这个页面就会失效，下次使用需要重新运行启动脚本。",
      okText: "关闭服务",
      danger: true
    }).then(function (ok) {
      if (!ok) { return; }
      saidGoodbye = true;
      apiPost("/api/quit").catch(function () { /* 服务即将关闭，忽略 */ });

      var node = document.getElementById("server-status");
      if (node) { node.textContent = "服务已关闭"; }

      var main = mainNode();
      clear(main);
      main.appendChild(pageHead("服务已关闭", "可以直接关掉这个窗口了。下次使用请重新运行启动脚本。"));
      main.appendChild(emptyBlock("感谢使用", "✓"));
    });
  }

  /* ================= 服务状态 ================= */

  function humanDuration(seconds) {
    seconds = Math.max(0, Math.floor(seconds || 0));
    if (seconds < 60) { return seconds + " 秒"; }
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) { return minutes + " 分钟"; }
    var hours = Math.floor(minutes / 60);
    var rest = minutes % 60;
    if (hours < 24) {
      return rest ? (hours + " 小时 " + rest + " 分钟") : (hours + " 小时");
    }
    return Math.floor(hours / 24) + " 天 " + (hours % 24) + " 小时";
  }

  /* 侧栏底部那行小字：常驻模式下服务一直在后台，给个可见的凭据 */
  function refreshStatus() {
    var node = document.getElementById("server-status");
    apiGet("/api/status").then(function (data) {
      if (!node) { return; }
      node.textContent = "服务运行中 · 端口 " + data.port + " · " + humanDuration(data.uptime);
      var detail = "启动于 " + (data.started || "-")
        + (data.keep_alive
            ? "\n常驻模式：关掉窗口后服务会继续留在后台"
            : "\n跟随窗口：关掉窗口即退出");
      /* 提示层接管过这个元素后（有 data-tip），就写回 data-tip —— 否则每分钟
         重新塞回 title，恰好悬停时会让浏览器漏出一次原生提示框 */
      if (node.getAttribute("data-tip") !== null) {
        node.setAttribute("data-tip", detail);
      } else {
        node.title = detail;
      }
    }).catch(function () {
      if (node) { node.textContent = "服务状态未知"; }
    });
  }

  /* ================= 心跳与退出通知 ================= */

  function startHeartbeat() {
    if (heartbeatTimer) { clearInterval(heartbeatTimer); }
    heartbeatTimer = setInterval(function () {
      apiPost("/api/ping").catch(function () { /* 静默 */ });
    }, 15000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) { apiPost("/api/ping").catch(function () {}); }
    });
  }

  function sayGoodbye() {
    if (saidGoodbye) { return; }
    saidGoodbye = true;
    var url = "/api/bye?t=" + encodeURIComponent(TOKEN);
    try {
      if (navigator.sendBeacon) { navigator.sendBeacon(url, "{}"); return; }
    } catch (e) { /* 继续尝试 fetch */ }
    try { fetch(url, { method: "POST", keepalive: true }); } catch (e) { /* 忽略 */ }
  }

  /* ================= 主题 ================= */

  var THEME_ORDER = ["light", "dark", "auto"];
  var THEME_LABELS = { light: "浅色", dark: "深色", auto: "跟随系统" };
  var themePref = "auto";

  function prefersDark() {
    return !!(window.matchMedia
      && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }

  /* CSS 只认 data-theme（light / dark）；"跟随系统"在这里解析成实际值。
     data-theme-pref 保留用户的原始偏好，切换按钮和系统主题变化都依赖它。 */
  function applyTheme(pref) {
    if (THEME_ORDER.indexOf(pref) < 0) { pref = "auto"; }
    themePref = pref;

    var resolved = (pref === "auto") ? (prefersDark() ? "dark" : "light") : pref;
    document.documentElement.setAttribute("data-theme", resolved);
    document.documentElement.setAttribute("data-theme-pref", pref);

    var button = document.getElementById("btn-theme");
    if (button) { button.textContent = "主题：" + THEME_LABELS[pref]; }
  }

  function cycleTheme() {
    var next = THEME_ORDER[(THEME_ORDER.indexOf(themePref) + 1) % THEME_ORDER.length];
    applyTheme(next);
    apiPost("/api/config", { theme: next }).catch(function (err) {
      toast("主题已切换，但保存到配置文件失败：" + err.message, true);
    });
  }

  function initTheme() {
    applyTheme(document.documentElement.getAttribute("data-theme-pref") || "auto");

    if (window.matchMedia) {
      var query = window.matchMedia("(prefers-color-scheme: dark)");
      var onChange = function () {
        if (themePref === "auto") { applyTheme("auto"); }
      };
      if (query.addEventListener) { query.addEventListener("change", onChange); }
      else if (query.addListener) { query.addListener(onChange); }
    }
  }

  /* ================= 对外接口 ================= */

  var ctx = {
    apiGet: apiGet,
    apiPost: apiPost,
    callTool: callTool,
    toast: toast,
    confirm: confirmDialog,
    dialogOpen: dialogOpen,
    openModal: openModal,
    closeModal: closeModal,
    go: function (key) { window.location.hash = "#" + key; },
    el: el,
    clear: clear,
    /* 日期选择浮层（页内自绘）—— 实现在 ui/datepicker.js，加载后挂到 window.ToolBox.datePicker。
       这里只做一层转发：工具侧认 ctx.pickDate，不直接依赖那个模块，模块缺席时也不会崩。 */
    pickDate: function (options) {
      var picker = window.ToolBox && window.ToolBox.datePicker;
      if (!picker) { return false; }
      picker.open(options);
      return true;
    }
  };

  window.ToolBox = {
    registerTool: function (id, mod) { registry[id] = mod; },
    toast: toast,
    confirm: confirmDialog,
    el: el,
    clear: clear,
    ctx: ctx
  };

  /* ================= 启动 ================= */

  function boot() {
    /* 自绘日期选择浮层（ui/datepicker.js 若已加载）—— 需要 ctx 才能取日历数据 */
    if (window.ToolBox.datePicker) { window.ToolBox.datePicker.init(ctx); }

    document.getElementById("btn-theme").addEventListener("click", cycleTheme);
    document.getElementById("btn-doctor").addEventListener("click", showDoctor);
    document.getElementById("btn-quit").addEventListener("click", quitApp);
    document.getElementById("modal-close").addEventListener("click", closeModal);
    document.getElementById("modal").addEventListener("click", function (event) {
      if (event.target === this) { closeModal(); }
    });

    /* 确认框：确定 / 取消 / 右上角 ✕ / 点遮罩都算回答，Esc 取消、回车确定 */
    document.getElementById("confirm-ok").addEventListener("click", function () {
      settleConfirm(true);
    });
    document.getElementById("confirm-cancel").addEventListener("click", function () {
      settleConfirm(false);
    });
    document.getElementById("confirm-x").addEventListener("click", function () {
      settleConfirm(false);
    });
    document.getElementById("confirm").addEventListener("click", function (event) {
      if (event.target === this) { settleConfirm(false); }
    });
    document.addEventListener("keydown", function (event) {
      if (!confirmOpen()) { return; }
      if (event.key === "Escape") {
        settleConfirm(false);
      } else if (event.key === "Enter") {
        // 焦点在某个按钮上时交给按钮自己处理（否则"取消"会被回车变成"确定"）
        var tag = (event.target && event.target.tagName) || "";
        if (tag !== "BUTTON") { settleConfirm(true); }
      }
    });
    window.addEventListener("hashchange", route);
    window.addEventListener("pagehide", sayGoodbye);
    window.addEventListener("beforeunload", sayGoodbye);

    initTheme();
    initTooltip();          /* 接管 title，换成跟主题一致的自绘提示（开关见 TIP_OPTIONS） */
    refreshStatus();
    setInterval(refreshStatus, 60000);

    apiGet("/api/tools").then(function (data) {
      tools = (data && data.tools) || [];
      renderNav();
      route();
    }).catch(function (err) {
      toast("加载工具列表失败：" + err.message, true);
      route();
    });

    startHeartbeat();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(window, document);
