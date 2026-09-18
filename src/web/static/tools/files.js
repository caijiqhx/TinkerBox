/* 文件浏览前端模块。
 *
 * 只做两件事：展示后端返回的文件信息、把用户的操作翻成 action 调用。
 * **不判断任何业务规则**（能不能打开、路径是否越界都在后端）。
 *
 * 结构约定：工具栏（位置栏、排序、筛选框）**只建一次**，之后只重绘
 * 面包屑 / 列表 / 状态行 —— 否则每次刷新都会把输入框重建，用户打字打到一半
 * 焦点就丢了。
 */
(function (window, document) {
  "use strict";

  /* ================= 图标 =================
     一律用内联 SVG：项目里踩过"目标机字体缺字形，符号变问号"的坑。 */
  var ICONS = {
    folder: '<svg viewBox="0 0 16 16" class="ic" width="15" height="15" fill="none" ' +
      'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M1.9 4.3h4.2l1.3 1.7h6.7v6.1a1 1 0 0 1-1 1H2.9a1 1 0 0 1-1-1z"/></svg>',
    file: '<svg viewBox="0 0 16 16" class="ic" width="15" height="15" fill="none" ' +
      'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M9 1.9H4.4a1 1 0 0 0-1 1v10.2a1 1 0 0 0 1 1h7.2a1 1 0 0 0 1-1V5.4z"/>' +
      '<path d="M9 1.9v3.5h3.6"/></svg>',
    link: '<svg viewBox="0 0 16 16" class="ic" width="15" height="15" fill="none" ' +
      'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M6.6 9.4a2.4 2.4 0 0 0 3.4 0l2.3-2.3a2.4 2.4 0 0 0-3.4-3.4l-.8.8"/>' +
      '<path d="M9.4 6.6a2.4 2.4 0 0 0-3.4 0L3.7 8.9a2.4 2.4 0 0 0 3.4 3.4l.8-.8"/></svg>',
    up: '<svg viewBox="0 0 16 16" class="ic" width="15" height="15" fill="none" ' +
      'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M8 12.5V3.5"/><path d="M4 7.4 8 3.4l4 4"/></svg>',
    add: '<svg viewBox="0 0 16 16" class="ic" width="13" height="13" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
      '<path d="M8 3.5v9"/><path d="M3.5 8h9"/></svg>',
    close: '<svg viewBox="0 0 16 16" class="ic" width="11" height="11" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
      '<path d="M4 4l8 8"/><path d="M12 4l-8 8"/></svg>',
    open: '<svg viewBox="0 0 16 16" class="ic" width="13" height="13" fill="none" ' +
      'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M6.5 3.4H3.9a1 1 0 0 0-1 1v7.7a1 1 0 0 0 1 1h7.7a1 1 0 0 0 1-1V9.5"/>' +
      '<path d="M9.8 2.6h3.6v3.6"/><path d="M13 3 7.6 8.4"/></svg>',
    find: '<svg viewBox="0 0 16 16" class="ic" width="13" height="13" fill="none" ' +
      'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">' +
      '<circle cx="7.2" cy="7.2" r="3.9"/><path d="M10.2 10.2 13.4 13.4"/></svg>',
    arrow: '<svg viewBox="0 0 16 16" class="ic" width="10" height="10" fill="none" ' +
      'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="M4 6l4 4 4-4"/></svg>'
  };

  /* ================= 状态 ================= */

  var ctx = null;
  var nodes = {};              /* 只建一次的骨架节点 */
  var state = {
    roots: [],
    quick: [],
    path: "",
    parent: "",
    crumbs: [],
    items: [],
    total: 0,
    matched: 0,
    shown: 0,
    hidden: 0,
    truncated: false,
    note: "",
    store: "",
    sort: "name",
    desc: false,
    keyword: "",
    showHidden: false,
    selected: "",
    addOpen: false,
    /* 路径比较口径由后端给出：Windows 不区分大小写、Linux 区分 */
    caseSensitive: false
  };
  var keywordTimer = null;

  var SORT_LABELS = [["name", "名称"], ["size", "大小"], ["time", "修改时间"]];

  function call(action, payload) {
    return ctx.callTool("files", action, payload || {});
  }

  /* ================= 骨架（只建一次） ================= */

  function render(container, context) {
    ctx = context;

    var shell = ctx.el("div", { class: "fb-shell" });

    nodes.placeBar = ctx.el("div", { class: "fb-places" });
    nodes.addPanel = ctx.el("div", { class: "fb-add hidden" });
    nodes.crumbs = ctx.el("div", { class: "fb-crumbs" });
    nodes.list = ctx.el("div", { class: "fb-list" });
    nodes.foot = ctx.el("div", { class: "fb-foot" });

    shell.appendChild(nodes.placeBar);
    shell.appendChild(nodes.addPanel);
    shell.appendChild(buildBar());
    shell.appendChild(nodes.list);
    shell.appendChild(nodes.foot);
    container.appendChild(shell);

    loadInfo().then(function () {
      if (state.roots.length) {
        go(state.last || state.roots[0].path);
      } else {
        renderEmptyStart();
      }
    });
  }

  /* 工具行：面包屑 + 排序 + 显示隐藏 + 筛选。**只建一次**。 */
  function buildBar() {
    var upBtn = ctx.el("button", {
      class: "ico-btn fb-up",
      html: ICONS.up,
      title: "上一级",
      onclick: function () { if (state.parent) { go(state.parent); } }
    });
    nodes.upBtn = upBtn;

    nodes.crumbStrip = ctx.el("div", { class: "fb-crumb-strip" });

    var hiddenBox = ctx.el("input", { type: "checkbox", class: "fb-check" });
    hiddenBox.checked = state.showHidden;
    hiddenBox.addEventListener("change", function () {
      state.showHidden = hiddenBox.checked;
      refresh();
    });

    nodes.keywordInput = ctx.el("input", {
      class: "input fb-search",
      type: "search",
      placeholder: "筛选名称…",
      title: "按名称筛选当前目录"
    });
    nodes.keywordInput.addEventListener("input", function () {
      if (keywordTimer) { window.clearTimeout(keywordTimer); }
      keywordTimer = window.setTimeout(function () {
        state.keyword = nodes.keywordInput.value.trim();
        refresh();
      }, 260);
    });

    var bar = ctx.el("div", { class: "fb-bar" }, [
      upBtn,
      nodes.crumbStrip,
      ctx.el("div", { class: "fb-tools" }, [
        ctx.el("label", { class: "fb-toggle", title: "显示以点开头的隐藏条目" }, [
          hiddenBox, ctx.el("span", { text: "隐藏项" })
        ]),
        nodes.keywordInput
      ])
    ]);
    return bar;
  }

  /* ================= 位置栏 ================= */

  function loadInfo() {
    return call("info").then(function (data) {
      state.roots = (data && data.roots) || [];
      state.quick = (data && data.quick) || [];
      state.store = (data && data.store) || "";
      state.last = (data && data.last) || "";
      state.caseSensitive = !!(data && data.case_sensitive);
      renderPlaces();
      renderAddPanel();
      return data;
    }).catch(function (err) {
      ctx.toast(err.message, true);
    });
  }

  function renderPlaces() {
    var box = nodes.placeBar;
    ctx.clear(box);
    box.appendChild(ctx.el("span", { class: "fb-places-label", text: "位置" }));

    if (!state.roots.length) {
      box.appendChild(ctx.el("span", { class: "fb-muted", text: "还没有添加位置" }));
    }

    state.roots.forEach(function (root) {
      var active = state.path && samePath(state.path, root.path);
      var chip = ctx.el("span", {
        class: "fb-place" + (active ? " active" : ""),
        title: root.path
      }, [
        ctx.el("button", {
          class: "fb-place-name",
          text: root.label,
          onclick: function () { go(root.path); }
        }),
        ctx.el("button", {
          class: "fb-place-del",
          html: ICONS.close,
          title: "移除这个位置（只从列表移除，不动文件夹）",
          onclick: function () { removeRoot(root); }
        })
      ]);
      box.appendChild(chip);
    });

    box.appendChild(ctx.el("button", {
      class: "btn small ghost fb-add-btn",
      html: ICONS.add + "<span>添加位置</span>",
      title: "添加一个可浏览的文件夹",
      onclick: function () { toggleAdd(!state.addOpen); }
    }));
  }

  function renderAddPanel() {
    var box = nodes.addPanel;
    ctx.clear(box);
    if (!state.addOpen) {
      box.className = "fb-add hidden";
      return;
    }
    box.className = "fb-add";

    box.appendChild(ctx.el("div", { class: "fb-add-tip",
      text: "选择一个常用位置，或直接填写文件夹路径。只读：不会改动、删除任何文件。" }));

    if (state.quick.length) {
      var chips = ctx.el("div", { class: "fb-quick" });
      state.quick.forEach(function (item) {
        chips.appendChild(ctx.el("button", {
          class: "chip fb-quick-item",
          text: item.label,
          title: item.path,
          onclick: function () {
            call("add_root", { path: item.path }).then(function () {
              return loadInfo();
            }).then(function () {
              toggleAdd(false);
              go(item.path);
            }).catch(function (err) { ctx.toast(err.message, true); });
          }
        }));
      });
      box.appendChild(chips);
    }

    var input = ctx.el("input", {
      class: "input fb-add-input",
      type: "text",
      placeholder: "例如 /home/用户名/文档",
      title: "填写一个存在的文件夹路径"
    });
    function submit() {
      var value = input.value.trim();
      if (!value) { return; }
      call("add_root", { path: value }).then(function () {
        return loadInfo();
      }).then(function () {
        input.value = "";
        toggleAdd(false);
        go(value);
      }).catch(function (err) { ctx.toast(err.message, true); });
    }
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") { submit(); }
    });

    box.appendChild(ctx.el("div", { class: "fb-add-row" }, [
      input,
      ctx.el("button", { class: "btn primary small", text: "添加", onclick: submit })
    ]));
  }

  function toggleAdd(open) {
    state.addOpen = open;
    renderAddPanel();
  }

  function removeRoot(root) {
    ctx.confirm({
      title: "移除位置",
      message: "把「" + root.label + "」从列表里移除？\n（只是不再浏览它，文件夹本身不会有任何改动）",
      okText: "移除"
    }).then(function (yes) {
      if (!yes) { return; }
      call("remove_root", { path: root.path }).then(function () {
        return loadInfo();
      }).then(function () {
        if (!state.roots.length) {
          state.path = "";
          renderEmptyStart();
        } else if (!state.path) {
          go(state.roots[0].path);
        }
      }).catch(function (err) { ctx.toast(err.message, true); });
    });
  }

  /* ================= 导航与列目录 ================= */

  function go(path) {
    state.selected = "";
    return call("list", {
      path: path,
      sort: state.sort,
      desc: state.desc,
      keyword: state.keyword,
      show_hidden: state.showHidden
    }).then(function (data) {
      applyList(data);
      return data;
    }).catch(function (err) {
      ctx.toast(err.message, true);
    });
  }

  function refresh() {
    if (!state.path) { return; }
    return go(state.path);
  }

  function applyList(data) {
    state.path = (data && data.path) || "";
    state.parent = (data && data.parent) || "";
    state.crumbs = (data && data.crumbs) || [];
    state.items = (data && data.items) || [];
    state.total = (data && data.total) || 0;
    state.matched = (data && data.matched) || 0;
    state.shown = (data && data.shown) || 0;
    state.hidden = (data && data.hidden) || 0;
    state.truncated = !!(data && data.truncated);
    state.note = (data && data.note) || "";
    state.store = (data && data.store) || state.store;

    nodes.upBtn.className = "ico-btn fb-up" + (state.parent ? "" : " disabled");
    renderPlaces();
    renderCrumbs();
    renderList();
    renderFoot();
  }

  function renderCrumbs() {
    var box = nodes.crumbStrip;
    ctx.clear(box);
    state.crumbs.forEach(function (crumb, index) {
      if (index > 0) {
        box.appendChild(ctx.el("span", { class: "fb-sep", text: "/" }));
      }
      var last = index === state.crumbs.length - 1;
      box.appendChild(ctx.el("button", {
        class: "fb-crumb" + (last ? " current" : ""),
        text: crumb.label,
        title: crumb.path,
        onclick: function () { if (!last) { go(crumb.path); } }
      }));
    });
  }

  function renderEmptyStart() {
    ctx.clear(nodes.crumbs);
    ctx.clear(nodes.foot);
    var box = nodes.list;
    ctx.clear(box);
    box.appendChild(ctx.el("div", { class: "empty" }, [
      ctx.el("span", { class: "empty-icon", html: ICONS.folder }),
      ctx.el("div", { text: "还没有添加任何位置" }),
      ctx.el("div", { class: "fb-hint",
        text: "点上面的「添加位置」选一个常用位置，或直接填写文件夹路径。" })
    ]));
  }

  /* ================= 列表 ================= */

  function renderList() {
    var box = nodes.list;
    ctx.clear(box);

    if (!state.path) { return; }

    /* 表头：名称 / 大小 / 修改时间可点排序 */
    var head = ctx.el("div", { class: "fb-head" });
    SORT_LABELS.forEach(function (pair) {
      var key = pair[0];
      var active = state.sort === key;
      head.appendChild(ctx.el("button", {
        class: "fb-col fb-col-" + key + (active ? " active" : ""),
        title: "按" + pair[1] + "排序（再点一次切换升降）",
        onclick: function () { changeSort(key); }
      }, [
        ctx.el("span", { text: pair[1] }),
        active ? ctx.el("span", { class: "fb-sort-mark" + (state.desc ? " desc" : ""), html: ICONS.arrow }) : null
      ]));
    });
    head.appendChild(ctx.el("span", { class: "fb-col-acts" }));
    box.appendChild(head);

    if (!state.items.length) {
      var text = state.keyword ? ("没有匹配「" + state.keyword + "」的条目")
                               : "这个文件夹是空的";
      box.appendChild(ctx.el("div", { class: "empty" }, [
        ctx.el("span", { class: "empty-icon", text: "◌" }),
        ctx.el("div", { text: text })
      ]));
      return;
    }

    state.items.forEach(function (item) {
      box.appendChild(buildRow(item));
    });
  }

  function buildRow(item) {
    var usable = !!item.path;                 /* 越界链接没有可回传路径 */
    var cls = "fb-row";
    if (item.dir) { cls += " is-dir"; }
    if (!usable) { cls += " unusable"; }
    if (state.selected && item.path && samePath(state.selected, item.path)) { cls += " picked"; }

    var glyph = item.link ? ICONS.link : (item.dir ? ICONS.folder : ICONS.file);
    var nameCell = ctx.el("span", { class: "fb-name" }, [
      ctx.el("span", { class: "fb-ico", html: glyph }),
      ctx.el("span", { class: "fb-name-text", text: item.name })
    ]);
    if (item.broken) {
      nameCell.appendChild(ctx.el("span", { class: "chip fb-bad", text: "名字异常" }));
    }
    if (item.link) {
      nameCell.appendChild(ctx.el("span", { class: "chip fb-link", text: "链接" }));
    }
    if (item.error) {
      nameCell.appendChild(ctx.el("span", { class: "chip fb-bad", text: item.error }));
    }

    var acts = ctx.el("span", { class: "fb-col-acts" });
    if (usable && !item.dir) {
      acts.appendChild(ctx.el("button", {
        class: "ico-btn",
        html: ICONS.open,
        title: item.openable ? "用系统默认程序打开" : "这类文件不能直接打开（可在文件管理器中打开）",
        onclick: function (event) {
          event.stopPropagation();
          openItem(item);
        }
      }));
    }
    if (usable) {
      acts.appendChild(ctx.el("button", {
        class: "ico-btn",
        html: ICONS.find,
        title: item.dir ? "在系统文件管理器中打开这个文件夹" : "在系统文件管理器中定位",
        onclick: function (event) {
          event.stopPropagation();
          revealItem(item);
        }
      }));
    }

    var row = ctx.el("div", {
      class: cls,
      title: item.path || (item.escapes ? "指向已添加位置之外，无法进入" : item.name),
      onclick: function () {
        state.selected = item.path || "";
        renderList();
      },
      ondblclick: function () { activate(item); }
    }, [
      nameCell,
      ctx.el("span", { class: "fb-size", text: item.dir ? "" : (item.size_text || "") }),
      ctx.el("span", { class: "fb-time", text: item.mtime_text || "" }),
      acts
    ]);
    return row;
  }

  function renderFoot() {
    var box = nodes.foot;
    ctx.clear(box);

    var bits = [];
    bits.push("共 " + state.matched + " 项");
    if (state.truncated) { bits.push("已显示前 " + state.shown + " 项"); }
    if (state.hidden) { bits.push("另有 " + state.hidden + " 个隐藏项"); }
    box.appendChild(ctx.el("span", { text: bits.join(" · ") }));
    if (state.note) {
      box.appendChild(ctx.el("span", { class: "fb-note", text: state.note }));
    }
    if (state.store) {
      box.appendChild(ctx.el("span", { class: "fb-store", text: "位置清单：" + state.store }));
    }
  }

  function changeSort(key) {
    if (state.sort === key) {
      state.desc = !state.desc;
    } else {
      state.sort = key;
      state.desc = false;
    }
    renderList();
    refresh();
  }

  /* ================= 交给系统 ================= */

  function activate(item) {
    if (!item.path) {
      ctx.toast(item.escapes ? "这一项指向已添加位置之外，无法进入" : "这一项无法访问", true);
      return;
    }
    if (item.dir) { go(item.path); return; }
    openItem(item);
  }

  function openItem(item) {
    if (!item.path) { return; }
    if (!item.openable) {
      ctx.toast("这类文件不能直接打开，可以用「在文件管理器中打开」", true);
      return;
    }
    call("open", { path: item.path }).then(function () {
      ctx.toast("已交给系统默认程序打开");
    }).catch(function (err) { ctx.toast(err.message, true); });
  }

  function revealItem(item) {
    if (!item.path) { return; }
    call("reveal", { path: item.path }).then(function () {
      ctx.toast(item.dir ? "已在文件管理器中打开" : "已在文件管理器中定位");
    }).catch(function (err) { ctx.toast(err.message, true); });
  }

  /* ================= 小工具 ================= */

  /* 路径比较：跟后端 guard.key 同一口径。
     不能一律转小写 —— Linux 上 /home/A 与 /home/a 是两个不同的目录。 */
  function samePath(a, b) {
    a = String(a || "");
    b = String(b || "");
    if (!a || !b) { return false; }
    if (a === b) { return true; }
    return state.caseSensitive ? false : a.toLowerCase() === b.toLowerCase();
  }

  window.ToolBox.registerTool("files", { render: render });
})(window, document);
