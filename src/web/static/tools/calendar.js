/* 日历 —— 前端界面（带节假日 / 调休 / 农历标注的月历）
 *
 * 布局：顶部标题 + 上/下月切换 + 回到今天；中部月份概览；下方 7 列月历网格。
 * 状态四态（与后端 model 一致）：
 *   holiday  法定节假日 —— 红字 + 节日名
 *   workday  调休补班日 —— 橙字 + 「班」徽标
 *   weekend  普通周末   —— 灰字
 *   work     普通工作日 —— 默认色
 * 每格第二行显示农历（每月初一显示月名，其余显示日名，如 正月 / 初二 / 十五）。
 *
 * 只负责渲染与交互，所有数据（含节假日 / 农历判定）都在后端 action。
 * 数据源：内置 holidays.json + 内置农历表（1900-2100），彻底离线可用。
 */
(function (window, document) {
  "use strict";

  var ctx = null;
  var el = null;

  var headBox = null, overviewBox = null, gridBox = null;
  var pickerBox = null, titleBtn = null;   /* 年月快速选择面板 + 触发它的标题按钮 */
  var state = { year: 0, month: 0, pickerOpen: false, editingYear: false };
  var dueMap = {};                     /* date -> {pending, done}，来自 todo.due_map */

  /* 小 SVG（行为与 todo.js 一致：不用文本字符，避免 UOS 字体缺字形） */
  function chevron(dir) {
    var d = dir === "left" ? "M10 3 5 8l5 5" : "M6 3l5 5-5 5";
    return '<svg viewBox="0 0 16 16" class="ic" width="16" height="16" fill="none" ' +
      'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="' + d + '"/></svg>';
  }

  /* 格内「＋」：给这一天新建任务。用内联 SVG（不用文本 + 号，避免字体缺字形） */
  var PLUS_SVG = '<svg viewBox="0 0 16 16" class="ic" width="11" height="11" fill="none" ' +
    'stroke="currentColor" stroke-width="2.6" stroke-linecap="round">' +
    '<path d="M8 3.5v9"/><path d="M3.5 8h9"/></svg>';

  /* ================= 渲染 ================= */

  function renderHead(view) {
    ctx.clear(headBox);
    var prev = el("button", {
      class: "btn ghost icon",
      html: chevron("left"),
      title: "上个月",
      onclick: function () { goMonth(state.year, state.month - 1); }
    });
    var next = el("button", {
      class: "btn ghost icon",
      html: chevron("right"),
      title: "下个月",
      onclick: function () { goMonth(state.year, state.month + 1); }
    });
    var nums = view.year_month.split("-");
    titleBtn = el("button", {
      class: "cal-title",
      text: nums[0] + " 年 " + parseInt(nums[1], 10) + " 月",
      title: "点击选择年月",
      /* 别让按钮抢走焦点：否则被替换掉的节点带着焦点，浏览器回退焦点时会顺手滚动页面 */
      onmousedown: noFocus,
      onclick: function () { setPickerOpen(!state.pickerOpen); }
    });

    var todayBtn = el("button", {
      class: "btn ghost",
      text: "今天",
      title: "回到当前月份",
      onclick: function () {
        var now = new Date();
        goMonth(now.getFullYear(), now.getMonth() + 1);
      }
    });

    var group = el("div", { class: "cal-head-group" }, [
      prev, next, titleBtn, todayBtn
    ]);
    headBox.appendChild(group);
  }

  function noFocus(event) { event.preventDefault(); }

  /* ================= 年月快速选择面板 =================
     点标题弹出：年份行 + 12 个月格 + 回到今天。
     - 近处用"点"（月份格）；远处用"打"（点年份变输入框，跳十年八年比一格一格翻快得多） */
  function setPickerOpen(on) {
    state.pickerOpen = !!on;
    if (!on) { state.editingYear = false; }
    if (!pickerBox) { return; }
    if (!on) {
      pickerBox.className = "cal-picker hidden";
      return;
    }
    renderPicker();
    pickerBox.className = "cal-picker";
    /* 贴在头部下方（头部高度随字号/缩放变化，所以现算） */
    var headH = (headBox && headBox.offsetHeight) || 40;
    pickerBox.style.top = (headH + 6) + "px";
  }

  function renderPicker() {
    if (!pickerBox) { return; }
    ctx.clear(pickerBox);

    var year = state.year || new Date().getFullYear();

    var yearRow = el("div", { class: "cal-pick-yearrow" });
    yearRow.appendChild(el("button", {
      class: "btn ghost icon",
      html: chevron("left"),
      title: "上一年",
      onmousedown: noFocus,
      onclick: function () { goMonth(year - 1, state.month); setPickerOpen(false); }
    }));

    if (state.editingYear) {
      /* 行内输入年份：回车提交、Esc 放弃、失焦也提交（与"点标题改名"同一套） */
      var input = el("input", {
        class: "cal-pick-yearinput",
        type: "text",
        onkeydown: function (event) {
          if (event.key === "Enter") { input.blur(); }
          else if (event.key === "Escape") { state.editingYear = false; renderPicker(); }
        },
        onblur: function () {
          var value = String(input.value || "").trim();
          state.editingYear = false;
          if (value === String(year)) { renderPicker(); return; }
          if (!/^\d{4}$/.test(value) || Number(value) < 1900 || Number(value) > 2400) {
            ctx.toast("年份请填 1900–2400 的四位数字", true);
            renderPicker();
            return;
          }
          goMonth(Number(value), state.month);
          setPickerOpen(false);
        }
      });
      input.value = String(year);
      yearRow.appendChild(input);
      /* 渲染完再聚焦（此刻还没进 DOM） */
      window.setTimeout(function () { if (input.focus) { input.focus(); input.select(); } }, 0);
    } else {
      yearRow.appendChild(el("button", {
        class: "cal-pick-yearbtn",
        text: String(year),
        title: "点击可直接输入年份",
        onmousedown: noFocus,
        onclick: function () { state.editingYear = true; renderPicker(); }
      }));
    }

    yearRow.appendChild(el("button", {
      class: "btn ghost icon",
      html: chevron("right"),
      title: "下一年",
      onmousedown: noFocus,
      onclick: function () { goMonth(year + 1, state.month); setPickerOpen(false); }
    }));
    pickerBox.appendChild(yearRow);

    var months = el("div", { class: "cal-pick-months" });
    for (var m = 1; m <= 12; m++) {
      (function (mm) {
        months.appendChild(el("button", {
          class: "cal-pick-month" + (mm === state.month ? " active" : ""),
          text: mm + " 月",
          onmousedown: noFocus,
          onclick: function () {
            setPickerOpen(false);
            if (mm !== state.month) { goMonth(year, mm); }
          }
        }));
      })(m);
    }
    pickerBox.appendChild(months);

    pickerBox.appendChild(el("div", { class: "cal-pick-foot" }, [
      el("button", {
        class: "btn ghost small",
        text: "回到今天",
        onmousedown: noFocus,
        onclick: function () {
          var now = new Date();
          goMonth(now.getFullYear(), now.getMonth() + 1);
          setPickerOpen(false);
        }
      })
    ]));
  }

  /* 月份概览：如「节假日 9 天 · 春节(9天)」「调休 2 天 · 2/14、2/28」 */
  function renderOverview(view) {
    ctx.clear(overviewBox);
    var ov = view.overview || {};
    var m = parseInt(view.year_month.split("-")[1], 10);
    var parts = [];

    if (ov.holidays > 0) {
      var names = (ov.holiday_names || [])
        .map(function (n) { return n.name + "(" + n.days + "天)"; })
        .join("、");
      var hInfo = "节假日 " + ov.holidays + " 天";
      if (names) { hInfo += " · " + names; }
      var hChip = el("span", { class: "ov-chip holiday", text: hInfo });
      if (ov.holiday_span && ov.holiday_span.length === 2) {
        hChip.title = m + "/" + ov.holiday_span[0] + "-" + m + "/" + ov.holiday_span[1];
      }
      parts.push(hChip);
    }

    if (ov.adjusts > 0) {
      var aDays = ov.adjust_span || [];
      var aText = "调休 " + ov.adjusts + " 天";
      if (aDays.length === 2) {
        aText += " · " + m + "/" + aDays[0] +
          (aDays[1] === aDays[0] ? "" : "、" + m + "/" + aDays[1]);
      }
      parts.push(el("span", { class: "ov-chip adj", text: aText }));
    }

    if (parts.length === 0) {
      overviewBox.appendChild(el("div", { class: "ov-empty", text: "本月无节假日 / 调休安排" }));
    } else {
      var row = el("div", { class: "cal-overview" });
      for (var i = 0; i < parts.length; i++) { row.appendChild(parts[i]); }
      overviewBox.appendChild(row);
    }
  }

  function renderGrid(view) {
    ctx.clear(gridBox);

    var weekHead = el("div", { class: "cal-week" });
    var weekNames = ["一", "二", "三", "四", "五", "六", "日"];
    for (var i = 0; i < 7; i++) {
      weekHead.appendChild(el("div", { class: "cal-wday", text: weekNames[i] }));
    }
    gridBox.appendChild(weekHead);

    var grid = el("div", { class: "cal-grid" });
    /* 前置空白格：月份第一天是周几（weekday0，0=周一），前面补空格 */
    for (var pad = 0; pad < view.weekday0; pad++) {
      grid.appendChild(el("div", { class: "cal-cell empty" }));
    }

    var today = view.today;   /* 仅当月含今天时才非空 */
    for (var n = 0; n < view.items.length; n++) {
      (function (item) {
        var cls = "cal-cell " + item.status;
        if (item.date === today) { cls += " today"; }

        var counts = dueMap[item.date] || { pending: 0, done: 0 };
        var hasTask = counts.pending > 0 || counts.done > 0;
        if (hasTask) { cls += " has-task"; }

        /* 悬停提示：节日/农历打底，有待办再补一行明细 */
        var tip = item.name || item.lunar || "";
        if (hasTask) {
          var line = "待办 " + counts.pending + " 项未完成";
          if (counts.done) { line += "、" + counts.done + " 项已完成"; }
          tip = (tip ? tip + " · " : "") + line;
        }

        var kids = [];
        kids.push(el("span", { class: "cal-num", text: String(item.day) }));

        /* 业务行：节假日名 / 调休「班」徽标（比农历重要，放前面） */
        if (item.status === "holiday" && item.name) {
          kids.push(el("span", { class: "cal-name", text: item.name }));
        } else if (item.status === "workday") {
          kids.push(el("span", { class: "cal-adj", text: "班" }));
        }

        /* 农历行：每月初一显示月名（正月 / 闰二月），其余显示日名（初二 / 十五） */
        if (item.lunar) {
          kids.push(el("span", { class: "cal-lunar", text: item.lunar }));
        }

        /* 当天待办：未完成醒目（实心点 + 数字）、已完成弱化（空心点），
           口径与「某天待办」视图一致。（已完成也按到期日归属） */
        if (hasTask) {
          var dueRow = el("span", { class: "cal-due" });
          if (counts.pending) {
            dueRow.appendChild(el("span", { class: "due-pending", text: String(counts.pending) }));
          }
          if (counts.done) {
            dueRow.appendChild(el("span", { class: "due-done", text: String(counts.done) }));
          }
          kids.push(dueRow);
        }

        /* 只有"有任务的那天"才可点整格跳转 —— 点一个没有待办的日子只会进到空态，
           属于无效跳转，还容易误点（格子密集）。
           新建走角落里那个小小的「＋」，与"看"分开，避免误点整格。 */
        var attrs = { class: cls, title: tip };
        if (hasTask) {
          attrs.onclick = function () { gotoDay(item.date); };
        }

        kids.push(el("button", {
          class: "cal-add",
          html: PLUS_SVG,
          title: "在这一天新建任务",
          onclick: function (event) {
            event.stopPropagation();
            gotoAdd(item.date);
          }
        }));

        grid.appendChild(el("div", attrs, kids));
      })(view.items[n]);
    }
    gridBox.appendChild(grid);

    /* 图例 */
    var legend = el("div", { class: "cal-legend" }, [
      el("span", { class: "lg" }, [el("i", { class: "lg-dot holiday" }), el("span", { text: "节假日" })]),
      el("span", { class: "lg" }, [el("i", { class: "lg-dot adj" }), el("span", { text: "调休补班" })]),
      el("span", { class: "lg" }, [el("i", { class: "lg-dot weekend" }), el("span", { text: "周末" })]),
      el("span", { class: "lg" }, [el("i", { class: "lg-dot today" }), el("span", { text: "今天" })]),
      el("span", { class: "lg" }, [el("i", { class: "lg-dot due" }), el("span", { text: "有待办（点击查看）" })])
    ]);
    gridBox.appendChild(legend);
  }

  function loadMonth(year, month) {
    /* 日历数据与"当天待办数"并行取。
       待办那边取失败（例如工具被停用）就退化成纯日历，不影响主功能。 */
    var calendarReq = ctx.callTool("calendar", "month", { year: year, month: month });
    var todoReq = ctx.callTool("todo", "due_map", { year: year, month: month })
      .catch(function () { return null; });

    Promise.all([calendarReq, todoReq]).then(function (results) {
      var view = results[0] && results[0].view;
      if (!view) { return; }
      dueMap = (results[1] && results[1].days) || {};
      state.year = view.year;
      state.month = view.month;
      renderHead(view);
      renderOverview(view);
      renderGrid(view);
    }).catch(function (err) {
      ctx.toast(err.message, true);
    });
  }

  function goMonth(year, month) {
    if (month < 1) { year -= 1; month = 12; }
    else if (month > 12) { year += 1; month = 1; }
    loadMonth(year, month);
  }

  /* 点某一天 → 跳到待办的「某天待办」视图（跨清单，按完成状态分组）。
     日期通过 hash 的 query 传递，由 todo 前端自己解析。 */
  function gotoDay(date) {
    window.location.hash = "#/todo?due=" + date;
  }

  /* 点格子里的「＋」→ 跳到那天并**直接聚焦添加框**（add=1），落地就能打字 */
  function gotoAdd(date) {
    window.location.hash = "#/todo?due=" + date + "&add=1";
  }

  function render(container, context) {
    ctx = context;
    el = ctx.el;

    state.year = 0;
    state.month = 0;
    state.pickerOpen = false;
    state.editingYear = false;

    var shell = el("div", { class: "cal-shell" });
    headBox = el("div", { class: "cal-head" });
    pickerBox = el("div", { class: "cal-picker hidden" });
    overviewBox = el("div", { class: "cal-overview-wrap" });
    gridBox = el("div", { class: "cal-body" });
    shell.appendChild(headBox);
    shell.appendChild(pickerBox);
    shell.appendChild(overviewBox);
    shell.appendChild(gridBox);
    container.appendChild(shell);

    var now = new Date();
    loadMonth(now.getFullYear(), now.getMonth() + 1);
  }

  /* ================= 面板的关闭途径 =================
     注册在模块层（脚本加载时一次）—— 写进 render() 里会随每次进入工具不断累积。 */

  /* 点面板外面（或再点一次标题）就收起 */
  document.addEventListener("click", function (event) {
    if (!state.pickerOpen) { return; }
    var target = event.target;
    if (pickerBox && pickerBox.contains && pickerBox.contains(target)) { return; }
    if (titleBtn && titleBtn.contains && titleBtn.contains(target)) { return; }
    setPickerOpen(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" || !state.pickerOpen) { return; }
    /* 焦点在年份输入框里时，Esc 是"放弃这次修改"，交给输入框自己处理（面板不关） */
    var tag = (event.target && event.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA") { return; }
    setPickerOpen(false);
  });

  window.ToolBox.registerTool("calendar", { render: render });
})(window, document);