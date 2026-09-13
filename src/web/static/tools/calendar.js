/* 日历 —— 前端界面（带节假日 / 调休标注的月历）
 *
 * 布局：顶部标题 + 上/下月切换 + 回到今天；下方 7 列月历网格。
 * 状态四态（与后端 model 一致）：
 *   holiday  法定节假日 —— 红字 + 节日名
 *   workday  调休补班日 —— 橙字 + 「班」徽标
 *   weekend  普通周末   —— 灰字
 *   work     普通工作日 —— 默认色
 *
 * 只负责渲染与交互，所有数据（含节假日判定）都在后端 action。
 * 数据源：内置 holidays.json（离线可用），年份缺失时正常显示、只是无节日标注。
 */
(function (window, document) {
  "use strict";

  var ctx = null;
  var el = null;

  var headBox = null, gridBox = null;
  var state = { year: 0, month: 0 };   /* 0 = 尚未加载 */

  /* 小 SVG（行为与 todo.js 一致：不用文本字符，避免 UOS 字体缺字形） */
  function chevron(dir) {
    var d = dir === "left" ? "M10 3 5 8l5 5" : "M6 3l5 5-5 5";
    return '<svg viewBox="0 0 16 16" class="ic" width="16" height="16" fill="none" ' +
      'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
      '<path d="' + d + '"/></svg>';
  }

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
    var title = el("div", {
      class: "cal-title",
      text: nums[0] + " 年 " + parseInt(nums[1], 10) + " 月"
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
      prev, next, title, todayBtn
    ]);
    headBox.appendChild(group);
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

        var kids = [];
        var num = el("span", { class: "cal-num", text: String(item.day) });
        kids.push(num);

        if (item.status === "holiday" && item.name) {
          kids.push(el("span", { class: "cal-name", text: item.name }));
        } else if (item.status === "workday") {
          kids.push(el("span", { class: "cal-adj", text: "班" }));
        }
        grid.appendChild(el("div", { class: cls, title: item.name || "", }, kids));
      })(view.items[n]);
    }
    gridBox.appendChild(grid);

    /* 图例 */
    var legend = el("div", { class: "cal-legend" }, [
      el("span", { class: "lg" }, [el("i", { class: "lg-dot holiday" }), el("span", { text: "节假日" })]),
      el("span", { class: "lg" }, [el("i", { class: "lg-dot adj" }), el("span", { text: "调休补班" })]),
      el("span", { class: "lg" }, [el("i", { class: "lg-dot weekend" }), el("span", { text: "周末" })]),
      el("span", { class: "lg" }, [el("i", { class: "lg-dot today" }), el("span", { text: "今天" })])
    ]);
    gridBox.appendChild(legend);
  }

  function loadMonth(year, month) {
    ctx.callTool("calendar", "month", { year: year, month: month }).then(function (data) {
      var view = data && data.view;
      if (!view) { return; }
      state.year = view.year;
      state.month = view.month;
      renderHead(view);
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

  function render(container, context) {
    ctx = context;
    el = ctx.el;

    state.year = 0;
    state.month = 0;

    var shell = el("div", { class: "cal-shell" });
    headBox = el("div", { class: "cal-head" });
    gridBox = el("div", { class: "cal-body" });
    shell.appendChild(headBox);
    shell.appendChild(gridBox);
    container.appendChild(shell);

    var now = new Date();
    loadMonth(now.getFullYear(), now.getMonth() + 1);
  }

  window.ToolBox.registerTool("calendar", { render: render });
})(window, document);