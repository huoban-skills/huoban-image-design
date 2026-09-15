#!/usr/bin/env python3
"""界面示意图产出物检查。纯标准库；渲染类检查只在显式 --render 且本机有 Chrome 时执行。

用法：
    python3 scripts/check.py 图.html               # 静态检查（沙箱可用）
    python3 scripts/check.py 图.html --render      # 加渲染检查（空隙、裁切、浮层出界、并排不齐；要 Chrome，找不到就明说）
    python3 scripts/check.py 图.html --json
    python3 scripts/check.py 图.html --allow-local # 本图补充样式里定义的新类降为 Nit（默认 High）
    python3 scripts/check.py 图.html --acceptance  # 起草十条人工验收表，机器能答的先填

检查的是"该由机器判定、肉眼容易漏"的项：色值有没有写死、有没有用不存在的组件类或 token、
规模是否超出出图约束、几条踩过坑的结构禁令、列丢了行容器、待办竖叠、并排不等高（按实测行高静态估算）。对齐与观感仍要看渲染，见 references/canvas/verify-export.md。

退出码：有 Blocker 返回 1，其余返回 0。
"""
import difflib
import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"
sys.path.insert(0, str(Path(__file__).resolve().parent))

HEX = re.compile(r'#[0-9A-Fa-f]{3,8}\b')
RGB = re.compile(r'\brgba?\(')
ALLOW_LITERAL = {"#fff", "#ffffff", "#000", "#000000"}
# 工具类前缀：图标着色、色调、标签色、大屏装饰底图、图标 id、栅格跨度与行跨度、主题
UTILITY_PREFIXES = ("ic-", "tone-", "c-", "bg-", "i-", "span-", "sp-", "rs-", "stats-", "cols-", "theme-", "tint-", "sw-")

SURNAMES = ("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
            "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐"
            "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄")
_NAME = "[" + SURNAMES + "][一-龥]{1,2}"
PERSON_PATTERNS = [re.compile(_NAME + r"的?(?:工作台|看板|首页|主页)"),
                   re.compile(_NAME + r"[，,]?\s*(?:你好|您好|早上好|上午好|下午好|晚上好|欢迎)"),
                   re.compile(r"(?:欢迎回来|欢迎|[Hh]i|[Hh]ello)[，,]?\s*" + _NAME)]
PERSON_EXCLUDE = ("周报", "月报", "日报", "年报", "简报", "快报", "财报", "战报", "周会", "周期", "周边", "周转", "金额", "马上", "于今")

# 规模上限（本 skill 出图约束，几何问题的生成侧规避；超出报 Medium）
SCALE = {"grid_rows": (6, 14), "stats_per_row": (4, 6), "kanban_cols": (3, 5), "float_cards": (0, 2), "pivot_per_page": (0, 2)}


def load_known_classes():
    css = (ASSETS / "base.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return set(re.findall(r"\.([A-Za-z_][\w-]*)", css))


def load_known_icons():
    svg = (ASSETS / "icons.svg").read_text(encoding="utf-8")
    return set(re.findall(r'<symbol id="i-([\w-]+)"', svg))


def load_registry_ids():
    try:
        reg = json.loads((ASSETS / "registry.json").read_text(encoding="utf-8"))
        return {e["id"].split()[0] for e in reg["entries"]}
    except Exception:
        return set()


def split_doc(text):
    styles = [re.sub(r"/\*.*?\*/", "", s, flags=re.S) for s in re.findall(r"<style[^>]*>(.*?)</style>", text, flags=re.S)]
    body = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    body = re.sub(r"<script>.*?</script>", "", body, flags=re.S)
    return "\n".join(styles), body


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def suggest(name, pool):
    c = difflib.get_close_matches(name, pool, n=3, cutoff=0.6)
    return f"，是不是 {' / '.join(c)}" if c else ""



# ── 结构解析与静态高度估算（不依赖 Chrome）─────────────────────────
def top_divs(seg):
    """seg 里顶层 <div>…</div> 列表 [(class, inner)]；只数 div，其他标签不影响深度。"""
    out, depth, start, inner_start, cls = [], 0, None, 0, ""
    for t in re.finditer(r"<div\b[^>]*>|</div>", seg):
        if t.group(0) == "</div>":
            depth -= 1
            if depth == 0 and start is not None:
                out.append((cls, seg[inner_start:t.start()]))
                start = None
        else:
            if depth == 0:
                start, inner_start = t.start(), t.end()
                m = re.search(r'class="([^"]*)"', t.group(0))
                cls = m.group(1) if m else ""
            depth += 1
    return out


PAGE_W = 1160          # 页面内容区常见宽度，只用于估算按钮组换行
ROW_GAP = 20           # .page / .w-row 组件间距


def _span_of(cls):
    m = re.fullmatch(r"span-(\d+)", cls.strip())
    return int(m.group(1)) if m else None


def est_card(cls, inner, col_w):
    """按 base.css 实测行高估算一张组件卡的高度；估不了返回 None。"""
    c = cls.split()
    head = 40 if re.match(r'\s*<div class="(wc-hd|ws-hd)', inner) else 0
    if "chart_single" in c:
        return 80 if "strip" in c else 120
    if "multi_stats" in c:
        return head + 40 * inner.count('class="multi-stat-row"') + 10
    if "subtotal" in c:
        return head + 40 * inner.count('class="subtotal-head"') + 40 * inner.count('class="subtotal-row"') + 10
    if "procedure_process" in c:
        return head + 80 * inner.count('class="proc"') + 40 * inner.count('class="proc-empty"') + 10
    if "procedure_task" in c:
        return head + 80 * inner.count('class="task"') + 10
    if "w-field-group" in c:
        m = re.search(r"fg-grid fg-c(\d+)", inner)
        cols = int(m.group(1)) if m else 2
        fields = len(re.findall(r'class="fg-field"', inner))
        full = len(re.findall(r'class="fg-field full"', inner))
        groups = len(re.findall(r'class="fg-group', inner))
        return head + 40 * groups + -(-fields // cols) * 69 + full * 110
    if "table_item_list" in c:
        rows = max(len(re.findall(r"<tr\b", inner)) - 1, 0)
        return head + 32 + 35 * rows + (40 if "til-foot" in inner else 0)
    if "chart_table" in c:
        return head + 34 + 33 * max(len(re.findall(r"<tr\b", inner)) - 1, 0) + 14
    if "chart" in c:
        return head + 240 + 28
    if "progress_bar" in c:
        return head + 40 * inner.count('class="pg-row') + 20
    if "button" in c and "shortcuts" in c:
        n = inner.count('class="sc"')
        per_row = max(1, int((col_w - 28 + 20) // 182))
        return head + 28 + -(-n // per_row) * 54 - 14
    if "tabs" in c:
        m = re.search(r'<div class="(wt-body|page-tabs-body)">', inner)
        if not m:
            return None
        body = est_col(inner[m.end():], col_w)
        return None if body is None else 44 + body
    return None


def est_col(seg, col_w):
    """一栏（或页面）里顶层组件竖叠的总高；有一块估不了就返回 None。"""
    total, n = 0, 0
    for cls, inner in top_divs(seg):
        if "w-row" in cls.split():
            h = est_row(inner, col_w)
        elif "w-col" in cls.split():
            h = est_col(inner, col_w)
        elif {"w-card", "procedure_task"} & set(cls.split()):
            h = est_card(cls, inner, col_w)
        elif _span_of(cls) is not None:
            h = est_col(inner, col_w)
        else:
            h = None
        if h is None:
            return None
        total += h
        n += 1
    return total + ROW_GAP * (n - 1) if n else 0


def est_row(inner, row_w):
    kids = top_divs(inner)
    hs = []
    for cls, kin in kids:
        sp = _span_of(cls)
        if sp is not None:
            h = est_col(kin, (row_w - ROW_GAP * (len(kids) - 1)) * sp / 24)
        elif {"w-card", "procedure_task"} & set(cls.split()):
            h = est_card(cls, kin, row_w / max(len(kids), 1))
        else:
            h = None
        if h is None:
            return None
        hs.append(h)
    return max(hs) if hs else 0


def walk_divs(seg, parent_cls, fn, col_w=PAGE_W):
    """深度优先遍历所有 div，对每个 (class, inner, parent_class, 兄弟列表, col_w) 调 fn。"""
    kids = top_divs(seg)
    for cls, inner in kids:
        fn(cls, inner, parent_cls, kids, col_w)
        sp = _span_of(cls)
        walk_divs(inner, cls, fn, (col_w - ROW_GAP * (len(kids) - 1)) * sp / 24 if sp else col_w)


def check(path, render=False, allow_local=False):
    text = Path(path).read_text(encoding="utf-8")
    styles, body = split_doc(text)
    findings = []

    def add(level, rule, msg, line=None):
        findings.append({"level": level, "rule": rule, "msg": msg, "line": line})

    # ── Blocker：色值写死 ────────────────────────────────────────────
    for m in re.finditer(r'(?:fill|stroke|stop-color)="([^"]+)"', body):
        v = m.group(1).strip()
        if v.lower() in ALLOW_LITERAL or v in ("none", "currentColor") or v.startswith("url("):
            continue
        if HEX.match(v) or RGB.match(v):
            add("Blocker", "hardcoded-color", f'SVG 属性写死颜色 {v}，改成 var(--primary)/var(--c-red) 这类皮肤 token', line_of(body, m.start()))
    for m in re.finditer(r'style="([^"]*)"', body):
        for cm in re.finditer(r"(?:background|color|fill|stroke|border)[^;:]*:\s*([^;\"]+)", m.group(1)):
            v = cm.group(1).strip()
            if v.lower() in ALLOW_LITERAL or v.startswith("var(") or v.startswith("url("):
                continue
            if HEX.search(v) or RGB.search(v):
                add("Blocker", "hardcoded-color", f'行内 style 写死颜色 {v}，改成 var(--…) 皮肤 token', line_of(body, m.start()))
    tail = styles.split("/* ── 本图布局 ── */")[-1] if "/* ── 本图布局 ── */" in styles else ""
    for m in re.finditer(r"(?:background|color|fill|stroke)\s*:\s*([^;{}]+)", tail):
        v = m.group(1).strip()
        if v.lower() in ALLOW_LITERAL or "var(" in v or v.startswith("url("):
            continue
        if HEX.search(v) or RGB.search(v):
            add("High", "hardcoded-color", f'本图补充样式里写死颜色 {v}；改用皮肤 token，确属一次性微调可忽略')

    # ── 组件存在性：base.css 有 / 只在本图样式里有 / 哪都没有 ──────
    known = load_known_classes()
    reg_ids = load_registry_ids()
    base_css = re.sub(r"/\*.*?\*/", "", (ASSETS / "base.css").read_text(encoding="utf-8"), flags=re.S)
    extra_css = styles                                        # 去掉 base.css 与皮肤后＝本图补充样式＋片段自带 <style>
    for chunk in [base_css] + [re.sub(r"/\*.*?\*/", "", p.read_text(encoding="utf-8"), flags=re.S) for p in sorted((ASSETS / "skins").glob("*.css"))]:
        extra_css = extra_css.replace(chunk.strip(), "")
    local = set(re.findall(r"\.([A-Za-z][\w-]*)", extra_css)) - known
    used = set()
    for m in re.finditer(r'class="([^"]+)"', body):
        used.update(c for c in m.group(1).split() if c)
    for c in sorted(used):
        if c.startswith(UTILITY_PREFIXES) or c in known:
            continue
        if c in local:
            add("Nit" if allow_local else "High", "local-class",
                f'.{c} 只在本图补充样式里定义：这是自造组件的常见入口{suggest(c, known)}；确属一次性布局加 --allow-local 放行，多图复用要沉淀进 base.css')
        else:
            add("High", "unknown-component", f'.{c} 在 base.css 和本图样式里都没有定义：自造组件或拼错类名{suggest(c, known | reg_ids)}')

    # ── High：未定义的 token ──────────────────────────────────────────
    defined = set(re.findall(r"--([a-z0-9-]+)\s*:", styles))
    for m in re.finditer(r"var\(--([a-z0-9-]+)", body + "\n" + tail):
        if m.group(1) not in defined:
            add("High", "unknown-token", f'var(--{m.group(1)}) 在皮肤和 base.css 里都没定义，换肤时会失效{suggest(m.group(1), defined)}')
            break

    # ── High：引用了不存在的图标 ───────────────────────────────────
    icons = load_known_icons()
    for m in re.finditer(r'<use href="#i-([\w-]+)"', body):
        if m.group(1) not in icons:
            add("High", "unknown-icon", f'#i-{m.group(1)} 不在 icons.svg 里{suggest(m.group(1), icons)}', line_of(body, m.start()))
    if "<use href=" in body and 'id="i-' not in text:
        add("Blocker", "missing-sprite", "用了 <use> 但没把 assets/icons.svg 拼进文件，图标会全部空白")

    # ── Medium：结构禁令（踩过的坑） ───────────────────────────────
    if re.search(r'class="[^"]*\bico\b[^"]*"[^>]*>\s*<path', body):
        add("Medium", "inline-icon-path", "图标仍在内联 path，应改 <use href=\"#i-...\"/>")
    if "■" in body or "●" in body:
        add("Medium", "legend-char", "图例用了 ■/● 字符：字符只能着文字色，应改 <rect>/<circle>")
    auto = bool(re.search(r'class="stage[^"]*\bauto\b', body))
    if not auto and re.search(r'class="stage\b', body) and 'class="window' in body:
        if not re.search(r"\.stage\s*\{[^}]*height", styles):
            add("High", "stage-no-height", "手写外壳的 .stage 没设 height：改用 <hb-page> 骨架宏（自动撑高），或按渲染实测回填")
    for m in re.finditer(r'<div class="w-card tabs[^"]*">', body):
        inner = body[m.end():m.end() + 30000]
        depth, i, end = 1, 0, len(inner)
        for t in re.finditer(r"<div\b|</div>", inner):
            depth += 1 if t.group(0) == "<div" else -1
            if depth == 0:
                end = t.start()
                break
        if 'class="w-card tabs' in inner[:end]:
            add("Medium", "tabs-nested", "页签容器里又套了页签容器：拆成两页或改用段落标题", line_of(body, m.start()))
            break

    # ── 结构：列丢了行容器、待办竖叠、并排不等高（静态估算） ─────────
    TODO_CARDS = {"multi_stats", "procedure_process", "procedure_task"}
    seen_rows = set()

    def _struct(cls, inner, parent_cls, kids, col_w):
        sp = _span_of(cls)
        if sp is not None and sp < 24 and not {"w-row", "item-grid"} & set(parent_cls.split()):
            n = sum(1 for k, _ in kids if _span_of(k) is not None)
            if not any(f["rule"] == "orphan-span" and f.get("key") == id(kids) for f in findings):
                findings.append({"level": "Blocker", "rule": "orphan-span", "key": id(kids),
                                 "msg": f"{n} 个 .span-N 列外面没有 w-row 行容器，会退化成通栏竖叠：并排的组件写进同一个 <hb-row spans=…>，不要自己包 span 列", "line": None})
        toks = cls.split()
        if "w-row" in toks:
            key = id(inner)
            if key in seen_rows:
                return
            seen_rows.add(key)
            cols = [(k, kin) for k, kin in top_divs(inner) if _span_of(k) is not None]
            if len(cols) >= 2:
                hs = []
                for k, kin in cols:
                    h = est_col(kin, (col_w - ROW_GAP * (len(cols) - 1)) * _span_of(k) / 24)
                    if h is None:
                        return
                    kk = top_divs(kin)
                    stretch = len(kk) == 1 and bool({"w-card", "procedure_task"} & set(kk[0][0].split()))   # 单张卡会被 base.css 拉到等高
                    hs.append((h, k, stretch))
                short, tall = min(hs), max(hs)
                if tall[0] - short[0] > 150 and short[2]:
                    add("Medium", "card-stretched", f"并排里 .{short[1]} 只有一张矮卡（内容约 {int(short[0])}px），会被拉到和 .{tall[1]}（约 {int(tall[0])}px）等高，卡里空一大块：用 <hb-col> 在这一栏再叠一个组件（如按钮组＋多项统计），或换更高的组件")
                if tall[0] - short[0] > 100 and not short[2]:
                    add("Medium", "column-short", f"并排不等高（按实测行高估算）：.{short[1]} 约 {int(short[0])}px，.{tall[1]} 约 {int(tall[0])}px，差约 {int(tall[0] - short[0])}px；给短栏补 1～2 张图表、数值字段组或待办列表，或改成单栏，不用固定高度硬撑")
        if "page" in toks or "item-page-canvas" in toks:
            run = 0
            for k, _ in top_divs(inner):
                kt = set(k.split())
                if "w-card" in kt and kt & TODO_CARDS:
                    run += 1
                    if run == 2:
                        add("High", "todo-stacked", "待办、我处理的、我发起的各占通栏竖着叠，每块只有几行，整屏都是空：并排写进一个 <hb-row spans=\"8|8|8\">（或 8|16）")
                        break
                else:
                    run = 0

    walk_divs(body, "", _struct)
    if re.search(r'class="(ocard|m-workbench|m-chat|rec-card|obar)\b', body) and 'class="phone' not in body:
        add("High", "mobile-in-pc", "PC 图里出现了手机组件（订单卡、手机工作台、会话流等），样式只在 hb-phone 里生效，会散成一堆裸文字：PC 页和 PC 浮层改用 hb-fields、hb-list、hb-multistats 这类 PC 组件")
    if 'class="wempty"' in body or "暂无数据" in body:
        add("Medium", "empty-state", "画面里有「没有找到任务／暂无数据」空态：营销图每个区域都要有内容，给它几行数据或去掉这块")

    # ── Medium：规模上限（本 skill 出图约束） ────────────────────────
    for m in re.finditer(r'<div class="[^"]*\bview-grid\b[^"]*">.*?</table>', body, re.S):
        rows = len(re.findall(r"<tr(?![^>]*class=\"group\")", m.group(0))) - 1
        lo, hi = SCALE["grid_rows"]
        if rows and (rows < lo or rows > hi):
            add("Medium", "scale-limit", f"网格视图 {rows} 行：常态 {lo}～{hi} 行，少了像凑数，多了被窗口裁断也无意义", line_of(body, m.start()))
    for m in re.finditer(r'<div class="w-row[^"]*">', body):
        n = len(re.findall(r'class="w-card chart_single', body[m.end():m.end() + 4000].split('<div class="w-row')[0]))
        lo, hi = SCALE["stats_per_row"]
        if n and (n < lo or n > hi):
            add("Medium", "scale-limit", f"单指标一行 {n} 个：常态 {lo}～{hi} 个（4 或 6 能在 24 栅格等分）", line_of(body, m.start()))
    n_cols = len(re.findall(r'class="kanban-group', body))
    if n_cols and not SCALE["kanban_cols"][0] <= n_cols <= SCALE["kanban_cols"][1]:
        add("Medium", "scale-limit", f"看板 {n_cols} 列：常态 3～5 列")
    _num = re.compile(r"^[+\-−]?[\d,]+(?:\.\d+)?\s*(?:%|万|亿|元|件|天|次|家|个|人|条|单|台|kg|k)?$")
    for m in re.finditer(r'<div class="w-card chart_table">.*?</table>', body, re.S):
        trs = re.findall(r"<tr>(.*?)</tr>", m.group(0), re.S)[1:]
        vals = []
        for tr in trs:
            tds = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)][1:]
            vals += [v for v in tds if v and v not in ("—", "-", "–")]
        if vals and sum(1 for v in vals if _num.match(v)) / len(vals) < 0.6:
            add("High", "pivot-as-list", "透视表里装的是一条条记录（大部分格子是文字）：透视表是维度 × 指标的统计，做数据分析用；记录列表改 hb-list（表格列表）", line_of(body, m.start()))
    n_pivot = len(re.findall(r'class="w-card chart_table', body))
    if n_pivot > SCALE["pivot_per_page"][1]:
        add("Medium", "scale-limit", f"透视表 {n_pivot} 张：默认 ≤2 张，多了先并成一张多维透视")
    for m in re.finditer(r'<div class="mk-float[^"]*"[^>]*>', body):
        n = len(re.findall(r'class="w-card', body[m.end():m.end() + 8000]))
        if n > SCALE["float_cards"][1]:
            add("Medium", "scale-limit", f"浮层里 {n} 张组件卡：浮层只强调一两个底层没有的东西", line_of(body, m.start()))

    # ── High：横幅写成某个具体人 ───────────────────────────────────
    for bm in re.finditer(r'<div class="[^"]*\brich title\b[^"]*"[^>]*>(.*?)</div>\s*(?=<div|</)', body, re.S):
        for tm in re.finditer(r"<(h1|p)[^>]*>(.*?)</\1>", bm.group(1), re.S):
            txt = re.sub(r"<[^>]+>", "", tm.group(2)).strip()
            for pat in PERSON_PATTERNS:
                hit = pat.search(txt)
                if hit and not hit.group().startswith(PERSON_EXCLUDE):
                    add("High", "banner-person-name", f'横幅写成具体某个人「{hit.group()}」：工作台服务的是角色（律师、库管、店长），改成「库管工作台」这类角色名', line_of(body, bm.start()))
                    break

    # ── 渲染检查（显式 --render 且有 Chrome）────────────────────────
    if render:
        import export
        r = export.probe(path)
        if r is None:
            note = "渲染检查未执行：未找到 Chrome（empty-gap / content-clipped / float-out / column-uneven 四项未检）"
        else:
            note = None
            for e in r.get("extra", []):
                if e["kind"] == "clipped":
                    add("High", "content-clipped", f"cut 窗口内容比窗口高 {e['over']}px，底部被裁：调 cut 值或减内容")
                else:
                    add("High", "float-out", f"浮层探出画布 {e['over']}px：调 hb-float 的 top 或减少浮层内容")
            findings[:] = [f for f in findings if f["rule"] != "column-short"]
            for u in r.get("uneven", []):
                add("Medium", "column-uneven", f"并排底部不齐：.{u['short']} 高 {u['shortH']}，.{u['tall']} 高 {u['tallH']}，差 {u['diff']}px；给短栏补数据行或调 spans")
            for g in r.get("gaps", []):
                part = []
                if g.get("bottom"):
                    part.append(f"底部空 {g['bottom']}px")
                if g.get("right"):
                    part.append(f"右侧空 {g['right']}px")
                x, y, w, h = g["box"]
                add("Medium", "empty-gap", f".{g['cls']} {'，'.join(part)}（{w}×{h}，位置 x{x} y{y}）：补内容或收高度")
    else:
        note = "渲染检查未执行：未加 --render（空隙、裁切、浮层出界、并排不齐四项未检）"

    for f in findings:
        f.pop("key", None)
    order = {"Blocker": 0, "High": 1, "Medium": 2, "Nit": 3}
    findings.sort(key=lambda f: (order[f["level"]], f["rule"], f["line"] or 0))
    return findings, note


def acceptance(path):
    """起草十条人工验收表：机器能答的先填，其余留给人逐条写。"""
    text = Path(path).read_text(encoding="utf-8")
    _, body = split_doc(text)
    reg = json.loads((ASSETS / "registry.json").read_text(encoding="utf-8"))
    _k = re.search(r'data-kind="(\w+)"', body)
    _pk = f"page:{_k.group(1)}" if _k else ""
    cn = {}
    for e in reg["entries"]:                 # 同 id 多条（如大屏表格列表）按页面类型取名
        if e["kind"] != "component":
            continue
        _id = e["id"].split()[0]
        if _id not in cn or _pk in e.get("allowed_in", []):
            cn[_id] = e["cn"]
    used = sorted({c for m in re.finditer(r'class="([^"]+)"', body) for c in m.group(1).split() if c in cn})
    rows = len(re.findall(r"<tr(?![^>]*class=\"group\")", body)) - body.count("<table>")
    stats = len(re.findall(r'class="w-card chart_single', body))
    floats = body.count('class="mk-float')
    kind = re.search(r'data-kind="(\w+)"', body)
    name = Path(path).stem
    lines = [f"验收 {name}",
             f"1 需求单落全 （图上组件：{'、'.join(cn[c] for c in used) or '—'}；页面类型 {kind.group(1) if kind else '手写外壳'}）对照需求单逐项打勾后填",
             f"2 组件都是真的 {'通过：类名全在登记表与 base.css 里' if used else '待填'}",
             "3 层次关系对 待填（对照 data-measured：白卡浮灰底还是透明融入）",
             "4 对齐与选型 待填（状态色红绿灯、按钮主次、表单列数一致、图表选型）",
             f"5 浮层不重复底层 {'待填（有 ' + str(floats) + ' 个浮层，逐个看是否复制了底层内容）' if floats else '通过：无浮层'}",
             f"6 浮层底下是完整页面 {'待填' if floats else '通过：无浮层'}",
             f"7 浮层没挡关键内容 {'待填' if floats else '通过：无浮层'}",
             f"8 信息密度够 机检：表格行 {max(rows, 0)}、单指标 {stats}；对照 check.py 的 scale-limit 后填",
             "9 数据像真的 待填（编号不连号、金额带零头、日期不等距、有非理想态）",
             "10 整体观感 待填：有 Chrome 时 `export.py --png` 后目检；无 Chrome 时写「未渲染目检，静态与规模检查已过」"]
    return "\n".join(lines)


def main():
    if "--help" in sys.argv or "-h" in sys.argv or len(sys.argv) < 2:
        print(__doc__.strip()); return 0
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    if "--acceptance" in sys.argv:
        print(acceptance(args[0]))
        return 0
    findings, note = check(args[0], render="--render" in sys.argv, allow_local="--allow-local" in sys.argv)
    if "--json" in sys.argv:
        print(json.dumps({"findings": findings, "render": note}, ensure_ascii=False, indent=2))
    else:
        if not findings:
            print("静态检查通过（颜色 token、组件与 token 存在性、结构禁令、规模上限）")
        else:
            counts = {}
            for f in findings:
                counts[f["level"]] = counts.get(f["level"], 0) + 1
            print("　".join(f"{k} {v}" for k, v in counts.items()))
            print()
            for f in findings:
                loc = f"  第{f['line']}行" if f["line"] else ""
                print(f"[{f['level']}] {f['rule']}{loc}\n    {f['msg']}")
        if note:
            print(f"\n{note}")
        print("对齐与观感仍要看渲染：references/canvas/verify-export.md 的人工验收表")
    return 1 if any(f["level"] == "Blocker" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
