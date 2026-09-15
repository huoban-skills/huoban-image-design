#!/usr/bin/env python3
"""把内容片段里的 <hb-*> 宏展开成真实组件 HTML。build.py 组装前自动调用，也可单独跑。

用法：
    python3 scripts/expand.py stage.html                 # 展开后的 HTML 打到标准输出
    python3 scripts/expand.py stage.html --out /tmp/x.html
    python3 scripts/expand.py --list                     # 通用写法＋宏目录（一宏一行）
    python3 scripts/expand.py --doc hb-shell hb-grid     # 只取要用的宏的详细语法
    python3 scripts/expand.py --doc all > references/macros.md   # 生成人看的全文

宏只消灭机械重复（壳层、表格行、卡片、图表坐标），不做设计决策：用哪个视图、放不放浮层、
字段怎么排，仍由写片段的人定。每个宏对应 assets/c1～c4 里的一个已收录组件，输出的类名与
结构正本一致，check.py 照常检查。宏语法在本文件 DOCS，--list / --doc 按需取。

规则：
- 宏体按行写，行内用 | 分列，\\| 表示字面竖线；空行和 // 开头的行忽略。
- 单元格文本里含 < 视为已写好的 HTML 原样放入，否则按纯文本处理。
- 值后缀 :red/:blue/:green/:orange/:teal/:purple/:yellow/:gray 表示做成彩色标签。
- 宏可嵌套；内层先展开。写错列数、用了不存在的图标或工具名会直接报错并指出行。
"""
import argparse
import html
import math
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"

COLORS = {"red", "blue", "green", "orange", "teal", "purple", "yellow", "gray"}


def ctok(c):
    """系列色 token：皮肤只定义 --c-红蓝绿橙青紫黄，gray 走墨色 25%。"""
    return "var(--ink-25)" if c == "gray" else f"var(--c-{c})"
NAV_ICONS = {"home", "table", "doc", "flow"}
TOOL_ICONS = {"字段": "fields", "分组": "group", "筛选": "filter", "排序": "sort", "冻结": "freeze",
              "行高": "rowheight", "导入": "import", "导出": "export", "打印": "print", "分享": "share"}
STAT_WORDS = {"sum": "求和", "avg": "平均值", "max": "最大值", "min": "最小值", "count": "已填写",
              "median": "中间值", "range": "极差", "empty": "未填写"}
SERIES_COLORS = ["red", "blue", "purple", "teal", "green", "orange", "yellow"]


class ExpandError(Exception):
    pass


def known_icons():
    svg = (ASSETS / "icons.svg").read_text(encoding="utf-8")
    return set(re.findall(r'<symbol id="i-([\w-]+)"', svg))


ICONS = known_icons()


# ── 基础工具 ────────────────────────────────────────────────────────────
def esc(s):
    s = s.strip()
    if "<" in s:
        return s
    return re.sub(r"&(?![a-zA-Z#]\w*;)", "&amp;", s)


def ico(name, cls="ico", tag=""):
    if name not in ICONS:
        raise ExpandError(f"{tag}图标 #i-{name} 不在 assets/icons.svg 里。可用：{'、'.join(sorted(ICONS))}")
    return f'<svg class="{cls}"><use href="#i-{name}"/></svg>'


def lines(body):
    out = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s or s.startswith("//"):
            continue
        out.append(s)
    return out


def cells(line):
    parts = re.split(r"(?<!\\)\|", line)
    return [p.replace("\\|", "|").strip() for p in parts]


def split_color(v):
    """'酒品:red' → ('酒品', 'red')；没有颜色后缀返回 (v, None)。"""
    if ":" in v:
        head, tail = v.rsplit(":", 1)
        if tail.strip() in COLORS:
            return head.strip(), tail.strip()
    return v, None


def tag(text, color=None):
    text = esc(text)
    return f'<span class="tag c-{color}">{text}</span>' if color and color != "gray" else f'<span class="tag">{text}</span>'


def user(name):
    name = name.strip()
    return f'<span class="user"><span class="av">{esc(name[:1])}</span>{esc(name)}</span>'


def op_btn(spec, tagname):
    # 下载:download:teal
    parts = [p.strip() for p in spec.split(":")]
    label = parts[0]
    icon = parts[1] if len(parts) > 1 and parts[1] else "arrow-right"
    color = parts[2] if len(parts) > 2 else ""
    cls = "op-btn" + (f" {color}" if color else "")
    return f'<span class="{cls}">{ico(icon, tag=tagname)}{esc(label)}</span>'


def render_val(v, typ="text", tagname=""):
    v = v.strip()
    if not v:
        return ""
    if v.startswith("~"):
        return f'<span class="muted">{esc(v[1:])}</span>'
    if v.startswith("="):
        return v[1:].strip()  # 强制原样 HTML
    if typ == "user":
        return " ".join(user(n) for n in v.split("/") if n.strip())
    if typ == "tags":
        return '<span class="tags">' + "".join(tag(*split_color(t)) for t in v.split("/") if t.strip()) + "</span>"
    if typ == "ops":
        return " ".join(op_btn(o, tagname) for o in v.split("/") if o.strip())
    text, color = split_color(v)
    if typ == "tag" or color:
        return tag(text, color)
    return esc(text)


def attrs_of(raw):
    out = {}
    for m in re.finditer(r'([\w-]+)(?:="([^"]*)")?', raw or ""):
        out[m.group(1)] = m.group(2) if m.group(2) is not None else True
    return out


def parse_header(cols):
    """表头列：'当前库存:sum=4,386' / '品类:tag' / '操作:ops' → [{name,type,stat}]"""
    out = []
    for c in cols:
        parts = c.split(":")
        col = {"name": parts[0].strip(), "type": "text", "stat": None}
        for p in parts[1:]:
            p = p.strip()
            if p in ("tag", "tags", "user", "ops", "num", "text"):
                col["type"] = p
            elif "=" in p and p.split("=", 1)[0] in STAT_WORDS:
                k, val = p.split("=", 1)
                col["stat"] = (STAT_WORDS[k], val.strip())
            else:
                raise ExpandError(f"表头「{c}」里的 :{p} 不认识（类型 tag/tags/user/ops/num；统计 sum=/avg=/max=/min=/count=）")
        out.append(col)
    return out


def table_rows(body_lines, header, tagname, ck=False, idx=False):
    rows = []
    n = 1
    for ln in body_lines:
        if ln.startswith("#"):
            text, color = split_color(ln[1:].strip())
            rows.append(f'<tr class="group"><td colspan="99"><span class="caret">▾</span>{tag(text, color or "green")}</td></tr>')
            continue
        sel = ln.startswith("!")
        if sel:
            ln = ln[1:].strip()
        vals = cells(ln)
        if len(vals) != len(header):
            raise ExpandError(f"<{tagname}> 第 {n} 行有 {len(vals)} 列，表头是 {len(header)} 列：{ln}")
        tds = []
        if ck:
            tds.append('<td class="ck"><span class="cb"></span></td>')
        if idx:
            tds.append(f'<td class="idx">{n}</td>')
        for col, v in zip(header, vals):
            cls = ' class="ops"' if col["type"] == "ops" else ""
            tds.append(f"<td{cls}>{render_val(v, col['type'], tagname)}</td>")
        rows.append(f'<tr{" class=\"sel\"" if sel else ""}>{"".join(tds)}</tr>')
        n += 1
    return rows


# ── 宏实现 ──────────────────────────────────────────────────────────────
def m_nav(a, body):
    out = []
    sub = []

    def flush():
        nonlocal sub
        if sub:
            out.append('<div class="sub">' + "".join(sub) + "</div>")
            sub = []

    for ln in lines(body):
        if ln.startswith("#"):
            flush()
            out.append(f'<div class="group">{esc(ln[1:])}</div>')
            continue
        if ln.startswith(">"):
            flush()
            c = cells(ln[1:])
            n = f'<span class="n">{esc(c[1])}</span>' if len(c) > 1 else ""
            out.append(f'<div class="shell-nav-folder"><span class="fi">{ico("folder", tag="<hb-nav> ")}</span>{esc(c[0])}{n}<span class="more">{ico("more")}</span></div>')
            continue
        is_sub = ln.startswith("-")
        if is_sub:
            ln = ln[1:].strip()
        elif sub:
            flush()
        cur = ln.startswith("*")
        if cur:
            ln = ln[1:].strip()
        c = cells(ln)
        icon = c[1] if len(c) > 1 and c[1] else "app-s"
        color = c[2] if len(c) > 2 and c[2] else ""
        li = "li" + (f" ic-{color}" if color and not cur else "")
        leaf = f'<div class="shell-nav-leaf{" current" if cur else ""}"><span class="{li}">{ico(icon, tag="<hb-nav> ")}</span>{esc(c[0])}</div>'
        (sub if is_sub else out).append(leaf)
    flush()
    return "<!--HB-NAV-->" + '<div class="tree">' + "".join(out) + "</div><!--/HB-NAV-->"


def m_shell(a, body):
    ws = a.get("ws", "")
    if not ws:
        raise ExpandError("<hb-shell> 缺 ws（工作区名）")
    logo = a.get("logo", ws[:1])
    page = a.get("page", "")
    nav = a.get("nav", "table")
    if nav not in NAV_ICONS:
        raise ExpandError(f"<hb-shell nav> 只能是 {'/'.join(sorted(NAV_ICONS))}")
    theme = a.get("theme", "band")
    me = a.get("me", "管")
    bottom = cells(a.get("bottom", "管理|成员"))
    m = re.search(r"<!--HB-NAV-->(.*?)<!--/HB-NAV-->", body, re.S)
    tree = m.group(1) if m else '<div class="tree"></div>'
    content = (body[:m.start()] + body[m.end():]) if m else body
    icons_row = "".join(f'<i{" class=\"on\"" if k == nav else ""}>{ico(k)}</i>' for k in ("home", "table", "doc", "flow"))
    bottom_html = "".join(
        f'<span>{ico("settings" if b == "管理" else "users" if b == "成员" else "settings")} {esc(b)}</span>' for b in bottom
    ) + f'<span class="more">{ico("more")}</span>'
    return f'''<div class="window theme-{theme}">
  <div class="win-body">
    <div class="shell-side">
      <div class="side-top"><span class="ws-logo">{esc(logo)}</span><span class="ws-name">{esc(ws)}</span><span class="plus">{ico("plus")}</span></div>
      <div class="ico-row">{icons_row}</div>
      {tree}
      <div class="bottom">{bottom_html}</div>
    </div>
    <div class="main">
      <div class="shell-top-bar">
        <span class="menu">{ico("menu")}</span><span class="pg">{esc(page)}</span><span class="caret">▾</span>
        <div class="right">{ico("headset")}{ico("bell")}{ico("inbox")}{ico("help")}<span class="me">{esc(me)}</span></div>
      </div>
{content.strip()}
    </div>
  </div>
</div>'''


def m_views(a, body):
    out = []
    for ln in lines(body):
        cur = ln.startswith("*")
        c = cells(ln[1:] if cur else ln)
        icon = c[1] if len(c) > 1 and c[1] else "grid-s"
        out.append(f'<span class="v{" on" if cur else ""}">{ico(icon, tag="<hb-views> ")}{esc(c[0])}</span>')
    if "noadd" not in a:
        out.append(f'<span class="add">{ico("plus")}{esc(a.get("add", "创建视图"))}</span>')
    out.append(f'<span class="ovf">{ico("more")}</span>')
    return '<div class="view-tabs">' + "".join(out) + "</div>"


def m_tools(a, body):
    items = []
    for ln in lines(body):
        items.extend(cells(ln))
    out = []
    for it in items:
        if not it:
            continue
        parts = it.split(":")
        label = parts[0].strip()
        act = ""
        icon = TOOL_ICONS.get(label)
        for p in parts[1:]:
            p = p.strip()
            if p.isdigit():
                act = p
            elif p:
                icon = p
        if not icon:
            raise ExpandError(f"<hb-tools> 工具「{label}」没有默认图标，写成「{label}:图标名」；内置：{'、'.join(TOOL_ICONS)}")
        text = f"{esc(label)} {act}" if act else esc(label)
        out.append(f'<span class="tool{" act" if act else ""}">{ico(icon, tag="<hb-tools> ")}{text}</span>')
    right = []
    if "search" in a:
        right.append(f'<span class="search">{ico("search")}<span class="ph">{esc(a["search"])}</span></span>')
    if "new" in a:
        dd = "" if "nodd" in a else '<span class="dd">▾</span>'
        right.append(f'<span class="btn-new">{esc(a["new"])}{dd}</span>')
    if right:
        out.append('<div class="right">' + "".join(right) + "</div>")
    return '<div class="view-tools">' + "".join(out) + "</div>"


def m_grid(a, body):
    ls = lines(body)
    if not ls:
        raise ExpandError("<hb-grid> 至少要有表头一行")
    header = parse_header(cells(ls[0]))
    ck = "nock" not in a
    idx = "noidx" not in a
    ths = []
    if ck:
        ths.append('<th class="ck"><span class="cb"></span></th>')
    if idx:
        ths.append('<th class="idx"></th>')
    for col in header:
        cls = ' class="ops"' if col["type"] == "ops" else ""
        ths.append(f"<th{cls}>{esc(col['name'])}</th>")
    rows = table_rows(ls[1:], header, "hb-grid", ck, idx)
    tfoot = ""
    if "total" in a or any(c["stat"] for c in header):
        first_span = (1 if ck else 0) + (1 if idx else 0) + 1
        tds = [f'<td colspan="{first_span}">{esc(str(a.get("total", "")))}</td>']
        for col in header[1:]:
            if col["stat"]:
                tds.append(f'<td><span>{col["stat"][0]}</span><b>{esc(col["stat"][1])}</b></td>')
            else:
                tds.append("<td></td>")
        tfoot = "<tfoot><tr>" + "".join(tds) + "</tr></tfoot>"
    table = f'<table><tr>{"".join(ths)}</tr>{"".join(rows)}{tfoot}</table>'
    if "bare" in a:
        return f'<div class="grid">{table}</div>'
    return f'<div class="table-view view-grid"><div class="grid">{table}<div class="hscroll"><i></i></div></div></div>'


def card_head(a, tagname):
    """w-card 的标题栏：title 必填时用；icon/tint 可选。"""
    title = a.get("title", "")
    if not title:
        return ""
    tint = f" tint-{a['tint']}" if "tint" in a else ""
    icon = ""
    if "icon" in a:
        color = a.get("icolor", a.get("tint", ""))
        icon = ico(a["icon"], cls="ico" + (f" ic-{color}" if color else ""), tag=f"<{tagname}> ")
    return f'<div class="wc-hd{tint}">{icon}{esc(title)}</div>'


def m_pivot(a, body):
    ls = lines(body)
    if len(ls) < 2:
        raise ExpandError("<hb-pivot> 要有表头和至少一行数据")
    header = parse_header(cells(ls[0]))
    if any(c["type"] in ("user", "tag", "tags", "ops") for c in header):
        raise ExpandError("<hb-pivot> 是维度 × 指标的统计表，列里不放人员、状态标签、操作这类记录字段；一条条记录（编号、门店、负责人、日期、状态）用 hb-list（表格列表）")
    _num = re.compile(r"^[+\-−]?[\d,]+(?:\.\d+)?\s*(?:%|万|亿|元|件|天|次|家|个|人|条|单|台|kg|k)?$")
    _cells = [v.split(":")[0].strip() for ln in ls[1:] for v in cells(ln)[1:]]
    _cells = [v for v in _cells if v and v not in ("—", "-", "–")]
    if _cells and sum(1 for v in _cells if _num.match(v)) / len(_cells) < 0.6:
        raise ExpandError("<hb-pivot> 里大部分格子是文字，这是记录列表不是统计表：透视表首列是维度（区域／产品／月份），其余列都是数字；一条条记录用 hb-list（表格列表）")
    ths = "".join(f"<th>{esc(c['name'])}</th>" for c in header)
    rows = []
    for i, ln in enumerate(ls[1:], 1):
        vals = cells(ln)
        if len(vals) != len(header):
            raise ExpandError(f"<hb-pivot> 第 {i} 行有 {len(vals)} 列，表头是 {len(header)} 列：{ln}")
        tds = []
        for j, (col, v) in enumerate(zip(header, vals)):
            cls = ' class="dim"' if j == 0 and "dim" in a else ""
            tds.append(f"<td{cls}>{render_val(v, col['type'], 'hb-pivot')}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    table = f"<table><tr>{ths}</tr>{''.join(rows)}</table>"
    if "bare" in a:
        return table
    return f'<div class="w-card chart_table">{card_head(a, "hb-pivot")}{table}</div>'


def spark_svg(vals):
    nums = [float(x) for x in vals.split(",") if x.strip()]
    if len(nums) < 2:
        raise ExpandError(f"<hb-stats> spark 至少两个数：{vals}")
    lo, hi = min(nums), max(nums)
    span = (hi - lo) or 1
    pts = []
    for i, v in enumerate(nums):
        x = round(96 * i / (len(nums) - 1), 1)
        y = round(4 + 28 * (1 - (v - lo) / span), 1)
        pts.append(f"{x:g},{y:g}")
    return ('<div class="st-spark"><svg viewBox="0 0 96 36" preserveAspectRatio="none">'
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="var(--primary)" stroke-width="2"/></svg></div>')


def m_stats(a, body):
    mode = a.get("mode", "center")
    if mode not in ("center", "strip"):
        raise ExpandError("<hb-stats mode> 只能是 center 或 strip")
    out = []
    ls = lines(body)
    for ln in ls:
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-stats> 每行至少「指标名 | 值」：{ln}")
        label, value = c[0], c[1]
        unit, spark, trend = "", "", None
        for extra in c[2:]:
            if extra.startswith("spark:"):
                spark = extra[6:]
            elif extra.startswith("trend"):
                trend = extra.split(":", 1)[1] if ":" in extra else ""
            elif extra:
                unit = extra
        vl = esc(value) + (f"<small>{esc(unit)}</small>" if unit else "")
        if mode == "center":
            tr = f'<div class="st-trend{" " + trend if trend else ""}"></div>' if trend is not None else ""
            out.append(f'<div class="w-card chart_single center"><div class="st-lb">{esc(label)}</div><div class="st-vl">{vl}</div>{tr}</div>')
        else:
            sp = spark_svg(spark) if spark else ""
            out.append(f'<div class="w-card chart_single strip"><div class="st-bd"><div class="st-lb">{esc(label)}</div><div class="st-vl">{vl}</div></div>{sp}</div>')
    n = len(ls)
    cls = "w-row" + (f" stats-{n}" if n in (4, 5, 6) else "")
    return f'<div class="{cls}">' + "".join(out) + "</div>"


def m_tasks(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        title = esc(c[0])
        time = f'<span class="t-time">{esc(c[1])}</span>' if len(c) > 1 and c[1] else ""
        node = f'<div class="t-node">{esc(c[2])}</div>' if len(c) > 2 and c[2] else ""
        # 实测：流程任务行右侧固定有办理按钮（次要按钮 68×32）；第 4 列可改按钮名，写 - 去掉
        label = c[3].strip() if len(c) > 3 and c[3].strip() else "办理"
        act = "" if label == "-" else f'<div class="t-act"><span class="b line">{esc(label)}</span></div>'
        out.append(f'<div class="task"><div class="t-bd"><div class="t-title">{title}{time}</div>{node}</div>{act}</div>')
    hd = f'<div class="ws-hd">{esc(a.get("title", ""))}</div>' if a.get("title") else ""
    return f'<div class="procedure_task">{hd}{"".join(out)}</div>'


def m_shortcuts(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        icon = c[1] if len(c) > 1 and c[1] else "app-s"
        out.append(f'<div class="sc"><span class="sc-ic">{ico(icon, tag="<hb-shortcuts> ")}</span>{esc(c[0])}</div>')
    return (f'<div class="w-card button shortcuts">{card_head(a, "hb-shortcuts")}'
            f'<div class="wc-bd sc-list">{"".join(out)}</div></div>')


def m_filters(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        icon = c[1] if len(c) > 1 and c[1] else "f-select"
        out.append(f'<div class="w-filter">{esc(c[0])} {ico(icon, cls="ico cal", tag="<hb-filters> ")}</div>')
    return '<div class="filter">' + "".join(out) + "</div>"


def m_banner(a, body):
    ls = lines(body)
    if not ls:
        raise ExpandError("<hb-banner> 第一行是页面名称，第二行是一句话介绍")
    if "card" in a:
        dt = ""
        if "date" in a or "time" in a:
            dt = f'<div class="ban-dt"><b>{esc(str(a.get("date", "")))}</b><span>{esc(str(a.get("time", "")))}</span></div>'
        img = f'<div class="ban-img">{a["img"] if isinstance(a.get("img"), str) and "<" in a["img"] else ""}</div>' if "img" in a else ""
        return f'<div class="rich title card"><div class="ban-body"><h1>{esc(ls[0])}</h1>{dt}</div>{img}</div>'
    p = f"<p>{esc(ls[1])}</p>" if len(ls) > 1 else ""
    cls = "rich title" + (" bg-solid" if "solid" in a else "")
    return f'<div class="{cls}"><h1>{esc(ls[0])}</h1>{p}</div>'


# ── 图表 ────────────────────────────────────────────────────────────────
def nums_of(s):
    """系列值：逗号分隔，不写千分位（1,842 会被拆成两个数）。"""
    return [float(x) for x in s.split(",") if x.strip()]


def num_of(s):
    """单个数值：允许千分位逗号和单位后缀，如 1,842 / 217 瓶。"""
    m = re.search(r"-?[\d,]*\.?\d+", s.replace(" ", ""))
    if not m:
        raise ExpandError(f"读不出数值：{s}")
    return float(m.group(0).replace(",", ""))


def nice_max(m):
    if m <= 0:
        return 1
    step = 10 ** math.floor(math.log10(m))
    top = math.ceil(m / step) * step
    if top / m < 1.15:
        top += step
    if m <= 100 < top:
        top = 100          # 覆盖率、及时率这类 0～100 的数，轴顶不画到 110
    return top


def fmt_num(v):
    return f"{int(v):,}" if float(v).is_integer() else f"{v:g}"


def parse_series(body, tagname):
    series = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<{tagname}> 每行「系列名 | 数值,数值,… | 颜色(可选)」：{ln}")
        series.append({"name": c[0], "vals": nums_of(c[1]), "color": c[2] if len(c) > 2 and c[2] else None})
    if not series:
        raise ExpandError(f"<{tagname}> 没有数据行")
    return series


def series_fill(i, s):
    """主系列 var(--primary)，同系第二层加 opacity .45，再往后用状态色；显式给了颜色就用状态色。"""
    if s["color"]:
        return f'fill="{ctok(s["color"])}"', f'stroke="{ctok(s["color"])}"', ""
    if i == 0:
        return 'fill="var(--primary)"', 'stroke="var(--primary)"', ""
    if i == 1:
        return 'fill="var(--primary)"', 'stroke="var(--primary)"', ' opacity=".45"'
    c = SERIES_COLORS[(i - 2) % len(SERIES_COLORS)]
    return f'fill="{ctok(c)}"', f'stroke="{ctok(c)}"', ""


def axes(labels, vmax, ticks, W, H, L, T, B, R):
    pw, ph = W - L - R, H - T - B
    out = []
    for i in range(ticks + 1):
        y = T + ph * (1 - i / ticks)
        out.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" stroke="var(--line)" stroke-width="1"/>')
        out.append(f'<text x="{L - 8}" y="{y + 4:.1f}" font-size="11" fill="var(--ink-45)" text-anchor="end">{fmt_num(vmax * i / ticks)}</text>')
    gw = pw / len(labels)
    for i, lb in enumerate(labels):
        x = L + gw * (i + 0.5)
        out.append(f'<text x="{x:.1f}" y="{H - B + 20}" font-size="11" fill="var(--ink-45)" text-anchor="middle">{esc(lb)}</text>')
    return out, pw, ph, gw


def legend_html(series):
    items = []
    for i, s in enumerate(series):
        fill, _, op = series_fill(i, s)
        items.append(f'<span><svg width="10" height="10" xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10" rx="2" {fill}{op}/></svg> {esc(s["name"])}</span>')
    return '<div class="legend">' + "".join(items) + "</div>"


def chart_shell(a, tagname, inner_html, extra=""):
    """图表外壳：默认卡片（白底圆角阴影）；plain＝产品的 common 样式，只剩 40 高标题行。"""
    cls = "chart plain" if "plain" in a else "w-card chart"
    span = f' span-{a["span"]}' if "span" in a else ""
    ex = f" {extra}" if extra else ""
    return f'<div class="{cls}{ex}{span}">{card_head(a, tagname)}{inner_html}</div>'


def chart_card(a, inner, legend, tagname, par="none"):
    # par：柱/折线拉伸填满卡片（none）；环图必须等比，否则圆被抻成椭圆
    W, H = int(a.get("w", 560)), int(a.get("h", 240))
    svg = f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="{par}" xmlns="http://www.w3.org/2000/svg">{"".join(inner)}</svg>'
    if "bare" in a:
        return svg + legend
    return chart_shell(a, tagname, f'<div class="wc-bd">{svg}</div>{legend}')


def m_bar(a, body):
    labels = cells(a.get("labels", ""))
    if not a.get("labels"):
        raise ExpandError("<hb-bar> 缺 labels（横轴标签，| 分隔）")
    series = parse_series(body, "hb-bar")
    for s in series:
        if len(s["vals"]) != len(labels):
            raise ExpandError(f"<hb-bar> 系列「{s['name']}」有 {len(s['vals'])} 个值，labels 有 {len(labels)} 个")
    W, H = int(a.get("w", 560)), int(a.get("h", 240))
    L, T, B, R = 44, 16, 34, 12
    vmax = float(a["max"]) if "max" in a else nice_max(max(v for s in series for v in s["vals"]))
    ticks = int(a.get("ticks", 4))
    inner, pw, ph, gw = axes(labels, vmax, ticks, W, H, L, T, B, R)
    n = len(series)
    bw = min(26, gw * 0.7 / n)
    gap = 4 if n > 1 else 0
    total = n * bw + (n - 1) * gap
    for i, s in enumerate(series):
        fill, _, op = series_fill(i, s)
        for j, v in enumerate(s["vals"]):
            x = L + gw * (j + 0.5) - total / 2 + i * (bw + gap)
            h = ph * v / vmax
            inner.append(f'<rect x="{x:.1f}" y="{T + ph - h:.1f}" width="{bw:.1f}" height="{h:.1f}" {fill}{op}/>')
    return chart_card(a, inner, legend_html(series), "hb-bar")


def m_line(a, body):
    labels = cells(a.get("labels", ""))
    if not a.get("labels"):
        raise ExpandError("<hb-line> 缺 labels（横轴标签，| 分隔）")
    series = parse_series(body, "hb-line")
    for s in series:
        if len(s["vals"]) != len(labels):
            raise ExpandError(f"<hb-line> 系列「{s['name']}」有 {len(s['vals'])} 个值，labels 有 {len(labels)} 个")
    W, H = int(a.get("w", 560)), int(a.get("h", 240))
    L, T, B, R = 44, 16, 34, 12
    vmax = float(a["max"]) if "max" in a else nice_max(max(v for s in series for v in s["vals"]))
    ticks = int(a.get("ticks", 4))
    inner, pw, ph, gw = axes(labels, vmax, ticks, W, H, L, T, B, R)
    for i, s in enumerate(series):
        fill, stroke, op = series_fill(i, s)
        pts = []
        for j, v in enumerate(s["vals"]):
            x, y = L + gw * (j + 0.5), T + ph * (1 - v / vmax)
            pts.append((x, y))
        inner.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" {stroke} stroke-width="2"{op}/>')
        for x, y in pts:
            inner.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" {fill}{op}/>')
    return chart_card(a, inner, legend_html(series), "hb-line")


def m_donut(a, body):
    slices = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-donut> 每行「名称 | 数值 | 颜色(可选)」：{ln}")
        slices.append({"name": c[0], "raw": c[1], "val": num_of(c[1]), "color": c[2] if len(c) > 2 and c[2] else None})
    if not slices:
        raise ExpandError("<hb-donut> 没有数据行")
    total = sum(s["val"] for s in slices) or 1
    W, H = int(a.get("w", 560)), int(a.get("h", 240))
    # 窄卡（大屏左右列 6 栏）里按 W 收环径与图例列位，避免整张 SVG 被缩到看不清字
    narrow = W < 480
    r, sw = (56, 28) if narrow else (66, 34)
    cx, cy = (r + 42 if narrow else 150), H / 2
    C = 2 * math.pi * r
    inner = [f'<g transform="translate({cx},{cy:.0f})">']
    cum = 0.0
    for i, s in enumerate(slices):
        color = s["color"] or SERIES_COLORS[i % len(SERIES_COLORS)]
        s["color"] = color
        length = C * s["val"] / total
        inner.append(f'<circle r="{r}" fill="none" stroke="{ctok(color)}" stroke-width="{sw}" '
                     f'stroke-dasharray="{length:.1f} {C - length:.1f}" transform="rotate({-90 + 360 * cum:.1f})"/>')
        cum += s["val"] / total
    inner.append("</g>")
    if "center" in a:
        cl = cells(a["center"])
        inner.append(f'<text x="{cx}" y="{cy - 5:.0f}" font-size="13" fill="var(--ink-45)" text-anchor="middle">{esc(cl[0])}</text>')
        if len(cl) > 1:
            inner.append(f'<text x="{cx}" y="{cy + 17:.0f}" font-size="20" font-weight="600" fill="var(--ink-85)" text-anchor="middle">{esc(cl[1])}</text>')
    n = len(slices)
    step = (26 if n <= 5 else 22) if narrow else (36 if n <= 5 else 28)
    lx = cx + r + 22 if narrow else 290
    y0 = cy - (n - 1) * step / 2
    inner.append('<g font-size="12" fill="var(--ink-65)">')
    for i, s in enumerate(slices):
        y = y0 + i * step
        pct = round(100 * s["val"] / total)
        inner.append(f'<rect x="{lx:.0f}" y="{y - 9:.0f}" width="10" height="10" rx="2" fill="{ctok(s["color"])}"/>'
                     f'<text x="{lx + 18:.0f}" y="{y:.0f}">{esc(s["name"])}　{esc(s["raw"])}（{pct}%）</text>')
    inner.append("</g>")
    return chart_card(a, inner, "", "hb-donut", par="xMidYMid meet")


def m_area(a, body):
    """面积图：折线 + 线下 20% 透明填充（2026-09-14 实测 chart_area 走线实色、下方渐变面积）。"""
    labels = cells(a.get("labels", ""))
    if not a.get("labels"):
        raise ExpandError("<hb-area> 缺 labels（横轴标签，| 分隔）")
    series = parse_series(body, "hb-area")
    for s in series:
        if len(s["vals"]) != len(labels):
            raise ExpandError(f"<hb-area> 系列「{s['name']}」有 {len(s['vals'])} 个值，labels 有 {len(labels)} 个")
    W, H = int(a.get("w", 560)), int(a.get("h", 240))
    L, T, B, R = 44, 16, 34, 12
    vmax = float(a["max"]) if "max" in a else nice_max(max(v for s in series for v in s["vals"]))
    ticks = int(a.get("ticks", 4))
    inner, pw, ph, gw = axes(labels, vmax, ticks, W, H, L, T, B, R)
    for i, s in enumerate(series):
        fill, stroke, op = series_fill(i, s)
        pts = [(L + gw * (j + 0.5), T + ph * (1 - v / vmax)) for j, v in enumerate(s["vals"])]
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        base = T + ph
        area = f"{pts[0][0]:.1f},{base:.1f} {poly} {pts[-1][0]:.1f},{base:.1f}"
        inner.append(f'<polygon points="{area}" {fill} opacity=".2"/>')
        inner.append(f'<polyline points="{poly}" fill="none" {stroke} stroke-width="2"{op}/>')
        for x, y in pts:
            inner.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" {fill}{op}/>')
    return chart_card(a, inner, legend_html(series), "hb-area")


def m_biaxial(a, body):
    """双轴图（chart_biaxial）：柱走左轴、折线走右轴，两轴刻度各自算。

    2026-09-14 实测：柱＝次色（宏里的第二系列，大屏换 --screen-series-2），折线＝主色；
    外壳与标题行同其他图表卡。
    """
    labels = cells(a.get("labels", ""))
    if not a.get("labels"):
        raise ExpandError("<hb-biaxial> 缺 labels（横轴标签，| 分隔）")
    rows = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 3:
            raise ExpandError(f"<hb-biaxial> 每行「系列名 | 数值,数值,… | bar 或 line」：{ln}")
        role = c[2].strip().lower()
        if role not in ("bar", "line"):
            raise ExpandError(f"<hb-biaxial> 第三列只能是 bar（柱，左轴）或 line（折线，右轴），写了「{c[2]}」")
        rows.append({"name": c[0], "vals": nums_of(c[1]), "role": role,
                     "color": c[3].strip() if len(c) > 3 and c[3].strip() else None})
    bars = [r for r in rows if r["role"] == "bar"]
    lns = [r for r in rows if r["role"] == "line"]
    if len(bars) != 1 or len(lns) != 1:
        raise ExpandError(f"<hb-biaxial> 要正好两行：一行 bar、一行 line（现在 {len(bars)} 行柱、{len(lns)} 行线）")
    bar, line = bars[0], lns[0]
    for r in rows:
        if len(r["vals"]) != len(labels):
            raise ExpandError(f"<hb-biaxial> 系列「{r['name']}」有 {len(r['vals'])} 个值，labels 有 {len(labels)} 个")
    W, H = int(a.get("w", 560)), int(a.get("h", 240))
    L, T, B, R = 44, 16, 34, 44
    ticks = int(a.get("ticks", 4))
    vmax_l = float(a["max"]) if "max" in a else nice_max(max(bar["vals"]))
    vmax_r = float(a["max2"]) if "max2" in a else nice_max(max(line["vals"]))
    inner, pw, ph, gw = axes(labels, vmax_l, ticks, W, H, L, T, B, R)
    for i in range(ticks + 1):
        y = T + ph * (1 - i / ticks)
        inner.append(f'<text x="{W - R + 8}" y="{y + 4:.1f}" font-size="11" fill="var(--ink-45)">{fmt_num(vmax_r * i / ticks)}</text>')
    bfill = f'fill="{ctok(bar["color"])}"' if bar["color"] else 'fill="var(--primary)"'
    bop = "" if bar["color"] else ' opacity=".45"'
    lstroke = f'stroke="{ctok(line["color"])}"' if line["color"] else 'stroke="var(--primary)"'
    lfill = f'fill="{ctok(line["color"])}"' if line["color"] else 'fill="var(--primary)"'
    bw = min(26, gw * 0.5)
    for j, v in enumerate(bar["vals"]):
        h = ph * v / vmax_l
        inner.append(f'<rect x="{L + gw * (j + 0.5) - bw / 2:.1f}" y="{T + ph - h:.1f}" width="{bw:.1f}" height="{h:.1f}" {bfill}{bop}/>')
    pts = [(L + gw * (j + 0.5), T + ph * (1 - v / vmax_r)) for j, v in enumerate(line["vals"])]
    inner.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" {lstroke} stroke-width="2"/>')
    for x, y in pts:
        inner.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" {lfill}/>')
    legend = ('<div class="legend">'
              f'<span><svg width="10" height="10" xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10" rx="2" {bfill}{bop}/></svg> {esc(bar["name"])}</span>'
              f'<span><svg width="10" height="10" xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10" rx="2" {lfill}/></svg> {esc(line["name"])}</span>'
              "</div>")
    return chart_card(a, inner, legend, "hb-biaxial")


def m_funnel(a, body):
    """漏斗图（chart_funnel）：自上而下逐级收窄的梯形，右侧标转化率；单色系由深到浅（2026-09-14 实测）。"""
    rows = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-funnel> 每行「阶段名 | 值」：{ln}")
        rows.append({"name": c[0], "raw": c[1], "val": num_of(c[1])})
    if len(rows) < 2:
        raise ExpandError("<hb-funnel> 至少两段：漏斗讲的是一级级掉下来的转化")
    top = rows[0]["val"] or 1
    W, H = int(a.get("w", 560)), int(a.get("h", 240))
    L, T, B, R = 16, 14, 14, 150
    pw, ph = W - L - R, H - T - B
    seg = ph / len(rows)
    inner = []
    for i, r in enumerate(rows):
        w0 = pw * max(r["val"] / top, 0.12)
        nxt = rows[i + 1]["val"] if i + 1 < len(rows) else r["val"]
        w1 = pw * max(nxt / top, 0.12) if i + 1 < len(rows) else w0
        cx = L + pw / 2
        y0, y1 = T + seg * i, T + seg * (i + 1) - 4
        op = max(0.3, 1 - i * 0.18)
        inner.append(f'<polygon points="{cx - w0 / 2:.1f},{y0:.1f} {cx + w0 / 2:.1f},{y0:.1f} '
                     f'{cx + w1 / 2:.1f},{y1:.1f} {cx - w1 / 2:.1f},{y1:.1f}" fill="var(--primary)" opacity="{op:.2f}"/>')
        inner.append(f'<text x="{cx:.1f}" y="{(y0 + y1) / 2 + 4:.1f}" font-size="12" fill="#fff" text-anchor="middle">{esc(r["name"])}</text>')
        rate = f"　{100 * r['val'] / top:.0f}%" if i else ""
        inner.append(f'<text x="{W - R + 12}" y="{(y0 + y1) / 2 + 4:.1f}" font-size="12" fill="var(--ink-65)">{esc(r["raw"])}{rate}</text>')
    return chart_card(a, inner, "", "hb-funnel", par="xMidYMid meet")


def m_scatter(a, body):
    """散点图（chart_scatter）：两个数值轴，点按第三列定大小（2026-09-14 实测：点单色、轴与文字深灰）。"""
    rows = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 3:
            raise ExpandError(f"<hb-scatter> 每行「名称 | x 值 | y 值 | 大小(可省)」：{ln}")
        rows.append({"name": c[0], "x": num_of(c[1]), "y": num_of(c[2]),
                     "size": num_of(c[3]) if len(c) > 3 and c[3].strip() else None})
    if not rows:
        raise ExpandError("<hb-scatter> 没有数据行")
    W, H = int(a.get("w", 560)), int(a.get("h", 240))
    L, T, B, R = 48, 28, 36, 16
    pw, ph = W - L - R, H - T - B
    xmax = float(a["xmax"]) if "xmax" in a else nice_max(max(r["x"] for r in rows))
    ymax = float(a["ymax"]) if "ymax" in a else nice_max(max(r["y"] for r in rows))
    ticks = int(a.get("ticks", 4))
    inner = []
    for i in range(ticks + 1):
        y = T + ph * (1 - i / ticks)
        inner.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" stroke="var(--line)" stroke-width="1"/>')
        inner.append(f'<text x="{L - 8}" y="{y + 4:.1f}" font-size="11" fill="var(--ink-45)" text-anchor="end">{fmt_num(ymax * i / ticks)}</text>')
        x = L + pw * i / ticks
        inner.append(f'<text x="{x:.1f}" y="{H - B + 20}" font-size="11" fill="var(--ink-45)" text-anchor="middle">{fmt_num(xmax * i / ticks)}</text>')
    smax = max((r["size"] or 0) for r in rows) or 1
    for r in rows:
        x = L + pw * r["x"] / xmax
        y = T + ph * (1 - r["y"] / ymax)
        rr = 4 + 8 * (r["size"] / smax) if r["size"] else 5
        inner.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rr:.1f}" fill="var(--primary)" opacity=".55"><title>{esc(r["name"])}</title></circle>')
    if a.get("y") and isinstance(a["y"], str):
        inner.append(f'<text x="4" y="12" font-size="11" fill="var(--ink-45)">{esc(a["y"])}</text>')
    if a.get("x") and isinstance(a["x"], str):
        inner.append(f'<text x="{L + pw / 2:.0f}" y="{H - 2}" font-size="11" fill="var(--ink-45)" text-anchor="middle">{esc(a["x"])}</text>')
    return chart_card(a, inner, "", "hb-scatter", par="xMidYMid meet")


def m_map(a, body):
    """地图（chart_map）：网点阵底＋发光标记点，标记点大小按值；右侧列地点小表。

    不画任何国家或省份轮廓；要真实地图时用 img 放客户提供的地图图片。
    """
    rows = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-map> 每行「地点 | 值」：{ln}")
        rows.append({"name": c[0], "raw": c[1], "val": num_of(c[1])})
    if a.get("img") and isinstance(a["img"], str):
        body_html = f'<div class="wc-bd"><img src="{a["img"]}" alt="" style="width:100%;display:block"></div>'
        if "bare" in a:
            return body_html
        return chart_shell(a, "hb-map", body_html)
    if not rows:
        raise ExpandError("<hb-map> 没有数据行（每行「地点 | 值」），或用 img 放客户提供的地图图片")
    W, H = int(a.get("w", 560)), int(a.get("h", 240))
    MW = W - 170
    vmax = max(r["val"] for r in rows) or 1
    inner = []
    cx, cy = MW / 2, H / 2
    for y in range(14, H - 8, 12):
        for x in range(14, int(MW) - 8, 12):
            d = ((x - cx) / (MW / 2)) ** 2 + ((y - cy) / (H / 2)) ** 2
            if d > 1.02:
                continue
            inner.append(f'<circle cx="{x}" cy="{y}" r="1.4" fill="var(--primary)" opacity="{max(0.1, 0.34 - 0.2 * d):.2f}"/>')
    spots = [(0.34, 0.62), (0.56, 0.34), (0.70, 0.66), (0.24, 0.34), (0.48, 0.80), (0.78, 0.30),
             (0.62, 0.52), (0.36, 0.22)]
    for i, r in enumerate(rows[:len(spots)]):
        fx, fy = spots[i]
        x, y = MW * fx, H * fy
        rr = 4 + 9 * (r["val"] / vmax)
        inner.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rr * 2.4:.1f}" fill="var(--primary)" opacity=".12"/>')
        inner.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rr:.1f}" fill="var(--primary)" opacity=".85"/>')
    lx = MW + 24
    n = len(rows)
    step = min(26, (H - 24) / max(n, 1))
    y0 = H / 2 - (n - 1) * step / 2
    inner.append('<g font-size="12" fill="var(--ink-65)">')
    for i, r in enumerate(rows):
        y = y0 + i * step
        inner.append(f'<circle cx="{lx + 5:.0f}" cy="{y - 4:.0f}" r="4" fill="var(--primary)" opacity=".85"/>'
                     f'<text x="{lx + 18:.0f}" y="{y:.0f}">{esc(r["name"])}　{esc(r["raw"])}</text>')
    inner.append("</g>")
    return chart_card(a, inner, "", "hb-map", par="xMidYMid meet")


def m_hbar(a, body):
    """条形图（chart_bar_y）：横向条，名称在左、数值在右（2026-09-14 实测）。"""
    rows = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-hbar> 每行「名称 | 值 | 颜色(可选)」：{ln}")
        rows.append({"name": c[0], "raw": c[1], "val": num_of(c[1]), "color": c[2].strip() if len(c) > 2 and c[2].strip() else None})
    if not rows:
        raise ExpandError("<hb-hbar> 没有数据行")
    vmax = float(a["max"]) if "max" in a else nice_max(max(r["val"] for r in rows))
    out = []
    for i, r in enumerate(rows):
        color = r["color"] or SERIES_COLORS[i % len(SERIES_COLORS)]
        if color not in COLORS:
            raise ExpandError(f"<hb-hbar> 颜色「{color}」不认识，可用：{'、'.join(sorted(COLORS))}")
        pct = max(0.0, min(100.0, 100 * r["val"] / vmax))
        out.append(f'<div class="hbar-row"><span class="hbar-name">{esc(r["name"])}</span>'
                   f'<span class="hbar-track"><i style="width:{pct:.1f}%;--pg:{ctok(color)}"></i></span>'
                   f'<span class="hbar-val">{esc(r["raw"])}</span></div>')
    return chart_shell(a, "hb-hbar", f'<div class="hbar-list">{"".join(out)}</div>', extra="chart_bar_y")


# ── 详情页 ──────────────────────────────────────────────────────────────
def m_info(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-info> 每行「字段名 | 值」：{ln}")
        typ = c[2] if len(c) > 2 else "text"
        out.append(f'<div class="page-header-info-item"><div class="page-header-info-label">{esc(c[0])}</div>'
                   f'<div class="page-header-info-value">{render_val(c[1], typ, "hb-info")}</div></div>')
    return '<div class="page-header-info">' + "".join(out) + "</div>"


def m_steps(a, body):
    items = []
    for ln in lines(body):
        items.extend(cells(ln))
    items = [i for i in items if i]
    cur = next((i for i, it in enumerate(items) if it.startswith("*")), None)
    if cur is None:
        raise ExpandError("<hb-steps> 要用 * 标出当前步骤")
    span = a.get("span", "24")
    if "pill" in a:
        # 选项字段平铺形态（2026-09-14 实测）：全圆角胶囊 20 高，选中填该选项自身颜色，其余透明底
        out = []
        for i, it in enumerate(items):
            name, color = split_color(it[1:].strip() if it.startswith("*") else it)
            cls = "tile" + (" on" if i == cur else "")
            style = f' style="--pg:{ctok(color)}"' if i == cur and color else ""
            out.append(f'<span class="{cls}"{style}>{esc(name)}</span>')
        return f'<div class="item-tiles span-{span}">' + "".join(out) + "</div>"
    out = []
    for i, it in enumerate(items):
        name = split_color(it[1:].strip() if it.startswith("*") else it)[0]
        cls = "preceding" if i < cur else "current" if i == cur else "following"
        out.append(f'<span class="{cls}">{esc(name)}</span>')
    return f'<div class="item-steps span-{span}">' + "".join(out) + "</div>"


# ── 独立自定义详情页 ──────────────────────────────────────────────────────
def m_itembar(a, body):
    title = a.get("title", "")
    if not title:
        raise ExpandError("<hb-itembar> 缺 title（记录主标题）")
    btns = []
    for ln in lines(body):
        for it in cells(ln):
            if not it:
                continue
            parts = [x.strip() for x in it.split(":")]
            style = parts[1] if len(parts) > 1 and parts[1] else "line"
            if style not in ("solid", "line"):
                raise ExpandError(f"<hb-itembar> 按钮样式只能是 solid/line（可再加 :dis 置灰、:green/:orange/:teal 实底色）：{it}")
            extra = " ".join(x for x in parts[2:] if x)
            btns.append(f'<span class="b {style}{" " + extra if extra else ""}">{esc(parts[0])}</span>')
    sys_ = "" if "nosys" in a else (
        '<span class="b text">编辑</span>' + "".join(ico(i) for i in ("copy", "share", "print", "history", "more"))
        + f'<span class="close">{ico("close")}</span>')
    return (f'<div class="item-toolbar"><div class="item-page-nav">{ico("prev")}{ico("next")}</div>'
            f'<div class="item-page-record-title">{esc(title)} <span class="caret">▾</span></div>'
            f'<div class="item-page-shortcuts">{"".join(btns)}</div>'
            f'<div class="item-page-system-actions">{sys_}</div></div>')


def m_hcard(a, body):
    title = a.get("title", "")
    if not title:
        raise ExpandError("<hb-hcard> 缺 title（主标题）")
    sub = f'<div class="page-header-subtitle">{esc(a["sub"])}</div>' if a.get("sub") else ""
    info = m_info(a, body) if lines(body) else ""
    return (f'<div class="w-card header_card span-{a.get("span", "24")}"><div class="page-header-heading">'
            f'<div class="page-header-title">{esc(title)}</div>{sub}</div>{info}</div>')


def m_tabcard(a, body):
    tabs = "".join(f'<span{" class=\"on\"" if on else ""}>{esc(n)}</span>' for n, on in star_items(a.get("tabs", "")))
    if not tabs:
        raise ExpandError('<hb-tabcard> 缺 tabs（如 tabs="*出库明细|历史出入库"，* 为当前页签）')
    if "pill" in a:
        # 胶囊底块只在居中时成立；靠左的页签在产品里是下划线式，不带底块
        tabs = tabs.replace('<span class="on">', '<span class="wt-tab on">').replace("<span>", '<span class="wt-tab">')
        card = (f'<div class="w-card tabs pill"><div class="wt-nav center">{tabs}</div>'
                f'<div class="wt-body">{body.strip()}</div></div>')
    else:
        card = (f'<div class="w-card tabs"><div class="page-tabs-nav"><div class="page-tabs-list">{tabs}</div></div>'
                f'<div class="page-tabs-body">{body.strip()}</div></div>')
    return f'<div class="span-{a["span"]}">{card}</div>' if "span" in a else card


def m_flow(a, body):
    name = a.get("name", "")
    if not name:
        raise ExpandError('<hb-flow> 缺 name（流程名）；by="发起人 · 时间"')
    by = f'<small>{esc(a["by"])}</small>' if a.get("by") else ""
    cancel = "" if "nocancel" in a else '<div class="flow-msg-actions">撤销流程</div>'
    boxes = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-flow> 每行「节点名 | 状态文本:颜色 | 日期 | 耗时 | 链接」；启动事件写「启动事件 | 事件描述 | 日期」：{ln}")
        node, st = c[0], c[1]
        date = c[2] if len(c) > 2 else ""
        dur = c[3] if len(c) > 3 else ""
        link = c[4] if len(c) > 4 else ""
        start = node == "启动事件"
        icon = "play" if start else "f-user"
        if start:
            body_ = f'<div class="txt">{esc(st)}</div>'
        else:
            text, color = split_color(st)
            body_ = f'<div class="st{" " + color if color else ""}">{esc(text)}</div>'
        tm = ""
        if date or dur:
            tm = '<div class="tm">' + (f"<span>{esc(date)}</span>" if date else "") + (f'<span>{ico("history")} {esc(dur)}</span>' if dur else "") + "</div>"
        links = f'<div class="flowbox-links">{esc(link)}</div>' if link else ""
        boxes.append(f'<div class="flowbox"><div class="flowbox-head"><span class="n-ic">{ico(icon)}</span><strong>{esc(node)}</strong></div>'
                     f'<div class="flowbox-body">{body_}{tm}</div>{links}</div>')
    return (f'<div class="process"><div class="flow-msg-body"><span class="app-ic">{ico("grid-s")}</span><span><b>{esc(name)}</b>{by}</span></div>{cancel}</div>'
            f'<div class="flowbox-timeline">{"".join(boxes)}</div><div class="flow-foot">{esc(a.get("foot", "查看详细记录"))}</div>')


# ── 骨架层新增组件（2026-09-14 实测：ERP 演示 / 项目管理 v2.0 / 进销存 v6.0）────────
def span_wrap(a, html_):
    return f'<div class="span-{a["span"]}">{html_}</div>' if "span" in a else html_


FIELD_TYPES = ("text", "tag", "tags", "user", "multi", "file", "image")
FULL_ROW_TYPES = ("multi", "file", "image")
MS_COLORS = ["orange", "green", "red", "yellow", "purple", "blue"]
PG_COLORS = ["blue", "green", "yellow", "purple", "orange", "teal"]
LIST_TOOL_ICONS = {"搜索": "search", "新建": "plus", "新增": "plus", "导出": "export", "导入": "import",
                   "更多": "more", "筛选": "filter", "打印": "print", "分享": "share", "设置": "settings"}


def m_fields(a, body):
    """字段组：# 开分组，其余每行「字段名 | 值 | 类型」。行 69 高＝标签 24 ＋ 值框 32 ＋ 内距。"""
    cols = int(a.get("cols", 2))
    if cols not in (1, 2, 3, 4):
        raise ExpandError("<hb-fields cols> 只能是 1～4（实测每行 1～4 个字段）")
    out, gi = [], 0
    for ln in lines(body):
        if ln.startswith("#"):
            out.append(f'<div class="fg-group t{gi % 3}">{esc(ln[1:].strip())}</div>')
            gi += 1
            continue
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-fields> 每行「字段名 | 值 | 类型(可选)」：{ln}")
        typ = c[2].strip() if len(c) > 2 and c[2].strip() else "text"
        if typ not in FIELD_TYPES:
            raise ExpandError(f"<hb-fields> 字段类型「{typ}」不认识，可用：{'、'.join(FIELD_TYPES)}")
        full = typ in FULL_ROW_TYPES
        val = render_val(c[1], "text" if full else typ, "hb-fields")
        out.append(f'<div class="fg-field{" full" if full else ""}"><div class="fg-label">{esc(c[0])}</div>'
                   f'<div class="fg-value">{val}</div></div>')
    if not out:
        raise ExpandError("<hb-fields> 没有字段行")
    card = (f'<div class="w-card w-field-group">{card_head(a, "hb-fields")}'
            f'<div class="fg-grid fg-c{cols}">{"".join(out)}</div></div>')
    return span_wrap(a, card)


def m_multistats(a, body):
    """多项统计：每行「名称 | 数值 | 颜色」，条 40 高，右侧 20 高圆角 10 胶囊，六色轮转。"""
    out = []
    for i, ln in enumerate(lines(body)):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-multistats> 每行「名称 | 数值 | 颜色(可选)」：{ln}")
        color = c[2].strip() if len(c) > 2 and c[2].strip() else MS_COLORS[i % len(MS_COLORS)]
        if color not in COLORS:
            raise ExpandError(f"<hb-multistats> 颜色「{color}」不认识，可用：{'、'.join(sorted(COLORS))}")
        out.append(f'<div class="multi-stat-row"><span>{esc(c[0])}</span><b class="pill {color}">{esc(c[1])}</b></div>')
    if not out:
        raise ExpandError("<hb-multistats> 没有数据行")
    card = f'<div class="w-card multi_stats">{card_head(a, "hb-multistats")}{"".join(out)}</div>'
    return span_wrap(a, card)


def m_procs(a, body):
    """我发起的：每行「流程名 | 单据 | 当前节点 | 状态:颜色 | 时间」，行 80 高、三行 14/12/12。"""
    out = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 3:
            raise ExpandError(f"<hb-procs> 每行「流程名 | 单据 | 当前节点 | 状态:颜色 | 时间」：{ln}")
        st = ""
        if len(c) > 3 and c[3].strip():
            text, color = split_color(c[3])
            st = tag(text, color)
        tm = f'<span class="proc-time">{esc(c[4])}</span>' if len(c) > 4 and c[4].strip() else ""
        out.append(f'<div class="proc"><div class="proc-t1">{esc(c[0])}{tm}</div>'
                   f'<div class="proc-t2">{esc(c[1])}</div>'
                   f'<div class="proc-t3">{esc(c[2])}{st}</div></div>')
    body_ = "".join(out) if out else '<div class="proc-empty">暂无</div>'
    card = f'<div class="w-card procedure_process">{card_head(a, "hb-procs")}<div class="proc-list">{body_}</div></div>'
    return span_wrap(a, card)


def m_list(a, body):
    """表格列表：外壳（标题 40 ＋ 表体 ＋ 分页 40）＋ hb-grid 的表体；体内语法同 hb-grid。"""
    ga = {"bare": True}
    for k in ("nock", "noidx", "total"):
        if k in a:
            ga[k] = a[k]
    grid = m_grid(ga, body)
    tools = []
    for t in [x.strip() for x in str(a.get("tools", "")).split("|") if x.strip()]:
        if t not in LIST_TOOL_ICONS:
            raise ExpandError(f"<hb-list tools> 里的「{t}」没有对应图标，可用：{'、'.join(LIST_TOOL_ICONS)}")
        tools.append(ico(LIST_TOOL_ICONS[t], tag="<hb-list> "))
    hd = card_head(a, "hb-list")
    if tools:
        acts = f'<span class="acts">{"".join(tools)}</span>'
        hd = hd.replace("</div>", acts + "</div>", 1) if hd else f'<div class="wc-hd">{acts}</div>'
    count = f'<span class="til-count">共 {esc(str(a["count"]))} 条</span>' if "count" in a else ""
    pager = ('<span class="til-pager"><span class="pg">‹</span><span class="pg on">1</span>'
             '<span class="pg">2</span><span class="pg">3</span><span class="pg">›</span></span>')
    card = (f'<div class="w-card table_item_list">{hd}{grid}'
            f'<div class="til-foot">{count}{pager}</div></div>')
    return span_wrap(a, card)


def m_progress(a, body):
    """进度条：每行「名称 | 完成值 | 目标值 | 颜色」；style=bar（新样式，文字嵌条内）或 text（普通样式）。"""
    style = a.get("style", "bar")
    if style not in ("bar", "text"):
        raise ExpandError('<hb-progress style> 只能是 bar（新样式，32 高条内文字）或 text（普通样式，文字行＋细条）')
    out = []
    for i, ln in enumerate(lines(body)):
        c = cells(ln)
        if len(c) < 3:
            raise ExpandError(f"<hb-progress> 每行「名称 | 完成值 | 目标值 | 颜色(可选)」：{ln}")
        done, target = num_of(c[1]), num_of(c[2])
        if target <= 0:
            raise ExpandError(f"<hb-progress> 目标值要大于 0：{ln}")
        pct = max(0.0, min(100.0, 100 * done / target))
        color = c[3].strip() if len(c) > 3 and c[3].strip() else PG_COLORS[i % len(PG_COLORS)]
        if color not in COLORS:
            raise ExpandError(f"<hb-progress> 颜色「{color}」不认识，可用：{'、'.join(sorted(COLORS))}")
        st = f'style="--pct:{pct:.1f}%;--pg:{ctok(color)}"'
        txt = f'<span class="pg-name">{esc(c[0])}</span><span class="pg-num">{pct:.0f}%</span>'
        if style == "bar":
            out.append(f'<div class="pg-row pg-bar" {st}><span class="pg-track"></span><span class="pg-fill"></span>'
                       f'<span class="pg-txt">{txt}</span><span class="pg-txt light">{txt}</span></div>')
        else:
            out.append(f'<div class="pg-row pg-text" {st}><span class="pg-txt">{txt}</span>'
                       f'<span class="pg-track"><i></i></span></div>')
    if not out:
        raise ExpandError("<hb-progress> 没有数据行")
    card = f'<div class="w-card progress_bar">{card_head(a, "hb-progress")}<div class="pg-list">{"".join(out)}</div></div>'
    return span_wrap(a, card)


def m_subtotal(a, body):
    """分类汇总：首行是合计（加粗），其后每行「名称 | 数值」；条目 40 高，右侧纯文本无胶囊。"""
    ls = lines(body)
    if not ls:
        raise ExpandError("<hb-subtotal> 至少要有一行合计「共计 | 值」")
    rows = []
    for i, ln in enumerate(ls):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-subtotal> 每行「名称 | 数值」：{ln}")
        cls = "subtotal-head" if i == 0 else "subtotal-row"
        left = f"<strong>{esc(c[0])}</strong><strong>{esc(c[1])}</strong>" if i == 0 else f"<span>{esc(c[0])}</span><span>{esc(c[1])}</span>"
        rows.append(f'<div class="{cls}">{left}</div>')
    card = f'<div class="w-card subtotal">{card_head(a, "hb-subtotal")}{"".join(rows)}</div>'
    return span_wrap(a, card)


def m_cover(a, body):
    """页面封面：封面 280 高取内容区全宽，页面图标 80×80 压在封面下沿，标题 40/56/500。"""
    title = a.get("title", "")
    if not title:
        raise ExpandError("<hb-cover> 缺 title（页面标题）")
    icon = ico(a.get("icon", "app-s") if isinstance(a.get("icon"), str) else "app-s", tag="<hb-cover> ")
    sub = f'<div class="cover-sub">{esc(a["sub"])}</div>' if a.get("sub") else ""
    return (f'<div class="page-cover"><div class="cover-band"></div>'
            f'<div class="cover-head"><span class="cover-icon">{icon}</span>'
            f'<div class="cover-title">{esc(title)}</div>{sub}</div></div>')


def m_stream(a, body):
    """动态：每行「人名 | 时间 | 内容…」，人名写 sys:名 出系统动态（铅笔图标）。无标题行。"""
    out = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 3:
            raise ExpandError(f"<hb-stream> 每行「人名 | 时间 | 内容」（内容可再用 | 续写多行）：{ln}")
        who, sysmode = c[0], False
        if who.startswith("sys:"):
            who, sysmode = who[4:].strip(), True
        side = (f'<span class="fd-ic">{ico("edit", tag="<hb-stream> ")}</span>' if sysmode
                else f'<span class="av">{esc(who[:1])}</span>')
        ct = "".join(f"<div>{esc(x)}</div>" for x in c[2:] if x.strip())
        out.append(f'<div class="fd-item">{side}<div class="fd-bd">'
                   f'<div class="fd-t">{esc(who)} · {esc(c[1])}</div><div class="fd-c">{ct}</div></div></div>')
    if not out:
        raise ExpandError("<hb-stream> 没有动态行")
    card = f'<div class="w-card w-stream"><div class="fd-list">{"".join(out)}</div></div>'
    return span_wrap(a, card)


def m_comment(a, body):
    """评论：属性 title；每行「人名 | 时间 | 内容」，无行画空态；底部发布条 68。"""
    out = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 3:
            raise ExpandError(f"<hb-comment> 每行「人名 | 时间 | 内容」：{ln}")
        ct = "".join(f"<div>{esc(x)}</div>" for x in c[2:] if x.strip())
        out.append(f'<div class="fd-item"><span class="av">{esc(c[0][:1])}</span><div class="fd-bd">'
                   f'<div class="fd-t">{esc(c[0])} · {esc(c[1])}</div><div class="fd-c">{ct}</div></div></div>')
    inner = (f'<div class="fd-list">{"".join(out)}</div>' if out else
             f'<div class="empty"><span class="e-ic">{ico("f-text", tag="<hb-comment> ")}</span>暂无评论</div>')
    pub = ('<div class="cm-publish"><div class="cm-ipt">写评论，@ 提及某人</div>'
           f'<div class="cm-ops">{ico("at")}{ico("f-attach")}<span class="cm-send">{ico("send")}</span></div></div>')
    card = f'<div class="w-card w-comment">{card_head(a, "hb-comment")}{inner}{pub}</div>'
    return span_wrap(a, card)


# ── 数据大屏（assets/c5-screen.html）──────────────────────────────────────
# 官方六张样板的骨架：标题行（logo 3 ＋ 大标题 18 ＋ 时间 3，高 5）→ 分隔条 24×2 →
# 主体三列 6 ｜ 12 ｜ 6（各 38 行）→ 底部 12＋12（各 26 行）。大屏不缩放，行高公式同普通页面：h 行 = 20h−20。
SCREEN_THEMES = {"cyan", "blue", "gold", "red", "light"}
SCREEN_BGS = {"earth", "city", "grid", "gold"}


def _span(a, tag, default):
    n = str(a.get("span", default))
    if n not in ("3", "4", "5", "6", "8", "10", "12", "14", "16", "18", "24"):
        raise ExpandError(f"<{tag} span> 只能是 3/4/5/6/8/10/12/14/16/18/24（24 栅格），给的是 {n}")
    return f"sp-{n}"


def _rs(a, tag, default):
    try:
        n = int(str(a.get("rs", default)))
    except ValueError:
        raise ExpandError(f"<{tag} rs> 要是 2～40 的整数（行数，高 20N−20）")
    if not 2 <= n <= 40:
        raise ExpandError(f"<{tag} rs> 要是 2～40 的整数（行数，高 20N−20），给的是 {n}")
    return f"rs-{n}"


def m_screen(a, body):
    theme = a.get("theme", "cyan")
    bg = a.get("bg", "")
    if theme not in SCREEN_THEMES:
        raise ExpandError(f"<hb-screen theme> 只能是 {'/'.join(sorted(SCREEN_THEMES))}")
    if bg is True or (bg and bg not in SCREEN_BGS):
        raise ExpandError(f"<hb-screen bg> 只能是 {'/'.join(sorted(SCREEN_BGS))}（装饰底图，默认不用）")
    title = a.get("title", "")
    if not title:
        raise ExpandError("<hb-screen> 缺 title（大屏页面名）")
    sub = f"<small>{esc(a['sub'])}</small>" if a.get("sub") else ""
    logo = esc(a["logo"]) if a.get("logo") else ""
    dt = ""
    if a.get("date"):
        week = f"<span>{esc(a['week'])}</span>" if a.get("week") else ""
        tm = f"<small>{esc(a['time'])}</small>" if a.get("time") else ""
        dt = f'<b>{esc(a["date"])}</b>{week}{tm}'
    head = (f'<div class="screen-head sp-24 rs-5"><div class="screen-logo">{logo}</div>'
            f'<div class="screen-title"><h1>{esc(title)}</h1>{sub}</div>'
            f'<div class="screen-dt">{dt}</div></div>'
            f'<div class="screen-deco sp-24 rs-2"></div>')
    cls = f"screen theme-{theme}" + (f" bg-{bg}" if bg else "")
    return f'<div class="{cls}"><div class="screen-grid">{head}{body.strip()}</div></div>'


def m_scol(a, body):
    """主体分栏：一列里的组件竖着排；列内各组件 rs 之和要等于本列的 rs，三列才等高。"""
    return f'<div class="screen-col {_span(a, "hb-scol", "6")} {_rs(a, "hb-scol", "38")}">{body.strip()}</div>'


def m_skpi(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-skpi> 每行「指标名 | 值 | 单位 | up/down」：{ln}")
        unit = f"<small>{esc(c[2])}</small>" if len(c) > 2 and c[2] else ""
        st = c[3].strip() if len(c) > 3 and c[3].strip() in ("up", "down") else ""
        out.append(f'<div class="screen-kpi{" " + st if st else ""}"><div class="lb">{esc(c[0])}</div>'
                   f'<div class="vl">{esc(c[1])}{unit}</div></div>')
    if not out:
        raise ExpandError("<hb-skpi> 没有数据行")
    if len(out) > 3:
        raise ExpandError(f"<hb-skpi> 一行放 2 个指标框（官方样板 3 栏 ×2），最多 3 个，给了 {len(out)} 个")
    return f'<div class="screen-kpis {_span(a, "hb-skpi", "6")} {_rs(a, "hb-skpi", "6")}">{"".join(out)}</div>'


def m_scard(a, body):
    title = a.get("title", "")
    if not title:
        raise ExpandError("<hb-scard> 缺 title（组件名）")
    return (f'<div class="screen-card {_span(a, "hb-scard", "6")} {_rs(a, "hb-scard", "16")}">'
            f'<div class="screen-hd"><span class="t">{esc(title)}</span></div>'
            f'<div class="screen-bd">{body.strip()}</div></div>')


def m_sbars(a, body):
    out = []
    for i, ln in enumerate(lines(body)):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-sbars> 每行「名称 | 百分比」：{ln}")
        pct = num_of(c[1])
        out.append(f'<div class="screen-bar"><div class="t"><span>{esc(c[0])}</span><span>{esc(c[1])}</span></div>'
                   f'<div class="r"><i style="width:{pct:g}%;--sb:var(--screen-bar-{i % 4 + 1})"></i></div></div>')
    if not out:
        raise ExpandError("<hb-sbars> 没有数据行")
    return '<div class="screen-bars">' + "".join(out) + "</div>"


def visual_globe():
    """中央视觉位默认形态：线框地球＋节点连线＋地台光环，走 var(--screen-accent)，不含任何真实国界。"""
    import random
    r = random.Random(42)
    A = "var(--screen-accent)"
    W, H, cx, cy, R = 700, 460, 350, 200, 168
    g = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">']
    g.append(f'<defs><radialGradient id="gl" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{A}" stop-opacity=".35"/><stop offset=".7" stop-color="{A}" stop-opacity=".06"/><stop offset="1" stop-color="{A}" stop-opacity="0"/></radialGradient>'
             f'<linearGradient id="ring" x1="0" x2="1"><stop offset="0" stop-color="{A}" stop-opacity="0"/><stop offset=".5" stop-color="{A}"/><stop offset="1" stop-color="{A}" stop-opacity="0"/></linearGradient></defs>')
    g.append(f'<circle cx="{cx}" cy="{cy}" r="{R + 40}" fill="url(#gl)"/>')
    g.append(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{A}" stroke-opacity=".55" stroke-width="1.2"/>')
    for k in (0.33, 0.66, 0.88):
        ry = R * k
        g.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{R}" ry="{ry:.0f}" fill="none" stroke="{A}" stroke-opacity=".22"/>')
        g.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{ry:.0f}" ry="{R}" fill="none" stroke="{A}" stroke-opacity=".22"/>')
    g.append(f'<line x1="{cx - R}" y1="{cy}" x2="{cx + R}" y2="{cy}" stroke="{A}" stroke-opacity=".3"/>')
    g.append(f'<line x1="{cx}" y1="{cy - R}" x2="{cx}" y2="{cy + R}" stroke="{A}" stroke-opacity=".3"/>')
    pts = []
    for _ in range(9):
        t = r.uniform(0, 6.283); rr = R * r.uniform(.4, .92)
        pts.append((cx + rr * math.cos(t), cy + rr * 0.8 * math.sin(t)))
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        mx, my = (x1 + x2) / 2, min(y1, y2) - 60
        g.append(f'<path d="M{x1:.0f} {y1:.0f} Q{mx:.0f} {my:.0f} {x2:.0f} {y2:.0f}" fill="none" stroke="{A}" stroke-opacity=".7" stroke-width="1.2"/>')
    for x, y in pts:
        g.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="7" fill="{A}" fill-opacity=".18"/><circle cx="{x:.0f}" cy="{y:.0f}" r="3" fill="{A}"/>')
    for i in range(140):
        t = r.uniform(0, 6.283); rr = R * r.uniform(0, .97)
        x, y = cx + rr * math.cos(t), cy + rr * math.sin(t)
        g.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="1.2" fill="{A}" fill-opacity="{r.uniform(.2, .7):.2f}"/>')
    by = cy + R + 38
    for rx, op in ((R + 60, .8), (R + 100, .45), (R + 140, .2)):
        g.append(f'<ellipse cx="{cx}" cy="{by}" rx="{rx}" ry="{rx * .16:.0f}" fill="none" stroke="url(#ring)" stroke-opacity="{op}" stroke-width="1.5"/>')
    g.append("</svg>")
    return "".join(g)


def visual_map():
    """中央视觉位地图占位：网点阵＋发光标记点＋扩散圈，不画任何国家或省份轮廓（审图号与边界准确性）。"""
    import random
    r = random.Random(7)
    A, M, H2 = "var(--screen-accent)", "var(--screen-series-1)", "var(--screen-bar-2)"
    W, H = 700, 460
    g = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice">']
    g.append(f'<defs><radialGradient id="mg" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{M}" stop-opacity=".55"/><stop offset="1" stop-color="{M}" stop-opacity="0"/></radialGradient>'
             f'<radialGradient id="mh" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{H2}" stop-opacity=".55"/><stop offset="1" stop-color="{H2}" stop-opacity="0"/></radialGradient></defs>')
    cx, cy = W / 2, H / 2
    dots = []
    for y in range(24, H - 12, 15):
        for x in range(24, W - 12, 15):
            d = ((x - cx) / (W / 2)) ** 2 + ((y - cy) / (H / 2)) ** 2
            if d > 1.05:
                continue
            op = (0.5 - 0.34 * d) * r.uniform(.55, 1.25)
            dots.append(f'<circle cx="{x}" cy="{y}" r="1.6" fill="{A}" fill-opacity="{min(op, .6):.2f}"/>')
    g += dots
    marks = [(205, 300, M, 1), (318, 214, M, 0), (392, 330, H2, 1), (470, 188, M, 0), (520, 296, H2, 0), (268, 158, M, 0)]
    for x, y, col, big in marks:
        grad = "mh" if col == H2 else "mg"
        rr = 54 if big else 40
        g.append(f'<circle cx="{x}" cy="{y}" r="{rr}" fill="url(#{grad})"/>')
        g.append(f'<circle cx="{x}" cy="{y}" r="{16 if big else 12}" fill="none" stroke="{col}" stroke-opacity=".45"/>')
        g.append(f'<circle cx="{x}" cy="{y}" r="{26 if big else 20}" fill="none" stroke="{col}" stroke-opacity=".18"/>')
        g.append(f'<circle cx="{x}" cy="{y}" r="{5 if big else 3.6}" fill="{col}"/>')
        if big:
            g.append(f'<line x1="{x}" y1="{y - 12}" x2="{x}" y2="{y - 62}" stroke="{col}" stroke-opacity=".55" stroke-width="2"/>')
            g.append(f'<circle cx="{x}" cy="{y - 66}" r="3.4" fill="{col}"/>')
    g.append("</svg>")
    return "".join(g)


def m_svisual(a, body):
    inner = body.strip()
    title = a.get("title", "")
    if a.get("img") and isinstance(a["img"], str):
        inner = f'<img src="{a["img"]}" alt="">'
    elif "map" in a and not inner:
        inner = visual_map()
        title = title or "区域分布"
    inner = inner or visual_globe()
    hd = f'<div class="screen-hd"><span class="t">{esc(title)}</span></div>' if title else ""
    return (f'<div class="screen-card {_span(a, "hb-svisual", "12")} {_rs(a, "hb-svisual", "38")}">'
            f'{hd}<div class="screen-bd screen-visual">{inner}</div></div>')


# ── 卡片与看板 ──────────────────────────────────────────────────────────
def kv_pairs(s, tagname):
    out = []
    for kv in s.split(";"):
        kv = kv.strip()
        if not kv:
            continue
        if "=" not in kv:
            raise ExpandError(f"<{tagname}> 字段要写成「字段名=值」，用 ; 分隔：{kv}")
        k, v = kv.split("=", 1)
        out.append((k.strip(), v.strip()))
    return out


def m_kanban(a, body):
    cols = []
    for ln in lines(body):
        if ln.startswith("#"):
            c = cells(ln[1:])
            name, color = split_color(c[0])
            color = color or "blue"
            cnt = c[1] if len(c) > 1 else ""
            cols.append({"name": name, "color": color, "cnt": cnt, "cards": []})
            continue
        if not cols:
            raise ExpandError("<hb-kanban> 第一行要用 # 开一列：# 分组名:颜色 | 数量")
        c = cells(ln)
        fields = kv_pairs(c[1], "hb-kanban") if len(c) > 1 else []
        cols[-1]["cards"].append((c[0], fields))
    out = []
    for col in cols:
        cards = []
        for title, fields in col["cards"]:
            dl = "".join(f"<dt>{esc(k)}</dt><dd>{render_val(v, 'text', 'hb-kanban')}</dd>" for k, v in fields)
            cards.append(f'<article class="kanban-item"><b>{esc(title)}</b><dl>{dl}</dl></article>')
        cnt = f'<span class="cnt">{esc(col["cnt"])}</span>' if col["cnt"] else ""
        out.append(f'<section class="kanban-group"><header class="line-{col["color"]}">{tag(col["name"], col["color"])}{cnt}'
                   f'<span class="add">{ico("plus")}</span><span class="more">{ico("more")}</span></header>'
                   f'<div class="kanban-list">{"".join(cards)}</div></section>')
    return f'<div class="table-view view-kanban"><div class="kanban-columns">{"".join(out)}</div></div>'


def m_cards(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        fields = kv_pairs(c[1], "hb-cards") if len(c) > 1 else []
        dl = "".join(f"<dt>{esc(k)}</dt><dd>{render_val(v, 'text', 'hb-cards')}</dd>" for k, v in fields)
        ops = f'<div class="ci-ops">{render_val(c[2], "ops", "hb-cards")}</div>' if len(c) > 2 and c[2] else ""
        out.append(f'<article class="record-card"><b>{esc(c[0])}</b><dl>{dl}</dl>{ops}</article>')
    return f'<div class="table-view view-cards"><div class="record-card-grid">{"".join(out)}</div></div>'


# ── 手机端（2026-09-03 H5 实测结构，类名见 assets/c4-mobile.html）──────────
def m_phone(a, body):
    bar = ""
    if "nobar" not in a:
        bar = f'<div class="m-topbar"><span class="bk">{ico("prev")}</span><span class="tt">{esc(a.get("title", ""))}</span><span class="dots">···</span></div>'
    cls = "phone" + (" h-fix" if "fix" in a else "")
    return f'<div class="{cls}">{bar}{body.strip()}</div>'


def star_items(spec):
    """'表格|*流程|页面' → [(name, is_on)]"""
    out = []
    for t in cells(spec):
        if not t:
            continue
        on = t.startswith("*")
        out.append((t[1:].strip() if on else t, on))
    return out


def m_mhome(a, body):
    tabs = "".join(f'<span{" class=\"on\"" if on else ""}>{esc(n)}</span>' for n, on in star_items(a.get("tabs", "*表格|流程|页面|动态")))
    rows = [f'<div class="sfh">{esc(a.get("head", "全部表格"))}<span class="r">{ico("plus")}</span></div>']
    for ln in lines(body):
        sub = ln.startswith("-")
        name = ln[1:].strip() if sub else ln
        icon = "grid-s" if sub else "folder"
        rows.append(f'<div class="sfr{" sub" if sub else ""}">{ico(icon)}{esc(name)}</div>')
    return (f'<div class="m-home">{tabs}</div><div class="ssearch">{ico("search")}{esc(a.get("search", "搜索"))}</div>'
            f'<div class="sfold">{"".join(rows)}</div>')


def m_vbar(a, body):
    view = esc(a.get("view", "全部数据"))
    cnt = f'<small>{esc(str(a["count"]))}</small>' if "count" in a else ""
    icon = a.get("icon", "grid-s")
    right = "" if "nosearch" in a else f'<span class="vic">{ico("table")}</span><span class="vic">{ico("search")}</span>'
    return f'<div class="m-viewbar"><span class="vbtn">{ico(icon, tag="<hb-vbar> ")}{view}{cnt}<span class="dd">▾</span></span><span class="sp"></span>{right}</div>'


def slot_val(v):
    v = v.strip()
    if not v or v == "~":
        return ""
    if v.startswith("~"):
        return f'<span class="muted">{esc(v[1:])}</span>'
    text, color = split_color(v)
    if color:
        return tag(text, color)
    return esc(text)


def m_ocards(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 3:
            raise ExpandError(f"<hb-ocards> 每行「标题 | 副标题 | 字段=值; 字段=值; 字段=值 | 按钮:图标(可选) | img(可选)」：{ln}")
        fields = kv_pairs(c[2], "hb-ocards")
        if len(fields) > 3:
            raise ExpandError(f"<hb-ocards> 三槽卡片最多 3 个字段（产品实测）：{ln}")
        slots = "".join(f'<div class="slot"><div class="sl">{esc(k)}</div><div class="sv">{slot_val(v)}</div></div>' for k, v in fields)
        os_ = f'<div class="os">{esc(c[1])}</div>' if c[1] else ""
        btn = ""
        if len(c) > 3 and c[3]:
            b = c[3].split(":")
            btn = f'<div class="obtn">{ico(b[1] if len(b) > 1 and b[1] else "check", tag="<hb-ocards> ")}{esc(b[0])}</div>'
        img = ""
        if len(c) > 4 and c[4]:
            img = f'<div class="oimg">{c[4] if "<" in c[4] else ico("f-image")}</div>'
        out.append(f'<div class="ocard"><div class="obody"><div class="ot">{esc(c[0])}</div>{os_}<div class="slots">{slots}</div>{btn}</div>{img}</div>')
    cards = "".join(out)
    if "bare" in a:
        return cards
    fab = f'<div class="m-fab">{ico("plus")}</div>' if "fab" in a else ""
    pager = ""
    if "pager" in a:
        pp = f'<span class="pp">{esc(a["pager"])} ▾</span>' if isinstance(a["pager"], str) else ""
        pager = f'<div class="mpager"><span class="pg">‹</span><span class="pg on">1</span><span class="pg">›</span>{pp}</div>'
    return f'<div class="m-cards">{cards}</div>{fab}{pager}'


MTOOL_ICONS = {"列统计": "fields", "字段设置": "settings", "分组": "group", "筛选": "filter", "排序": "sort",
               "上一条": "prev", "下一条": "next", "编辑": "edit", "评论": "at", "更多": "more",
               "空间": "home", "流程": "flow", "通知": "bell", "我的": "f-user"}


def m_mtool(a, body):
    mode = a.get("mode", "list")
    items = []
    for ln in lines(body):
        items.extend(cells(ln))
    items = [i for i in items if i]
    if not items:
        items = {"list": ["列统计", "字段设置", "分组", "筛选", "排序"],
                 "obar": ["上一条:prev:dis", "下一条", "编辑", "评论", "更多"],
                 "app": ["空间", "*流程", "通知", "我的"]}[mode] if mode in ("list", "obar", "app") else []
    out = []
    for it in items:
        on = it.startswith("*")
        it = it[1:] if on else it
        parts = it.split(":")
        label = parts[0].strip()
        icon = MTOOL_ICONS.get(label)
        cls = []
        for p in parts[1:]:
            if p == "dis":
                cls.append("dis")
            elif p:
                icon = p
        if not icon:
            raise ExpandError(f"<hb-mtool> 「{label}」没有默认图标，写成「{label}:图标名」")
        if on:
            cls.append("on")
        out.append(f'<span{" class=\"" + " ".join(cls) + "\"" if cls else ""}>{ico(icon, tag="<hb-mtool> ")}{esc(label)}</span>')
    wrap = "apptab" if mode == "app" else ("m-tool obar" if mode == "obar" else "m-tool")
    return f'<div class="{wrap}">' + "".join(out) + "</div>"


def rec_field(c, edit):
    """'字段名 | 值 | 类型' → .m-field；前缀 ! 高亮块。"""
    name = c[0]
    hl = name.startswith("!")
    if hl:
        name = name[1:].strip()
    val = c[1] if len(c) > 1 else ""
    typ = c[2].strip() if len(c) > 2 else "text"
    fl = f'<div class="fl">{esc(name)}</div>'
    ecls = " edit" if edit else ""
    if typ.startswith("opt"):
        parts = [x.strip() for x in val.split("/") if x.strip()]
        inner = ""
        for i, part in enumerate(parts):
            text, color = split_color(part)
            inner += tag(text, color or "blue") if (i == 0 and (color or "*" in part)) or color else f'<span class="opt">{esc(text)}</span>'
        fv = f'<div class="fv opts{ecls}">{inner}<span class="dd">▾</span></div>'
    elif typ == "mem":
        fv = f'<div class="fv{ecls}">' + "".join(f'<span class="mem"><span class="av">{esc(n.strip()[:1])}</span>{esc(n.strip())}</span>' for n in val.split("/") if n.strip()) + "</div>"
    elif typ == "rel":
        r = [x.strip() for x in val.split("/", 1)]
        r2 = f'<div class="r2">{esc(r[1])}</div>' if len(r) > 1 else ""
        fv = f'<div class="fv rel{ecls}"><div class="r1">{ico("f-relation")}{esc(r[0])}</div>{r2}</div>'
    elif typ == "img":
        n = int(val) if val.strip().isdigit() else 1
        ths = "".join(f'<span class="th">{ico("f-image")}</span>' for _ in range(n))
        fv = f'<div class="fv img{ecls}"><div class="thumbs">{ths}</div><div class="up">{ico("f-image")}上传图片</div></div>'
    elif typ.startswith("num"):
        unit = typ.split(":", 1)[1] if ":" in typ else ""
        u = f'<span class="unit">{esc(unit)}</span>' if unit and edit else ""
        v = esc(val) if val else ""
        if not edit and unit and val:
            v = esc(f"{val} {unit}")
        fv = f'<div class="fv{ecls}">{v}{u}</div>'
    else:
        if val.startswith("~"):
            v = f'<span class="ph">{esc(val[1:])}</span>'
        else:
            v = esc(val)
        dd = '<span class="dd">▾</span>' if typ == "sel" else ""
        fv = f'<div class="fv{ecls}">{v}{dd}</div>'
    return f'<div class="m-field{" hl" if hl else ""}">{fl}{fv}</div>'


def m_rec(a, body):
    edit = "edit" in a
    out = []
    for ln in lines(body):
        if ln.startswith("#"):
            out.append(f'<div class="rsec">{esc(ln[1:])}</div>')
        elif ln.startswith(">"):
            c = cells(ln[1:])
            tabs = "".join(f'<span{" class=\"on\"" if i == 0 else ""}>{esc(t)}</span>' for i, t in enumerate(c[:-1] if len(c) > 1 and "来自" in c[-1] else c))
            bd = f'<div class="sv">{esc(c[-1])}</div>' if len(c) > 1 and "来自" in c[-1] else ""
            out.append(f'<div class="m-subtabs"><div class="stab-hd">{tabs}</div><div class="stab-bd">{bd}</div></div>')
        else:
            out.append(rec_field(cells(ln), edit))
    title = f'<div class="rtitle">{esc(a.get("title", ""))}</div>' if a.get("title") else ""
    qr = "" if "noqr" in a else f'<div class="rqr">{ico("f-barcode")}二维码</div>'
    elapsed = f'<div class="elapsed">耗时 {esc(a["elapsed"])}</div>' if "elapsed" in a else ""
    return f'{elapsed}<div class="m-rec">{title}{qr}{"".join(out)}</div>'


def m_fbar(a, body):
    sq = f'<span class="sq">{ico("more")}</span>' if "more" in a else ""
    return f'<div class="m-savebar">{sq}<span class="b cancel">{esc(a.get("cancel", "取消"))}</span><span class="b save">{esc(a.get("save", "保存"))}</span></div>'


def m_taskbar(a, body):
    who = a.get("who", "")
    if not who:
        raise ExpandError('<hb-taskbar> 缺 who（如 who="詹达富 · 出库审批"）')
    sub = f'<small>{esc(a["sub"])}</small>' if "sub" in a else ""
    btns = []
    for ln in lines(body):
        btns.extend(cells(ln))
    tb = "".join(f'<span class="b solid">{esc(b)}</span>' for b in btns if b)
    return (f'<div class="m-taskbar"><div class="th"><span class="av">{esc(who[:1])}</span><span class="tn">{esc(who)}{sub}</span>'
            f'<span class="more">{ico("expand")}</span></div><div class="tb">{tb}</div></div>')


def m_ptasks(a, body):
    tabs = "".join(f'<span{" class=\"on\"" if on else ""}>{esc(n)}{"<i class=\"dot\"></i>" if on and "dot" in a else ""}</span>'
                   for n, on in star_items(a.get("tabs", "我发起的|*我处理的|发起流程")))
    cnt = esc(a.get("count", ""))
    cards = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 4:
            raise ExpandError(f"<hb-ptasks> 每行「发起人 | 时间 | 流程名 · 记录标题 | 节点名 | 按钮(可选)」：{ln}")
        btn = c[4] if len(c) > 4 and c[4] else "办理"
        dd = '<span class="dd">▾</span>' if btn == "办理" else ""
        cards.append(f'<div class="pcard"><div class="ph"><span class="av">{esc(c[0][:1])}</span><span class="who">{esc(c[0])}</span><span class="when">{esc(c[1])}</span>'
                     f'<span class="src">{ico("grid-s")}</span></div><div class="pt">{esc(c[2])}</div><div class="pn">任务：{esc(c[3])}</div>'
                     f'<div class="pact"><span class="b line">{esc(btn)}{dd}</span></div></div>')
    app = m_mtool({"mode": "app"}, "") if "app" in a else ""
    return (f'<div class="m-ptasks">{tabs}</div><div class="pfilter"><span class="cnt">{cnt}</span><span class="sp"></span>'
            f'<span class="b text">批量</span><span class="vic on">{ico("filter")}</span></div><div class="m-cards">{"".join(cards)}</div>{app}')


def m_wpage(a, body):
    out = []
    tabs_html = ""
    sub_html = ""
    for ln in lines(body):
        if ln.startswith("#"):
            out.append(f'<div class="wban">{esc(ln[1:])}</div>')
        elif ln.startswith("sc:"):
            items = []
            for it in cells(ln[3:]):
                if not it:
                    continue
                n, _, ic = it.partition(":")
                items.append(f'<span>{ico(ic.strip() or "app-s", tag="<hb-wpage> ")}{esc(n)}</span>')
            out.append(f'<div class="wcard wsc">{"".join(items)}</div>')
        elif ln.startswith("tabs:"):
            tabs_html = '<div class="wtabs">' + "".join(f'<span{" class=\"on\"" if on else ""}>{esc(n)}</span>' for n, on in star_items(ln[5:])) + "</div>"
        elif ln.startswith("sub:"):
            c = cells(ln[4:])
            chips = ""
            if len(c) > 1:
                chips = '<span class="chips">' + "".join(f'<span class="chip{" on" if on else ""}">{esc(n)}</span>' for n, on in star_items("|".join(c[1:]))) + "</span>"
            sub_html = f'<div class="wsub"><div class="wsh">{esc(c[0])}{chips}</div><div class="wempty"><i></i>没有找到任务</div></div>'
            warn("hb-wpage 的 sub: 会渲染成「没有找到任务」空态：营销图不放空态，任务列表用 hb-ptasks 另起一屏，或去掉 sub:")
        else:
            raise ExpandError(f"<hb-wpage> 行要以 #（横幅）/ sc:（快捷方式）/ tabs:（页签）/ sub:（任务子区）开头：{ln}")
    if tabs_html or sub_html:
        out.append(f'<div class="wcard">{tabs_html}{sub_html}</div>')
    return f'<div class="m-workbench">{"".join(out)}</div>'


def m_chat(a, body):
    out = []
    msg = None

    def close():
        nonlocal msg
        if msg is not None:
            out.append('<div class="msg">' + "".join(msg) + "</div>")
            msg = None

    for ln in lines(body):
        if ln.startswith("@"):
            close()
            out.append(f'<div class="mtime">{esc(ln[1:])}</div>')
        elif ln.startswith("["):
            close()
            m = re.match(r"\[(.*?)\]\s*(.*)", ln)
            msg = [f'<div class="mtag">{esc(m.group(1))}</div>', f'<div class="mt2">{esc(m.group(2))}</div>']
        elif ln.startswith("!"):
            close()
            msg = [f'<div class="mt2">{esc(ln[1:])}</div>']
        elif msg is None:
            raise ExpandError(f"<hb-chat> 消息要先用「[标签] 标题」或「! 标题」开头：{ln}")
        elif ln.startswith(">"):
            msg.append(f'<div class="ml"><span>{esc(ln[1:])}</span>{ico("next")}</div>')
        elif " = " in ln:
            k, v = ln.split(" = ", 1)
            msg.append(f'<div class="kv"><span>{esc(k)}</span>{esc(v)}</div>')
        else:
            msg.append(f'<div class="md2">{esc(ln)}</div>')
    close()
    return '<div class="m-chat">' + "".join(out) + "</div>"


def m_conn(a, body):
    rows = [cells(ln) for ln in lines(body)]
    for c in rows:
        if len(c) > 1 and len(c[1]) > 18:
            warn(f"hb-conn 说明「{c[1]}」超过 18 字：中缝只有 216px 宽，会绕成三四行贴到手机上，精简成一句")
    steps = [f'<div class="step"><b>{esc(c[0])}</b>{esc(c[1]) if len(c) > 1 else ""}</div>' for c in rows]
    arrow = f'<div class="bigarr">{ico("arrow-right")}</div>'
    return '<div class="conn">' + arrow.join(steps) + "</div>"


# ── 页面骨架：hb-page / hb-row / hb-float / hb-duo ─────────────────────
# 模型只填槽位内容，外壳（.stage、.window、.page、详情页画布）由这里产出；
# 槽位表来自 references/principles/ 五篇页面原则里的"固定顺序"。
WARNINGS = []


def warn(msg):
    if msg not in WARNINGS:
        WARNINGS.append(msg)


VIEW_MACROS = {"hb-grid", "hb-kanban", "hb-cards"}
PAGE_SLOTS = {
    "list": dict(
        cn="列表和视图页",
        allowed={"hb-nav", "hb-views", "hb-tools", "hb-grid", "hb-kanban", "hb-cards", "hb-float"},
        required=["hb-nav", "hb-views", "hb-tools"],
        order=["hb-nav", "hb-views", "hb-tools", "视图", "hb-float"],
        need_view=True,
        doc="产品壳 → 视图页签 → 视图区白卡（工具栏 → 视图 → 合计/分页）。视图三选一：hb-grid / hb-kanban / hb-cards；甘特、日历、任务、透视用 extract_templates.py 提模板手写在同一位置。",
        example="""<hb-page kind="list" ws="云图贸易" page="物资档案" me="周">
<hb-nav>
# 物资台账
* 物资档案 | app-s
库存明细 | grid-s | green
</hb-nav>
<hb-views>
* 全部物资
按品类查看
</hb-views>
<hb-tools search="搜索物资" new="新建物资">字段|筛选:1|排序|导入</hb-tools>
<hb-grid total="1,217条">
物资编号 | 品名 | 品类:tag | 当前库存:sum=4,386 | 建档人:user
WZ-JS-0106 | 茅台飞天 53° 500ml | 酒品:red | 36 | 周敏
</hb-grid>
<hb-float top="96" w="356">…浮层内容（底层没有的组件）…</hb-float>
</hb-page>"""),
    "workbench": dict(
        cn="工作台",
        allowed={"hb-nav", "hb-cover", "hb-banner", "hb-stats", "hb-shortcuts", "hb-tasks", "hb-row", "hb-col", "hb-tabcard",
                 "hb-pivot", "hb-filters", "hb-float", "hb-bar", "hb-line", "hb-donut", "hb-area", "hb-hbar",
                 "hb-biaxial", "hb-funnel", "hb-scatter", "hb-map",
                 "hb-multistats", "hb-procs", "hb-list", "hb-progress", "hb-subtotal"},
        required=["hb-nav", "hb-banner", "hb-shortcuts"],
        order=["hb-nav", "hb-cover", "hb-banner", "hb-stats", "hb-shortcuts", "hb-row", "hb-tasks", "hb-multistats",
               "hb-procs", "hb-progress", "hb-subtotal", "hb-list", "hb-pivot", "hb-tabcard", "hb-float"],
        order_free={"hb-tabcard"},
        first_screen_ban={"hb-bar", "hb-line", "hb-donut", "hb-area", "hb-hbar", "hb-biaxial", "hb-funnel",
                          "hb-scatter", "hb-map", "hb-filters"},
        doc="产品壳 → 横幅（必）→ 单指标一行（可选，4～6 个）→ 快捷方式（必）与待办（hb-row 并排）→ 我的数据 → 页签容器。趋势与对比图表、筛选不放首屏（顶层出现会提示），要收进 hb-tabcard 或放页面末尾；hb-tabcard 位置自由，放在 hb-list、hb-pivot 之后把图表收进末位页签也可以。",
        example="""<hb-page kind="workbench" ws="云图贸易" page="库管工作台" me="周">
<hb-nav>
# 物资台账
* 库管工作台 | home
</hb-nav>
<hb-banner>
库管工作台
集中处理出入库审批、库存预警与盘点任务
</hb-banner>
<hb-stats>
待我审批 | 3 | | trend:red
本月出库 | 217 | 件
本仓在库 | 1,842 | 件
库存预警品种 | 6
</hb-stats>
<hb-row spans="8|16">
<hb-shortcuts title="快捷方式">
扫码出入库 | f-barcode
发起盘点 | chart-s
</hb-shortcuts>
<hb-tasks title="待我办理的流程">
出库审批 · CK-20260824-0037 领用出库 | 1.4 小时前 | 库管审批
</hb-tasks>
</hb-row>
<hb-tabcard pill tabs="*出库明细|历史出入库">
<hb-grid bare>…</hb-grid>
</hb-tabcard>
</hb-page>"""),
    "dashboard": dict(
        cn="数据看板",
        allowed={"hb-nav", "hb-cover", "hb-banner", "hb-filters", "hb-stats", "hb-row", "hb-col", "hb-bar", "hb-line", "hb-donut",
                 "hb-area", "hb-hbar", "hb-biaxial", "hb-funnel", "hb-scatter", "hb-map", "hb-pivot", "hb-tabcard",
                 "hb-float", "hb-multistats", "hb-list", "hb-progress", "hb-subtotal"},
        required=["hb-nav", "hb-banner"],
        order=["hb-nav", "hb-cover", "hb-banner", "hb-filters", "hb-stats", "hb-row", "hb-bar", "hb-line", "hb-donut",
               "hb-area", "hb-hbar", "hb-biaxial", "hb-funnel", "hb-scatter", "hb-map", "hb-multistats",
               "hb-progress", "hb-subtotal", "hb-pivot", "hb-list", "hb-float"],
        doc="产品壳 → 横幅（必，一行高）→ 筛选（可选）→ 单指标一行（看板必有）→ 图表行（hb-row 16+8 或 12+12）→ 透视表/明细（底部，≤2 张）。",
        example="""<hb-page kind="dashboard" ws="云图贸易" page="库存分析" me="周">
<hb-nav>
* 库存分析 | chart-s
</hb-nav>
<hb-banner>
库存分析
按仓库与品类查看库存结构、周转与预警
</hb-banner>
<hb-filters>
月份 | f-date
仓库 | f-select
</hb-filters>
<hb-stats>
在库总量 | 4,386 | 件 | trend
本月出库 | 217 | 件 | trend:red
库存周转天数 | 42 | 天 | trend
预警品种 | 6 | | trend:red
</hb-stats>
<hb-row spans="16|8">
<hb-line title="近 30 日出入库趋势" labels="1|5|10|15|20|25|30">
出库 | 12,18,15,22,19,25,21 | blue
入库 | 9,14,11,17,16,19,18 | teal
</hb-line>
<hb-donut title="库存构成" center="在库|4,386">
酒品 | 1842 | red
茶叶 | 1204 | green
</hb-donut>
</hb-row>
<hb-pivot title="库存预警明细">
品名 | 仓库 | 在库 | 下限 | 状态:tag
茅台飞天 53° | 城建大厦酒窖 | 36 | 60 | 低于下限:red
</hb-pivot>
</hb-page>"""),
    "detail": dict(
        cn="自定义详情页",
        allowed={"hb-itembar", "hb-cover", "hb-hcard", "hb-steps", "hb-fields", "hb-row", "hb-col", "hb-tabcard", "hb-flow",
                 "hb-stats", "hb-pivot", "hb-grid", "hb-float", "hb-multistats", "hb-list", "hb-progress",
                 "hb-subtotal", "hb-stream", "hb-comment"},
        required=["hb-itembar", "hb-hcard", "hb-fields", "hb-tabcard"],
        order=["hb-itembar", "hb-cover", "hb-hcard", "hb-steps", "hb-fields", "hb-row", "hb-list", "hb-tabcard",
               "hb-flow", "hb-stream", "hb-comment", "hb-float"],
        doc="记录功能区（必）→ 封面（可选，放最前）→ 页头卡片（必）→ 状态条（可选）→ 字段组（必，单栏或 hb-row spans=13|11 双栏）→ 页签容器（必）→ 流程执行记录、动态、评论。"
            "页头卡片、字段组必有：一条记录先说清是哪条、有哪些字段，页签内的字段组也算。图表宏只能放在 hb-row 或 hb-tabcard 体内，不在顶层。"
            "不套产品壳；浮层只能右探出（side=\"left\" 会报错）。",
        example="""<hb-page kind="detail">
<hb-itembar title="CK-20260824-0037 领用出库">
打印出库单:solid | 撤销:line | 复制:line:dis
</hb-itembar>
<hb-hcard title="CK-20260824-0037" sub="领用出库 · 城建大厦酒窖">
出库状态 | 待审批 | tag
领用人 | 周敏 | user
</hb-hcard>
<hb-steps>已提交 | *库管审批 | 财务复核 | 完成</hb-steps>
<hb-fields title="出库信息" cols="2">
出库单号 | CK-20260824-0037
出库类型 | 领用出库
存放点 | 城建大厦酒窖
用途 | 客户接待
</hb-fields>
<hb-tabcard span="24" tabs="*出库明细|审批记录">
<hb-grid bare>…</hb-grid>
</hb-tabcard>
</hb-page>"""),
    "screen": dict(
        cn="数据大屏",
        allowed={"hb-screen"},
        required=["hb-screen"],
        order=["hb-cover", "hb-screen"],
        doc=("只放一个 hb-screen，不套产品壳、不放浮层。体内按官方骨架排：左列 hb-scol（6 栏：指标框 ×2 → 面积图 → 饼图）"
             "｜中间 hb-svisual（12 栏，跨整个主体高度）｜右列 hb-scol（6 栏：进度条 → 对比图），底部两张 hb-scard 各 12 栏。"
             "标题行与分隔条由 hb-screen 产出。大屏不缩放：24 栅格、行高 20h−20、间距 20 与其他页面一致。"),
        example="""<hb-page kind="screen">
<hb-screen title="物资运营数据大屏" logo="云图贸易" date="2026年09月14日" week="星期一" time="09:41:20" theme="cyan">
<hb-scol span="6" rs="38">
<hb-skpi rs="6">
在库总量 | 4,386 | 件
本月出库 | 217 | 件
</hb-skpi>
<hb-scard title="近 12 个月出库量" rs="16">
<hb-area bare w="355" h="214" labels="10月|11月|12月|1月|2月|3月|4月|5月|6月|7月|8月|9月">
出库量 | 186,204,241,198,152,233,268,247,219,262,288,217
</hb-area>
</hb-scard>
<hb-scard title="库存构成" rs="16">
<hb-donut bare w="355" h="236" center="在库|4,386">
酒品 | 1842
茶叶 | 1204
办公耗材 | 628
礼品 | 402
劳保用品 | 310
</hb-donut>
</hb-scard>
</hb-scol>
<hb-svisual map span="12" rs="38"/>
<hb-scol span="6" rs="38">
<hb-scard title="季度盘点完成率" rs="12">
<hb-sbars>
城建大厦酒窖 | 92%
高新库 | 74%
经开区备件库 | 61%
临时周转库 | 38%
</hb-sbars>
</hb-scard>
<hb-scard title="各仓库出入库对比" rs="26">
<hb-bar bare w="355" h="414" labels="城建大厦|高新库|经开区|周转库">
出库 | 862,517,394,168
入库 | 705,623,288,241
</hb-bar>
</hb-scard>
</hb-scol>
<hb-scard title="近 30 日出入库趋势" span="12" rs="26">
<hb-line bare w="760" h="414" labels="9/1|9/5|9/9|9/13|9/17|9/21|9/25|9/30">
出库 | 128,164,142,218,186,247,203,231
入库 | 96,141,118,173,162,194,176,188
</hb-line>
</hb-scard>
<hb-scard title="库存预警明细" span="12" rs="26">
<hb-list nock noidx count="128">
物资编号 | 品名 | 仓库 | 在库 | 下限 | 状态:tag
WZ-JS-0106 | 茅台飞天 53° 500ml | 城建大厦酒窖 | 36 | 60 | 低于下限:red
WZ-CY-0218 | 明前龙井 250g | 高新库 | 74 | 40 | 正常:green
WZ-BG-1042 | A4 复印纸 70g | 经开区备件库 | 18 | 50 | 低于下限:red
WZ-LB-0377 | 防砸安全鞋 42 码 | 临时周转库 | 9 | 30 | 低于下限:red
WZ-JS-0219 | 五粮液 52° 500ml | 城建大厦酒窖 | 128 | 60 | 正常:green
WZ-LP-0088 | 中秋礼盒 双支装 | 高新库 | 24 | 80 | 低于下限:red
WZ-BG-1106 | 中性笔 0.5mm 黑 | 经开区备件库 | 640 | 200 | 正常:green
WZ-LB-0412 | 劳保手套 12 副装 | 临时周转库 | 47 | 60 | 低于下限:red
WZ-CY-0331 | 安溪铁观音 500g | 高新库 | 83 | 40 | 正常:green
</hb-list>
</hb-scard>
</hb-screen>
</hb-page>"""),
    "mobile": dict(
        cn="手机端",
        allowed={"hb-phone", "hb-screens", "hb-duo", "hb-cover"},
        required=[],
        order=["hb-cover", "hb-phone", "hb-screens"],
        doc="只看一个页面：放一个 hb-phone（画布 520 宽）。讲一段流程：放一个 hb-screens，体内 hb-phone 与 hb-conn 交替，一步一屏，2～3 屏（画布 1100／1640 宽）。不套 .window。",
        example="""<hb-page kind="mobile">
<hb-screens>
<hb-phone title="待办">
<hb-ptasks tabs="*待办|已办" count="3">
周敏 | 10:24 | 出库审批 · CK-0037 | 库管审批 | 办理
</hb-ptasks>
</hb-phone>
<hb-conn>
点「办理」 | 进入任务办理页
核对后审批 | 一键通过或驳回
</hb-conn>
<hb-phone title="任务办理">
<hb-rec title="CK-0037 领用出库">
物资 | 茅台飞天 53° | text
</hb-rec>
<hb-taskbar who="周敏" sub="库管审批">通过 | 驳回</hb-taskbar>
</hb-phone>
</hb-screens>
</hb-page>"""),
}
PAGE_SLOTS["analysis"] = PAGE_SLOTS["dashboard"]

SHELL_ATTRS = ("ws", "logo", "page", "nav", "me", "theme", "bottom")


def _top_level(raw):
    """把 hb-page 体内拆成顶层片段：[(宏名或 None, 原文)]，非宏的手写 HTML 原样保留。"""
    parts, pos = [], 0
    for m in TAG_RE.finditer(raw):
        gap = raw[pos:m.start()].strip()
        if gap:
            parts.append((None, gap))
        parts.append((m.group(1), m.group(0)))
        pos = m.end()
    tail = raw[pos:].strip()
    if tail:
        parts.append((None, tail))
    return parts


def m_float(a, body):
    side = a.get("side", "right")
    if side not in ("right", "left"):
        raise ExpandError('<hb-float side> 只能是 right 或 left')
    top = str(a.get("top", "96")).rstrip("px")
    w = str(a.get("w", "356")).rstrip("px")
    n_cards = len(re.findall(r'class="w-card', body))
    if n_cards > 2:
        warn(f"浮层里放了 {n_cards} 个组件卡：浮层只强调一两个底层没有的东西，多了就成了第二张图")
    title = f'<div class="float-title">{esc(a["title"])}</div>' if a.get("title") else ""
    return (f'<div class="mk-float{" left" if side == "left" else ""}" data-side="{side}" '
            f'style="--float-top:{top}px;--float-w:{w}px">{title}{body.strip()}</div>')


def m_col(a, body):
    parts = [p for p in _top_level(a.get("_raw", body))]
    items = [expand(raw) if name else raw for name, raw in parts]
    names = [n for n, _ in parts if n]
    if len(names) < 2:
        raise ExpandError("<hb-col> 是给一栏里竖叠 2～3 个组件用的；只有 1 个组件就直接放进 hb-row 那一段")
    if len(names) > 3:
        warn(f"hb-col 里竖叠了 {len(names)} 个组件：一栏最多叠 3 个，多了这栏会比邻栏高出一截")
    return '<div class="w-col">' + "".join(items) + "</div>"


def m_row(a, body):
    parts = [p for p in _top_level(a.get("_raw", body))]
    spans = [s.strip() for s in str(a.get("spans", "")).split("|") if s.strip()]
    items = []
    for name, raw in parts:
        items.append(expand(raw) if name else raw)
    if spans:
        if len(spans) != len(items):
            raise ExpandError(f'<hb-row spans="{a["spans"]}"> 有 {len(spans)} 段，体内却有 {len(items)} 个组件，两者要一样多')
        total = sum(int(s) for s in spans)
        if total != 24:
            raise ExpandError(f'<hb-row spans="{a["spans"]}"> 跨度加起来是 {total}，必须等于 24（常用 12|12、16|8、8|16、8|8|8、13|11）')
        items = [f'<div class="span-{s}">{it}</div>' for s, it in zip(spans, items)]
    if len(items) > 4:
        warn(f"hb-row 里并排了 {len(items)} 个组件：一行最多 4 个，图表行只放 2～3 个")
    return '<div class="w-row">' + "".join(items) + "</div>"


def m_screens(a, body):
    html = body.strip()
    phones = html.count('<div class="phone')
    conns = html.count('<div class="conn">')
    if phones < 2 or phones > 3:
        raise ExpandError(f"<hb-screens> 体内有 {phones} 个 hb-phone：流程壳放 2～3 屏（一步一屏）；超过 3 步拆成两张图")
    if conns != phones - 1:
        raise ExpandError(f"<hb-screens> 有 {phones} 屏但 {conns} 条 hb-conn：每两屏之间放一条中缝说明（hb-phone、hb-conn 交替）")
    return f'<div class="duo" data-screens="{phones}">{html}</div>'


m_duo = m_screens  # 旧名，保留给已有片段


def _check_slots(kind, spec, names, deep, first_screen=None):
    allowed = spec["allowed"]
    for n in (first_screen if first_screen is not None else deep):
        if n in spec.get("first_screen_ban", set()):
            warn(f"<hb-page kind=\"{kind}\"> 顶层放了 <{n}>：{spec['cn']}首屏不放图表与筛选，要放就收进 <hb-tabcard> 或放页面末尾")
    for n in names:
        if n not in allowed:
            raise ExpandError(f"<hb-page kind=\"{kind}\"> 顶层不能放 <{n}>；{spec['cn']}顶层可用：{'、'.join(sorted(allowed))}。"
                              f"{'图表与筛选请放进 <hb-tabcard> 或页面末尾。' if n in spec.get('first_screen_ban', set()) else ''}")
    for r in spec["required"]:
        if r not in deep:
            raise ExpandError(f"<hb-page kind=\"{kind}\"> 缺 <{r}>：{spec['cn']}必有。顺序：{' → '.join(spec['order'])}")
    if spec.get("need_view") and not (set(names) & VIEW_MACROS):
        warn("列表页顶层没有视图宏（hb-grid/hb-kanban/hb-cards）：用模板手写的甘特/日历/任务/透视视图请放在 hb-tools 之后")
    # 顺序：按 order 表的位次应单调不减（视图宏都算"视图"位）；order_free 的宏位置自由，不参与比对
    rank = {n: i for i, n in enumerate(spec["order"])}
    free = spec.get("order_free", set())
    last = -1
    for n in names:
        if n in free:
            continue
        r = rank.get(n if n not in VIEW_MACROS else "视图", rank.get(n, -1))
        if r == -1:
            continue
        if r < last:
            warn(f"<hb-page kind=\"{kind}\"> 的 <{n}> 位置靠后了：建议顺序 {' → '.join(spec['order'])}")
        last = max(last, r)
    from collections import Counter
    c = Counter(names)
    if c.get("hb-stats", 0) > 1:
        warn("出现了两组单指标：单指标只放一行，多出来的并成多项统计或改进度条/透视表")
    if c.get("hb-banner", 0) > 1 and kind != "dashboard":
        warn("横幅出现了两次：只有看板中段可以再放一个做段落标题")
    if c.get("hb-pivot", 0) > 2:
        warn(f"透视表 {c['hb-pivot']} 张：默认 ≤2 张，多了先并成一张多维透视")


def m_page(a, body):
    kind = a.get("kind")
    if kind not in PAGE_SLOTS:
        raise ExpandError(f"<hb-page kind> 只能是 {'/'.join(k for k in PAGE_SLOTS if k != 'analysis')}（analysis 同 dashboard）")
    spec = PAGE_SLOTS[kind]
    canvas = a.get("canvas", "marketing")
    if canvas not in ("marketing", "product"):
        raise ExpandError('<hb-page canvas> 只能是 marketing（营销类，一张图）或 product（产品设计类，照着搭）')
    parts = _top_level(a.get("_raw", body))
    names = [n for n, _ in parts if n]
    deep = list(names)          # 「必有」用：容器体内的宏也算出现过
    first_screen = list(names)   # 首屏禁令用：并排行仍在首屏，页签容器里的不算
    _ban = spec.get("first_screen_ban", set())
    _tail = 0
    for _n in reversed(first_screen):
        if _n in _ban or _n == "hb-float":
            _tail += 1
        else:
            break
    if _tail:
        first_screen = first_screen[:len(first_screen) - _tail]   # 页面末尾的图表不算首屏
    for n, raw in parts:
        if n in ("hb-row", "hb-tabcard", "hb-col"):
            inner = TAG_RE.match(raw).group(3) or ""
            for m in TAG_RE.finditer(inner):
                deep.append(m.group(1))
                if n == "hb-row":
                    first_screen.append(m.group(1))
                if m.group(1) in ("hb-row", "hb-tabcard", "hb-col"):
                    sub = TAG_RE.match(m.group(0)).group(3) or ""
                    deep += [x.group(1) for x in TAG_RE.finditer(sub)]
                    if n == "hb-row" and m.group(1) == "hb-col":
                        first_screen += [x.group(1) for x in TAG_RE.finditer(sub)]
    if kind != "mobile":
        bad = re.search(r"<(hb-(?:phone|screens|mhome|vbar|ocards|mtool|rec|fbar|taskbar|ptasks|wpage|chat|conn))\b", a.get("_raw", body))
        if bad:
            raise ExpandError(f"<{bad.group(1)}> 是手机组件，只能放在 kind=\"mobile\" 的页面里；PC 页和 PC 浮层里放 hb-fields、hb-list、hb-multistats、hb-stats 这类 PC 组件，样式才会生效")
    _check_slots(kind, spec, names, deep, first_screen)
    floats, main_parts, nav_html = [], [], ""
    for name, raw in parts:
        if name == "hb-nav":
            mm = TAG_RE.match(raw)
            nav_html = m_nav(attrs_of(mm.group(2)), mm.group(3) or "")
            continue
        html_ = expand(raw) if name else raw
        if name == "hb-float":
            if canvas == "product":
                raise ExpandError("产品设计类画布不放浮层：去掉 <hb-float>，或改 canvas=\"marketing\"")
            if kind == "detail" and 'data-side="left"' in html_:
                raise ExpandError("自定义详情页的浮层只能右探出：把 <hb-float> 的 side 改成 right（详情页左边是字段与正文，左探会盖住记录本身）")
            floats.append(html_)
        else:
            main_parts.append((name, html_))
    stage_cls = ["stage", "auto"]
    if floats:
        stage_cls.append("has-float")
        if any('data-side="left"' in f for f in floats):
            stage_cls.append("float-left")
    if canvas == "product":
        stage_cls.append("product")
    stage_style = ""
    cut = str(a.get("cut", "")).rstrip("px")

    def shell(inner):
        attrs = " ".join(f'{k}="{a[k]}"' for k in SHELL_ATTRS if k in a and a[k] is not True)
        if "ws" not in a:
            raise ExpandError(f'<hb-page kind="{kind}"> 缺 ws（工作区名，产品壳左上角）')
        return m_shell(attrs_of(attrs), nav_html + inner)

    if kind == "list":
        views = "".join(h for n, h in main_parts if n == "hb-views")
        tools = "".join(h for n, h in main_parts if n == "hb-tools")
        rest = "".join(h for n, h in main_parts if n not in ("hb-views", "hb-tools"))
        inner = f'{views}<div class="view-box">{tools}{rest}</div>'
        body_html = shell(inner)
    elif kind in ("workbench", "dashboard", "analysis"):
        level = a.get("level", "flat")
        if level not in ("flat", "card"):
            raise ExpandError('<hb-page level> 只能是 flat（白底描边，默认）或 card（浅底白卡）')
        page_cls = "page flat" if level == "flat" else "page"
        inner = f'<div class="{page_cls}">' + "".join(h for _, h in main_parts) + "</div>"
        body_html = shell(inner)
    elif kind == "detail":
        bar = "".join(h for n, h in main_parts if n == "hb-itembar")
        rest = []
        for n, h in main_parts:
            if n == "hb-itembar":
                continue
            rest.append(h if re.match(r'\s*<div class="(span-|w-row)', h) else f'<div class="span-24">{h}</div>')
        body_html = (f'<main class="item-page">{bar}<div class="item-page-scroll"><div class="item-page-canvas">'
                     f'<div class="item-grid">{"".join(rest)}</div></div></div></main>')
    elif kind == "screen":
        body_html = "".join(h for _, h in main_parts)
    else:  # mobile
        body_html = "".join(h for _, h in main_parts)
        screens = max([int(m) for _, h in main_parts for m in re.findall(r'data-screens="(\d)"', h)] or [1])
        stage_style = {1: "width:520px", 2: "width:1100px", 3: "width:1640px"}[screens]
    if kind in ("list", "workbench", "dashboard", "analysis") and cut:
        body_html = body_html.replace('<div class="window ', f'<div class="window cut" style="height:{cut}px" ', 1)
    st = f' style="{stage_style}"' if stage_style else ""
    return f'<div class="{" ".join(stage_cls)}" data-kind="{kind}"{st}>{body_html}{"".join(floats)}</div>'


def render_page(kind):
    if kind not in PAGE_SLOTS:
        raise ExpandError(f"没有页面类型 {kind}。可用：{'/'.join(k for k in PAGE_SLOTS if k != 'analysis')}")
    spec = PAGE_SLOTS[kind]
    lines_ = [f"[{spec['cn']}] <hb-page kind=\"{kind}\">", spec["doc"],
              f"必有：{'、'.join(spec['required']) or '无'}；顺序：{' → '.join(spec['order'])}",
              "顶层可用宏：" + "、".join(f"<{n}>" for n in sorted(spec["allowed"]) if n != "hb-duo"),
              "hb-page 通用属性：canvas=marketing|product（默认 marketing）、ws/page/nav/me/theme/logo/bottom（产品壳，同 hb-shell）、level=flat|card（页面底色，默认 flat）、cut=高度px（窗口截到主要内容为止，默认按内容撑高）",
              "", "最小示例：", spec["example"], "",
              "各宏语法：python3 scripts/expand.py --doc " + " ".join(sorted(n for n in spec["allowed"] if n != "hb-float")) + " hb-row hb-float"]
    return "\n".join(lines_)


MACROS = {
    "hb-page": (m_page, "页面骨架：kind=list|workbench|dashboard|detail|screen|mobile；产出画布与外壳，体内按槽位放宏；--page kind 看槽位表"),
    "hb-row": (m_row, "24 栅格一行：属性 spans=16|8（加起来 24）；体内并排放组件宏，最多 4 个"),
    "hb-col": (m_col, "hb-row 某一段里竖叠 2～3 个组件：矮组件（按钮组、多项统计、进度条）别单独占一栏被拉高"),
    "hb-float": (m_float, "营销浮层：属性 side=right|left、top、w、title；体内放底层没有的 PC 组件（hb-list / hb-fields / hb-multistats…），不放手机宏"),
    "hb-screens": (m_screens, "手机流程壳（2～3 屏）：体内 hb-phone 与 hb-conn 交替，一步一屏"),
    "hb-duo": (m_duo, "hb-screens 的旧名"),
    "hb-shell": (m_shell, "PC 产品壳：左侧导航＋一级顶栏，体内先写 <hb-nav>，其后是 .main 里的页面内容"),
    "hb-nav": (m_nav, "左侧导航树：# 分组；名称 | 图标 | 颜色，* 前缀＝当前页；> 文件夹，- 子项"),
    "hb-views": (m_views, "视图页签行：名称 | 图标，* 前缀＝当前视图"),
    "hb-tools": (m_tools, "工具栏：字段|筛选:1|排序|导入|自定义:图标；属性 search、new"),
    "hb-grid": (m_grid, "网格表格：首行表头（列名:类型 / :sum=值），其后每行一条记录；# 分组行，! 选中行"),
    "hb-pivot": (m_pivot, "透视表（维度 × 指标的统计，做数据分析用）：首行表头，其后数据行，值是数字；一条条记录用 hb-list"),
    "hb-stats": (m_stats, "单指标一行：指标名 | 值 | 单位 | spark:1,2,3 或 trend:red；mode=center|strip"),
    "hb-tasks": (m_tasks, "待办子区：标题 | 时间 | 节点说明；属性 title"),
    "hb-shortcuts": (m_shortcuts, "快捷方式：名称 | 图标；属性 title"),
    "hb-filters": (m_filters, "筛选组件：筛选文本 | 图标"),
    "hb-banner": (m_banner, "横幅组件：第一行页面名称，第二行一句话介绍；属性 solid；card 出背景图卡片式（date、time、img）"),
    "hb-bar": (m_bar, "柱状图卡：labels=横轴|…；每行「系列名 | 值,值,… | 颜色」"),
    "hb-line": (m_line, "折线图卡：同 hb-bar；属性 plain 去掉卡片外壳"),
    "hb-donut": (m_donut, "环图卡：每行「名称 | 值 | 颜色」；属性 center=标签|值"),
    "hb-area": (m_area, "面积图卡：同 hb-line 语法，折线下 20% 透明填充"),
    "hb-hbar": (m_hbar, "条形图卡（横向条）：每行「名称 | 值 | 颜色」，标签在左、数值在右"),
    "hb-biaxial": (m_biaxial, "双轴图卡：labels=横轴|…；两行「系列名 | 值,值,… | bar」柱走左轴、「… | line」折线走右轴"),
    "hb-funnel": (m_funnel, "漏斗图卡：每行「阶段名 | 值」，自上而下逐级收窄，右侧标转化率"),
    "hb-scatter": (m_scatter, "散点图卡：属性 x、y 轴名；每行「名称 | x 值 | y 值 | 大小(可省)」"),
    "hb-map": (m_map, "地图卡：每行「地点 | 值」，网点阵＋标记点（不画轮廓）；属性 img 放客户提供的地图图片"),
    "hb-fields": (m_fields, "字段组：# 开分组；每行「字段名 | 值 | 类型」；属性 title、cols（默认 2）、span"),
    "hb-multistats": (m_multistats, "多项统计：每行「名称 | 数值 | 颜色」，右侧彩色胶囊；属性 title、span"),
    "hb-procs": (m_procs, "我发起的：每行「流程名 | 单据 | 当前节点 | 状态:颜色 | 时间」；属性 title、span"),
    "hb-list": (m_list, "表格列表：体内同 hb-grid（首行表头）；属性 title、span、tools、count"),
    "hb-progress": (m_progress, "进度条：每行「名称 | 完成值 | 目标值 | 颜色」；属性 title、span、style=bar|text"),
    "hb-subtotal": (m_subtotal, "分类汇总：首行是合计，其后每行「名称 | 数值」；属性 title、span"),
    "hb-cover": (m_cover, "页面封面：属性 title、sub、icon；放页面最前，封面 280 高＋80 图标＋40 号大标题"),
    "hb-stream": (m_stream, "动态：每行「人名 | 时间 | 内容」，人名写 sys:名 出系统动态；属性 span"),
    "hb-comment": (m_comment, "评论：每行「人名 | 时间 | 内容」，无行出空态；属性 title、span"),
    "hb-itembar": (m_itembar, "详情页记录功能区：属性 title；体内快捷按钮「名:solid|名:line|名:line:dis」"),
    "hb-hcard": (m_hcard, "详情页页头卡片：属性 title、sub；体内关键字段行同 hb-info"),
    "hb-tabcard": (m_tabcard, "页签卡：属性 tabs=*页签|页签、span；pill 出工作台胶囊式（一律居中）；体内放已展开的内容"),
    "hb-flow": (m_flow, "流程页签时间线：属性 name、by；每行「节点名 | 状态:颜色 | 日期 | 耗时 | 链接」"),
    "hb-info": (m_info, "详情页页头卡片信息区：字段名 | 值 | 类型"),
    "hb-steps": (m_steps, "状态条：步骤 | *当前 | 步骤；默认箭头式（status_bar），pill 出选项字段平铺胶囊"),
    "hb-kanban": (m_kanban, "看板视图：# 分组:颜色 | 数量 开列，其后每行「标题 | 字段=值; 字段=值」"),
    "hb-cards": (m_cards, "卡片视图：标题 | 字段=值; 字段=值 | 操作:图标:颜色"),
    "hb-screen": (m_screen, "数据大屏画布：属性 title、sub、logo、date、week、time、theme=cyan|blue|gold|red|light、bg（装饰底图，默认不用）；体内放 hb-scol/hb-scard/hb-svisual"),
    "hb-scol": (m_scol, "大屏主体分栏：属性 span（默认 6）、rs（默认 38）；体内竖着放 hb-skpi/hb-scard，各组件 rs 之和等于本列 rs"),
    "hb-skpi": (m_skpi, "大屏指标框：每行「指标名 | 值 | 单位 | up/down」，一行 2 个；属性 span（默认 6）、rs（默认 6）"),
    "hb-scard": (m_scard, "大屏组件卡：属性 title、span（默认 6）、rs（默认 16）；体内放 hb-area/line/bar/donut 的 bare 输出、hb-sbars 或 hb-list"),
    "hb-sbars": (m_sbars, "大屏进度条列表：每行「名称 | 百分比」，条底色蓝/橙/绿/红轮转"),
    "hb-svisual": (m_svisual, "大屏中央视觉位：属性 span（默认 12）、rs（默认 38）、title、img=客户图片路径、map=网点阵占位；空则线框地球"),
    "hb-phone": (m_phone, "手机壳＋顶栏：属性 title、fix、nobar；体内放页面内容"),
    "hb-mhome": (m_mhome, "工作区首页：属性 tabs=表格|*流程…；每行一个分组，- 前缀为展开的表"),
    "hb-vbar": (m_vbar, "列表页视图条：属性 view、count、icon、nosearch"),
    "hb-ocards": (m_ocards, "三槽卡片列表：标题 | 副标题 | 字段=值; 字段=值; 字段=值 | 按钮:图标 | img；属性 fab、pager、bare"),
    "hb-mtool": (m_mtool, "底部 56 栏：mode=list（列表工具栏，默认）/ obar（记录操作条）/ app（应用页签栏）；体内可自定义项"),
    "hb-rec": (m_rec, "记录页：属性 title、edit、noqr、elapsed；# 分组；字段名 | 值 | 类型(text/sel/opt/mem/rel/img/num:单位)；! 前缀高亮；> 子表页签"),
    "hb-fbar": (m_fbar, "表单保存条：属性 cancel、save、more"),
    "hb-taskbar": (m_taskbar, "任务办理区：属性 who、sub；体内按钮名 | 按钮名"),
    "hb-ptasks": (m_ptasks, "流程任务列表：属性 tabs、count、dot、app；每行「发起人 | 时间 | 流程名 · 记录标题 | 节点名 | 按钮」"),
    "hb-wpage": (m_wpage, "手机工作台：# 页面名；sc: 名:图标 | …；tabs: *页签 | 页签；sub: 子区名 | 全部 | *待执行 | 已完成"),
    "hb-chat": (m_chat, "企微会话流：@时间；[标签] 标题 开一条消息；k = v；> 链接；其余为正文"),
    "hb-conn": (m_conn, "屏间中缝说明：每行「步骤标题 | 一句说明」，行间自动加箭头"),
}

# ── 宏说明（--list 看目录，--doc 名 取详细语法；references/macros.md 由 --doc all 生成）──
COMMON = """通用写法
- 宏体按行写，一行一条；行内用 | 分列，\\| 表示字面竖线；空行和 // 开头的行忽略。
- 值后缀 :red :blue :green :orange :teal :purple :yellow :gray 把该值做成彩色标签（:gray 是灰底标签）。
- 值前缀 ~ 做成次要灰字（空值、备注）；值前缀 = 表示后面是写好的 HTML 原样放入；含 < 的值也按 HTML 原样放。
- 宏可嵌套，内层先展开。列数不对、图标名不存在、工具名没图标都会报错并指出行，改完重跑。
- 宏只消灭机械重复，不替你做设计决策：用哪种视图、放不放浮层、字段怎么排、数据编成什么样，仍按 SKILL.md 和设计原则定。
- 没有对应宏的组件：`python3 scripts/registry.py --list 页面类型` 里「宏」一列是 — 的那些，按 SKILL.md 路由表用 extract_templates.py 提取模板手写。"""

GROUPS = [
    ("页面骨架（先写它，外壳由它产出）", ["hb-page", "hb-row", "hb-col", "hb-float", "hb-screens"]),
    ("产品壳（PC）", ["hb-shell", "hb-nav"]),
    ("列表页", ["hb-views", "hb-tools", "hb-grid", "hb-kanban", "hb-cards"]),
    ("自定义页面组件（工作台 / 数据看板）", ["hb-cover", "hb-banner", "hb-filters", "hb-stats", "hb-shortcuts", "hb-tasks",
                                            "hb-multistats", "hb-procs", "hb-list", "hb-progress", "hb-subtotal",
                                            "hb-bar", "hb-line", "hb-donut", "hb-area", "hb-hbar", "hb-biaxial",
                                            "hb-funnel", "hb-scatter", "hb-map", "hb-pivot"]),
    ("独立自定义详情页", ["hb-itembar", "hb-hcard", "hb-info", "hb-fields", "hb-steps", "hb-tabcard", "hb-flow", "hb-stream", "hb-comment"]),
    ("数据大屏（2026-09-14 实测官方六张样板，c5-screen.html）", ["hb-screen", "hb-scol", "hb-skpi", "hb-scard", "hb-sbars", "hb-svisual"]),
    ("手机端（2026-09-03 H5 实测结构，壳 375 宽）", ["hb-phone", "hb-mhome", "hb-vbar", "hb-ocards", "hb-mtool", "hb-rec", "hb-fbar", "hb-taskbar", "hb-ptasks", "hb-wpage", "hb-chat", "hb-conn"]),
]

DOCS = {
"hb-page": """整页骨架。属性 kind（必填）list/workbench/dashboard/detail/screen/mobile；canvas=marketing（默认，一张图，可放 hb-float）/product（照着搭，全屏无浮层）；产品壳属性 ws（PC 页必填）/page/nav/me/theme/logo/bottom 同 hb-shell；level=flat（默认）/card；cut=高度 px（把窗口截到主要内容为止）。
体内直接写各槽位的宏，不再写 .stage/.window/.page/.item-page；先 python3 scripts/expand.py --page kind 看槽位表与最小示例。""",
"hb-col": """一栏里竖叠组件。只放在 hb-row 的某一段里，体内按上下顺序放 2～3 个组件宏，算 hb-row 的一个组件。
并排时同一行各栏会被拉到等高：一栏只有一张矮卡（按钮组 3～6 个、多项统计 3 行、进度条）而邻栏是长列表或字段组时，矮卡会被拉高、卡里空一大块。这时用 hb-col 把矮组件叠在一起，或叠一个待办／统计在下面。
例：
<hb-row spans="8|16">
<hb-col>
<hb-shortcuts title="快捷方式">
新建巡检计划 | check-s
飞行检查派单 | warn
</hb-shortcuts>
<hb-multistats title="待办">
待我审核的整改 | 12 | orange
超期未整改 | 3 | red
</hb-multistats>
</hb-col>
<hb-tasks title="待我审核的整改">
…
</hb-tasks>
</hb-row>""",
"hb-row": """24 栅格一行。属性 spans="16|8"（各段跨度，加起来必须 24；不写则等分）。体内并排放组件宏（hb-shortcuts、hb-tasks、hb-bar、hb-donut、hb-pivot、hb-tabcard…），最多 4 个；一段里要叠两个组件就包一层 hb-col。
例：
<hb-row spans="16|8">
<hb-line title="趋势" labels="1|2|3">出库 | 1,2,3 | blue</hb-line>
<hb-donut title="构成">酒品 | 60 | red</hb-donut>
</hb-row>""",
"hb-float": """营销浮层。属性 side=right（默认）/left、top（距画布顶 px，默认 96）、w（宽 px，默认 356）、title。体内放底层没有的东西，且只能是 PC 组件：hb-list、hb-fields、hb-multistats、hb-stats、hb-grid bare，或 extract_templates.py 提的表单编辑页模板；手机宏（hb-ocards、hb-rec 等）样式只在 hb-phone 里生效，放进来会散成裸文字，expand 会报错。不复制底层已有内容；最多两张卡。
例：
<hb-float side="left" top="220" w="392" title="华北区整改超期门店">
<hb-list title="整改超期门店" nock noidx count="3">
门店 | 督导 | 超期:tag | 状态:tag
味捷·北京朝阳大悦城店 | 张伟 | 6 天:red | 待跟进
味小捷·天津和平路店 | 刘洋 | 4 天:red | 待跟进
味捷·石家庄万象城店 | 张伟 | 2 天:orange | 已催办:green
</hb-list>
</hb-float>""",
"hb-screens": """手机流程壳：体内 hb-phone、hb-conn、hb-phone（、hb-conn、hb-phone）交替，一步一屏，2～3 屏；每个 hb-phone 加 fix。hb-page kind=mobile 按屏数把画布设成 1100／1640 宽；超过 3 步拆成两张图。企微会话那一屏用 hb-chat 写在第一个 hb-phone 里。""",
"hb-duo": """hb-screens 的旧名，语法相同。""",
"hb-shell": """属性：ws 工作区名（必填）、logo（默认取 ws 首字）、page 顶栏当前页名、nav 图标行高亮项 home/table/doc/flow（默认 table）、me 头像字、theme band/side/full/light（默认 band）、bottom（默认 管理|成员）。
体内先写 <hb-nav>，其后是放进 .main 的页面内容（视图页签、view-box、.page 等）。
.stage、has-float、.mk-float 浮层、补充样式仍由你写；hb-shell 只产出 .window 到 .main 顶栏为止的壳。
例：
<div class="stage">
<hb-shell ws="云图贸易" page="物资档案" nav="table" me="周">
<hb-nav>…</hb-nav>
…页面内容…
</hb-shell>
</div>""",
"hb-nav": """行：# 分组名；名称 | 图标 | 颜色（图标默认 app-s，颜色给 ic-* 类）；* 前缀＝当前页；> 文件夹名 | 子项数；- 前缀＝文件夹下的子项。
例：
# 物资台账
* 物资档案 | app-s
库存明细 | grid-s | green
> 归档资料 | 3
- 2025 年台账 | doc
# 出入库
出库单 | check-s | orange""",
"hb-views": """行：名称 | 图标，图标默认 grid-s（看板 board-s、日历 f-date、甘特 chart-s）；* 前缀＝当前视图。自动补「创建视图」和溢出入口，noadd 去掉创建。
例：
* 全部物资
按品类查看
珍藏品专区 | board-s""",
"hb-tools": """工具用 | 分开；内置图标的工具名：字段 分组 筛选 排序 冻结 行高 导入 导出 打印 分享；筛选:1＝激活态并显示条数；其他工具写 名称:图标名。
属性 search 搜索框占位文字、new 新建按钮文字（nodd 去掉分裂箭头）。放在 <div class="view-box"> 里、hb-grid 之前。
例：
<hb-tools search="搜索品名或编号" new="新建物资">字段 | 筛选:1 | 排序 | 导入 | 打印二维码:print</hb-tools>""",
"hb-grid": """首行表头，列名后可接类型 :tag（彩色选项）:tags（多值，值用 / 分）:user（人员，多人用 / 分）:ops（行内按钮，名:图标:颜色，多个用 / 分）；统计 :sum=值 :avg= :max= :min= :count=。
其后每行一条记录，列数必须与表头一致。# 分组值:颜色 插分组行；! 前缀＝选中行。
属性 total="1,217条" 出底部合计行（有统计列时自动出）；nock 去勾选列、noidx 去行号列；bare 只出 .grid（放进 w-card、浮层、页签容器内时用），默认带 .table-view.view-grid 和横向滚动条。
例：
<hb-grid total="1,217条">
物资编号 | 品名 | 品类:tag | 当前库存:sum=4,386 | 建档人:user | 操作:ops
WZ-JS-0106 | 茅台飞天 53° 500ml | 酒品:red | 36 | 周敏 | 打印:print:teal / 出库:arrow-right:blue
# 茶叶:green
WZ-CY-0412 | 武夷山大红袍 | 茶叶:green | 24 | 陈晓东 | ~
</hb-grid>""",
"hb-kanban": """# 分组名:颜色 | 数量 开一列，其后每行 标题 | 字段=值; 字段=值。
例：
# 待审核:orange | 3
SO-2026-0901 | 客户=杭州云图; 金额=¥12,480.00
# 已完成:green | 12
SO-2026-0812 | 客户=上海博远; 金额=¥7,650.00""",
"hb-cards": """卡片视图，每行 标题 | 字段=值; 字段=值 | 操作:图标:颜色。
例：
杭州云图 | 行业=制造; 年采购=¥1,204,000 | 拜访:arrow-right:blue""",
"hb-banner": """第一行页面名称，第二行一句话介绍（口吻规则见 references/principles/workbench.md）；属性 solid 铺纯色背景。
属性 card 出背景图卡片式（120 高白卡，实测工作台常用）：date="2026年09月04日"、time="16:51:17" 出日期时间行；img 出右侧图片位（值写 <img src="…"> 放客户配图，空值留渐变占位）。卡片式不放介绍句。
例：
<hb-banner>库管工作台
实现物资出入库与盘点的集中管理</hb-banner>
<hb-banner card date="2026年09月04日" time="16:51:17" img>任务工作台</hb-banner>""",
"hb-filters": """行：筛选文本 | 图标，图标默认 f-select（日期用 f-date）。
例：
统计月份：2026 年 8 月 | f-date
存放点：全部""",
"hb-stats": """每行 指标名 | 值 | 单位 | 附加。mode="center"（默认，居中大数）或 mode="strip"（左文右图，附加写 spark:数,数,… 自动画走势线）；居中大数的附加可写 trend 或 trend:red 出底部趋势条。4～6 个时自动加 stats-N。
例：
<hb-stats>
在库总量 | 4,386
本月出库 | 217 | 件
库存预警品种 | 6 | | trend:red
</hb-stats>
<hb-stats mode="strip">
今日扫码开单 | 14 | spark:28,22,25,14,17,9,6
</hb-stats>""",
"hb-shortcuts": """行：名称 | 图标；属性 title 出标题栏。按钮宽度自适应内容、文字不折行，一行排不下自动换第二行（2026-09-04 实测）。
例：
<hb-shortcuts title="常用">
扫码出入库 | f-barcode
发起盘点 | chart-s
</hb-shortcuts>""",
"hb-tasks": """行：标题 | 时间 | 节点说明 | 按钮名（缺省「办理」，写 - 去掉）；属性 title 出子区标题。任务行右侧固定有办理按钮（2026-09-04 实测）。
例：
<hb-tasks title="待我办理的流程">
出库审批 · CK-20260824-0037 | 1.4 小时前 | 陈晓东 扫码创建 · 待仓库主管审批
</hb-tasks>""",
"hb-bar": """属性 title、labels（横轴，| 分）、max（不给自动取整）、ticks（默认 4）、h（配合本图补充样式改 .chart .wc-bd 高度时同步给）。
每行 系列名 | 值,值,… | 颜色；系列值用逗号分隔，不写千分位。颜色缺省：第一系列主色，第二系列主色 45% 透明，再往后状态色；显式给颜色用状态色。图例自动生成。默认 w-card w-chart 卡，bare 只出 svg＋图例，plain 去掉卡片外壳只留 40 高标题行（产品 common 样式）。
例：
<hb-bar title="近 6 个月出入库趋势" labels="3 月|4 月|5 月|6 月|7 月|8 月">
出库 | 135,165,115,185,212,217
入库 | 82,102,70,135,117,143
</hb-bar>""",
"hb-line": """折线图，属性和行格式同 hb-bar（同样支持 bare / plain）。
例：
<hb-line title="近 5 周签约额" labels="W31|W32|W33|W34|W35">
签约额 | 42,55,38,61,70
目标 | 50,50,50,50,50 | orange
</hb-line>""",
"hb-area": """面积图，属性和行格式同 hb-bar；折线下方铺 20% 透明的同色面积（2026-09-14 实测 chart_area）。
加 plain 去掉卡片外壳（产品的 common 样式：无底、无边、无影，只剩 40 高标题行）。
例：
<hb-area title="近 6 个月库存水位" labels="3 月|4 月|5 月|6 月|7 月|8 月">
在库总量 | 3820,4010,3960,4180,4290,4386 | teal
</hb-area>""",
"hb-biaxial": """双轴图（官方 chart_biaxial）。属性 title、labels（横轴，| 分）、span、max（左轴上限，柱）、max2（右轴上限，线）、ticks（默认 4）、plain、bare、w、h。
体内正好两行：第一行「系列名 | 值,值,… | bar」画柱走左轴，第二行「系列名 | 值,值,… | line」画折线走右轴；两轴刻度各自算，图例两项。
颜色按实测走：柱次色、线主色（大屏里自动换成大屏系列色），第四列可显式给状态色。量纲不同的两组数（金额与数量、件数与达成率）才用双轴，同量纲就用 hb-bar 多系列。
例：
<hb-biaxial title="近 6 个月出库量与周转天数" labels="3 月|4 月|5 月|6 月|7 月|8 月">
出库量 | 135,165,115,185,212,217 | bar
周转天数 | 48,45,51,43,40,42 | line
</hb-biaxial>""",
"hb-funnel": """漏斗图（官方 chart_funnel）。属性 title、span、plain、bare、w、h。每行「阶段名 | 值」，至少两段，自上而下逐级收窄；右侧标原值与对首段的转化率，颜色是主色由深到浅。
讲一条链路一级级掉下来的量才用它（线索→商机→报价→签约）；并列的几类量用 hb-bar 或 hb-hbar。
例：
<hb-funnel title="销售漏斗">
线索 | 1,240
商机 | 486
报价 | 214
签约 | 96
</hb-funnel>""",
"hb-scatter": """散点图（官方 chart_scatter）。属性 title、x（横轴名）、y（纵轴名）、xmax、ymax、ticks（默认 4）、span、plain、bare、w、h。
每行「名称 | x 值 | y 值 | 大小(可省)」：给了第四列就按它定点的大小（气泡图），点用主色半透明。
看两个指标之间有没有关系才用它（客单价与复购率、库龄与周转），只有一个维度时用柱图。
例：
<hb-scatter title="客户库龄与周转" x="平均库龄（天）" y="周转次数">
城建大厦酒窖 | 42 | 8.6 | 1842
高新库 | 61 | 5.2 | 1097
经开区备件库 | 28 | 11.4 | 764
</hb-scatter>""",
"hb-map": """地图（官方 chart_map）。属性 title、span、plain、bare、w、h、img（客户提供的地图图片路径，给了就直接放图）。
每行「地点 | 值」：网点阵底上按值定标记点大小，右侧列成地点小表。**不画任何国家或省份轮廓**（审图号与边界准确性），要真实地图就让客户给图走 img。
例：
<hb-map title="各仓库在库分布">
城建大厦酒窖 | 1,842
高新库 | 1,097
经开区备件库 | 764
临时周转库 | 310
</hb-map>""",
"hb-hbar": """条形图（官方 chart_bar_y，横向条）。每行 名称 | 值 | 颜色（颜色缺省按 red/blue/purple/teal/green/orange 轮转）；属性 title、span、max（不给按最大值取整）、plain。
标签在左、条在中、数值在右；条长按 值/max 算。
例：
<hb-hbar title="各存放点在库量" plain>
城建大厦酒窖 | 1,842 | blue
北京办公室 | 1,097 | teal
上海仓 | 764 | green
</hb-hbar>""",
"hb-fields": """字段组（官方 field_group，详情页最常用的组件）。属性 title、cols=1～4（每行字段数，默认 2）、span、icon、tint。
体内：# 分组名 开一组（分组标题行 40 高，三种浅色底轮转）；其余每行 字段名 | 值 | 类型。
类型：缺省文本；user 人员（多人用 / 分）、tag 彩色选项、tags 多选项（/ 分）；multi 多行文本、file 附件、image 图片是不定高类型，自动独占一行。
字段行 69 高＝标签 24 ＋ 值框 32 ＋ 上下内距（2026-09-14 实测）。
例：
<hb-fields title="订单详情" cols="2" tint="blue">
# 基本信息
订单编号 | SO-2026-0901
客户 | 杭州云图 | tag
# 交付与回款
负责人 | 周敏 | user
交付状态 | 已发货:green
备注 | 客户要求分两批发货，第二批下月初 | multi
</hb-fields>""",
"hb-multistats": """多项统计（官方 multi_stats，工作台「待办」那一类）。属性 title、span。
每行 名称 | 数值 | 颜色（缺省按 orange/green/red/yellow/purple/blue 六色轮转，实测就是按条目顺序轮转）。
条 40 高，右侧数值是 20 高、圆角 10 的彩色胶囊——这是它和分类汇总最直观的差别。
例：
<hb-multistats title="待办" span="8">
待我审批的出库单 | 3
待确认的入库单 | 7
超期未盘点品种 | 2 | red
</hb-multistats>""",
"hb-procs": """我发起的（官方 procedure_process）。属性 title、span。
每行 流程名 | 单据 | 当前节点 | 状态:颜色 | 时间，行 80 高、三行字号 14/12/12；一行都不写时画「暂无」空态。
例：
<hb-procs title="我发起的" span="8">
出库审批 | CK-20260824-0037 领用出库 | 仓库主管审批 | 审批中:orange | 1.4 小时前
采购申请 | CG-20260820-0012 | 财务复核 | 已完成:green | 8月20日
</hb-procs>""",
"hb-list": """表格列表（官方 table_item_list，工作区里用得最多的组件）。属性 title、span、tools（工具图标，| 分：搜索/新建/新增/导出/导入/更多/筛选/打印/分享/设置）、count（记录数，出底部「共 N 条」）、nock / noidx / total 透传给表体。
体内就是 hb-grid 的写法：首行表头（列名:类型 / :sum=值），其后每行一条记录。
外壳实测：标题行 40、表头 32、数据行 35、底部分页条 40，白卡圆角 9。
例：
<hb-list title="出库记录" tools="搜索|新建|导出" count="1,217" span="12">
出库单号 | 物资 | 数量 | 领用人:user | 状态:tag
CK-20260824-0037 | 茅台飞天 53° | 12 | 周敏 | 待审批:orange
CK-20260823-0036 | 武夷山大红袍 | 6 | 陈晓东 | 已出库:green
</hb-list>""",
"hb-progress": """进度条（官方 progress_bar），一个组件里可以放多条。属性 title、span、style：
- style="bar"（默认，产品 newStyle）：条 32 高圆角 6，名称与百分比嵌在条内，进度覆盖到的那段文字转白。
- style="text"（产品 normal）：文字行 24（名称左、百分比右）＋ 下方 4 高圆角 10 的细条。
两种形态每条都占 40 高。每行 名称 | 完成值 | 目标值 | 颜色（缺省按 blue/green/yellow/purple/orange/teal 轮转），百分比＝完成值/目标值。
例：
<hb-progress title="计划完成进度" style="bar" span="8">
9 月生产计划 | 8200 | 10000 | purple
9 月发货计划 | 6400 | 10000
</hb-progress>""",
"hb-subtotal": """分类汇总（官方 subtotal）。属性 title、span。首行是合计行（加粗），其后每行 名称 | 数值。
条目 40 高，右侧是纯文本、没有胶囊，顶部多一条合计行——与多项统计的区别就在这两点。
例：
<hb-subtotal title="分品类库存金额" span="6">
共计 | 5,076.8 k
酒品 | 2,841.2 k
茶叶 | 1,320.4 k
礼盒 | 915.2 k
</hb-subtotal>""",
"hb-cover": """页面封面（官方 cover 元素，不是组件）。属性 title（必填，页面标题）、sub、icon（图标名，默认 app-s）。
放页面最前：封面 280 高、取内容区全宽；页面图标 80×80 圆角 8 压在封面下沿；标题 40 号 / 56 行高 / 500 粗（2026-09-14 实测）。
list 之外的 hb-page 都能用，一页只放一个。
例：
<hb-cover title="库存分析" sub="按仓库与品类查看库存结构、周转与预警" icon="chart-s"></hb-cover>""",
"hb-stream": """动态（官方 stream）。属性 span。没有标题行——实测该组件 is_name_show 为 false。
每行 人名 | 时间 | 内容，内容可以再用 | 续写成多行（一个字段变更一行，实测多字段变更就是这么排的）。
人名写成 sys:名 出系统动态：左侧画铅笔图标而不是头像，用来表示自动化、自动计算这类系统来源。
单行条目 40 高、三行 72 高，条间距 16。
例：
<hb-stream span="24">
周敏 | 12 分钟前 | 订单状态：待审批 → 审批中
sys:自动化 | 1 小时前 | 订单总额：修改为 941 | 待回款金额：修改为 941 | 订单总利润：修改为 0
</hb-stream>""",
"hb-comment": """评论（官方 comment）。属性 title、span。每行 人名 | 时间 | 内容，内容可用 | 续写多行。
一行都不写时画空态：48 圆图标＋「暂无评论」。底部固定一条 68 高的发布条。
例：
<hb-comment title="评论" span="8">
陈晓东 | 昨天 17:06 | 第二批发货时间已与客户确认
</hb-comment>
<hb-comment title="评论" span="8"></hb-comment>""",
"hb-donut": """每行 名称 | 值 | 颜色（值可带千分位；颜色缺省按 red/blue/purple/teal/green/orange 轮转）；center="标签|值" 出中心文字；百分比自动算，图例画在右侧。默认 w-card w-chart 卡，bare 只出 svg，plain 去掉卡片外壳只留标题行。
例：
<hb-donut title="各存放点库存占比" center="在库总量|4,386">
城建大厦酒窖 | 1,842
北京办公室 | 1,097
</hb-donut>""",
"hb-pivot": """透视表（官方 chart_table），做数据分析用：首列是维度（区域、产品、月份、人员），其余列是该维度下的数字指标，值可带 :red 做成标签。它不是记录列表，编号、门店、负责人、日期、状态这种一条条的记录用 hb-list（表格列表）；列里带 :user/:tag、或大部分格子是文字时会报错。属性 title、icon、tint（yellow/blue/teal 标题栏底色）、dim（首列维度灰底）、bare 只出 <table>。
例：
<hb-pivot title="分存放点库存统计" dim>
存放点 | 品种数 | 在库数量
城建大厦酒窖 | 486 | 1,842
</hb-pivot>""",
"hb-itembar": """记录功能区（自定义详情页默认自带，56 高）。属性 title 记录主标题（必填）、nosys 不出右侧系统操作。
体内快捷按钮用 | 分开：名:solid（主色实底）、名:line（线框）、再接 :dis 置灰或 :green/:orange/:teal 实底色。
例：
<hb-itembar title="出库单 CK-20260824-0037">确认出库:solid | 驳回修改:line | 打印出库单:line:dis</hb-itembar>""",
"hb-hcard": """页头卡片（信息摘要，不放按钮）。属性 title 主标题（必填）、sub 副标题或编号、span（默认 24）。体内 1～4 行关键字段，格式同 hb-info：字段名 | 值 | 类型。
例：
<hb-hcard title="领用出库 · 城建大厦酒窖" sub="CK-20260824-0037 · 共 8 个品种 / 14 瓶">
出库类型 | 领用出库:orange
出库仓库 | 城建大厦酒窖
申请人 | 陈晓东 | user
申请日期 | 2026-08-24
</hb-hcard>""",
"hb-tabcard": """页签卡（页签容器）。属性 tabs="*出库明细|历史出入库|现场照片"（* 当前页签，必填）、span（给了就外包一层 .span-N 栅格）。体内放页签内容：hb-grid bare、字段、hb-flow、form-hint 等。
默认是详情页的下划线页签，靠左；工作台/看板要胶囊式页签（选中主色 20% 底条）写 pill，胶囊只在居中时成立，pill 一律居中；页签按角色工作流程从左到右或按业务分类编排。
例：
<hb-tabcard tabs="*出库明细|历史出入库|现场照片" span="16">
<hb-grid bare nock>
品名 | 库位 | 本次出库:sum=14 | 领用人:user
七燕酒庄干红 750ml | 3 号酒柜 2 层 | 2 瓶 | 徐慧敏
</hb-grid>
<div class="form-hint">审批状态变为「已出库」时库存自动扣减。</div>
</hb-tabcard>
<hb-tabcard tabs="*流程|动态|评论" span="8">
<hb-flow …>…</hb-flow>
</hb-tabcard>
<hb-tabcard tabs="*进行中任务|已完成任务|工作报告|跟进汇总" pill>
<hb-grid bare nock>…</hb-grid>
</hb-tabcard>""",
"hb-flow": """流程页签时间线（放在 tabs="*流程|动态|评论" 的 hb-tabcard 里）。属性 name 流程名（必填）、by="发起人 · 时间"、foot（默认「查看详细记录」）、nocancel 不出「撤销流程」。
每行一个节点，倒序（最新在上）：节点名 | 状态文本:颜色 | 日期 | 耗时 | 链接；颜色 orange 执行中（缺省）/ green 同意 / red 驳回 / gray 未开始；启动事件写「启动事件 | 事件描述 | 日期」。
例：
<hb-flow name="出库审批" by="陈晓东 · 8月24日 09:12">
仓库主管审批 | 周敏 执行中 | 8月24日 09:40 | 1.4小时 | 催办
启动事件 | 陈晓东 扫码创建了「CK-20260824-0037 领用出库单」 | 8月24日 09:12
</hb-flow>""",
"hb-info": """页头卡片信息区，每行 字段名 | 值 | 类型（类型 user/tag/tags，缺省文本；值带 :颜色 自动成标签）。放在 .header_card 里、标题区之后。
例：
出库类型 | 领用出库:orange
申请人 | 陈晓东 | user
申请日期 | 2026-08-24""",
"hb-steps": """状态条，* 标当前步骤；属性 span（默认 24）、pill。两种形态实测下来是两个不同的东西：
- 默认＝官方 status_bar 组件：箭头式分段，整条 40 高、白卡圆角 9；段间重叠 10px 咬合，已过段主色 25% 底＋ink-45 字，当前段主色实底白字，未到段透明底＋ink-85 字。
- pill＝选项字段的平铺展示（is_tile）：全圆角胶囊、20 高、固定宽，选中段填该选项自身颜色（当前项写 *名称:颜色 指定），其余透明底。
例：
<hb-steps>提交申请 | *仓库主管审批 | 行政总监审批 | 已出库</hb-steps>
<hb-steps pill>待派工 | 已派工 | *生产中:orange | 已完工</hb-steps>""",
"hb-screen": """数据大屏画布（不套产品壳）。属性 title 页面名（必填）、sub 副题、logo 左上企业名、date/week/time 右上日期星期时间、
theme 配色 cyan 深青未来（默认）/blue 蓝色科技/gold 黑金金融/red 红色党建/light 青色自然（浅色），bg 装饰底图 earth/city/grid/gold（默认不用，五个主题本身就有网格纹理和顶部光带）。
大屏就是普通的 24 栅格页面，不缩放：列宽、行高、20 间距与其他页面一致，h 行的组件高 20h−20。画布 1640 宽，官方骨架排下来 1440 高。
体内按官方骨架放：标题行和分隔条由本宏自动产出，其后依次是左列 hb-scol（6）、中间 hb-svisual（12）、右列 hb-scol（6），最后底部两张 hb-scard（12＋12）。
例：见 python3 scripts/expand.py --page screen 的最小示例（可直接 build）。""",
"hb-scol": """大屏主体分栏。属性 span 列宽（默认 6）、rs 列高行数（默认 38）。体内竖着放 hb-skpi、hb-scard，
列内各组件的 rs 之和要等于本列的 rs，三列才等高（官方：左 6＝6＋16＋16，中 12＝38，右 6＝12＋26）。
例：
<hb-scol span="6" rs="38">
<hb-skpi rs="6">在库总量 | 4,386 | 件
本月出库 | 217 | 件</hb-skpi>
<hb-scard title="近 12 个月出库量" rs="16"><hb-area bare labels="…">…</hb-area></hb-scard>
<hb-scard title="库存构成" rs="16"><hb-donut bare center="在库|4,386">…</hb-donut></hb-scard>
</hb-scol>""",
"hb-skpi": """大屏指标框，每行「指标名 | 值 | 单位 | up/down」（up 绿 down 红）。一行 2 个（官方左列是两个 3×6 的单指标），最多 3 个。
属性 span（默认 6）、rs（默认 6，高 100）。指标名 14 白 45% 在上，值 32/500 白 85% 在下，居中。
例：
<hb-skpi rs="6">
在库总量 | 4,386 | 件
本月出库 | 217 | 件 | up
</hb-skpi>""",
"hb-scard": """大屏组件卡：40 高标题条（左侧斜切铭牌）＋ 内容区。属性 title 组件名（必填）、span 列宽（默认 6）、rs 行数（默认 16，高 20rs−20）。
体内放 hb-area / hb-line / hb-bar / hb-donut / hb-biaxial / hb-funnel / hb-scatter / hb-map 的 bare 输出、hb-sbars 进度条、hb-list 表格列表或手绘 SVG；图表系列色自动走大屏固定配色。
例：
<hb-scard title="近 30 日出入库趋势" span="12" rs="26">
<hb-line bare labels="1|5|10|15|20|25|30">
出库 | 12,18,15,22,19,25,21
入库 | 9,14,11,17,16,19,18
</hb-line>
</hb-scard>""",
"hb-sbars": """大屏进度条列表（放进 hb-scard 体内），每行「名称 | 百分比」。条底色按蓝／橙／绿／红轮转（官方实测色序）。
例：
<hb-sbars>
城建大厦酒窖 | 92%
高新库 | 74%
</hb-sbars>""",
"hb-svisual": """大屏中央视觉位（12 栏，跨整个主体高度）。属性 span（默认 12）、rs（默认 38）、title 标题（给了就出标题条）、
img 客户图片路径（地图、3D 厂区图、产品图；本地文件 build.py 会内嵌进单文件）、map 网点阵占位（标题默认「区域分布」）。
都不给时画线框地球。三种形态都不画国家或省份轮廓（边界准确性与审图号）。
例：
<hb-svisual map span="12" rs="38"/>
<hb-svisual span="12" rs="38" title="厂区实时状态" img="素材/厂区3D.png"/>""",
"hb-phone": """手机壳＋顶栏 44。属性 title（顶栏标题：表名/流程名/企业名·应用名）、fix（固定 812 高，hb-screens 里必加）、nobar。体内按页面形态放手机端其他宏。
.stage 宽度由 hb-page 按屏数给（单屏 520、两屏 1100、三屏 1640）。
例：
<div class="stage">
  <div class="duo">
<hb-phone title="纳承国际 · 存货管理"><hb-chat>…</hb-chat></hb-phone>
<hb-conn>…</hb-conn>
<hb-phone title="客户存货单" fix><hb-vbar view="未取完" count="12"/><hb-ocards fab>…</hb-ocards><hb-mtool/></hb-phone>
  </div>
</div>""",
"hb-mhome": """工作区首页＝页签行＋搜索＋分组列表。属性 tabs="*表格|流程|页面|动态|库管工作台"（* 当前）、search 占位、head（默认「全部表格」）；每行一个分组名如 产品库存(3)，- 前缀是展开后的表名。
例：
<hb-mhome tabs="*表格|流程|页面|动态|库管工作台">
产品库存(3)
- 物品资料表
- 库存表
出库(2)
</hb-mhome>""",
"hb-vbar": """列表页视图条 48。属性 view 视图名、count 条数、icon（默认 grid-s）、nosearch。自闭合写法。
例：
<hb-vbar view="全部数据" count="11"/>""",
"hb-ocards": """手机专用，只放在 hb-phone 里。三槽卡片列表（产品默认卡片形态，最多 3 个字段）。每行 标题 | 副标题 | 字段=值; 字段=值; 字段=值 | 按钮名:图标 | img；副标题可留空；值后缀 :gray 做灰底标签、:orange 等做彩色选项标签；第四列省略则无按钮；第五列写 img 出右侧图片位。
属性 fab 出悬浮新建钮、pager="20 行/页" 出分页条、bare 只出卡片不带列表底。
例：
<hb-ocards fab>
王丽娟：8 件｜朝阳门店 | 2026-08-12 下单 · 收款 ¥3,680 | 未取件数=8 件; 状态=部分取货:orange; 经手=李明 | 登记取货:check
孙国强：0 件｜朝阳门店 | | 库位=A-03-02-02:gray; 当前库存数量=0; 库存下限=1
</hb-ocards>""",
"hb-mtool": """底部 56 栏。mode="list"（默认：列统计/字段设置/分组/筛选/排序）、mode="obar"（记录详情操作条：上一条置灰/下一条/编辑/评论/更多）、mode="app"（企业级应用页签：空间/*流程/通知/我的）；体内写 名:图标 | 名 可自定义，* 前缀高亮，:dis 置灰。
例：
<hb-mtool/>
<hb-mtool mode="obar"/>
<hb-mtool>列统计 | 筛选 | 排序</hb-mtool>""",
"hb-rec": """记录页（详情/编辑/新建/任务办理共用）。属性 title（记录标题；新建写表名）、edit（编辑态白值框）、noqr、elapsed="1.7天"（任务页顶部耗时条）。
体内：# 分组名 出居中分组标题；字段名 | 值 | 类型——类型缺省文本，sel 带下拉箭头，opt 选项并排（值写 当前值:blue / 其他 / 其他），mem 成员胶囊（多人 / 分），rel 关联（值写 主行 / 副行），img 图片（值写张数），num:元 数值带单位；值前缀 ~ 出占位灰字（「请先选择：仓库」「保存后显示计算结果」）；字段名前缀 ! 整块青绿高亮（计算字段、本节点可编辑字段）；> 页签1 | 页签2 | 来自 出库明细 的数据 · 共 1 条 出子表页签容器。
例：
<hb-rec title="CK_20260902_001 直接出库" elapsed="1.7天">
!出库状态 | 待审批:blue / 已出库 / 已驳回 / 作废 | opt
出库单号 | CK_20260902_001
# 出库信息
出库仓库 | 澄川珍藏物品库 / 联系电话 | rel
申请人 | 詹达富 | mem
出库拍照 | 1 | img
> 出库明细 | 辅助字段 | 来自 出库明细 的数据 · 共 1 条
</hb-rec>""",
"hb-fbar": """编辑/新建底部保存条 57。属性 cancel、save、more（新建页左侧方钮）。
例：
<hb-fbar more/>""",
"hb-taskbar": """任务办理页底部 100 高。属性 who="詹达富 · 出库审批"、sub 记录标题；体内 按钮名 | 按钮名。任务页＝hb-rec elapsed ＋ hb-taskbar，本节点可改字段加 !。
例：
<hb-taskbar who="詹达富 · 出库审批" sub="CK_20260902_001 直接出库">确认出库 | 驳回修改</hb-taskbar>""",
"hb-ptasks": """企业级流程任务列表。属性 tabs（默认 我发起的|*我处理的|发起流程）、count="筛选出 1990 条/共 17842 条"、dot（当前页签红点）、app（带底部应用页签栏）；每行 发起人 | 时间 | 流程名 · 记录标题 | 节点名 | 按钮（按钮缺省「办理 ▾」，可写「领取任务」）。
例：
<hb-ptasks count="筛选出 1990 条/共 17842 条" dot app>
詹达富 | 昨天 19:28 | 付款审批 · 待审批-啥都有集团 | 财务审批 | 领取任务
詹达富 | 昨天 01:37 | 出库审批 · CK_20260902_001 直接出库 | 出库审批
</hb-ptasks>""",
"hb-wpage": """手机工作台。# 页面名 横幅；sc: 库存看板:pie-s | 出库管理:check-s 快捷方式两列；tabs: *出入库情况 | 仓库报表 页签容器；sub: 出库审批 | 全部 | *待执行 | 已完成 流程任务子区（空态）。
例：
<hb-wpage>
# 库管工作台
sc: 库存看板:pie-s | 出库管理:check-s | 入库管理:trend-s | 库存盘点:chart-s
tabs: *出入库情况 | 仓库报表
sub: 出库审批 | 全部 | *待执行 | 已完成
</hb-wpage>""",
"hb-chat": """企微会话流（微信端样式，未实测）。@时间 出时间戳；[标签] 标题 开一条带标签的消息，! 标题 开一条无标签消息；字段 = 值（等号两边有空格）出键值行；> 文字 出底部链接；其余行是正文。
例：
@今天 09:21
[取货审批 · 待办] 王丽娟 的取货申请待你确认
门店 = 朝阳门店 · 经手 李明
> 去确认
@昨天 17:06
! 本周配货已确认
8 家门店的配货申请已由库管确认，合计 76 件。""",
"hb-conn": """屏间中缝，每行 步骤标题 | 一句说明，行间自动加大箭头。
例：
企业微信收到待办 | 不用另装 App，消息点进去就能办
进入本人工作台 | 销售只看得到自己名下的客户与存货""",
}
MOBILE_NOTE = "手机上没有独立的「审批流程条」组件：审批走流程页签的任务列表（hb-ptasks）和任务办理页（hb-rec ＋ hb-taskbar），不要画 PC 那种时间线。"


def render_docs(names):
    out = []
    for n in names:
        if n not in MACROS:
            raise ExpandError(f"没有宏 <{n}>。可用：{'、'.join(MACROS)}")
        out.append(f"<{n}>  {MACROS[n][1]}\n{DOCS[n]}")
    return "\n\n".join(out)


def render_all():
    parts = ["# 宏语法\n\n本文件由 `python3 scripts/expand.py --doc all` 生成，改语法请改 expand.py 的 DOCS，不要手改这里。\n出图时不整读本文件：先 `--list` 看目录，再 `--doc 宏名…` 只取要用的几条。\n", COMMON]
    for title, names in GROUPS:
        parts.append(f"\n## {title}\n")
        for n in names:
            parts.append(f"### {n}\n{MACROS[n][1]}\n\n```\n{DOCS[n]}\n```\n")
        if title.startswith("手机端"):
            parts.append(MOBILE_NOTE + "\n")
    return "\n".join(parts)



TAG_RE = re.compile(r"<(hb-[\w-]+)(\s[^>]*?)?(?:/>|>(.*?)</\1>)", re.S)


def expand(text):
    """递归展开：先展开宏体里的内层宏，再展开自己。"""
    def repl(m):
        name, raw_attrs, body = m.group(1), m.group(2), m.group(3) or ""
        if name not in MACROS:
            raise ExpandError(f"不认识的宏 <{name}>。可用：{'、'.join(MACROS)}（python3 scripts/expand.py --list 看说明）")
        attrs = attrs_of(raw_attrs)
        if name in ("hb-page", "hb-row", "hb-col"):
            attrs["_raw"] = body
            return MACROS[name][0](attrs, body)
        if "<hb-" in body:
            body = TAG_RE.sub(repl, body)
        return MACROS[name][0](attrs, body)

    text = TAG_RE.sub(repl, text)
    if "<hb-" in text:
        m = re.search(r"<hb-[\w-]+[^>]*>", text)
        raise ExpandError(f"有宏没闭合或嵌套写错：{m.group(0) if m else ''}")
    return re.sub(r"<!--/?HB-NAV-->", "", text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--list", action="store_true", help="通用写法＋全部宏目录（一宏一行）")
    ap.add_argument("--doc", nargs="+", metavar="宏名", help="打印指定宏的详细语法；all 打印全部（用于生成 references/macros.md）")
    ap.add_argument("--page", metavar="页面类型", help="打印该页面类型的槽位表、可用宏与最小示例（list/workbench/dashboard/detail/screen/mobile）")
    a = ap.parse_args()
    if a.list:
        print(COMMON + "\n")
        for title, names in GROUPS:
            print(f"[{title}]")
            for n in names:
                print(f"  <{n}>  {MACROS[n][1]}")
        print("\n详细语法：python3 scripts/expand.py --doc 宏名 宏名…")
        return 0
    if a.page:
        try:
            print(render_page(a.page))
        except ExpandError as e:
            sys.stderr.write(f"{e}\n")
            return 1
        return 0
    if a.doc:
        try:
            print(render_all() if a.doc == ["all"] else render_docs(a.doc))
        except ExpandError as e:
            sys.stderr.write(f"{e}\n")
            return 1
        return 0
    if not a.file:
        print(__doc__)
        return 2
    try:
        out = expand(Path(a.file).read_text(encoding="utf-8"))
    except ExpandError as e:
        sys.stderr.write(f"展开失败：{e}\n")
        return 1
    for w in WARNINGS:
        sys.stderr.write(f"提示：{w}\n")
    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
        sys.stderr.write(f"已展开：{a.out}\n")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
