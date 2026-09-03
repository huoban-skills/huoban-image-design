#!/usr/bin/env python3
"""把内容片段里的 <hb-*> 宏展开成真实组件 HTML。build.py 组装前自动调用，也可单独跑。

用法：
    python3 scripts/expand.py stage.html                 # 展开后的 HTML 打到标准输出
    python3 scripts/expand.py stage.html --out /tmp/x.html
    python3 scripts/expand.py --list                     # 列出全部宏与一行说明

宏只消灭机械重复（壳层、表格行、卡片、图表坐标），不做设计决策：用哪个视图、放不放浮层、
字段怎么排，仍由写片段的人定。每个宏对应 assets/c1～c4 里的一个已收录组件，输出的类名与
结构正本一致，check.py 照常检查。宏语法见 references/macros.md。

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
        out.append(f'<div class="task"><div class="t-bd"><div class="t-title">{title}{time}</div>{node}</div></div>')
    hd = f'<div class="ws-hd">{esc(a.get("title", ""))}</div>' if a.get("title") else ""
    return f'<div class="w-sub">{hd}{"".join(out)}</div>'


def m_shortcuts(a, body):
    out = []
    for ln in lines(body):
        c = cells(ln)
        icon = c[1] if len(c) > 1 and c[1] else "app-s"
        out.append(f'<div class="sc"><span class="sc-ic">{ico(icon, tag="<hb-shortcuts> ")}</span>{esc(c[0])}</div>')
    return f'<div class="w-card w-shortcut">{card_head(a, "hb-shortcuts")}<div class="wc-bd sc-grid">{"".join(out)}</div></div>'


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


def chart_card(a, inner, legend, tagname):
    W, H = int(a.get("w", 560)), int(a.get("h", 240))
    svg = f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">{"".join(inner)}</svg>'
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
    return chart_card(a, inner, "", "hb-donut")


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
    "hb-banner": (m_banner, "横幅部件：第一行页面名称，第二行一句话介绍；属性 solid"),
    "hb-bar": (m_bar, "柱状图卡：labels=横轴|…；每行「系列名 | 值,值,… | 颜色」"),
    "hb-line": (m_line, "折线图卡：同 hb-bar"),
    "hb-donut": (m_donut, "环图卡：每行「名称 | 值 | 颜色」；属性 center=标签|值"),
    "hb-info": (m_info, "详情页标题卡片信息区：字段名 | 值 | 类型"),
    "hb-steps": (m_steps, "选项字段步骤条：步骤 | *当前 | 步骤"),
    "hb-kanban": (m_kanban, "看板视图：# 分组:颜色 | 数量 开列，其后每行「标题 | 字段=值; 字段=值」"),
    "hb-cards": (m_cards, "卡片视图：标题 | 字段=值; 字段=值 | 操作:图标:颜色"),
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
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for k, (_, doc) in MACROS.items():
            print(f"<{k}>  {doc}")
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
