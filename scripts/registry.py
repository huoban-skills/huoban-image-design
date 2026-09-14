#!/usr/bin/env python3
"""登记表 assets/registry.json 的校验与查询。

用法：
    python3 scripts/registry.py --check            # 三向核对：登记表 ↔ 结构文件 ↔ base.css
    python3 scripts/registry.py --list [页面类型]   # 按页面类型列可用组件（id、官方名、宏）
    python3 scripts/registry.py --find 关键词       # 按 id / 官方 type / 中文名 / 旧类名查

--check 报三类问题：
  1. 结构文件里有 data-component/data-architecture 但登记表没有
  2. 登记表 id（首记号）在 base.css 里没有对应样式（原子类与页面级 id 除外）
  3. 登记表登记的 file+name 在结构文件里找不到
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
    for p in problems:
        print(p)
    print(f"{'✓ 登记表与结构、样式一致' if not problems else f'{len(problems)} 处不一致'}")
    return 1 if problems else 0


def list_(page):
    reg = load()
    key = {"list": "page:list", "detail": "page:detail", "workbench": "page:workbench", "dashboard": "page:dashboard",
           "screen": "page:screen", "mobile": "page:mobile"}.get(page, page)
    rows = [e for e in reg["entries"] if e["kind"] == "component" and (not page or key in e.get("allowed_in", []))]
    for e in rows:
        tk = e.get("type_key") or "—"
        mc = e.get("macro") or "—"
        st = {"measured": "实测", "imitated": "仿写", "unverified": "未核"}.get(e.get("measured"), "")
        print(f"{e['id']:<22} {tk:<20} {e['cn']:<18} 宏 {mc:<18} {st}")
    print(f"共 {len(rows)} 项")


def find(kw):
    reg = load()
    for e in reg["entries"]:
        hay = " ".join(str(e.get(k) or "") for k in ("id", "type_key", "cn", "old_class", "name"))
        if kw.lower() in hay.lower():
            print(json.dumps({k: e.get(k) for k in ("id", "type_key", "cn", "old_class", "file", "name", "macro", "grid", "measured", "note")},
                             ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", nargs="?", const="", metavar="页面类型")
    ap.add_argument("--find")
    a = ap.parse_args()
    if a.check:
        return check()
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
