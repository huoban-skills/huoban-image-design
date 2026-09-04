#!/usr/bin/env python3
"""从结构文件（assets/c1～c4）按名精确提取 <template>，实现按需读取，不整读文件。

用法：
    python3 scripts/extract_templates.py --list                      # 全部结构文件的架构/组件目录
    python3 scripts/extract_templates.py assets/c3-page-detail.html \
        --architecture "独立自定义详情页" \
        --component "记录功能区" --component "标题卡片"              # 精确提取，写入临时文件并打印路径
    ... --group "统计"                                               # 按 data-group 取一组
    ... --out /tmp/tpl.html                                          # 指定输出文件

规则：
- 按 data-architecture / data-component / data-group 的值精确匹配，不做模糊匹配；
  名字不存在直接报错并列出该文件的可用名。
- 输出自动带上：文件头部说明注释、模板紧邻的前置注释、模板标签上的全部
  data-* 属性（data-measured 实测注释是层次关系的判据，禁止剥离）。
- 只读不写：结构正本永远是 assets/c1～c4，本脚本不修改它们。
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
C_FILES = ["c1-shell.html", "c2-table-form.html", "c3-page-detail.html", "c4-mobile.html", "c5-screen.html"]

TPL_OPEN = re.compile(r"^\s*<template\b")  # 只认行首，避免命中注释里提到的 <template> 字样


def parse(path):
    """返回 (file_header, [block])；block = {attrs, text(含前置注释), start_line}"""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    first = next((i for i, ln in enumerate(lines) if TPL_OPEN.search(ln)), len(lines))
    header = "".join(lines[:first]).strip()

    blocks = []
    i = first
    while i < len(lines):
        if not TPL_OPEN.search(lines[i]):
            i += 1
            continue
        # 前置注释：上一个 </template>（或文件头）到本模板之间的所有内容，
        # 只要含注释就整段带上——这是模板的关联说明，不许剥离
        j = i - 1
        while j >= first and "</template>" not in lines[j]:
            j -= 1
        pre = "".join(lines[j + 1:i])
        if "<!--" not in pre:
            pre = ""
        else:
            pre = pre.strip("\n") + "\n"
        # 开标签可能跨行，读到第一个 '>' 为止拿属性
        open_tag = ""
        k = i
        while k < len(lines):
            open_tag += lines[k]
            if ">" in lines[k]:
                break
            k += 1
        attrs = dict(re.findall(r'(data-[\w-]+)="([^"]*)"', open_tag))
        # 到闭标签
        end = k
        while end < len(lines) and "</template>" not in lines[end]:
            end += 1
        block_text = (pre if pre.strip() else "") + "".join(lines[i:end + 1])
        blocks.append({"attrs": attrs, "text": block_text, "line": i + 1})
        i = end + 1
    return header, blocks


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("files", nargs="*", help="结构文件路径；--list 时可省略")
    ap.add_argument("--architecture", action="append", default=[])
    ap.add_argument("--component", action="append", default=[])
    ap.add_argument("--group", action="append", default=[])
    ap.add_argument("--out", help="输出文件；缺省写临时文件并打印路径")
    ap.add_argument("--list", action="store_true", help="打印目录（架构与组件名），不提取")
    a = ap.parse_args()

    if a.list:
        files = a.files or [str(SKILL / "assets" / f) for f in C_FILES]
        for f in files:
            _, blocks = parse(f)
            print(f"== {Path(f).name} ==")
            for b in blocks:
                at = b["attrs"]
                if "data-architecture" in at:
                    extra = "".join(f" [{k[5:]}:{v}]" for k, v in at.items()
                                    if k in ("data-use", "data-default-for", "data-slot", "data-layer"))
                    print(f"  架构: {at['data-architecture']}{extra}")
                elif "data-component" in at:
                    g = at.get("data-group", "")
                    print(f"    组件: {at['data-component']}" + (f"（{g}）" if g else ""))
        return 0

    if not a.files:
        ap.error("需要结构文件路径（或用 --list）")
    # 目录里组件名带「（分组）」后缀，直接照抄也能命中
    a.component = [re.sub(r"（[^）]*）$", "", c) for c in a.component]
    if not (a.architecture or a.component or a.group):
        ap.error("至少给一个 --architecture / --component / --group")

    picked, headers = [], []
    avail_arch, avail_comp, avail_group = set(), set(), set()
    for f in a.files:
        header, blocks = parse(f)
        headers.append(f"<!-- 来源：{Path(f).name} -->\n{header}")
        for b in blocks:
            at = b["attrs"]
            avail_arch.add(at.get("data-architecture", ""))
            avail_comp.add(at.get("data-component", ""))
            avail_group.add(at.get("data-group", ""))
            hit = (at.get("data-architecture") in a.architecture
                   or at.get("data-component") in a.component
                   or at.get("data-group") in a.group)
            if hit:
                picked.append(b)

    missing = ([f"架构「{n}」" for n in a.architecture if n not in avail_arch]
               + [f"组件「{n}」" for n in a.component if n not in avail_comp]
               + [f"组「{n}」" for n in a.group if n not in avail_group])
    if missing:
        sys.stderr.write("找不到：" + "、".join(missing) + "\n")
        sys.stderr.write("可用架构：" + "、".join(sorted(n for n in avail_arch if n)) + "\n")
        sys.stderr.write("可用组件：" + "、".join(sorted(n for n in avail_comp if n)) + "\n")
        return 1

    out = "\n\n".join(headers) + "\n\n" + "\n".join(b["text"].rstrip() + "\n" for b in picked)
    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
        print(a.out)
    else:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                          prefix="hb-templates-", encoding="utf-8")
        tmp.write(out)
        tmp.close()
        print(tmp.name)
    n_arch = sum(1 for b in picked if "data-architecture" in b["attrs"])
    sys.stderr.write(f"提取 {len(picked)} 个模板（架构 {n_arch}，组件 {len(picked) - n_arch}）\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
