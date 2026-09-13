/* 待办清单 —— 前端界面（参考微软待办）
 *
 * 布局：左栏分组（我的一天 / 重要 / 已计划 + 清单 + 已完成）
 *       中栏任务列表（已计划视图按日期分组）
 *       右栏任务详情（步骤 / 标记 / 到期日 / 备注 / 所属清单）
 *
 * 只负责渲染与交互，所有业务规则都在后端 action 里。
 *
 * 一个实现要点：工具栏（添加框、搜索框）只在 render() 时创建一次 ——
 * 如果放进每次刷新都重建的区域，输入框会在每次按键后失焦。
 */
(function (window, document) {
  "use strict";

  var ctx = null;
  var el = null;

  var shell = null, railBox = null, headBox = null, listBox = null, detailBox = null;
  var stepsBox = null, searchInput = null;

  var state = {
    view: "my_day",
    listId: "default",
    keyword: "",
    board: null,
    selected: null,
    stepDraft: "",
    renaming: false        /* 刚建完清单：下一次渲染要把标题输入框聚焦起来 */
  };

  var VIEW_META = {
    my_day:    { icon: "☀", label: "我的一天" },
    important: { icon: "★", label: "重要" },
    planned:   { icon: "◷", label: "已计划" },
    completed: { icon: "✓", label: "已完成" }
  };

  var WEEKDAY = "日一二三四五六";

  /* ================= 小工具 ================= */

  function pad2(value) { return (value < 10 ? "0" : "") + value; }

  function isoToday() {
    var now = new Date();
    return now.getFullYear() + "-" + pad2(now.getMonth() + 1) + "-" + pad2(now.getDate());
  }

  function dayDiff(value) {
    var parts = String(value).split("-");
    if (parts.length !== 3) { return 0; }
    var target = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    var now = new Date();
    var base = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.round((target.getTime() - base.getTime()) / 86400000);
  }

  function dateLabel(value) {
    if (!value) { return ""; }
    var diff = dayDiff(value);
    if (diff === 0) { return "今天"; }
    if (diff === 1) { return "明天"; }
    if (diff === -1) { return "昨天"; }
    if (diff < 0) { return "过期 " + Math.abs(diff) + " 天"; }
    var parts = value.split("-");
    if (diff < 7) {
      var day = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
      return "周" + WEEKDAY.charAt(day.getDay());
    }
    return Number(parts[1]) + "月" + Number(parts[2]) + "日";
  }

  function stepProgress(task) {
    var steps = task.steps || [];
    var done = 0;
    for (var i = 0; i < steps.length; i++) {
      if (steps[i].done) { done += 1; }
    }
    return { done: done, total: steps.length };
  }

  function inMyDay(task) {
    return !!task.my_day && task.my_day === isoToday();
  }

  /* 把命中的关键词拆成 <mark>。只用于展示，拼接一律走 textContent。 */
  function highlight(text, keyword) {
    var raw = String(text || "");
    var needle = String(keyword || "");
    if (!needle) { return document.createTextNode(raw); }

    var lower = raw.toLowerCase();
    var target = needle.toLowerCase();
    var frag = document.createDocumentFragment();
    var from = 0;
    var found = false;
    for (;;) {
      var at = lower.indexOf(target, from);
      if (at < 0) { break; }
      if (at > from) { frag.appendChild(document.createTextNode(raw.slice(from, at))); }
      frag.appendChild(el("mark", { class: "hit", text: raw.slice(at, at + needle.length) }));
      from = at + needle.length;
      found = true;
    }
    if (!found) { return document.createTextNode(raw); }
    if (from < raw.length) { frag.appendChild(document.createTextNode(raw.slice(from))); }
    return frag;
  }

  function isSelected(task) {
    return !!state.selected && state.selected.id === task.id;
  }

  /* ================= 数据 ================= */

  /* 重建 DOM 会把主滚动区（#main）滚回顶部 —— 表现就是"点一下按钮，页面跳到最上面"。
     直接原因：被删掉的那个按钮还带着焦点，浏览器把焦点退回 body 时顺手滚了一次。
     这里在重建前后把滚动位置搬回去，不管浏览器具体走哪条路径都不会跳；
     再补一帧是防"焦点回退之后才滚"的引擎。 */
  function keepScroll(rebuild) {
    var box = document.getElementById("main");
    var top = box ? box.scrollTop : 0;
    var page = window.pageYOffset || 0;

    function restore() {
      var node = document.getElementById("main");
      if (node && top) { node.scrollTop = top; }
      if (page) { window.scrollTo(0, page); }
    }

    rebuild();
    restore();
    if (window.requestAnimationFrame) { window.requestAnimationFrame(restore); }
  }

  function refresh() {
    return ctx.callTool("todo", "board", {
      view: state.view,
      list_id: state.listId,
      keyword: state.keyword
    }).then(function (data) {
      state.board = data;
      syncSelection(data);
      keepScroll(function () {
        renderHead();
        renderRail();
        renderList();
        renderDetail();
      });
      return data;
    }).catch(function (err) {
      ctx.toast("读取待办失败：" + err.message, true);
      return null;
    });
  }

  /* 当前选中的任务若出现在新数据里，就用新数据覆盖本地副本，
     这样别的操作（比如在列表里勾选）也会反映到详情面板。 */
  function syncSelection(data) {
    if (!state.selected) { return; }
    var groups = (data && data.groups) || [];
    for (var i = 0; i < groups.length; i++) {
      var tasks = groups[i].tasks || [];
      for (var j = 0; j < tasks.length; j++) {
        if (tasks[j].id === state.selected.id) {
          state.selected = tasks[j];
          return;
        }
      }
    }
  }

  function act(action, payload) {
    return ctx.callTool("todo", action, payload).then(function (data) {
      if (data && data.task && state.selected && data.task.id === state.selected.id) {
        state.selected = data.task;
      }
      return refresh();
    }).catch(function (err) {
      ctx.toast(err.message, true);
      return null;
    });
  }

  /* ================= 左栏 ================= */

  function railItem(options) {
    /* 用 div 而不是 button：条目里还要放「删除清单」按钮，
       而 button 嵌套 button 是非法 HTML，浏览器会自动闭合外层标签，
       导致整个左栏结构错乱。 */
    var item = el("div", {
      class: "rail-item" + (options.active ? " active" : ""),
      title: options.title || options.label,
      onclick: options.onclick
    }, [
      el("span", { class: "rail-ico", text: options.icon || "" }),
      el("span", { class: "rail-label", text: options.label })
    ]);

    if (options.count) {
      item.appendChild(el("span", { class: "rail-count", text: String(options.count) }));
    }
    if (options.onRemove) {
      item.appendChild(el("button", {
        class: "rail-mini",
        text: "✕",
        title: "删除清单",
        onclick: function (event) {
          event.stopPropagation();
          options.onRemove();
        }
      }));
    }
    return item;
  }

  function goView(view) {
    state.view = view;
    if (view !== "list") { state.listId = "default"; }
    state.keyword = "";
    if (searchInput) { searchInput.value = ""; }
    refresh();
  }

  function goList(listId) {
    state.view = "list";
    state.listId = listId;
    state.keyword = "";
    if (searchInput) { searchInput.value = ""; }
    refresh();
  }

  function renderRail() {
    if (!railBox) { return; }
    ctx.clear(railBox);

    var board = state.board || {};
    var views = board.views || {};
    var lists = board.lists || [];

    var order = ["my_day", "important", "planned"];
    for (var i = 0; i < order.length; i++) {
      (function (key) {
        var meta = VIEW_META[key];
        railBox.appendChild(railItem({
          icon: meta.icon,
          label: meta.label,
          count: views[key] || 0,
          active: state.view === key,
          onclick: function () { goView(key); }
        }));
      })(order[i]);
    }

    railBox.appendChild(el("div", { class: "rail-sep" }));
    railBox.appendChild(el("div", { class: "rail-head", text: "清单" }));

    for (var n = 0; n < lists.length; n++) {
      (function (item) {
        var isDefault = item.id === "default";
        railBox.appendChild(railItem({
          icon: isDefault ? "▤" : "•",
          label: item.name,
          count: item.count || 0,
          active: state.view === "list" && state.listId === item.id,
          title: item.name,
          onclick: function () { goList(item.id); },
          onRemove: isDefault ? null : function () { removeList(item); }
        }));
      })(lists[n]);
    }

    railBox.appendChild(el("div", {
      class: "rail-item",
      onclick: addList
    }, [
      el("span", { class: "rail-ico", text: "+" }),
      el("span", { class: "rail-label", text: "新建清单" })
    ]));

    railBox.appendChild(el("div", { class: "rail-sep" }));
    railBox.appendChild(railItem({
      icon: VIEW_META.completed.icon,
      label: VIEW_META.completed.label,
      count: views.completed || 0,
      active: state.view === "completed",
      onclick: function () { goView("completed"); }
    }));
  }

  function addList() {
    /* 不再弹输入框问名字：让后端取一个不重名的默认名（新清单 1 / 2 …），
       建好后切到该清单并直接进入改名状态 —— 少一次打断，想改也能立刻改。 */
    ctx.callTool("todo", "add_list", {}).then(function (data) {
      var item = data && data.list;
      if (!item) { return refresh(); }
      state.renaming = true;
      return goList(item.id);
    }).catch(function (err) {
      ctx.toast(err.message, true);
    });
  }

  function removeList(item) {
    ctx.confirm({
      title: "删除清单",
      message: "删除清单「" + item.name + "」？",
      detail: "其中的任务会移回「任务」，不会丢失。",
      okText: "删除",
      danger: true
    }).then(function (ok) {
      if (!ok) { return; }
      if (state.view === "list" && state.listId === item.id) {
        state.listId = "default";
      }
      act("remove_list", { list_id: item.id });
    });
  }

  /* ================= 中栏 ================= */

  function renderHead() {
    if (!headBox) { return; }
    ctx.clear(headBox);

    var board = state.board || {};
    var label = "";
    if (state.keyword) {
      label = board.title || ("搜索：" + state.keyword);
    } else if (state.view === "list") {
      label = board.title || "任务";
    } else {
      label = VIEW_META[state.view] ? VIEW_META[state.view].label : "";
    }

    var titleNode = listTitleNode(label);
    headBox.appendChild(titleNode);
    if (state.renaming) {
      /* 新建清单后直接进入改名状态：想改就改，不想改按 Esc 或点开别处 */
      state.renaming = false;
      if (titleNode.tagName === "INPUT") {
        titleNode.focus();
        titleNode.select();
      }
    }

    var sub = "";
    if (state.view === "my_day" && !state.keyword) {
      sub = board.today || "";
    }
    var shown = (board.shown === undefined) ? 0 : board.shown;
    sub = (sub ? sub + " · " : "") + shown + " 项";

    if (state.view === "completed" && shown) {
      headBox.appendChild(el("div", { class: "list-sub", text: sub }));
      headBox.appendChild(el("button", {
        class: "btn small ghost",
        text: "清理已完成",
        onclick: function () {
          ctx.confirm({
            title: "清理已完成",
            message: "清理全部 " + shown + " 项已完成任务？",
            detail: "清理后无法撤销。",
            okText: "清理",
            danger: true
          }).then(function (ok) {
            if (ok) { act("clear_done", {}); }
          });
        }
      }));
    } else {
      headBox.appendChild(el("div", { class: "list-sub", text: sub }));
    }
  }

  /* 自定义清单的标题可以直接改 —— 和详情面板里"点标题改标题"是同一套交互，
     比在左栏里再挤一个按钮更好按，也不占宽度。默认清单不可改名（后端也会拒绝）。 */
  function listTitleNode(label) {
    var item = null;
    if (state.view === "list" && !state.keyword) {
      var lists = (state.board && state.board.lists) || [];
      for (var i = 0; i < lists.length; i++) {
        if (lists[i].id === state.listId) { item = lists[i]; break; }
      }
    }
    if (!item || item.id === "default") {
      return el("div", { class: "list-title", text: label });
    }

    var mine = item;
    var input = el("input", {
      class: "list-title list-title-input",
      type: "text",
      title: "改完按回车即保存",
      onkeydown: function (event) {
        if (event.key === "Enter") { input.blur(); }
        else if (event.key === "Escape") { input.value = mine.name; input.blur(); }
      },
      onblur: function () {
        var value = String(input.value || "").trim();
        if (!value || value === mine.name) { input.value = mine.name; return; }
        act("rename_list", { list_id: mine.id, name: value });
      }
    });
    input.value = mine.name;
    return input;
  }

  function dueChip(task) {
    if (!task.due) { return null; }
    var diff = dayDiff(task.due);
    var cls = "chip";
    if (task.status !== "done") {
      if (diff < 0) { cls += " overdue"; }
      else if (diff <= 1) { cls += " soon"; }
    }
    return el("span", { class: cls, text: dateLabel(task.due), title: task.due });
  }

  function progressChip(task) {
    var info = stepProgress(task);
    if (!info.total) { return null; }
    return el("span", {
      class: "chip" + (info.done === info.total ? " progress" : ""),
      text: "步骤 " + info.done + "/" + info.total,
      title: "已完成 " + info.done + " / " + info.total + " 个步骤"
    });
  }

  /* 列表行里最多显示几个标签，多的折叠成 +N —— 免得长标签把整行撑爆 */
  function tagChips(task, limit) {
    var all = task.tags || [];
    var nodes = [];
    var shown = Math.min(all.length, limit);
    for (var i = 0; i < shown; i++) {
      nodes.push(el("span", { class: "chip tag", text: all[i] }));
    }
    if (all.length > shown) {
      nodes.push(el("span", { class: "chip", text: "+" + (all.length - shown) }));
    }
    return nodes;
  }

  function taskRow(task) {
    var done = task.status === "done";
    var row = el("div", {
      class: "task" + (done ? " done" : "") + (isSelected(task) ? " active" : "")
    });

    var check = el("input", {
      class: "check",
      type: "checkbox",
      title: done ? "标记为未完成" : "标记为已完成",
      onchange: function () { act("toggle", { id: task.id }); }
    });
    if (done) { check.checked = true; }
    row.appendChild(check);

    var meta = el("div", { class: "task-meta" });
    if (task.important) {
      meta.appendChild(el("span", { class: "chip", text: "★" }));
    }
    if (inMyDay(task) && state.view !== "my_day") {
      meta.appendChild(el("span", { class: "chip", text: "☀" }));
    }
    var progress = progressChip(task);
    if (progress) { meta.appendChild(progress); }
    var due = dueChip(task);
    if (due) { meta.appendChild(due); }
    var tagNodes = tagChips(task, 3);
    for (var ti = 0; ti < tagNodes.length; ti++) {
      meta.appendChild(tagNodes[ti]);
    }

    var title = el("div", { class: "task-title" }, [highlight(task.title, state.keyword)]);
    var main = el("div", {
      class: "task-main",
      title: "点击查看详情",
      onclick: function () { selectTask(task); }
    }, [title]);
    if (meta.children.length) { main.appendChild(meta); }
    row.appendChild(main);

    row.appendChild(el("div", { class: "task-actions" }, [
      el("button", {
        class: "ico-btn" + (task.important ? " star-on" : ""),
        text: "★",
        title: task.important ? "取消重要" : "标记为重要",
        onclick: function () { act("toggle_important", { id: task.id }); }
      }),
      el("button", {
        class: "ico-btn" + (inMyDay(task) ? " day-on" : ""),
        text: "☀",
        title: inMyDay(task) ? "移出我的一天" : "加入我的一天",
        onclick: function () { act("toggle_my_day", { id: task.id }); }
      }),
      el("button", {
        class: "ico-btn",
        text: "✕",
        title: "删除任务",
        onclick: function () {
          ctx.confirm({
            title: "删除任务",
            message: "删除「" + task.title + "」？",
            detail: "删除后无法撤销。",
            okText: "删除",
            danger: true
          }).then(function (ok) {
            if (!ok) { return; }
            if (isSelected(task)) { state.selected = null; }
            act("remove", { id: task.id });
          });
        }
      })
    ]));

    return row;
  }

  function renderList() {
    if (!listBox) { return; }
    ctx.clear(listBox);

    var board = state.board || {};
    var groups = board.groups || [];

    if (!groups.length) {
      listBox.appendChild(el("div", { class: "empty" }, [
        el("span", { class: "empty-icon", text: "◌" }),
        el("div", { text: emptyHint() })
      ]));
      return;
    }

    for (var i = 0; i < groups.length; i++) {
      var group = groups[i];
      if (group.label) {
        listBox.appendChild(el("div", {
          class: "group-head" + (group.key === "overdue" ? " overdue" : ""),
          text: group.label
        }));
      }
      var tasks = group.tasks || [];
      for (var j = 0; j < tasks.length; j++) {
        listBox.appendChild(taskRow(tasks[j]));
      }
    }
  }

  function emptyHint() {
    if (state.keyword) { return "没有匹配「" + state.keyword + "」的任务"; }
    if (state.view === "my_day") { return "今天还没有安排任务，用任务上的 ☀ 按钮加进来"; }
    if (state.view === "important") { return "还没有标星的任务"; }
    if (state.view === "planned") { return "还没有设置到期日的任务"; }
    if (state.view === "completed") { return "还没有已完成的任务"; }
    return "这个清单还是空的，在上面输入一条吧";
  }

  function selectTask(task) {
    state.selected = task;
    state.stepDraft = "";
    renderList();
    renderDetail();
  }

  /* ================= 右栏：详情 ================= */

  function removeFrom(list, value) {
    var result = [];
    for (var i = 0; i < list.length; i++) {
      if (list[i] !== value) { result.push(list[i]); }
    }
    return result;
  }

  /* 标签是整体替换：后端 update 收到什么就是什么。
     keepFocus 专给"连续添加"用 —— 刷新会重建详情面板，加完得把光标放回输入框。 */
  function saveTags(task, next, keepFocus) {
    return act("update", { id: task.id, fields: { tags: next } }).then(function () {
      if (!keepFocus || !detailBox) { return; }
      var node = detailBox.querySelector(".tag-input");
      if (node) { node.focus(); }
    });
  }

  function renderDetail() {
    if (!detailBox) { return; }
    ctx.clear(detailBox);
    shell.className = "todo-shell" + (state.selected ? "" : " without-detail");

    var task = state.selected;
    if (!task) {
      detailBox.appendChild(el("div", {
        class: "detail-empty",
        html: "点击左侧任务查看详情<br>步骤 · 到期日 · 备注"
      }));
      return;
    }

    /* --- 标题 --- */
    var titleInput = el("input", {
      class: "detail-title",
      type: "text",
      title: "回车或移开焦点即保存",
      onkeydown: function (event) {
        if (event.key === "Enter") { titleInput.blur(); }
        else if (event.key === "Escape") { titleInput.value = task.title; titleInput.blur(); }
      },
      onblur: function () {
        var value = String(titleInput.value || "").trim();
        if (!value) { titleInput.value = task.title; return; }
        if (value !== task.title) {
          act("update", { id: task.id, fields: { title: value } });
        }
      }
    });
    titleInput.value = task.title;
    detailBox.appendChild(titleInput);

    /* --- 步骤 --- */
    var info = stepProgress(task);
    var stepsSection = el("div", { class: "detail-sec" }, [
      el("div", { class: "detail-label" }, [
        el("span", { text: "步骤" }),
        el("span", { text: info.total ? (info.done + " / " + info.total) : "" })
      ])
    ]);
    stepsBox = el("div");
    drawSteps(task);
    stepsSection.appendChild(stepsBox);

    var stepInput = el("input", {
      class: "input step-input grow",
      type: "text",
      placeholder: "添加步骤，回车确定"
    });
    stepInput.value = state.stepDraft || "";
    stepInput.addEventListener("input", function () { state.stepDraft = stepInput.value; });
    stepInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter") { addStep(task); }
    });
    stepsSection.appendChild(el("div", { class: "step-add" }, [
      stepInput,
      el("button", { class: "btn small", text: "添加", onclick: function () { addStep(task); } })
    ]));
    detailBox.appendChild(stepsSection);

    /* --- 标记 --- */
    detailBox.appendChild(el("div", { class: "detail-sec" }, [
      el("div", { class: "detail-label" }, [el("span", { text: "标记" })]),
      el("div", { class: "detail-row" }, [
        el("button", {
          class: "toggle-btn" + (inMyDay(task) ? " on" : ""),
          text: "☀ 我的一天",
          onclick: function () { act("toggle_my_day", { id: task.id }); }
        }),
        el("button", {
          class: "toggle-btn" + (task.important ? " on" : ""),
          text: "★ 重要",
          onclick: function () { act("toggle_important", { id: task.id }); }
        })
      ])
    ]));

    /* --- 标签 --- */
    var tags = (task.tags || []).slice();
    var tagRow = el("div", { class: "detail-row" });
    for (var tg = 0; tg < tags.length; tg++) {
      (function (tag) {
        tagRow.appendChild(el("span", { class: "chip tag" }, [
          el("span", { text: tag }),
          el("button", {
            class: "tag-x",
            text: "✕",
            title: "移除标签「" + tag + "」",
            onclick: function () { saveTags(task, removeFrom(tags, tag), false); }
          })
        ]));
      })(tags[tg]);
    }
    if (!tags.length) {
      tagRow.appendChild(el("span", { class: "detail-label", text: "还没有标签" }));
    }

    var tagInput = el("input", {
      class: "input tag-input",
      type: "text",
      placeholder: "加标签，回车确定"
    });
    tagInput.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") { return; }
      var value = String(tagInput.value || "").trim();
      if (!value) { return; }
      tagInput.value = "";
      if (tags.indexOf(value) >= 0) { return; }
      saveTags(task, tags.concat([value]), true);
    });
    detailBox.appendChild(el("div", { class: "detail-sec" }, [
      el("div", { class: "detail-label" }, [el("span", { text: "标签" })]),
      tagRow,
      tagInput
    ]));

    /* --- 到期日 --- */
    var dueInput = el("input", { class: "input", type: "date" });
    dueInput.value = task.due || "";
    dueInput.addEventListener("change", function () {
      act("update", { id: task.id, fields: { due: dueInput.value } });
    });
    var dueLabel = el("div", { class: "detail-label" }, [el("span", { text: "到期日" })]);
    if (task.due) {
      dueLabel.appendChild(el("button", {
        class: "ico-btn",
        text: "清除",
        onclick: function () { act("update", { id: task.id, fields: { due: "" } }); }
      }));
    }
    /* 快捷项由后端给（口径统一在后端），前端只负责渲染。
       mousedown 阻止默认行为是为了**不让按钮拿到焦点** ——
       否则它被重建掉时焦点退回 body，浏览器会顺手把页面滚回顶部。 */
    var quick = el("div", { class: "detail-row due-quick" });
    var presets = (state.board && state.board.presets) || [];
    for (var qi = 0; qi < presets.length; qi++) {
      (function (preset) {
        quick.appendChild(el("button", {
          class: "btn small ghost" + (task.due === preset.value ? " on" : ""),
          text: preset.label,
          title: preset.value,
          onmousedown: function (event) { event.preventDefault(); },
          onclick: function () {
            act("update", { id: task.id, fields: { due: preset.value } });
          }
        }));
      })(presets[qi]);
    }

    detailBox.appendChild(el("div", { class: "detail-sec" }, [
      dueLabel,
      el("div", { class: "detail-row" }, [dueInput]),
      quick
    ]));

    /* --- 所属清单 --- */
    var select = el("select", { class: "select" });
    var lists = (state.board && state.board.lists) || [];
    for (var i = 0; i < lists.length; i++) {
      var option = el("option", { value: lists[i].id, text: lists[i].name });
      if (lists[i].id === (task.list_id || "default")) { option.selected = true; }
      select.appendChild(option);
    }
    select.addEventListener("change", function () {
      act("update", { id: task.id, fields: { list_id: select.value } });
    });
    detailBox.appendChild(el("div", { class: "detail-sec" }, [
      el("div", { class: "detail-label" }, [el("span", { text: "所属清单" })]),
      select
    ]));

    /* --- 备注 --- */
    var note = el("textarea", {
      class: "textarea",
      rows: "3",
      placeholder: "备注…"
    });
    note.value = task.note || "";
    note.addEventListener("change", function () {
      if ((task.note || "") !== note.value) {
        act("update", { id: task.id, fields: { note: note.value } });
      }
    });
    detailBox.appendChild(el("div", { class: "detail-sec" }, [
      el("div", { class: "detail-label" }, [el("span", { text: "备注" })]),
      note
    ]));

    /* --- 底部 --- */
    detailBox.appendChild(el("div", { class: "detail-foot" }, [
      el("span", { text: "创建于 " + (task.created || "") }),
      el("button", {
        class: "btn small ghost danger",
        text: "删除任务",
        onclick: function () {
          ctx.confirm({
            title: "删除任务",
            message: "删除「" + task.title + "」？",
            detail: "删除后无法撤销。",
            okText: "删除",
            danger: true
          }).then(function (ok) {
            if (!ok) { return; }
            state.selected = null;
            act("remove", { id: task.id });
          });
        }
      })
    ]));
  }

  /* 步骤文字可以点开改 —— 打错字不必删掉重加 */
  function stepTitleNode(task, step) {
    var node = el("div", {
      class: "step-title",
      title: "点击可修改",
      onclick: function () { editStepTitle(task, step, node); }
    }, [highlight(step.title, state.keyword)]);
    return node;
  }

  function editStepTitle(task, step, node) {
    if (!node.parentNode) { return; }
    var input = el("input", { class: "input step-edit", type: "text" });
    input.value = step.title;
    node.parentNode.replaceChild(input, node);
    input.focus();
    input.select();

    var settled = false;
    function finish(save) {
      if (settled) { return; }        // keydown 之后 blur 还会来一次，只认第一次
      settled = true;
      var value = String(input.value || "").trim();
      if (!save || !value || value === step.title) {
        refresh();                    // 放弃或空值：重绘还原，不必打扰后端
        return;
      }
      act("update_step", { id: task.id, step_id: step.id, title: value });
    }

    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") { finish(true); }
      else if (event.key === "Escape") { finish(false); }
    });
    input.addEventListener("blur", function () { finish(true); });
  }

  function drawSteps(task) {
    if (!stepsBox) { return; }
    ctx.clear(stepsBox);

    var steps = task.steps || [];
    if (!steps.length) {
      stepsBox.appendChild(el("div", { class: "detail-label", text: "还没有步骤" }));
      return;
    }
    for (var i = 0; i < steps.length; i++) {
      (function (step) {
        var row = el("div", { class: "step-row" + (step.done ? " done" : "") });
        var check = el("input", {
          class: "check",
          type: "checkbox",
          onchange: function () {
            act("toggle_step", { id: task.id, step_id: step.id });
          }
        });
        if (step.done) { check.checked = true; }
        row.appendChild(check);
        row.appendChild(stepTitleNode(task, step));
        row.appendChild(el("button", {
          class: "ico-btn",
          text: "✕",
          title: "删除步骤",
          onclick: function () {
            act("remove_step", { id: task.id, step_id: step.id });
          }
        }));
        stepsBox.appendChild(row);
      })(steps[i]);
    }
  }

  function addStep(task) {
    var title = String(state.stepDraft || "").trim();
    if (!title) { return; }
    state.stepDraft = "";
    act("add_step", { id: task.id, title: title }).then(function () {
      var input = detailBox ? detailBox.querySelector(".step-input") : null;
      if (input) { input.focus(); }
    });
  }

  /* ================= 组装 ================= */

  function render(container, context) {
    ctx = context;
    el = ctx.el;

    state.view = "my_day";
    state.listId = "default";
    state.keyword = "";
    state.selected = null;
    state.stepDraft = "";
    state.renaming = false;

    shell = el("div", { class: "todo-shell without-detail" });
    railBox = el("div", { class: "rail" });
    headBox = el("div", { class: "list-head" });

    /* 工具栏只建一次 —— 否则每次按键触发刷新都会重建输入框、导致失焦 */
    var addInput = el("input", {
      class: "input grow",
      type: "text",
      placeholder: "添加任务，回车确定"
    });
    addInput.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") { return; }
      var title = String(addInput.value || "").trim();
      if (!title) { return; }
      addInput.value = "";
      act("add", { title: title, view: state.view, list_id: state.listId });
    });

    searchInput = el("input", {
      class: "input",
      type: "text",
      placeholder: "搜索全部任务",
      style: "width:186px"
    });
    searchInput.addEventListener("input", function () {
      state.keyword = String(searchInput.value || "").trim();
      refresh();
    });

    var toolbar = el("div", { class: "toolbar" }, [
      addInput,
      searchInput
    ]);

    var mainCol = el("div", { class: "main-col" }, [
      headBox,
      toolbar,
      (listBox = el("div", { class: "list" }))
    ]);

    detailBox = el("div", { class: "detail" });

    shell.appendChild(railBox);
    shell.appendChild(mainCol);
    shell.appendChild(detailBox);
    container.appendChild(shell);

    refresh();
  }

  /* ================= 全局快捷键 ================= */

  /* Esc 收起详情面板。
     注册在模块层而不是 render() 里 —— render() 每次进入这个工具都会调用，
     注册在那里的监听器会越积越多。

     两种情况必须让位，否则"按一次 Esc 会关掉两样东西"：
     ① 有弹窗开着（Esc 该由外壳负责关弹窗）；
     ② 焦点在输入框里（行内编辑的 Esc 是"放弃本次修改"）。 */
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") { return; }
    if (ctx && ctx.dialogOpen && ctx.dialogOpen()) { return; }
    var tag = (event.target && event.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") { return; }
    if (!state.selected) { return; }
    state.selected = null;
    renderList();
    renderDetail();
  });

  window.ToolBox.registerTool("todo", { render: render });
})(window, document);
