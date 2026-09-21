#!/usr/bin/env python3
"""界面示意图产出物检查。纯标准库；本机找得到 Chrome（含 Playwright 装的 Chromium）就自动加渲染检查。

用法：
    python3 scripts/check.py 图.html               # 静态检查；有浏览器时自动加渲染检查（空隙、裁切、浮层出界与遮挡、并排不齐）
    python3 scripts/check.py 图.html --no-render   # 只做静态检查
    python3 scripts/check.py 图.html --json
    python3 scripts/check.py 图.html --allow-local # 本图补充样式里定义的新类降为 Nit（默认 High）
    python3 scripts/check.py 图.html --acceptance  # 起草十条人工验收表，机器能答的先填

检查的是"该由机器判定、肉眼容易漏"的项：色值有没有写死、有没有用不存在的组件类或 token、
规模是否超出出图约束、几条踩过坑的结构禁令、列丢了行容器、待办竖叠、并排不等高（按实测行高静态估算）。有浏览器时空隙、并排不齐、浮层遮挡改用实测值。

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
SLIDE_RE = re.compile(r'class="stage auto[^"]*\bslide\b')
SLIDE_W = 1300         # 演示尺寸窗口宽（整图 1500：图片位 930 宽时主体字 13px 渲染成 8px，正好在底线上）
SLIDE_MAX_H = 867      # 目标上限：底图比 ≥1.5，像一块真实显示器；超过它报 Medium，可让位于信息密度
SLIDE_HARD_H = 930     # 硬上限：底图比 <1.4，接近 4:3；超过它报 High
# 整张图（含浮层探出部分）宽高比，两档尺寸通用：一屏原则——图在载体里不该要滚动才看完
RATIO_OK = 1.45        # 目标下限：低于它报 Medium，先横向重排，重排后仍够不到可让位于信息密度
RATIO_HIGH = 1.25      # 硬下限：低于它报 High，图竖得在载体里一屏放不下
RATIO_THIN = 1.85      # 高于它报 Medium：画面偏扁、内容偏少
FLOAT_RATIO_MIN = 1.2  # 浮层自身宽高比下限：低于它就竖成了条，不像另一屏画面
SLIDE_RATIO_OK, SLIDE_RATIO_HIGH, SLIDE_RATIO_THIN = RATIO_OK, RATIO_HIGH, RATIO_THIN   # 旧名保留
FLOAT_ZOOM = 0.8        # 默认尺寸的浮层内容缩 0.8（base.css .float-screen）；演示尺寸不缩，见下
SCALE = {"grid_rows": (6, 14), "stats_per_row": (4, 6), "kanban_cols": (3, 5)}


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


FILL = {                                   # 短栏补什么：按页面类型给候选组件
    "workbench": "进度条、分类汇总、日历、多项统计，或在这一栏再放一个标签页容器",
    "dashboard": "分类汇总、进度条、饼图，或再加一张图表",
    "detail": "单指标、进度条、图表、流程执行记录、动态、评论，或给标签页容器多加一个页签",
    "list": "在视图区之外另起一块：单指标、进度条、分类汇总",
    "screen": "大屏指标框、大屏进度条、再加一张图表",
}


def fill_hint(body):
    m = re.search(r'data-kind="(\w+)"', body)
    return FILL.get(m.group(1) if m else "", "本页面原则里该位置列出的其他组件")


PAGE_W = 1160          # 页面内容区常见宽度，只用于估算按钮组件换行
ROW_GAP = 20           # .page / .w-row 组件间距


def _span_of(cls):
    m = re.fullmatch(r"span-(\d+)", cls.strip())
    return int(m.group(1)) if m else None


UNEST = []             # 本次检查里估不出高度的组件类名


def est_card(cls, inner, col_w):
    """按 base.css 实测行高估算一张组件卡的高度；估不了返回 None 并记下类名。"""
    c = cls.split()
    head = 40 if re.match(r'\s*<div class="(wc-hd|ws-hd)', inner) else 0
    if "header_card" in c:
        return 180
    if {"item-steps", "item-tiles"} & set(c):
        return 40
    if "rich" in c and "title" in c:
        return 80
    if "grid" in c and "w-card" not in c:
        rows = max(len(re.findall(r"<tr\b", inner)) - 1, 0)
        return 32 + 35 * rows + (40 if "til-foot" in inner or "pager" in inner else 0)
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
    if "w-stream" in c:                                    # 实测：条目 40，多一行 +16，条间 16
        items = re.findall(r'<div class="fd-item"', inner)
        lines = [len(re.findall(r"<div>", x)) or 1 for x in re.split(r'<div class="fd-item"', inner)[1:]]
        return head + 40 + sum(40 + 16 * (n - 1) for n in lines) + 16 * max(len(items) - 1, 0)
    if "w-comment" in c:                                   # 实测：发布条 68；空态整块 170
        if 'class="empty"' in inner:
            return head + 68 + 170
        lines = [len(re.findall(r"<div>", x)) or 1 for x in re.split(r'<div class="fd-item"', inner)[1:]]
        return head + 68 + 40 + sum(40 + 16 * (n - 1) for n in lines) + 16 * max(len(lines) - 1, 0)
    if "process" in c:                                     # 流程执行记录的头：消息体 52 ＋ 撤销行 41
        return 52 + (41 if "flow-msg-actions" in inner else 0)
    if "flowbox-timeline" in c:                            # 节点 89，带链接 128，节点间 12，上下内边距 32
        nodes = re.split(r'<div class="flowbox"', inner)[1:]
        return 32 + sum(128 if "flowbox-links" in x else 89 for x in nodes) + 12 * max(len(nodes) - 1, 0)
    if "flow-foot" in c:
        return 40
    if "w-field-group" in c:
        m = re.search(r"fg-grid fg-c(\d+)", inner)
        cols = int(m.group(1)) if m else 2
        fields = len(re.findall(r'class="fg-field"', inner))
        full = len(re.findall(r'class="fg-field full"', inner))
        tile_rows = len(re.findall(r'class="fg-field span-all"', inner))
        groups = len(re.findall(r'class="fg-group', inner))
        return head + 40 * groups + -(-fields // cols) * 69 + tile_rows * 69 + full * 110 + (32 if fields or tile_rows else 0)
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
            UNEST.append(cls)
            return None
        body = est_col(inner[m.end():], col_w)
        return None if body is None else 44 + body
    UNEST.append(cls)
    return None


def est_col(seg, col_w):
    """一栏（或页面）里顶层组件竖叠的总高；有一块估不了就返回 None。"""
    total, n = 0, 0
    for cls, inner in top_divs(seg):
        if "w-row" in cls.split():
            h = est_row(inner, col_w)
        elif "w-col" in cls.split():
            h = est_col(inner, col_w)
        elif {"w-card", "procedure_task", "grid", "rich", "process", "flowbox-timeline", "flow-foot"} & set(cls.split()):
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
        elif {"w-card", "procedure_task", "grid", "rich", "process", "flowbox-timeline", "flow-foot"} & set(cls.split()):
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


def _inner_of(body, pat):
    """取第一个 class 匹配 pat 的 div 的内容（配平闭合标签）；找不到返回 None。"""
    m = re.search(pat, body)
    if not m:
        return None
    depth, i = 0, m.start()
    for t in re.finditer(r"<div\b[^>]*>|</div>", body[i:]):
        depth += 1 if t.group(0) != "</div>" else -1
        if depth == 0:
            return body[i + m.end() - m.start():i + t.start()]
    return None


def _inner_of(body, pat):
    """取第一个 class 匹配 pat 的 div 的内容（配平闭合标签）；找不到返回 None。"""
    m = re.search(pat, body)
    if not m:
        return None
    depth, i = 0, m.start()
    for t in re.finditer(r"<div\b[^>]*>|</div>", body[i:]):
        depth += 1 if t.group(0) != "</div>" else -1
        if depth == 0:
            return body[i + m.end() - m.start():i + t.start()]
    return None


def page_height(body):
    """按实测行高估算底图高度；估不出返回 None。"""
    inner = _inner_of(body, r'<div class="page(?: [^"]*)?">')
    if inner is None:
        inner = _inner_of(body, r'<div class="item-grid(?: [^"]*)?">')
    if inner is None:
        return None
    total, n = 0, 0
    for cls, seg in top_divs(inner):
        k = set(cls.split())
        if "float-anchor" in k:
            seg = re.sub(r'<div class="mk-float.*', "", seg, flags=re.S)
        if "w-row" in k:
            h = est_row(seg, PAGE_W)
        elif _span_of(cls.replace("float-anchor", "").strip()) is not None:
            h = est_col(seg, PAGE_W)
        else:
            h = est_card(cls, seg, PAGE_W)
        if h is None:
            return None
        total += h
        n += 1
    return total + ROW_GAP * (n - 1) if n else None


def check(path, render=False, allow_local=False):
    text = Path(path).read_text(encoding="utf-8")
    styles, body = split_doc(text)
    UNEST.clear()
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
            add("Medium", "tabs-nested", "标签页里又套了标签页：拆成两页或改用段落标题", line_of(body, m.start()))
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
                        if UNEST:
                            add("Nit", "height-unknown", f"这一行的等高没检：.{UNEST[-1].split()[-1]} 没有实测高度，估不出这栏多高；肉眼确认两栏底边齐不齐")
                        return
                    kk = top_divs(kin)
                    stretch = len(kk) == 1 and bool({"w-card", "procedure_task"} & set(kk[0][0].split()))   # 单张卡会被 base.css 拉到等高
                    hs.append((h, k, stretch))
                short, tall = min(hs), max(hs)
                if tall[0] - short[0] > 150 and short[2]:
                    add("Medium", "card-stretched", f"并排里 .{short[1]} 只有一张矮卡（内容约 {int(short[0])}px），会被拉到和 .{tall[1]}（约 {int(tall[0])}px）等高，卡里空一大块：只补这一栏，用 <hb-col> 再叠一个组件（{fill_hint(body)}），不要给长栏删内容")
                if tall[0] - short[0] > 100 and not short[2]:
                    add("Medium", "column-short", f"并排不等高（按实测行高估算）：.{short[1]} 约 {int(short[0])}px，.{tall[1]} 约 {int(tall[0])}px，差约 {int(tall[0] - short[0])}px；只补短的那一栏，先补组件（{fill_hint(body)}），差 100px 以内才靠加数据行补；不要给长栏删内容，也不用固定高度硬撑")
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
    if "mk-float" in body and ('shell-side' in body or 'item-page' in body):
        left_css = re.search(r"\.mk-float[^{]*\{[^}]*\bleft\s*:\s*0", tail)
        if "float-left" in body or re.search(r'class="mk-float[^"]*\bleft\b', body) or left_css:
            add("High", "float-left", "浮层放在了左侧：左边是导航（详情页是页头与字段），会被盖住；浮层只从右侧探出，用 <hb-float> 默认位置")
    if re.search(r'class="(ocard|m-workbench|m-chat|m-wxg|rec-card|m-tool)\b', body) and 'class="phone' not in body:
        add("High", "mobile-in-pc", "PC 图里出现了手机组件（订单卡、手机工作台、企微消息流等），样式只在 hb-phone 里生效，会散成一堆裸文字：PC 页和 PC 浮层改用 hb-fields、hb-list、hb-multistats 这类 PC 组件")
    _ph = body.split("mk-float-phone", 1)[1] if "mk-float-phone" in body else (body if 'class="phone' in body else "")   # PC 底图＋手机浮层时只看浮层那段
    if _ph and ("<table" in _ph or 'class="table-view' in _ph):
        add("High", "mobile-table", "手机图里画了表格：手机端没有表格形态，列表页和自定义页面里的明细一律是三槽卡片，改用 <hb-ocards>")
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
    no_float = body
    fm = re.search(r'<div class="mk-float', no_float)
    while fm:                                              # 浮层里的表本来就短，不算
        inner = _inner_of(no_float[fm.start():], r'<div class="mk-float[^"]*"[^>]*>')
        if inner is None:
            break
        no_float = no_float[:fm.start()] + " " * (len(inner) + 40) + no_float[fm.start() + len(inner) + 40:]
        fm = re.search(r'<div class="mk-float', no_float)
    for m in re.finditer(r'<div class="w-card table_item_list[^"]*">.*?</table>', no_float, re.S):
        rows = max(len(re.findall(r"<tr\b", m.group(0))) - 1, 0)
        if 0 < rows < 4:
            add("Medium", "short-content", f"表格列表只有 {rows} 行，卡里会空一截：先在这一栏补一个别的组件（{fill_hint(body)}），别把这张表灌成一大堆数据；确实该长就补到 6 行以上（列表页视图是 6～14 行）", line_of(body, m.start()))
    for m in re.finditer(r'<div class="w-card chart_table[^"]*">.*?</table>', no_float, re.S):
        rows = max(len(re.findall(r"<tr\b", m.group(0))) - 1, 0)
        if 0 < rows < 3:
            add("Medium", "short-content", f"透视表只有 {rows} 行：维度太少就不用透视表，换单指标或多项统计；或者在这一栏补一个别的组件（{fill_hint(body)}）", line_of(body, m.start()))
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

    for m in re.finditer(r'<div class="mk-float[^"]*"[^>]*style="([^"]*)"', body):
        w = re.search(r"--float-w:(\d+)px", m.group(1))
        inner = _inner_of(body, r'<div class="float-screen">')
        fw = int(w.group(1)) if w else 640
        zoom = 1 if SLIDE_RE.search(body) else FLOAT_ZOOM     # 演示尺寸下浮层内容不缩小
        raw = est_col(inner, fw / zoom) if inner else None
        page_h = page_height(body)
        fh = raw * zoom + 12 if raw else None                 # 外框上下内边距 6
        if not (w and page_h and fh):
            continue
        covered = max(0, int(w.group(1)) - 200) * min(fh / 2, page_h / 2)   # 浮层最多一半压在底图上，且不高过底图半高
        win_w = SLIDE_W if SLIDE_RE.search(body) else 1440
        if covered > 0.25 * win_w * page_h:
            add("Medium", "float-cover", f"浮层盖住底图约 {covered / (win_w * page_h):.0%}：最多四分之一：只截画面的一块局部，或把宽度收小（480～920 里取小值）", line_of(body, m.start()))

    # ── 数据看板底图骨架不全（为了压比例删了筛选、图表或明细，或把它们挪进了浮层）：两档尺寸都查 ──
    if re.search(r'data-kind="dashboard"', body):
        main = re.split(r'class="[^"]*\bmk-float\b', body)[0]        # 只看底图，浮层里的不算
        slide = bool(SLIDE_RE.search(body))
        for n, pat in (("筛选", r'class="filter"'), ("图表", r'<svg[^>]*class="[^"]*chart|class="[^"]*\bchart\b'),
                       ("明细（透视表或表格列表）", r'class="til-|class="pivot|<table')):
            if not re.search(pat, main):
                sev = "High" if slide or n == "图表" else "Medium"     # 默认尺寸下筛选、明细在宫格式里可无，降一档
                add(sev, "base-skeleton", f"数据看板底图缺{n}：骨架是 横幅 → 筛选 → 单指标 → 图表行 → 明细，不为压比例删掉，也不挪进浮层；"
                                          f"先减数据（明细减到 4 行、单指标 4 个、图表卡压矮），再横向重排")
    if SLIDE_RE.search(body) and not any(x["rule"] == "slide-height" for x in findings):
        ph = page_height(body)
        est = None
        cols = re.findall(r'<section class="kanban-group">.*?</section>', body, re.S)
        if cols:                  # 看板视图：顶栏 56 ＋ 视图页签 52 ＋ 工具栏 70 ＋ 列头 50 ＋ 最高一列的卡片 ＋ 底边 56
            tallest = max(sum(48 + 39 * card.count("<dt>") + 10 for card in re.findall(r'<article class="kanban-item">.*?</article>', c, re.S)) for c in cols)
            est = 56 + 52 + 70 + 50 + tallest + 56
        elif ph:
            est = ph + (104 if "item-grid" in body else 76) + 48      # 顶栏或记录功能区 ＋ 页面上下内边距
        if est:
            if est > SLIDE_HARD_H + 60:
                add("High", "slide-height", f"演示尺寸窗口高约 {int(est)}px（估算），超过 {SLIDE_HARD_H}：底图会接近 4:3，不像真实显示器，放进 PPT 还被按高度缩小。先减数据（明细减到 4 行、字段组每组 4～6 个字段、单指标 4 个、图表卡压矮），再把明细与主图表并排（hb-row spans=\"14|10\"）；骨架组件留在底图，不删、不挪进浮层")

    # ── High：横幅写成某个具体人 ───────────────────────────────────
    for bm in re.finditer(r'<div class="[^"]*\brich title\b[^"]*"[^>]*>(.*?)</div>\s*(?=<div|</)', body, re.S):
        for tm in re.finditer(r"<(h1|p)[^>]*>(.*?)</\1>", bm.group(1), re.S):
            txt = re.sub(r"<[^>]+>", "", tm.group(2)).strip()
            for pat in PERSON_PATTERNS:
                hit = pat.search(txt)
                if hit and not hit.group().startswith(PERSON_EXCLUDE):
                    add("High", "banner-person-name", f'横幅写成具体某个人「{hit.group()}」：工作台服务的是角色（律师、库管、店长），改成「库管工作台」这类角色名', line_of(body, bm.start()))
                    break

    # ── 渲染检查（有浏览器就做，--no-render 关掉）───────────────────
    if render:
        import export
        r = export.probe(path)
        if r is None:
            note = "渲染检查未执行：没找到 Chrome 或 Playwright 的 Chromium（空隙、裁切、浮层出界、并排不齐按静态估算）"
        else:
            note = None
            for e in r.get("extra", []):
                if e["kind"] == "clipped":
                    add("High", "content-clipped", f"cut 窗口内容比窗口高 {e['over']}px，底部被裁：调 cut 值或减内容")
                else:
                    add("High", "float-out", f"浮层探出画布 {e['over']}px：减少浮层内容，或把宽度收小")
            findings[:] = [f for f in findings if f["rule"] not in ("column-short", "float-cover", "height-unknown", "slide-height")]
            sh = r.get("winH") or (r.get("stage") or {}).get("h")
            if SLIDE_RE.search(body) and sh and SLIDE_MAX_H < sh <= SLIDE_HARD_H:
                add("Medium", "slide-height", f"演示尺寸窗口高 {sh}px（实测），超过目标 {SLIDE_MAX_H}：底图 {SLIDE_W}×{sh} 比 {SLIDE_W/sh:.2f}，低于 1.5。先减数据、再横向重排；骨架组件放不下时可让位于信息密度，在验收表第 8 条写明理由（硬上限 {SLIDE_HARD_H}）")
            if SLIDE_RE.search(body) and sh and sh > SLIDE_HARD_H:
                add("High", "slide-height", f"演示尺寸窗口高 {sh}px（实测），超过 {SLIDE_HARD_H}：底图 {SLIDE_W}×{sh} 比 {SLIDE_W/sh:.2f}，接近 4:3，不像真实显示器。先减数据（明细减到 4 行、字段组每组 4～6 个字段、单指标 4 个、图表卡压矮），再把明细与主图表并排（hb-row spans=\"14|10\"）；骨架组件留在底图，不删、不挪进浮层")
            st = r.get("stage") or {}
            # 整张图的宽高比（含浮层向下探出的部分），两档尺寸通用；手机图壳高固定、全屏产品图跟着屏幕走，都不查
            exempt = re.search(r'kind="mobile"', body) or re.search(r'class="stage[^"]*\bproduct\b', body)
            if st.get("w") and st.get("h") and not exempt:
                ratio = st["w"] / st["h"]
                if ratio < RATIO_HIGH:
                    add("High", "figure-ratio", f"整张图 {st['w']}×{st['h']}，宽高比 {ratio:.2f}，低于硬下限 {RATIO_HIGH}：图太竖，在报告或演示稿里一屏放不下。先减数据（明细行数、字段数、图表高度），再横向重排（看板图表行 12+6+6、底部两表并排；详情页字段组 cols=4）；骨架组件不删，仍不行就拆成两张各自完整的图")
                elif ratio < RATIO_OK:
                    add("Medium", "figure-ratio", f"整张图 {st['w']}×{st['h']}，宽高比 {ratio:.2f}，低于目标 {RATIO_OK}（区间 {RATIO_OK}–{RATIO_THIN}）：先减数据、再横向重排，骨架组件不删；重排后仍够不到，可让位于信息密度并在验收表第 8 条写明理由")
                elif ratio > RATIO_THIN:
                    add("Medium", "figure-thin", f"整张图宽高比 {ratio:.2f}，高于 {RATIO_THIN}，画面偏扁、内容偏少：底图按完整一页画（看板是筛选、指标、一排图表、明细 4–6 行；列表页表格 8–14 行），或把浮层做足（四块排两行）把整图撑起来")
            fb = r.get("floatBox") or {}
            if fb.get("w") and fb.get("h"):
                fr_ = fb["w"] / fb["h"]
                if "mk-float-phone" in body:
                    if fb["h"] > 600:
                        add("Medium", "float-phone-tall", f"浮层里的手机高 {fb['h']}px（实测），超过 600：整图会被拉竖。减卡片张数或字段数，让这一屏只讲一件事")
                elif fr_ < FLOAT_RATIO_MIN:
                    add("Medium", "float-ratio", f"浮层 {fb['w']}×{fb['h']}，宽高比 {fr_:.2f}，低于 {FLOAT_RATIO_MIN}：竖成了条，不像另一屏画面。两块组件改左右并排（hb-row spans=\"12|12\"），或把其中一块压矮")
            if r.get("floatCover", 0) > 0.25:
                add("Medium", "float-cover", f"浮层盖住底图 {r['floatCover']:.0%}（实测）：最多四分之一，只截画面的一块局部，或把宽度收小")
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
        note = "渲染检查未执行：加了 --no-render（空隙、裁切、浮层出界、并排不齐按静态估算）"

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
             "10 整体观感 待填：渲染检查没报空隙、裁切、并排不齐、浮层遮挡就写通过；这批图第一次用某种版式，或要确认刚改的问题改对了，才导一张 PNG 看"]
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
    findings, note = check(args[0], render="--no-render" not in sys.argv, allow_local="--allow-local" in sys.argv)
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
        print("观感按 references/canvas/verify-export.md 的人工验收表逐条过")
    return 1 if any(f["level"] == "Blocker" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
