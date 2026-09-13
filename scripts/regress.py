#!/usr/bin/env python3
"""回归：把 tests/frags/*.frag.html 逐个拼装，与 tests/golden/ 的基线做规范化 DOM 比对。

用法：
    python3 scripts/regress.py            # 比对
    python3 scripts/regress.py --update   # 用当前输出覆盖基线（改了公共资产并确认无误后）

规范化：去掉空白差异、class 记号按字母序；不依赖 Chrome。有 Chrome 时可再手动 export.py --png 目检。
"""
import difflib
import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
FRAGS = SKILL / "tests" / "frags"
GOLD = SKILL / "tests" / "golden"
SKIN = "navy-gold"


def norm(html):
    html = re.sub(r"<head>.*?</head>", "", html, flags=re.S)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S)
    html = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
    html = re.sub(r"<svg[^>]*style=\"display:none\".*?</svg>", "", html, flags=re.S)
    html = re.sub(r'class="([^"]*)"', lambda m: 'class="' + " ".join(sorted(m.group(1).split())) + '"', html)
    html = re.sub(r">\s+<", "><", html)
    return re.sub(r"\s+", " ", html).strip()


def build(frag, out):
    r = subprocess.run([sys.executable, str(SKILL / "scripts" / "build.py"), "--skin", SKIN, "--content", str(frag),
                        "--output", str(out), "--title", frag.name.replace(".frag.html", "")], capture_output=True, text=True)
    return r.returncode == 0, r.stderr


def main():
    update = "--update" in sys.argv
    GOLD.mkdir(parents=True, exist_ok=True)
    tmp = SKILL / "tests" / "_out"
    tmp.mkdir(exist_ok=True)
    bad = 0
    for frag in sorted(FRAGS.glob("*.frag.html")):
        name = frag.name.replace(".frag.html", ".html")
        out = tmp / name
        ok, err = build(frag, out)
        if not ok:
            print(f"✗ {name} 拼装失败：{err.strip()[-300:]}")
            bad += 1
            continue
        g = GOLD / name
        if update or not g.exists():
            g.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"= {name} 基线已写入")
            continue
        a, b = norm(g.read_text(encoding="utf-8")), norm(out.read_text(encoding="utf-8"))
        if a == b:
            print(f"✓ {name}")
        else:
            bad += 1
            d = [l for l in difflib.unified_diff(a.split("><"), b.split("><"), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---")]
            print(f"✗ {name} 与基线不同（{len(d)} 处）")
            for l in d[:6]:
                print("   ", l[:160])
    print("全部一致" if not bad else f"{bad} 个不一致")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
