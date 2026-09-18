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
  var state = { year: 0, month: 0, pickerOpen: false, editingYear: false,
                pickerYear: 0,      /* 面板里正在浏览的年份（与日历当前显示的年份分开，互不影响） */
                picked: "" };       /* 被点选中的那一天（再点一次取消） */
  var dueMap = {};                     /* date -> {pending, done}，来自 todo.due_map */
  var cellNodes = {};                  /* date -> 格子节点：切换选中时只改这一个节点的 class，不整月重绘 */

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

  /* 格内「清单」：查看这一天已有的待办（与「＋」成对，一左一右） */
  var LIST_SVG = '<svg viewBox="0 0 16 16" class="ic" width="11" height="11" fill="none" ' +
    'stroke="currentColor" stroke-width="2.2" stroke-linecap="round">' +
    '<path d="M3.5 4.5h9"/><path d="M3.5 8h9"/><path d="M3.5 11.5h5.5"/></svg>';

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

  /* 提示里同一件事别说两遍：已有的名称包含它（如「清明节」含「清明」）就算重复 */
  function nameCovered(parts, text) {
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].indexOf(text) >= 0) { return true; }
    }
    return false;
  }

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
    /* 每次打开都从"日历当前显示的年份"起算；面板里的年份只是待选值，不影响日历 */
    state.pickerYear = state.year || new Date().getFullYear();
    renderPicker();
    pickerBox.className = "cal-picker";
    /* 贴在头部下方（头部高度随字号/缩放变化，所以现算） */
    var headH = (headBox && headBox.offsetHeight) || 40;
    pickerBox.style.top = (headH + 6) + "px";
  }

  function renderPicker() {
    if (!pickerBox) { return; }
    ctx.clear(pickerBox);

    var year = state.pickerYear || state.year || new Date().getFullYear();

    var yearRow = el("div", { class: "cal-pick-yearrow" });
    /* 箭头只是"翻面板里的年份"—— 不跳转、不收面板，方便先翻到目标年再点月份 */
    yearRow.appendChild(el("button", {
      class: "btn ghost icon",
      html: chevron("left"),
      title: "上一年",
      onmousedown: noFocus,
      onclick: function () { state.pickerYear = year - 1; renderPicker(); }
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
          /* 与箭头一致：只把面板翻到那一年，不跳转也不收面板，接着点月份即可 */
          state.pickerYear = Number(value);
          renderPicker();
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
      onclick: function () { state.pickerYear = year + 1; renderPicker(); }
    }));
    pickerBox.appendChild(yearRow);

    var months = el("div", { class: "cal-pick-months" });
    for (var m = 1; m <= 12; m++) {
      (function (mm) {
        months.appendChild(el("button", {
          /* 高亮只标"日历正显示的那个月"；翻到别的年份时 12 个月都不高亮 */
          class: "cal-pick-month" +
            ((year === state.year && mm === state.month) ? " active" : ""),
          text: mm + " 月",
          onmousedown: noFocus,
          onclick: function () {
            setPickerOpen(false);
            if (!(year === state.year && mm === state.month)) { goMonth(year, mm); }
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
    weekHead.appendChild(el("div", { class: "cal-wday", text: "周" }));   /* 第一列：周序号 */
    var weekNames = ["一", "二", "三", "四", "五", "六", "日"];
    for (var i = 0; i < 7; i++) {
      weekHead.appendChild(el("div", { class: "cal-wday", text: weekNames[i] }));
    }
    gridBox.appendChild(weekHead);

    var grid = el("div", { class: "cal-grid" });

    var today = view.today;   /* 仅当月含今天时才非空 */
    cellNodes = {};
    var lead = view.weekday0;
    var rows = Math.ceil((lead + view.items.length) / 7);

    /* 该行第一个"属于本月"的格子决定周号（同一行本来就是同一周） */
    function rowWeek(row) {
      for (var c = 0; c < 7; c++) {
        var idx = row * 7 + c - lead;
        if (idx >= 0 && idx < view.items.length) {
          return String(view.items[idx].week || "");
        }
      }
      return "";
    }

    /* 单个日期格子（原来是一段扁平循环，搬进函数后按行调用） */
    function buildCell(item) {
      var cls = "cal-cell " + item.status;
      if (item.date === today) { cls += " today"; }
      if (item.date === state.picked) { cls += " picked"; }

      var counts = dueMap[item.date] || { pending: 0, done: 0 };
      var hasTask = counts.pending > 0 || counts.done > 0;

      /* 名称行内容：法定节假日名 —— **只在"正日子"当天显示**（中秋只在中秋节那天，
         假期里的其他天不写，否则像是放了三个中秋），其余日子把名字放悬停提示里说明。 */
      var holidayName = (item.status === "holiday" && item.name) ? item.name : "";
      var badgeText = (holidayName && item.fest_day) ? holidayName : "";

      /* 农历行补一个"今天是什么日子"：农历节日优先，其次节气。 */
      var extra = item.fest || item.term || "";
      if (extra && badgeText && badgeText.indexOf(extra) >= 0) { extra = ""; }

      /* 格子里这一行只放"这天是什么日子"，优先级：法定假日名 > 农历节日 > 节气 > 农历日。
         正日子当天上面已经写了名字，就不再叠一个农历日（「中秋节」下面不必再来个「十五」，
         完整农历悬停提示里有）；若当天另有不重复的农历节日（如国庆节撞中秋）才保留。 */
      var lunarLine = badgeText ? extra : (extra || item.lunar || "");

      /* 悬停提示：第一行 = 假期名 / 农历节日 / 节气 / 完整农历（八月初三，格子里只放得下"初三"），
         第二行 = 当天待办情况（换行显示，挤在一行太长）。
         提示层支持多行（white-space: pre-line），这里直接放 \n 即可。 */
      var parts = [];
      if (holidayName && !nameCovered(parts, holidayName)) { parts.push(holidayName); }
      if (item.fest && !nameCovered(parts, item.fest)) { parts.push(item.fest); }
      if (item.term && !nameCovered(parts, item.term)) { parts.push(item.term); }
      if (item.lunar_full) { parts.push(item.lunar_full); }
      var tip = parts.join(" · ");
      if (hasTask) {
        var line = "待办 " + counts.pending + " 项未完成";
        if (counts.done) { line += "、" + counts.done + " 项已完成"; }
        tip = tip ? (tip + "\n" + line) : line;
      }

      var kids = [];
      kids.push(el("span", { class: "cal-num", text: String(item.day) }));

      /* 业务行：节假日名 / 调休「班」徽标（比农历重要，放前面） */
      if (badgeText) {
        kids.push(el("span", { class: "cal-name", text: badgeText }));
      } else if (item.status === "workday") {
        kids.push(el("span", { class: "cal-adj", text: "班" }));
      }

      /* 农历行：常态是农历（初一显示月名「正月」，其余显示「初二 / 十五」）；
         当天有农历节日 / 节气时，整行换成它（如「立秋」「除夕」「龙抬头」）——
         单独一层样式，比农历的灰更实一点 */
      if (lunarLine) {
        var lunarNode = el("span", { class: "cal-lunar" });
        if (extra) {
          lunarNode.appendChild(el("span", { class: "cal-extra", text: extra }));
        } else {
          lunarNode.appendChild(el("span", { text: item.lunar }));
        }
        kids.push(lunarNode);
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

      /* 点格子本体 = 选中这一天（再点一次取消）—— 不跳转：
         选中只是"边框加深 + 格内两个小按钮常驻"，真正的"看/加"仍由那两个按钮负责。
         有任务的那天才出现「清单」（跳这天的待办），任何一天都有「＋」（在这天新建）。 */
      var attrs = { class: cls, title: tip,
                    onclick: function () { togglePick(item.date); } };

      if (hasTask) {
        kids.push(el("button", {
          class: "cal-open",
          html: LIST_SVG,
          title: "查看这天的待办",
          onclick: function (event) {
            event.stopPropagation();
            gotoDay(item.date);
          }
        }));
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

      var node = el("div", attrs, kids);
      cellNodes[item.date] = node;
      var node = el("div", attrs, kids);
      cellNodes[item.date] = node;
      return node;
    }

    /* 每行：最左一列是周号，右边 7 天；行内不属于本月的格子留空 */
    for (var r = 0; r < rows; r++) {
      grid.appendChild(el("div", { class: "cal-wk", text: rowWeek(r) }));
      for (var c = 0; c < 7; c++) {
        var idx = r * 7 + c - lead;
        if (idx >= 0 && idx < view.items.length) {
          grid.appendChild(buildCell(view.items[idx]));
        } else {
          grid.appendChild(el("div", { class: "cal-cell empty" }));
        }
      }
    }

    gridBox.appendChild(grid);

    /* 图例 */
    var legend = el("div", { class: "cal-legend" }, [
      el("span", { class: "lg" }, [el("i", { class: "lg-dot holiday" }), el("span", { text: "节假日" })]),
      el("span", { class: "lg" }, [el("i", { class: "lg-dot adj" }), el("span", { text: "调休补班" })]),
      el("span", { class: "lg" }, [el("i", { class: "lg-dot weekend" }), el("span", { text: "周末" })]),
      el("span", { class: "lg" }, [el("i", { class: "lg-dot today" }), el("span", { text: "今天" })]),
      el("span", { class: "lg" }, [el("i", { class: "lg-dot due" }), el("span", { text: "有待办" })])
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
      state.picked = "";               /* 换月后原来选中的那天已经不在视野里 */
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

  /* 点格子本体 = 选中 / 取消选中这一天。
     只改被选中那一个节点的 class（不整月重绘），避免闪烁和节点重建。
     选中的作用：边框加深 + 格内两个小按钮常驻，方便"就盯着这天操作"。 */
  function togglePick(date) {
    var prev = cellNodes[state.picked];
    if (prev) { prev.className = prev.className.replace(/\s*\bpicked\b/, ""); }

    if (state.picked === date) {          /* 再点同一格 = 取消选中 */
      state.picked = "";
      return;
    }
    state.picked = date;
    var node = cellNodes[date];
    if (node) { node.className = node.className + " picked"; }
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

  /* 点面板外面（或再点一次标题）就收起。
     这里必须分两趟，否则有个隐蔽的坑：
     面板里的按钮在自己的 click 里可能重建节点（如"点年份 → 换成输入框"），
     等事件冒泡到 document 时，那个按钮**已经被摘出 DOM**，再用 contains(target)
     判断就会误判成"点在面板外" → 面板被关掉。
     所以：① 捕获阶段（DOM 还是点击前的样子）先记下点是否在面板内；
          ② 冒泡阶段只用这个记录来决定关不关。 */
  var pickerClickInside = false;

  document.addEventListener("click", function (event) {
    pickerClickInside = !!(pickerBox && pickerBox.contains && pickerBox.contains(event.target));
  }, true);

  document.addEventListener("click", function (event) {
    if (!state.pickerOpen) { pickerClickInside = false; return; }
    if (pickerClickInside) { pickerClickInside = false; return; }
    if (titleBtn && titleBtn.contains && titleBtn.contains(event.target)) { return; }
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