#!/usr/bin/env python3
"""登记表 assets/registry.json 的校验与查询。

用法：
    python3 scripts/registry.py --check            # 三向核对：登记表 ↔ 结构文件 ↔ base.css
    python3 scripts/registry.py --list [页面类型]   # 按页面类型列可用组件（id、官方名、宏）
    python3 scripts/registry.py --find 关键词       # 按 id / 官方 type / 中文名 / 别名 / 旧类名查
    python3 scripts/registry.py --coverage         # 各页面允许的官方组件是否都在页面原则或组件辞典里提到

--check 报四类问题：
  1. 结构文件里有 data-component/data-architecture 但登记表没有
  2. 登记表 id（首记号）在 base.css 里没有对应样式（原子类与页面级 id 除外）
  3. 登记表登记的 file+name 在结构文件里找不到
  4. 同一 type_key 在同一页面类型下既有 measured 条目、又有未采集的 unverified 占位条目
退出码：有问题返回 1。
"""
import argparse
import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"
REG = ASSETS / "registry.json"


def load():
    return json.loads(REG.read_text(encoding="utf-8"))


def css_classes():
    css = (ASSETS / "base.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return set(re.findall(r"\.([A-Za-z_][\w-]*)", css))


def templates():
    out = []
    for f in sorted(ASSETS.glob("c*.html")):
        t = f.read_text(encoding="utf-8")
        for m in re.finditer(r"<template\s+([^>]*?)>", t):
            nm = re.search(r'data-(architecture|component)="([^"]+)"', m.group(1))
            if nm:
                out.append((f.name, nm.group(2), nm.group(1)))
    return out


def check():
    reg = load()
    entries = reg["entries"]
    known = css_classes()
    problems = []
    registered = {(e.get("file"), e.get("name")) for e in entries if e.get("file")}
    for fname, name, kind in templates():
        if (fname, name) not in registered:
            problems.append(f"未登记：{fname} {kind} 「{name}」")
    tpl = {(f, n) for f, n, _ in templates()}
    for e in entries:
        if e.get("file") and (e["file"], e["name"]) not in tpl:
            problems.append(f"登记项找不到模板：{e['file']} 「{e['name']}」")
        if e["kind"] == "component" and e.get("file"):
            root = e["id"].split()[0]
            if root not in known and root not in ("tfoot",):
                problems.append(f"无样式：{e['id']}（{e['file']} 「{e['name']}」）")
    # 同一 type_key 不得同时存在 measured 与 unverified 两条：
    # 实测条目已经能画，未采集占位（file 为空）就是陈旧重复，按页面类型有交集才算撞车
    by_key = {}
    for e in entries:
        if e.get("kind") == "component" and e.get("type_key"):
            by_key.setdefault(e["type_key"], []).append(e)
    for tk, group in by_key.items():
        done = [e for e in group if e.get("measured") == "measured"]
        stale = [e for e in group if e.get("measured") == "unverified" and not e.get("file")]
        for s in stale:
            pages = set(s.get("allowed_in") or [])
            for d in done:
                if pages & set(d.get("allowed_in") or []):
                    problems.append(f"同一 type_key 既实测又未采集：{tk}「{s['cn']}」是未采集占位，"
                                    f"已有实测条目 {d['id']}「{d['cn']}」，删掉占位那条")
                    break
    try:
        import expand
        known = set(expand.MACROS)
        for e in entries:
            for m in re.split(r"[/,\s]+", e.get("macro") or ""):
                if m and m not in known:
                    problems.append(f"宏不存在：{e['id']} 写了 {m}（expand.py --list 里没有）")
    except ImportError:
        pass
    for p in problems:
        print(p)
    print(f"{'✓ 登记表与结构、样式一致' if not problems else f'{len(problems)} 处不一致'}")
    return 1 if problems else 0


def list_(page):
    reg = load()
    alias = {"列表页": "list", "详情页": "detail", "工作台": "workbench", "看板": "dashboard", "数据看板": "dashboard",
             "大屏": "screen", "数据大屏": "screen", "手机端": "mobile", "手机": "mobile", "表单编辑页": "form"}
    page = alias.get(page, page)
    if page == "form":
        print("表单编辑页不走登记表，按 assets/c2-table-form.html 的模板手写")
        return
    kinds = {"list": "page:list", "detail": "page:detail", "workbench": "page:workbench", "dashboard": "page:dashboard",
             "screen": "page:screen", "mobile": "page:mobile"}
    if page and page not in kinds:
        print(f"没有页面类型 {page}。可用：{'/'.join(kinds)}（或中文：{'/'.join(alias)}）"); return
    key = kinds.get(page, page)
    rows = [e for e in reg["entries"] if e["kind"] == "component" and (not page or key in e.get("allowed_in", []))]
    for e in rows:
        tk = e.get("type_key") or "—"
        mc = e.get("macro") or "—"
        st = {"measured": "实测", "imitated": "仿写", "unverified": "未核"}.get(e.get("measured"), "")
        print(f"{e['id']:<22} {tk:<20} {e['cn']:<18} 宏 {mc:<18} {st}")
    print(f"共 {len(rows)} 项")


def find(kw):
    reg = load()
    hit = 0
    for e in reg["entries"]:
        hay = " ".join(str(e.get(k) or "") for k in ("id", "type_key", "cn", "old_class", "name"))
        hay += " " + " ".join(e.get("aliases") or [])
        if kw.lower() in hay.lower():
            hit += 1
            print(json.dumps({k: e.get(k) for k in ("id", "type_key", "cn", "aliases", "old_class", "file", "name", "macro", "grid", "measured", "note")},
                             ensure_ascii=False))
    if not hit:
        print(f"没有匹配 {kw} 的条目")


def coverage():
    import re
    reg = load()
    root = SKILL / "references" / "principles"
    guide = (root / "component-guide.md").read_text(encoding="utf-8")
    docs = {"workbench": "workbench.md", "dashboard": "dashboard.md", "detail": "item-detail.md"}
    bad = 0
    for kind, doc in docs.items():
        text = (root / doc).read_text(encoding="utf-8")
        for e in reg["entries"]:
            if e.get("kind") != "component" or not e.get("type_key"):
                continue
            if f"page:{kind}" not in (e.get("allowed_in") or []):
                continue
            cn = re.sub(r"（.*?）", "", e["cn"]).strip()
            names = [cn] + (e.get("aliases") or [])
            if not any(n in text or n in guide for n in names):
                print(f"{doc} 与组件辞典都没提到：{cn}（{e['type_key']}）"); bad += 1
    print("✓ 各页面允许的组件都有出处" if not bad else f"{bad} 处未覆盖")
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", nargs="?", const="", metavar="页面类型")
    ap.add_argument("--find")
    ap.add_argument("--coverage", action="store_true")
    a = ap.parse_args()
    if a.check:
        return check()
    if a.coverage:
        return coverage()
    if a.list is not None:
        list_(a.list)
        return 0
    if a.find:
        find(a.find)
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
