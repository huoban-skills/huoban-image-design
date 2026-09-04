#!/usr/bin/env python3
"""确定性组装单文件 HTML：固定拼接顺序，模型只写内容片段和本图补充样式。

用法：
    python3 scripts/build.py \
        --skin dawn-blue \
        --content /tmp/stage.html \
        --extra-style /tmp/page.css \
        --output "源文件/图名.html" \
        [--fullbleed] [--title "图名"]

- --skin：皮肤名（assets/skins/ 下的文件名，不带 .css）或一个 css 文件路径（自定义皮肤）。
- --content：<body> 里的页面内容，即 <div class="stage">…</div> 整段（浮层、标注都在其中）。
  片段里的 <hb-*> 宏（壳层、表格行、卡片、图表等重复块，见 references/macros.md）先由 expand.py 展开。
- --extra-style：本图补充样式，可省略。自动加“/* ── 本图布局 ── */”分隔头供 check.py 识别。
- --fullbleed：产品设计类加此开关（body 加 class="fullbleed"）；营销类不加。

拼接顺序固定：宏展开 → 皮肤 css → base.css → 本图补充样式 → icons.svg（body 开头）→ 内容 → fit.js（body 末尾）。
改过 base.css 或皮肤后重跑本脚本即可重拼既有图（图里嵌的是拼装时的快照）。
"""
import argparse
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"

PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
{skin_css}
{base_css}
{extra_css}
</style>
</head>
<body{body_class}>
{icons}
{content}
<script>
{fit_js}
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skin", required=True)
    ap.add_argument("--content", required=True)
    ap.add_argument("--extra-style")
    ap.add_argument("--output", required=True)
    ap.add_argument("--fullbleed", action="store_true")
    ap.add_argument("--title", default="伙伴云界面示意图")
    a = ap.parse_args()

    skin_path = Path(a.skin)
    if not skin_path.exists():
        skin_path = ASSETS / "skins" / (a.skin + ".css")
    if not skin_path.exists():
        avail = "、".join(sorted(p.stem for p in (ASSETS / "skins").glob("*.css")))
        sys.stderr.write(f"皮肤不存在：{a.skin}\n可用：{avail}，或给一个 css 文件路径\n")
        return 1

    content = Path(a.content).read_text(encoding="utf-8").strip()
    if "<hb-" in content:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from expand import expand, ExpandError
        try:
            content = expand(content)
        except ExpandError as e:
            sys.stderr.write(f"宏展开失败：{e}\n")
            return 1
    if '<template' in content:
        sys.stderr.write("内容里还有 <template> 标签：模板要去壳后放进 .stage，template 元素浏览器不渲染\n")
        return 1
    if not re.search(r'class="stage[\s"]', content):
        sys.stderr.write('内容里没有 class="stage"：<body> 内容必须包在 <div class="stage"> 里\n')
        return 1

    extra = ""
    if a.extra_style:
        raw = Path(a.extra_style).read_text(encoding="utf-8").strip()
        if raw:
            head = "" if "本图布局" in raw else "/* ── 本图布局 ── */\n"
            extra = head + raw

    # 大屏背景：内容里出现 class="… bg-xxx …" 时把 assets/screens/bg-xxx.svg 以 data URI 注入
    import base64
    for name in sorted(set(re.findall(r'class="[^"]*\bbg-([a-z0-9-]+)\b', content))):
        svg_path = ASSETS / "screens" / f"bg-{name}.svg"
        if not svg_path.exists():
            avail = "、".join(sorted(p.stem[3:] for p in (ASSETS / "screens").glob("bg-*.svg")))
            sys.stderr.write(f"大屏背景 bg-{name} 不存在，可用：{avail}\n")
            return 1
        uri = "data:image/svg+xml;base64," + base64.b64encode(svg_path.read_bytes()).decode()
        extra += f"\n.screen.bg-{name} {{ background-image: url({uri}); }}"

    icons = (ASSETS / "icons.svg").read_text(encoding="utf-8").strip()
    html = PAGE.format(
        title=a.title,
        skin_css=skin_path.read_text(encoding="utf-8").strip(),
        base_css=(ASSETS / "base.css").read_text(encoding="utf-8").strip(),
        extra_css=extra,
        body_class=' class="fullbleed"' if a.fullbleed else "",
        icons=icons,
        content=content,
        fit_js=(ASSETS / "fit.js").read_text(encoding="utf-8").strip(),
    )
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    sys.stderr.write(f"已拼装：{out}（皮肤 {skin_path.stem}{'，全屏模式' if a.fullbleed else '，画布模式'}）\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
