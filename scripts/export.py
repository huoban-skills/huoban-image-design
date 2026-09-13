#!/usr/bin/env python3
"""可选导出：PNG（要 Chrome）、SVG（不要 Chrome）、渲染探针（给 check.py --render 用）。

用法：
    python3 scripts/export.py 图.html --png                 # 出 图@2x.png（同目录）；找不到 Chrome 退出码 2 并给手动命令
    python3 scripts/export.py 图.html --png --out 路径.png
    python3 scripts/export.py 图.html --svg                 # 出 图.svg：foreignObject 包 HTML，嵌报告用，不需要 Chrome
    python3 scripts/export.py 图.html --probe               # 渲染探针 JSON（空隙、裁切、浮层出界、并排不齐）

默认交付物是 HTML，本脚本只在用户或报告明确要 PNG/SVG 时用。
Chrome 探测顺序：CHROME_BIN → macOS 本机 Chrome → PATH 里的 chrome-headless-shell/google-chrome/chromium → ~/chrome-headless-shell-linux64。
不自动下载；沙箱里没有 Chrome 就跳过 PNG，交 HTML。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MANUAL = """未找到 Chrome，PNG 未导出。HTML 已是可交付的源文件；确需 PNG 时任选：
  1. 本机装了 Chrome：CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" python3 scripts/export.py 图.html --png
  2. Linux 沙箱可联网：下载 chrome-headless-shell（约 120MB）到 ~/chrome-headless-shell-linux64/ 后重跑：
     curl -sL -o /tmp/chs.zip "https://registry.npmmirror.com/-/binary/chrome-for-testing/152.0.7977.54/linux64/chrome-headless-shell-linux64.zip" && unzip -q -o /tmp/chs.zip -d ~ && chmod +x ~/chrome-headless-shell-linux64/chrome-headless-shell
  3. 嵌报告用矢量：python3 scripts/export.py 图.html --svg（不需要 Chrome）"""


def find_chrome():
    if os.environ.get("HB_NO_CHROME"):      # 沙箱模拟：强制当作没有 Chrome
        return None
    cands = [os.environ.get("CHROME_BIN"),
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
             os.path.expanduser("~/chrome-headless-shell-linux64/chrome-headless-shell")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    for name in ("chrome-headless-shell", "google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None


PROBE = r"""
<script>
(function () {
  var st = document.querySelector('.stage');
  document.querySelectorAll('.stage').forEach(function (s) { s.style.zoom = 1; });
  var out = { stage: st ? { w: Math.round(st.scrollWidth), h: Math.round(st.scrollHeight) } : null, gaps: [], extra: [], uneven: [] };
  var BOTTOM = 48, RIGHT = 120;
  var SKIP = /\b(stage|window|mk-float|shell-side|tree|win-body|main|mk-callout|hscroll|kanban-group|kanban-columns|w-card|comp|widget|kanban-item|record-card|field|f-value|modal|grid|page-header|item-page|item-page-scroll|item-page-canvas|screen|screen-grid|duo|phone|conn|procedure_task|button|tabs|chart_table|chart)\b/;
  document.querySelectorAll('*').forEach(function (e) {
    var cls = typeof e.className === 'string' ? e.className : '';
    if (e === document.body || e === document.documentElement || SKIP.test(cls) || !e.children.length) return;
    var s = getComputedStyle(e);
    if (s.display === 'none' || s.position === 'absolute') return;
    var r = e.getBoundingClientRect();
    if (r.width < 300 || r.height < 100) return;
    var maxB = 0, maxR = 0;
    for (var i = 0; i < e.children.length; i++) {
      var c = e.children[i].getBoundingClientRect();
      if (c.height === 0) continue;
      if (c.bottom > maxB) maxB = c.bottom;
      if (c.right > maxR) maxR = c.right;
    }
    if (!maxB) return;
    var gapB = Math.round(r.bottom - (parseFloat(s.paddingBottom) || 0) - maxB);
    var gapR = Math.round(r.right - (parseFloat(s.paddingRight) || 0) - maxR);
    var hit = { cls: cls.slice(0, 44) || e.tagName.toLowerCase(), box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] };
    if (gapB > BOTTOM) hit.bottom = gapB;
    if (gapR > RIGHT && r.width > 500) hit.right = gapR;
    if (hit.bottom || hit.right) out.gaps.push(hit);
  });
  out.gaps = out.gaps.filter(function (a) {
    return !out.gaps.some(function (b) {
      return b !== a && b.box[1] <= a.box[1] && b.box[1] + b.box[3] >= a.box[1] + a.box[3]
        && b.box[0] <= a.box[0] && b.box[0] + b.box[2] >= a.box[0] + a.box[2] && Math.abs((b.bottom || 0) - (a.bottom || 0)) < 8;
    });
  });
  document.querySelectorAll('.item-grid, .w-row').forEach(function (g) {
    var rows = {};
    [].forEach.call(g.children, function (c) {
      var r = c.getBoundingClientRect(); if (r.height === 0) return;
      var k = Math.round(r.top / 5);
      (rows[k] = rows[k] || []).push({ cls: (typeof c.className === 'string' ? c.className : c.tagName.toLowerCase()).slice(0, 40), h: Math.round(r.height), bottom: Math.round(r.bottom) });
    });
    Object.keys(rows).forEach(function (k) {
      var arr = rows[k]; if (arr.length < 2) return;
      arr.sort(function (a, b) { return a.bottom - b.bottom; });
      var d = arr[arr.length - 1].bottom - arr[0].bottom;
      if (d > 24) out.uneven.push({ diff: d, short: arr[0].cls, shortH: arr[0].h, tall: arr[arr.length - 1].cls, tallH: arr[arr.length - 1].h });
    });
  });
  var win = document.querySelector('.window.cut');
  if (win && win.scrollHeight > win.clientHeight + 4) out.extra.push({ kind: 'clipped', over: win.scrollHeight - win.clientHeight });
  if (st) {
    var sr = st.getBoundingClientRect();
    document.querySelectorAll('.mk-float').forEach(function (fl) {
      var fr = fl.getBoundingClientRect();
      if (fr.bottom > sr.bottom + 2) out.extra.push({ kind: 'float-out', over: Math.round(fr.bottom - sr.bottom) });
      if (fr.top < sr.top - 2) out.extra.push({ kind: 'float-out', over: Math.round(sr.top - fr.top) });
    });
  }
  document.title = 'PROBE' + JSON.stringify(out);
})();
</script>
"""


def probe(path, chrome=None):
    """渲染探针：返回 dict；没有 Chrome 返回 None。"""
    chrome = chrome or find_chrome()
    if not chrome:
        return None
    text = Path(path).read_text(encoding="utf-8")
    d = os.path.dirname(os.path.abspath(path))
    tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir=d, encoding="utf-8")
    tmp.write(text + PROBE)
    tmp.close()
    try:
        r = subprocess.run([chrome, "--headless", "--dump-dom", "--virtual-time-budget=3000",
                            "--window-size=1704,1200", "--hide-scrollbars", tmp.name],
                           capture_output=True, text=True, timeout=90)
        m = re.search(r"<title>PROBE(.*?)</title>", r.stdout, re.S)
        return json.loads(m.group(1)) if m else None
    except Exception:
        return None
    finally:
        os.unlink(tmp.name)


def export_png(path, out=None):
    chrome = find_chrome()
    if not chrome:
        sys.stderr.write(MANUAL + "\n")
        return 2
    text = Path(path).read_text(encoding="utf-8")
    full = 'class="fullbleed"' in text
    info = probe(path, chrome) or {}
    st = info.get("stage") or {}
    h = st.get("h") or 1000
    w = st.get("w") or 1640
    if full:
        size = f"{w},{h}"
        bg = []
    else:
        size = f"{w + 64},{h + 96}"       # body 左右 padding 32×2、上下留白
        bg = ["--default-background-color=00000000"]
    out = out or str(Path(path).with_name(Path(path).stem + "@2x.png"))
    cmd = [chrome, "--headless", f"--screenshot={out}", f"--window-size={size}", "--force-device-scale-factor=2",
           "--hide-scrollbars", "--virtual-time-budget=3000", *bg, f"file://{os.path.abspath(path)}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not os.path.exists(out):
        sys.stderr.write(f"PNG 未生成：{r.stderr[-400:]}\n")
        return 1
    sys.stderr.write(f"已导出：{out}（{size} ×2）\n")
    return 0


def export_svg(path, out=None):
    """把 <style>＋.stage 包进 <svg><foreignObject>，报告嵌图用。三个必修点：svg 补 xmlns、<br> 自闭合、垫不透明 rect。"""
    text = Path(path).read_text(encoding="utf-8")
    styles = "".join(re.findall(r"<style[^>]*>.*?</style>", text, flags=re.S))
    m = re.search(r'(<div class="stage[^"]*"[^>]*>.*)</body>', text, flags=re.S)
    if not m:
        sys.stderr.write("找不到 <div class=\"stage\">，不是本 skill 的产物\n")
        return 1
    stage = re.sub(r"<script>.*?</script>", "", m.group(1), flags=re.S).strip()
    icons = re.search(r'<svg[^>]*style="display:none"[^>]*>.*?</svg>', text, flags=re.S)
    body = (icons.group(0) if icons else "") + stage
    body = re.sub(r"<svg(?![^>]*xmlns)", '<svg xmlns="http://www.w3.org/2000/svg"', body)
    body = re.sub(r"<br\s*>", "<br/>", body)
    body = re.sub(r"<img([^>]*?)(?<!/)>", r"<img\1/>", body)
    info = probe(path) or {}
    st = info.get("stage") or {}
    w = st.get("w") or (1100 if "duo" in stage[:600] else 1640)
    h = st.get("h") or 1000
    if not st:
        sys.stderr.write("提示：没有 Chrome，SVG 高度按 1000 估算；打开后若有裁切，手动改 <svg height>\n")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
           f'<rect width="100%" height="100%" fill="#ffffff"/>'
           f'<foreignObject width="{w}" height="{h}"><div xmlns="http://www.w3.org/1999/xhtml">{styles}{body}</div></foreignObject></svg>')
    import xml.etree.ElementTree as ET
    try:
        ET.fromstring(svg.encode("utf-8"))
    except ET.ParseError as e:
        sys.stderr.write(f"SVG 不是合法 XML：{e}。常见原因：未闭合的 <br>/<img>、裸 & 符号\n")
        return 1
    out = out or str(Path(path).with_suffix(".svg"))
    Path(out).write_text(svg, encoding="utf-8")
    sys.stderr.write(f"已导出：{out}（{w}×{h}）\n")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--svg", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.probe:
        r = probe(a.file)
        if r is None:
            sys.stderr.write("渲染探针未执行：未找到 Chrome\n")
            return 2
        print(json.dumps(r, ensure_ascii=False))
        return 0
    if a.svg:
        return export_svg(a.file, a.out)
    if a.png:
        return export_png(a.file, a.out)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
