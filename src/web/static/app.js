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
          el("span", { class: "nav-icon", text: tool.icon || "◆" }),
          el("span", { text: tool.name })
        ]));
      })(tools[i]);
    }
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
          el("span", { class: "card-icon", text: tool.icon || "◆" }),
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
    if (!window.confirm("确定要退出工具箱吗？")) { return; }
    saidGoodbye = true;
    apiPost("/api/quit").catch(function () { /* 服务即将关闭，忽略 */ });
    var main = mainNode();
    clear(main);
    main.appendChild(pageHead("已退出", "服务已关闭，可以直接关闭这个窗口。"));
    main.appendChild(emptyBlock("感谢使用", "✓"));
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
    openModal: openModal,
    closeModal: closeModal,
    go: function (key) { window.location.hash = "#" + key; },
    el: el,
    clear: clear
  };

  window.ToolBox = {
    registerTool: function (id, mod) { registry[id] = mod; },
    toast: toast,
    el: el,
    clear: clear,
    ctx: ctx
  };

  /* ================= 启动 ================= */

  function boot() {
    document.getElementById("btn-theme").addEventListener("click", cycleTheme);
    document.getElementById("btn-doctor").addEventListener("click", showDoctor);
    document.getElementById("btn-quit").addEventListener("click", quitApp);
    document.getElementById("modal-close").addEventListener("click", closeModal);
    document.getElementById("modal").addEventListener("click", function (event) {
      if (event.target === this) { closeModal(); }
    });
    window.addEventListener("hashchange", route);
    window.addEventListener("pagehide", sayGoodbye);
    window.addEventListener("beforeunload", sayGoodbye);

    initTheme();

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
