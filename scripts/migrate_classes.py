#!/usr/bin/env python3
"""类名迁移：把 1.x 的组件根类改成 2.0 登记表里的名字（有官方组件的用官方 type key）。

用法：
    python3 scripts/migrate_classes.py --dry-run            # 只统计每个文件会改多少处
    python3 scripts/migrate_classes.py                      # 落盘改 skill 内资产、脚本、文档
    python3 scripts/migrate_classes.py --frag 旧片段.html…   # 只改旧图的宏片段/内容片段（class 属性与 <style> 选择器）

映射表 TOKEN_MAP 是唯一真相：键是旧记号，值是新记号（可多个，空格分隔）。
只按整词替换（记号边界＝非 [A-Za-z0-9_-]），三类位置：
  1. HTML/宏输出里的 class="…" 属性
  2. CSS 选择器里的 .记号（新记号多个时写成 .a.b）
  3. 文档里的 `.记号` 与 `记号`（只在反引号内）
歧义记号不改：row、group、sub、fi、tag、editing、modal-mask、elapsed（见 SKIP）。
"""
import argparse
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent

TOKEN_MAP = {
    # c1 产品壳
    "top-bar": "shell-top-bar", "side": "shell-side", "leaf": "shell-nav-leaf", "folder": "shell-nav-folder",
    "float": "mk-float", "callout": "mk-callout",
    # c2 列表页
    "views": "view-tabs", "tools": "view-tools", "grid-view": "view-grid", "pager": "view-pager",
    "record-card-grid-view": "view-cards", "card-list": "view-cards ops", "pivot-view": "view-pivot",
    "gantt-view": "view-gantt", "task-view": "view-task", "calendar-view": "view-calendar", "kanban-view": "view-kanban",
    # c2 字段
    "field-group": "field_group", "textarea-field": "field-textarea", "category-field": "field-category",
    "rich-field": "field-rich", "barcode-field": "field-barcode", "date-field": "field-date",
    "numeric-field": "field-numeric", "money-field": "field-money", "user-field": "field-user",
    "location-field": "field-location", "file-field": "field-file", "signature-field": "field-signature",
    "image-field": "field-image",
    # c3 自定义页面与详情
    "widget-card": "modal-card", "comment-box": "comment", "w-banner": "rich title", "w-filters": "filter",
    "w-shortcut": "button shortcuts", "shortcut-widget": "button", "w-stat": "chart_single",
    "page-tabs-card": "tabs", "w-tabs": "tabs pill", "w-sub": "procedure_task", "w-chart": "chart",
    "w-pivot": "chart_table", "pa": "portal-app", "rich-widget": "rich", "image-widget": "image",
    "carousel-widget": "carousel", "image-list-widget": "image_list", "graphic-list-widget": "image_text_list",
    "table-item-list-widget": "table_item_list", "fast-form-widget": "fast_form", "rich-checklist": "checklist",
    "embed-widget": "embed", "rich-hero": "rich hero", "multi-progress-card": "progress_bar",
    "datetime-hero": "timer hero", "datetime-time-date": "timer stack", "procedure-process-widget": "procedure_process",
    "multi-stats-widget": "multi_stats", "subtotal-widget": "subtotal", "calendar-agenda-widget": "calendar agenda",
    "calendar-month-view": "calendar month", "item-page-toolbar": "item-toolbar", "page-header-card": "header_card",
    "option-steps": "item-steps", "item-page-grid": "item-grid", "flow-msg": "process", "custom-detail-page": "item-page",
    # c4 手机端
    "wxbar": "m-topbar", "stabs": "m-home", "vbar": "m-viewbar", "plist": "m-cards", "fab": "m-fab",
    "mtool": "m-tool", "rec": "m-rec", "fld": "m-field", "stab": "m-subtabs", "fbar": "m-savebar",
    "taskbar": "m-taskbar", "ptabs": "m-ptasks", "wpage": "m-workbench", "chat": "m-chat",
    # c5 大屏（sc-ic / sc-list / sc 是快捷方式内部记号，不在此列）
    "sc-grid": "screen-grid", "sc-head": "screen-head", "sc-kpi": "screen-kpi", "sc-card": "screen-card",
    "sc-visual": "screen-visual", "sc-bars": "screen-bars", "sc-bar": "screen-bar", "sc-hd": "screen-hd",
    "sc-bd": "screen-bd", "sc-logo": "screen-logo", "sc-dt": "screen-dt", "sc-ticker": "screen-ticker",
}
SKIP = {"row", "group", "sub", "fi", "tag", "editing", "modal-mask", "elapsed"}

_tok = "|".join(sorted(map(re.escape, TOKEN_MAP), key=len, reverse=True))
RE_TOKEN = re.compile(r"(?<![\w-])(" + _tok + r")(?![\w-])")
RE_SEL = re.compile(r"\.(" + _tok + r")(?![\w-])")


def rename_class_attr(text):
    """class="…" 里的记号。"""
    n = 0

    def rep(m):
        nonlocal n
        inner, k = RE_TOKEN.subn(lambda t: TOKEN_MAP[t.group(1)], m.group(2))
        n += k
        return m.group(1) + inner + m.group(3)

    text = re.sub(r'(class=")([^"]*)(")', rep, text)
    return text, n


def rename_selectors(text):
    """CSS 选择器里的 .记号；新记号多个时连写 .a.b。"""
    n = 0

    def rep(m):
        nonlocal n
        n += 1
        return "".join("." + t for t in TOKEN_MAP[m.group(1)].split())

    return RE_SEL.subn(rep, text)[0], n


def rename_md(text):
    """文档：`.记号` 和反引号内的裸记号。"""
    n = 0

    def rep_code(m):
        nonlocal n
        inner, k1 = RE_SEL.subn(lambda t: "".join("." + x for x in TOKEN_MAP[t.group(1)].split()), m.group(1))
        inner, k2 = RE_TOKEN.subn(lambda t: TOKEN_MAP[t.group(1)], inner)
        n += k1 + k2
        return "`" + inner + "`"

    text = re.sub(r"`([^`\n]+)`", rep_code, text)
    text, k = rename_selectors(text)
    return text, n + k


def rename_expand(text):
    """expand.py：class="…" 属性 ＋ 少数拼接类名的字符串字面量。"""
    text, n = rename_class_attr(text)
    for old, new in (('cls = "w-banner"', 'cls = "rich title"'),
                     ('("mtool obar" if mode == "obar" else "mtool")', '("m-tool obar" if mode == "obar" else "m-tool")'),
                     ('"apptab" if mode == "app"', '"apptab" if mode == "app"')):
        if old in text:
            text = text.replace(old, new)
            n += 1
    # DOCS 文字里的 .记号
    text, k = rename_selectors(text)
    return text, n + k


def rename_check(text):
    text, n = rename_selectors(text)
    # SKIP 正则里的裸记号
    m = re.search(r"var SKIP = /\\b\((.*?)\)\\b/;", text)
    if m:
        inner, k = RE_TOKEN.subn(lambda t: TOKEN_MAP[t.group(1)].replace(" ", "|"), m.group(1))
        text = text.replace(m.group(1), inner, 1)
        n += k
    return text, n


def rename_html(text):
    t, n1 = rename_class_attr(text)
    # 内嵌 <style> 里的选择器
    def rep(m):
        s, k = rename_selectors(m.group(0))
        return s
    t2 = re.sub(r"<style[^>]*>.*?</style>", rep, t, flags=re.S)
    _, n2 = rename_selectors(t)
    return t2, n1 + (0 if t2 == t else n2)


TARGETS = [
    ("assets/base.css", rename_selectors),
    ("assets/c1-shell.html", rename_html), ("assets/c2-table-form.html", rename_html),
    ("assets/c3-page-detail.html", rename_html), ("assets/c4-mobile.html", rename_html), ("assets/c5-screen.html", rename_html),
    ("scripts/expand.py", rename_expand), ("scripts/check.py", rename_check),
    ("SKILL.md", rename_md), ("README.md", rename_md),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--frag", nargs="*", help="只改这些旧片段文件")
    a = ap.parse_args()
    if a.frag:
        for f in a.frag:
            p = Path(f)
            t, n = rename_html(p.read_text(encoding="utf-8"))
            if not a.dry_run:
                p.write_text(t, encoding="utf-8")
            print(f"{p}: {n} 处")
        return 0
    targets = list(TARGETS) + [(str(p.relative_to(SKILL)), rename_md) for p in sorted((SKILL / "references").rglob("*.md"))
                                if "measured" not in p.parts]
    total = 0
    for rel, fn in targets:
        p = SKILL / rel
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        out, n = fn(src)
        total += n
        print(f"{rel}: {n} 处")
        if not a.dry_run and out != src:
            p.write_text(out, encoding="utf-8")
    print(f"合计 {total} 处{'（空跑，未写盘）' if a.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
