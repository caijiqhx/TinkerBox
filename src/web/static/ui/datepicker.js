/* 日期选择浮层（页内自绘）—— 用来替代浏览器原生 <input type="date">
 *
 * 为什么要自绘：原生控件的弹层由浏览器自己画 —— 样式不跟主题、滚动与翻月不受控，
 * 而且"点日期即确认并关闭"是写死的行为，插不进「确定」按钮。
 *
 * 交互：
 *   - 点日期只是**选中**（高亮），点「确定」才回调 —— 手动确认
 *   - 滚轮 / ‹ › 翻月；「今天」= 跳到今天并选中
 *   - 「清除」立即回调空串（与详情面板里那个「清除」语义一致）
 *   - 点外部 / Esc /「取消」= 放弃，原件不变
 *
 * 数据：节假日 / 调休 / 农历 / 节气 全部来自 calendar.month（与日历同源，口径不重写）；
 *       取不到时退化成"纯日期网格"，选日期照常可用。
 */
(function (window, document) {
  "use strict";

  var ROWS = 6;                                  /* 网格固定 6 行，翻月时高度不跳动 */
  var WEEK = ["一", "二", "三", "四", "五", "六", "日"];

  var ctx = null;
  var box = null;
  var state = {
    open: false,
    anchor: null,
    onPick: null,
    picked: "",          /* 当前选中（还没确认） */
    year: 0,
    month: 0,
    view: null           /* calendar.month 的返回；取不到时为 null（纯日期网格） */
  };

  /* 点"外部关闭"要分两趟：捕获阶段先记下"点是否落在浮层里"，冒泡阶段只看这条记录。
     原因——被点的节点可能在它自己的 click 处理里被替换掉，那时再 contains 就判错了。 */
  var insideClick = false;
  /* 还要能认出"这次点击正是打开浮层的那一下"：点触发按钮时，捕获阶段浮层还没打开
     （记不到 insideClick），等冒泡到 document 时它已经被打开了 —— 不放过的话，
     刚打开就被自己的"点外部关闭"关掉（表现是点了没反应）。
     用点击序号而不是 contains(anchor)：序号不受节点被替换影响，也不会误豁免程序化的 open。 */
  var clickSeq = 0;
  var openedAtSeq = -1;
  var wheelAt = 0;

  function isoOf(y, m, d) {
    return y + "-" + (m < 10 ? "0" : "") + m + "-" + (d < 10 ? "0" : "") + d;
  }

  function todayText() {
    var now = new Date();
    return isoOf(now.getFullYear(), now.getMonth() + 1, now.getDate());
  }

  function daysInMonth(y, m) {
    return new Date(y, m, 0).getDate();
  }

  /* ================= 渲染 ================= */

  function navBtn(title, path, onclick) {
    return ctx.el("button", {
      class: "dp-nav",
      title: title,
      html: '<svg viewBox="0 0 16 16" class="ic" width="14" height="14" fill="none" ' +
        'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="' + path + '"/></svg>',
      onmousedown: function (event) { event.preventDefault(); },
      onclick: onclick
    });
  }

  function render() {
    ctx.clear(box);

    var v = state.view;
    var year = state.year;
    var month = state.month;
    var days = v ? v.days : daysInMonth(year, month);
    /* 周一开头：getDay() 里周日是 0，换算成 0=周一 */
    var lead = v ? v.weekday0 : (new Date(year, month - 1, 1).getDay() + 6) % 7;

    var byDay = {};
    if (v) {
      for (var i = 0; i < v.items.length; i++) { byDay[v.items[i].day] = v.items[i]; }
    }

    box.appendChild(ctx.el("div", { class: "dp-head" }, [
      navBtn("上个月", "M10 3 5 8l5 5", function () { go(-1); }),
      ctx.el("div", { class: "dp-title", text: year + " 年 " + month + " 月" }),
      navBtn("下个月", "M6 3l5 5-5 5", function () { go(1); })
    ]));

    var week = ctx.el("div", { class: "dp-week" });
    for (var w = 0; w < 7; w++) {
      week.appendChild(ctx.el("div", { class: "dp-wd", text: WEEK[w] }));
    }
    box.appendChild(week);

    var grid = ctx.el("div", { class: "dp-grid" });
    var firstDay = 1 - lead;                     /* 第一格对应的日号（≤0 表示上月的日子） */
    for (var n = 0; n < ROWS * 7; n++) {
      var day = firstDay + n;
      if (day < 1 || day > days) {
        grid.appendChild(ctx.el("div", { class: "dp-day out" }));
        continue;
      }
      var iso = isoOf(year, month, day);
      var item = byDay[day];
      var cls = "dp-day";
      if (item) {
        if (item.status === "holiday") { cls += " holiday"; }
        else if (item.status === "workday") { cls += " workday"; }
      }
      if (v && iso === v.today) { cls += " today"; }
      if (iso === state.picked) { cls += " sel"; }
      grid.appendChild(ctx.el("button", {
        class: cls,
        text: String(day),
        title: (item && item.hint) || "",
        onmousedown: function (event) { event.preventDefault(); },
        onclick: (function (d) { return function () { state.picked = d; render(); }; })(iso)
      }));
    }
    box.appendChild(grid);

    var foot = ctx.el("div", { class: "dp-foot" });
    foot.appendChild(ctx.el("button", {
      class: "btn ghost small", text: "今天",
      onmousedown: function (event) { event.preventDefault(); },
      onclick: function () { jumpToday(); }
    }));
    foot.appendChild(ctx.el("button", {
      class: "btn ghost small", text: "清除",
      onmousedown: function (event) { event.preventDefault(); },
      onclick: function () { commit(""); }
    }));
    foot.appendChild(ctx.el("span", { class: "dp-gap" }));
    foot.appendChild(ctx.el("button", {
      class: "btn ghost small", text: "取消",
      onmousedown: function (event) { event.preventDefault(); },
      onclick: function () { close(); }
    }));
    foot.appendChild(ctx.el("button", {
      class: "btn small primary", text: "确定",
      onmousedown: function (event) { event.preventDefault(); },
      onclick: function () { commit(state.picked); }
    }));
    box.appendChild(foot);
  }

  /* ================= 数据与定位 ================= */

  function load() {
    var year = state.year;
    var month = state.month;
    ctx.callTool("calendar", "month", { year: year, month: month }).then(function (data) {
      if (!state.open || year !== state.year || month !== state.month) { return; }   /* 已经翻走了 */
      state.view = (data && data.view) || null;
      render();
      position();
    }).catch(function () {
      if (!state.open || year !== state.year || month !== state.month) { return; }
      state.view = null;                         /* 日历不可用 → 退化成纯日期网格 */
      render();
      position();
    });
  }

  function position() {
    if (!state.anchor || !box || !box.offsetWidth) { return; }
    var rect = state.anchor.getBoundingClientRect();
    var width = box.offsetWidth;
    var height = box.offsetHeight;
    var gap = 6, edge = 8;

    var left = rect.left;
    if (left + width > window.innerWidth - edge) { left = window.innerWidth - edge - width; }
    if (left < edge) { left = edge; }

    var top = rect.bottom + gap;
    if (top + height > window.innerHeight - edge && rect.top - gap - height > edge) {
      top = rect.top - gap - height;             /* 下方放不下就上翻 */
    }
    box.style.left = Math.round(left) + "px";
    box.style.top = Math.round(top) + "px";
  }

  /* ================= 开合 ================= */

  function go(delta) {
    var year = state.year;
    var month = state.month + delta;
    if (month < 1) { year -= 1; month = 12; }
    else if (month > 12) { year += 1; month = 1; }
    state.year = year;
    state.month = month;
    load();
  }

  function jumpToday() {
    var iso = todayText();
    var parts = iso.split("-");
    state.year = parseInt(parts[0], 10);
    state.month = parseInt(parts[1], 10);
    state.picked = iso;
    load();
  }

  function commit(date) {
    var handler = state.onPick;
    close();
    if (handler) { handler(date || ""); }
  }

  function close() {
    state.open = false;
    state.anchor = null;
    state.onPick = null;
    openedAtSeq = -1;
    if (box) { box.className = "dp hidden"; }
  }

  function open(options) {
    options = options || {};
    if (!box) { return; }
    /* 再点一次同一个触发按钮 = 收起（浮层开着时它已被"点外部"放过，没有出口） */
    if (state.open && state.anchor === options.anchor) { close(); return; }
    openedAtSeq = clickSeq;                      /* 记下"是这一下点击打开的"，见 onDocClick */
    state.anchor = options.anchor || null;
    state.onPick = typeof options.onPick === "function" ? options.onPick : null;
    state.picked = String(options.value || "");

    var base = state.picked || todayText();
    var parts = base.split("-");
    state.year = parseInt(parts[0], 10);
    state.month = parseInt(parts[1], 10);
    state.view = null;

    state.open = true;
    box.className = "dp";
    render();                                    /* 先用"无日历数据"渲染一版，避免空白等待 */
    position();
    load();                                      /* 取到节假日数据后再重绘一次 */
  }

  /* ================= 事件 ================= */

  function onWheel(event) {
    if (!state.open) { return; }
    event.preventDefault();
    var now = Date.now();
    if (now - wheelAt < 120) { return; }         /* 轻节流：滚一下翻一个月，别一滑就飞走 */
    wheelAt = now;
    go(event.deltaY > 0 ? 1 : -1);
  }

  function onDocClickCapture(event) {
    clickSeq += 1;
    if (!state.open) { insideClick = false; return; }
    var target = event.target;
    insideClick = !!(box && box.contains && box.contains(target));
  }

  function onDocClick() {
    if (!state.open) { return; }
    if (insideClick) { insideClick = false; return; }
    if (openedAtSeq === clickSeq) { return; }          /* 这一下就是打开它的那次点击，别自己关自己 */
    close();
  }

  function onKeydown(event) {
    if (!state.open) { return; }
    if (event.key === "Escape") { close(); }
  }

  function build() {
    box = ctx.el("div", { class: "dp hidden" });
    if (box.addEventListener) {
      box.addEventListener("wheel", onWheel, { passive: false });   /* 需要 preventDefault */
    }
    document.body.appendChild(box);

    document.addEventListener("click", onDocClickCapture, true);
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKeydown);
    window.addEventListener("scroll", function () {
      if (state.open) { position(); }                                /* 面板内滚动也跟着走 */
    }, true);
    window.addEventListener("resize", function () {
      if (state.open) { position(); }
    });
  }

  function init(context) {
    if (ctx) { return; }                         /* 重复 init 直接忽略 */
    ctx = context;
    build();
  }

  window.ToolBox = window.ToolBox || {};
  window.ToolBox.datePicker = { init: init, open: open, close: close };
})(window, document);
