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
            out.append(f'<div class="folder"><span class="fi">{ico("folder", tag="<hb-nav> ")}</span>{esc(c[0])}{n}<span class="more">{ico("more")}</span></div>')
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
        leaf = f'<div class="leaf{" current" if cur else ""}"><span class="{li}">{ico(icon, tag="<hb-nav> ")}</span>{esc(c[0])}</div>'
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
    <div class="side">
      <div class="side-top"><span class="ws-logo">{esc(logo)}</span><span class="ws-name">{esc(ws)}</span><span class="plus">{ico("plus")}</span></div>
      <div class="ico-row">{icons_row}</div>
      {tree}
      <div class="bottom">{bottom_html}</div>
    </div>
    <div class="main">
      <div class="top-bar">
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
    return '<div class="views">' + "".join(out) + "</div>"


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
    return '<div class="tools">' + "".join(out) + "</div>"


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
    return f'<div class="table-view grid-view"><div class="grid">{table}<div class="hscroll"><i></i></div></div></div>'


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
    return f'<div class="w-card w-pivot">{card_head(a, "hb-pivot")}{table}</div>'


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
            out.append(f'<div class="w-card w-stat center"><div class="st-lb">{esc(label)}</div><div class="st-vl">{vl}</div>{tr}</div>')
        else:
            sp = spark_svg(spark) if spark else ""
            out.append(f'<div class="w-card w-stat strip"><div class="st-bd"><div class="st-lb">{esc(label)}</div><div class="st-vl">{vl}</div></div>{sp}</div>')
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
    return f'<div class="w-sub">{hd}{"".join(out)}</div>'


def m_shortcuts(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        icon = c[1] if len(c) > 1 and c[1] else "app-s"
        out.append(f'<div class="sc"><span class="sc-ic">{ico(icon, tag="<hb-shortcuts> ")}</span>{esc(c[0])}</div>')
    return (f'<div class="w-card w-shortcut">{card_head(a, "hb-shortcuts")}'
            f'<div class="wc-bd sc-list">{"".join(out)}</div></div>')


def m_filters(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        icon = c[1] if len(c) > 1 and c[1] else "f-select"
        out.append(f'<div class="w-filter">{esc(c[0])} {ico(icon, cls="ico cal", tag="<hb-filters> ")}</div>')
    return '<div class="w-filters">' + "".join(out) + "</div>"


def m_banner(a, body):
    ls = lines(body)
    if not ls:
        raise ExpandError("<hb-banner> 第一行是页面名称，第二行是一句话介绍")
    if "card" in a:
        dt = ""
        if "date" in a or "time" in a:
            dt = f'<div class="ban-dt"><b>{esc(str(a.get("date", "")))}</b><span>{esc(str(a.get("time", "")))}</span></div>'
        img = f'<div class="ban-img">{a["img"] if isinstance(a.get("img"), str) and "<" in a["img"] else ""}</div>' if "img" in a else ""
        return f'<div class="w-banner card"><div class="ban-body"><h1>{esc(ls[0])}</h1>{dt}</div>{img}</div>'
    p = f"<p>{esc(ls[1])}</p>" if len(ls) > 1 else ""
    cls = "w-banner" + (" bg-solid" if "solid" in a else "")
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
        return f'fill="var(--c-{s["color"]})"', f'stroke="var(--c-{s["color"]})"', ""
    if i == 0:
        return 'fill="var(--primary)"', 'stroke="var(--primary)"', ""
    if i == 1:
        return 'fill="var(--primary)"', 'stroke="var(--primary)"', ' opacity=".45"'
    c = SERIES_COLORS[(i - 2) % len(SERIES_COLORS)]
    return f'fill="var(--c-{c})"', f'stroke="var(--c-{c})"', ""


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


def chart_card(a, inner, legend, tagname, par="none"):
    # par：柱/折线拉伸填满卡片（none）；环图必须等比，否则圆被抻成椭圆
    W, H = int(a.get("w", 560)), int(a.get("h", 240))
    svg = f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="{par}" xmlns="http://www.w3.org/2000/svg">{"".join(inner)}</svg>'
    if "bare" in a:
        return svg + legend
    return f'<div class="w-card w-chart">{card_head(a, tagname)}<div class="wc-bd">{svg}</div>{legend}</div>'


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
    cx, cy, r, sw = 150, H / 2, 66, 34
    C = 2 * math.pi * r
    inner = [f'<g transform="translate({cx},{cy:.0f})">']
    cum = 0.0
    for i, s in enumerate(slices):
        color = s["color"] or SERIES_COLORS[i % len(SERIES_COLORS)]
        s["color"] = color
        length = C * s["val"] / total
        inner.append(f'<circle r="{r}" fill="none" stroke="var(--c-{color})" stroke-width="{sw}" '
                     f'stroke-dasharray="{length:.1f} {C - length:.1f}" transform="rotate({-90 + 360 * cum:.1f})"/>')
        cum += s["val"] / total
    inner.append("</g>")
    if "center" in a:
        cl = cells(a["center"])
        inner.append(f'<text x="{cx}" y="{cy - 5:.0f}" font-size="13" fill="var(--ink-45)" text-anchor="middle">{esc(cl[0])}</text>')
        if len(cl) > 1:
            inner.append(f'<text x="{cx}" y="{cy + 17:.0f}" font-size="20" font-weight="600" fill="var(--ink-85)" text-anchor="middle">{esc(cl[1])}</text>')
    n = len(slices)
    step = 36 if n <= 5 else 28
    y0 = cy - (n - 1) * step / 2
    inner.append('<g font-size="12" fill="var(--ink-65)">')
    for i, s in enumerate(slices):
        y = y0 + i * step
        pct = round(100 * s["val"] / total)
        inner.append(f'<rect x="290" y="{y - 9:.0f}" width="10" height="10" rx="2" fill="var(--c-{s["color"]})"/>'
                     f'<text x="308" y="{y:.0f}">{esc(s["name"])}　{esc(s["raw"])}（{pct}%）</text>')
    inner.append("</g>")
    return chart_card(a, inner, "", "hb-donut", par="xMidYMid meet")


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
    out = []
    for i, it in enumerate(items):
        name = it[1:].strip() if it.startswith("*") else it
        cls = "preceding" if i < cur else "current" if i == cur else "following"
        out.append(f'<span class="{cls}">{esc(name)}</span>')
    span = a.get("span", "24")
    return f'<div class="option-steps span-{span}">' + "".join(out) + "</div>"


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
    return (f'<div class="item-page-toolbar"><div class="item-page-nav">{ico("prev")}{ico("next")}</div>'
            f'<div class="item-page-record-title">{esc(title)} <span class="caret">▾</span></div>'
            f'<div class="item-page-shortcuts">{"".join(btns)}</div>'
            f'<div class="item-page-system-actions">{sys_}</div></div>')


def m_hcard(a, body):
    title = a.get("title", "")
    if not title:
        raise ExpandError("<hb-hcard> 缺 title（主标题）")
    sub = f'<div class="page-header-subtitle">{esc(a["sub"])}</div>' if a.get("sub") else ""
    info = m_info(a, body) if lines(body) else ""
    return (f'<div class="w-card page-header-card span-{a.get("span", "24")}"><div class="page-header-heading">'
            f'<div class="page-header-title">{esc(title)}</div>{sub}</div>{info}</div>')


def m_tabcard(a, body):
    tabs = "".join(f'<span{" class=\"on\"" if on else ""}>{esc(n)}</span>' for n, on in star_items(a.get("tabs", "")))
    if not tabs:
        raise ExpandError('<hb-tabcard> 缺 tabs（如 tabs="*出库明细|历史出入库"，* 为当前页签）')
    if "pill" in a:
        # 胶囊底块只在居中时成立；靠左的页签在产品里是下划线式，不带底块
        tabs = tabs.replace('<span class="on">', '<span class="wt-tab on">').replace("<span>", '<span class="wt-tab">')
        card = (f'<div class="w-card w-tabs"><div class="wt-nav center">{tabs}</div>'
                f'<div class="wt-body">{body.strip()}</div></div>')
    else:
        card = (f'<div class="w-card page-tabs-card"><div class="page-tabs-nav"><div class="page-tabs-list">{tabs}</div></div>'
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
    return (f'<div class="flow-msg"><div class="flow-msg-body"><span class="app-ic">{ico("grid-s")}</span><span><b>{esc(name)}</b>{by}</span></div>{cancel}</div>'
            f'<div class="flowbox-timeline">{"".join(boxes)}</div><div class="flow-foot">{esc(a.get("foot", "查看详细记录"))}</div>')


# ── 数据大屏（assets/c5-screen.html）──────────────────────────────────────
SCREEN_THEMES = {"blue", "teal", "gold"}
SCREEN_BGS = {"earth", "city", "grid", "gold"}
SCREEN_FRAMES = {"bracket", "round", "none"}
SCREEN_HDS = {"line", "tag", "chevron"}


def m_screen(a, body):
    theme = a.get("theme", "blue")
    bg = a.get("bg", "earth")
    if theme not in SCREEN_THEMES:
        raise ExpandError(f"<hb-screen theme> 只能是 {'/'.join(sorted(SCREEN_THEMES))}")
    if bg not in SCREEN_BGS:
        raise ExpandError(f"<hb-screen bg> 只能是 {'/'.join(sorted(SCREEN_BGS))}")
    title = a.get("title", "")
    if not title:
        raise ExpandError("<hb-screen> 缺 title（大屏页面名）")
    sub = f"<small>{esc(a['sub'])}</small>" if a.get("sub") else ""
    logo = f'<div class="sc-logo">{esc(a["logo"])}</div>' if a.get("logo") else ""
    dt = ""
    if a.get("date"):
        week = f"<span>{esc(a['week'])}</span>" if a.get("week") else ""
        time = f"<small>{esc(a['time'])}</small>" if a.get("time") else ""
        dt = f'<div class="sc-dt"><b>{esc(a["date"])}</b>{week}{time}</div>'
    head = f'<div class="sc-head{" band" if "band" in a else ""}">{logo}<h1>{esc(title)}{sub}</h1>{dt}</div>'
    return f'<div class="screen theme-{theme} bg-{bg}">{head}<div class="sc-grid">{body.strip()}</div></div>'


def m_skpi(a, body):
    frame = a.get("frame", "bracket")
    if frame not in SCREEN_FRAMES:
        raise ExpandError(f"<hb-skpi frame> 只能是 {'/'.join(sorted(SCREEN_FRAMES))}")
    span = a.get("span", "4")
    out = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-skpi> 每行「指标名 | 值 | 单位 | up/down」：{ln}")
        unit = f"<small>{esc(c[2])}</small>" if len(c) > 2 and c[2] else ""
        st = c[3].strip() if len(c) > 3 and c[3].strip() in ("up", "down") else ""
        out.append(f'<div class="sc-kpi frame-{frame} sp-{span}{" " + st if st else ""}"><div class="lb">{esc(c[0])}</div><div class="vl">{esc(c[1])}{unit}</div></div>')
    return "".join(out)


def m_scard(a, body):
    title = a.get("title", "")
    if not title:
        raise ExpandError("<hb-scard> 缺 title（图表名）")
    frame = a.get("frame", "bracket")
    hd = a.get("hd", "line")
    if frame not in SCREEN_FRAMES or hd not in SCREEN_HDS:
        raise ExpandError(f"<hb-scard> frame 只能是 {'/'.join(sorted(SCREEN_FRAMES))}，hd 只能是 {'/'.join(sorted(SCREEN_HDS))}")
    span = a.get("span", "8")
    rs = f" rs-{a['rs']}" if a.get("rs") else ""
    acts = "" if "noacts" in a else f'<span class="acts">{ico("linkout")}{ico("more")}</span>'
    ticker = " sc-ticker" if "ticker" in a else ""
    return (f'<div class="sc-card frame-{frame} sp-{span}{rs}"><div class="sc-hd {hd}">{esc(title)}{acts}</div>'
            f'<div class="sc-bd{ticker}">{body.strip()}</div></div>')


def m_sbars(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        if len(c) < 2:
            raise ExpandError(f"<hb-sbars> 每行「名称 | 百分比」：{ln}")
        pct = num_of(c[1])
        out.append(f'<div class="sc-bar"><div class="t"><span>{esc(c[0])}</span><span>{esc(c[1])}</span></div><div class="r"><i style="width:{pct:g}%"></i></div></div>')
    return '<div class="sc-bars">' + "".join(out) + "</div>"


def visual_globe():
    """默认中央视觉：线框地球＋节点连线＋地台光环，全部走 var(--screen-accent)，不含任何真实地图边界。"""
    import random
    r = random.Random(42)
    A = "var(--screen-accent)"
    W, H, cx, cy, R = 700, 420, 350, 180, 168
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
        pts.append((cx + rr * __import__("math").cos(t), cy + rr * 0.8 * __import__("math").sin(t)))
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        mx, my = (x1 + x2) / 2, min(y1, y2) - 60
        g.append(f'<path d="M{x1:.0f} {y1:.0f} Q{mx:.0f} {my:.0f} {x2:.0f} {y2:.0f}" fill="none" stroke="{A}" stroke-opacity=".7" stroke-width="1.2"/>')
    for x, y in pts:
        g.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="7" fill="{A}" fill-opacity=".18"/><circle cx="{x:.0f}" cy="{y:.0f}" r="3" fill="{A}"/>')
    for i in range(140):
        t = r.uniform(0, 6.283); rr = R * r.uniform(0, .97)
        x, y = cx + rr * __import__("math").cos(t), cy + rr * __import__("math").sin(t)
        g.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="1.2" fill="{A}" fill-opacity="{r.uniform(.2, .7):.2f}"/>')
    by = cy + R + 28
    for rx, op in ((R + 60, .8), (R + 100, .45), (R + 140, .2)):
        g.append(f'<ellipse cx="{cx}" cy="{by}" rx="{rx}" ry="{rx * .16:.0f}" fill="none" stroke="url(#ring)" stroke-opacity="{op}" stroke-width="1.5"/>')
    g.append("</svg>")
    return "".join(g)


def m_svisual(a, body):
    span = a.get("span", "8")
    rs = f" rs-{a['rs']}" if a.get("rs") else ""
    inner = body.strip()
    if a.get("img") and isinstance(a["img"], str):
        inner = f'<img src="{a["img"]}" alt="">'
    inner = inner or visual_globe()
    return f'<div class="sc-visual sp-{span}{rs}">{inner}</div>'


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
    return f'<div class="table-view kanban-view"><div class="kanban-columns">{"".join(out)}</div></div>'


def m_cards(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        fields = kv_pairs(c[1], "hb-cards") if len(c) > 1 else []
        dl = "".join(f"<dt>{esc(k)}</dt><dd>{render_val(v, 'text', 'hb-cards')}</dd>" for k, v in fields)
        ops = f'<div class="ci-ops">{render_val(c[2], "ops", "hb-cards")}</div>' if len(c) > 2 and c[2] else ""
        out.append(f'<article class="record-card"><b>{esc(c[0])}</b><dl>{dl}</dl>{ops}</article>')
    return f'<div class="table-view record-card-grid-view"><div class="record-card-grid">{"".join(out)}</div></div>'


# ── 手机端（2026-09-03 H5 实测结构，类名见 assets/c4-mobile.html）──────────
def m_phone(a, body):
    bar = ""
    if "nobar" not in a:
        bar = f'<div class="wxbar"><span class="bk">{ico("prev")}</span><span class="tt">{esc(a.get("title", ""))}</span><span class="dots">···</span></div>'
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
    return (f'<div class="stabs">{tabs}</div><div class="ssearch">{ico("search")}{esc(a.get("search", "搜索"))}</div>'
            f'<div class="sfold">{"".join(rows)}</div>')


def m_vbar(a, body):
    view = esc(a.get("view", "全部数据"))
    cnt = f'<small>{esc(str(a["count"]))}</small>' if "count" in a else ""
    icon = a.get("icon", "grid-s")
    right = "" if "nosearch" in a else f'<span class="vic">{ico("table")}</span><span class="vic">{ico("search")}</span>'
    return f'<div class="vbar"><span class="vbtn">{ico(icon, tag="<hb-vbar> ")}{view}{cnt}<span class="dd">▾</span></span><span class="sp"></span>{right}</div>'


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
    fab = f'<div class="fab">{ico("plus")}</div>' if "fab" in a else ""
    pager = ""
    if "pager" in a:
        pp = f'<span class="pp">{esc(a["pager"])} ▾</span>' if isinstance(a["pager"], str) else ""
        pager = f'<div class="mpager"><span class="pg">‹</span><span class="pg on">1</span><span class="pg">›</span>{pp}</div>'
    return f'<div class="plist">{cards}</div>{fab}{pager}'


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
    wrap = "apptab" if mode == "app" else ("mtool obar" if mode == "obar" else "mtool")
    return f'<div class="{wrap}">' + "".join(out) + "</div>"


def rec_field(c, edit):
    """'字段名 | 值 | 类型' → .fld；前缀 ! 高亮块。"""
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
    return f'<div class="fld{" hl" if hl else ""}">{fl}{fv}</div>'


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
            out.append(f'<div class="stab"><div class="stab-hd">{tabs}</div><div class="stab-bd">{bd}</div></div>')
        else:
            out.append(rec_field(cells(ln), edit))
    title = f'<div class="rtitle">{esc(a.get("title", ""))}</div>' if a.get("title") else ""
    qr = "" if "noqr" in a else f'<div class="rqr">{ico("f-barcode")}二维码</div>'
    elapsed = f'<div class="elapsed">耗时 {esc(a["elapsed"])}</div>' if "elapsed" in a else ""
    return f'{elapsed}<div class="rec">{title}{qr}{"".join(out)}</div>'


def m_fbar(a, body):
    sq = f'<span class="sq">{ico("more")}</span>' if "more" in a else ""
    return f'<div class="fbar">{sq}<span class="b cancel">{esc(a.get("cancel", "取消"))}</span><span class="b save">{esc(a.get("save", "保存"))}</span></div>'


def m_taskbar(a, body):
    who = a.get("who", "")
    if not who:
        raise ExpandError('<hb-taskbar> 缺 who（如 who="詹达富 · 出库审批"）')
    sub = f'<small>{esc(a["sub"])}</small>' if "sub" in a else ""
    btns = []
    for ln in lines(body):
        btns.extend(cells(ln))
    tb = "".join(f'<span class="b solid">{esc(b)}</span>' for b in btns if b)
    return (f'<div class="taskbar"><div class="th"><span class="av">{esc(who[:1])}</span><span class="tn">{esc(who)}{sub}</span>'
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
                     f'<div class="pa"><span class="b line">{esc(btn)}{dd}</span></div></div>')
    app = m_mtool({"mode": "app"}, "") if "app" in a else ""
    return (f'<div class="ptabs">{tabs}</div><div class="pfilter"><span class="cnt">{cnt}</span><span class="sp"></span>'
            f'<span class="b text">批量</span><span class="vic on">{ico("filter")}</span></div><div class="plist">{"".join(cards)}</div>{app}')


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
        else:
            raise ExpandError(f"<hb-wpage> 行要以 #（横幅）/ sc:（快捷方式）/ tabs:（页签）/ sub:（任务子区）开头：{ln}")
    if tabs_html or sub_html:
        out.append(f'<div class="wcard">{tabs_html}{sub_html}</div>')
    return f'<div class="wpage">{"".join(out)}</div>'


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
    return '<div class="chat">' + "".join(out) + "</div>"


def m_conn(a, body):
    steps = [f'<div class="step"><b>{esc(c[0])}</b>{esc(c[1]) if len(c) > 1 else ""}</div>' for c in map(cells, lines(body))]
    arrow = f'<div class="bigarr">{ico("arrow-right")}</div>'
    return '<div class="conn">' + arrow.join(steps) + "</div>"


MACROS = {
    "hb-shell": (m_shell, "PC 产品壳：左侧导航＋一级顶栏，体内先写 <hb-nav>，其后是 .main 里的页面内容"),
    "hb-nav": (m_nav, "左侧导航树：# 分组；名称 | 图标 | 颜色，* 前缀＝当前页；> 文件夹，- 子项"),
    "hb-views": (m_views, "视图页签行：名称 | 图标，* 前缀＝当前视图"),
    "hb-tools": (m_tools, "工具栏：字段|筛选:1|排序|导入|自定义:图标；属性 search、new"),
    "hb-grid": (m_grid, "网格表格：首行表头（列名:类型 / :sum=值），其后每行一条记录；# 分组行，! 选中行"),
    "hb-pivot": (m_pivot, "统计表（w-pivot 白卡）：首行表头，其后数据行；属性 title、icon、tint、dim"),
    "hb-stats": (m_stats, "单指标一行：指标名 | 值 | 单位 | spark:1,2,3 或 trend:red；mode=center|strip"),
    "hb-tasks": (m_tasks, "待办子区：标题 | 时间 | 节点说明；属性 title"),
    "hb-shortcuts": (m_shortcuts, "快捷方式：名称 | 图标；属性 title"),
    "hb-filters": (m_filters, "筛选部件：筛选文本 | 图标"),
    "hb-banner": (m_banner, "横幅部件：第一行页面名称，第二行一句话介绍；属性 solid；card 出背景图卡片式（date、time、img）"),
    "hb-bar": (m_bar, "柱状图卡：labels=横轴|…；每行「系列名 | 值,值,… | 颜色」"),
    "hb-line": (m_line, "折线图卡：同 hb-bar"),
    "hb-donut": (m_donut, "环图卡：每行「名称 | 值 | 颜色」；属性 center=标签|值"),
    "hb-itembar": (m_itembar, "详情页记录功能区：属性 title；体内快捷按钮「名:solid|名:line|名:line:dis」"),
    "hb-hcard": (m_hcard, "详情页标题卡片：属性 title、sub；体内关键字段行同 hb-info"),
    "hb-tabcard": (m_tabcard, "页签卡：属性 tabs=*页签|页签、span；pill 出工作台胶囊式（一律居中）；体内放已展开的内容"),
    "hb-flow": (m_flow, "流程页签时间线：属性 name、by；每行「节点名 | 状态:颜色 | 日期 | 耗时 | 链接」"),
    "hb-info": (m_info, "详情页标题卡片信息区：字段名 | 值 | 类型"),
    "hb-steps": (m_steps, "选项字段步骤条：步骤 | *当前 | 步骤"),
    "hb-kanban": (m_kanban, "看板视图：# 分组:颜色 | 数量 开列，其后每行「标题 | 字段=值; 字段=值」"),
    "hb-cards": (m_cards, "卡片视图：标题 | 字段=值; 字段=值 | 操作:图标:颜色"),
    "hb-screen": (m_screen, "数据大屏画布：属性 title、sub、logo、date、week、time、theme=blue|teal|gold、bg=earth|city|grid|gold、band；体内放 hb-skpi/hb-scard/hb-svisual"),
    "hb-skpi": (m_skpi, "大屏指标框：每行「指标名 | 值 | 单位 | up/down」；属性 span（默认 4）、frame=bracket|round|none"),
    "hb-scard": (m_scard, "大屏图表卡：属性 title、span（默认 8）、rs、hd=line|tag|chevron、frame、ticker、noacts；体内放 hb-bar/line/donut bare 或 hb-grid bare"),
    "hb-sbars": (m_sbars, "大屏进度条列表：每行「名称 | 百分比」"),
    "hb-svisual": (m_svisual, "大屏中央视觉位：属性 span、rs、img=客户图片路径；空则默认线框地球图"),
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
    "hb-conn": (m_conn, "双屏中缝说明：每行「步骤标题 | 一句说明」，行间自动加箭头"),
}

# ── 宏说明（--list 看目录，--doc 名 取详细语法；references/macros.md 由 --doc all 生成）──
COMMON = """通用写法
- 宏体按行写，一行一条；行内用 | 分列，\\| 表示字面竖线；空行和 // 开头的行忽略。
- 值后缀 :red :blue :green :orange :teal :purple :yellow :gray 把该值做成彩色标签（:gray 是灰底标签）。
- 值前缀 ~ 做成次要灰字（空值、备注）；值前缀 = 表示后面是写好的 HTML 原样放入；含 < 的值也按 HTML 原样放。
- 宏可嵌套，内层先展开。列数不对、图标名不存在、工具名没图标都会报错并指出行，改完重跑。
- 宏只消灭机械重复，不替你做设计决策：用哪种视图、放不放浮层、字段怎么排、数据编成什么样，仍按 SKILL.md 和设计原则定。
- 没有对应宏的组件（浮层内容、标题卡片标题区、流程页签、门户内容组件、手机端视图切换抽屉与卡片视图大卡等）按 SKILL.md 路由表用 extract_templates.py 提取模板手写。"""

GROUPS = [
    ("产品壳（PC）", ["hb-shell", "hb-nav"]),
    ("列表页", ["hb-views", "hb-tools", "hb-grid", "hb-kanban", "hb-cards"]),
    ("自定义页面部件（工作台 / 看板 / 数据分析页）", ["hb-banner", "hb-filters", "hb-stats", "hb-shortcuts", "hb-tasks", "hb-bar", "hb-line", "hb-donut", "hb-pivot"]),
    ("独立自定义详情页", ["hb-itembar", "hb-hcard", "hb-info", "hb-steps", "hb-tabcard", "hb-flow"]),
    ("数据大屏（2026-09-04 实测，c5-screen.html）", ["hb-screen", "hb-skpi", "hb-scard", "hb-sbars", "hb-svisual"]),
    ("手机端（2026-09-03 H5 实测结构，壳 375 宽）", ["hb-phone", "hb-mhome", "hb-vbar", "hb-ocards", "hb-mtool", "hb-rec", "hb-fbar", "hb-taskbar", "hb-ptasks", "hb-wpage", "hb-chat", "hb-conn"]),
]

DOCS = {
"hb-shell": """属性：ws 工作区名（必填）、logo（默认取 ws 首字）、page 顶栏当前页名、nav 图标行高亮项 home/table/doc/flow（默认 table）、me 头像字、theme band/side/full/light（默认 band）、bottom（默认 管理|成员）。
体内先写 <hb-nav>，其后是放进 .main 的页面内容（视图页签、view-box、.page 等）。
.stage、has-float、.float 浮层、补充样式仍由你写；hb-shell 只产出 .window 到 .main 顶栏为止的壳。
例：
<div class="stage">
<hb-shell ws="永铭世纪" page="物资档案" nav="table" me="周">
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
属性 total="1,217条" 出底部合计行（有统计列时自动出）；nock 去勾选列、noidx 去行号列；bare 只出 .grid（放进 w-card、浮层、页签容器内时用），默认带 .table-view.grid-view 和横向滚动条。
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
"hb-banner": """第一行页面名称，第二行一句话介绍（口吻规则见 SKILL.md 步骤 4）；属性 solid 铺纯色背景。
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
"hb-bar": """属性 title、labels（横轴，| 分）、max（不给自动取整）、ticks（默认 4）、h（配合本图补充样式改 .w-chart .wc-bd 高度时同步给）。
每行 系列名 | 值,值,… | 颜色；系列值用逗号分隔，不写千分位。颜色缺省：第一系列主色，第二系列主色 45% 透明，再往后状态色；显式给颜色用状态色。图例自动生成。默认 w-card w-chart 卡，bare 只出 svg＋图例。
例：
<hb-bar title="近 6 个月出入库趋势" labels="3 月|4 月|5 月|6 月|7 月|8 月">
出库 | 135,165,115,185,212,217
入库 | 82,102,70,135,117,143
</hb-bar>""",
"hb-line": """折线图，属性和行格式同 hb-bar。
例：
<hb-line title="近 5 周签约额" labels="W31|W32|W33|W34|W35">
签约额 | 42,55,38,61,70
目标 | 50,50,50,50,50 | orange
</hb-line>""",
"hb-donut": """每行 名称 | 值 | 颜色（值可带千分位；颜色缺省按 red/blue/purple/teal/green/orange 轮转）；center="标签|值" 出中心文字；百分比自动算，图例画在右侧。默认 w-card w-chart 卡，bare 只出 svg。
例：
<hb-donut title="各存放点库存占比" center="在库总量|4,386">
城建大厦酒窖 | 1,842
北京办公室 | 1,097
</hb-donut>""",
"hb-pivot": """统计表白卡，首行表头，其后数据行，值可带 :red 做成标签。属性 title、icon、tint（yellow/blue/teal 标题栏底色，浮层里常用）、dim（首列维度灰底）、bare 只出 <table>。
例：
<hb-pivot title="分存放点库存统计" dim>
存放点 | 品种数 | 在库数量
城建大厦酒窖 | 486 | 1,842
</hb-pivot>""",
"hb-itembar": """记录功能区（自定义详情页默认自带，56 高）。属性 title 记录主标题（必填）、nosys 不出右侧系统操作。
体内快捷按钮用 | 分开：名:solid（主色实底）、名:line（线框）、再接 :dis 置灰或 :green/:orange/:teal 实底色。
例：
<hb-itembar title="出库单 CK-20260824-0037">确认出库:solid | 驳回修改:line | 打印出库单:line:dis</hb-itembar>""",
"hb-hcard": """标题卡片（信息摘要，不放按钮）。属性 title 主标题（必填）、sub 副标题或编号、span（默认 24）。体内 1～4 行关键字段，格式同 hb-info：字段名 | 值 | 类型。
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
"hb-info": """标题卡片信息区，每行 字段名 | 值 | 类型（类型 user/tag/tags，缺省文本；值带 :颜色 自动成标签）。放在 .page-header-card 里、标题区之后。
例：
出库类型 | 领用出库:orange
申请人 | 陈晓东 | user
申请日期 | 2026-08-24""",
"hb-steps": """选项字段步骤条，* 标当前步骤；属性 span（默认 24）。
例：
<hb-steps>提交申请 | *仓库主管审批 | 行政总监审批 | 已出库</hb-steps>""",
"hb-screen": """数据大屏画布（不套产品壳）。属性 title 页面名（必填）、sub 英文副题、logo 左上企业名、date/week/time 右上日期星期时间、theme 配色 blue（科技蓝，默认）/teal（深青）/gold（黑金）、bg 背景 earth 星空地球（默认）/city 城市夜景/grid 科技网格/gold 黑金菱格、band 标题条带斜切底色。
体内直接放 hb-skpi / hb-scard / hb-svisual，它们自带 24 栅格跨度（sp-N），一行 24。常用排法：8 个指标框 sp-3 一行；图表卡 sp-8 ＋ 视觉位 sp-8 rs-2 ＋ 图表卡 sp-8；底部播报 sp-16。
本图补充样式给 .stage 高度；.screen 最低 922 高。
例：
<div class="stage">
<hb-screen title="生产车间大屏" logo="生产制造ERP" date="2026年09月04日" week="星期五" time="17:04:06" theme="blue" bg="earth">
<hb-skpi span="3">
本月产量 | 44 | 件
今日产量 | 2
在产产品数 | 28 | | up
</hb-skpi>
<hb-scard title="近30日产量趋势"><hb-line bare labels="…">…</hb-line></hb-scard>
<hb-svisual rs="2"/>
<hb-scard title="生产工单趋势分析"><hb-bar bare labels="…">…</hb-bar></hb-scard>
<hb-scard title="实时报工播报" span="16" ticker><hb-grid bare nock noidx>…</hb-grid></hb-scard>
</hb-screen>
</div>""",
"hb-skpi": """大屏指标框，每行「指标名 | 值 | 单位 | up/down」（up 绿 down 红）。属性 span 栅格跨度（默认 4＝一行 6 个；8 个一行写 3）、frame 装饰框 bracket 四角括号（默认）/round 圆角发光/none 无框。同一张图只用一种框。
例：
<hb-skpi span="3" frame="round">
本月产量 | 44 | 件
今日工序报工量 | 30,000 | | up
</hb-skpi>""",
"hb-scard": """大屏图表卡。属性 title 图表名（必填）、span（默认 8）、rs 行跨度、hd 标题条 line 左标题渐变底线（默认，科技蓝）/tag 斜切标签（深青）/chevron 雁翎居中（黑金）、frame 同 hb-skpi、ticker 播报表斑马底、noacts 不出右侧图标钮。
体内放 hb-bar/hb-line/hb-donut 的 bare 输出、hb-grid bare nock noidx、hb-sbars 或手绘 SVG，颜色自动走深色 token。同一张图标题条只用一种。
例：
<hb-scard title="近30日产量趋势" hd="tag" frame="none">
<hb-line bare labels="1|5|10|15|20|25|30">
产量 | 120,140,90,160,180,150,170
</hb-line>
</hb-scard>""",
"hb-sbars": """大屏进度条列表（放进 hb-scard 体内），每行「名称 | 百分比」。
例：
<hb-sbars>
一车间 | 82%
二车间 | 64%
</hb-sbars>""",
"hb-svisual": """大屏中央视觉位。属性 span（默认 8）、rs 行跨度（常写 2）、img 客户图片路径（3D 厂区图/地图/产品图；本地文件 build.py 会内嵌进单文件）；不给 img 则默认画线框地球＋节点连线（颜色跟主题），不画真实地图边界、不画灰图标。
例：
<hb-svisual rs="2"/>
<hb-svisual rs="2" img="素材/厂区3D.png"/>""",
"hb-phone": """手机壳＋顶栏 44。属性 title（顶栏标题：表名/流程名/企业名·应用名）、fix（固定 812 高，双屏对照必加）、nobar。体内按页面形态放手机端其他宏。
.stage 宽度（单屏 520、双屏 1100）和 .duo 仍由你写。
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
"hb-ocards": """三槽卡片列表（产品默认卡片形态，最多 3 个字段）。每行 标题 | 副标题 | 字段=值; 字段=值; 字段=值 | 按钮名:图标 | img；副标题可留空；值后缀 :gray 做灰底标签、:orange 等做彩色选项标签；第四列省略则无按钮；第五列写 img 出右侧图片位。
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
"hb-conn": """双屏中缝，每行 步骤标题 | 一句说明，行间自动加大箭头。
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
        if "<hb-" in body:
            body = TAG_RE.sub(repl, body)
        return MACROS[name][0](attrs_of(raw_attrs), body)

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
    a = ap.parse_args()
    if a.list:
        print(COMMON + "\n")
        for title, names in GROUPS:
            print(f"[{title}]")
            for n in names:
                print(f"  <{n}>  {MACROS[n][1]}")
        print("\n详细语法：python3 scripts/expand.py --doc 宏名 宏名…")
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
    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
        sys.stderr.write(f"已展开：{a.out}\n")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
