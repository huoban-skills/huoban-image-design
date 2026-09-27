#!/usr/bin/env python3
"""可选导出：PNG（要 Chrome）、渲染探针（给 check.py 的渲染检查用）。

用法：
    python3 <skill>/scripts/export.py 图.html --png                 # 出 图@2x.png（同目录）
    python3 <skill>/scripts/export.py 图.html --png --out 路径.png
    python3 <skill>/scripts/export.py 配图/*.html --png             # 批量：装了 Playwright 时整批只起一次浏览器
    python3 <skill>/scripts/export.py 图.html --probe               # 渲染探针 JSON（空隙、裁切、浮层出界、并排不齐）

默认交付物是 HTML，本脚本只在用户或报告明确要 PNG 时用。
浏览器探测顺序：CHROME_BIN → Playwright 自报的 Chromium 路径 → Playwright 缓存目录 → PATH 里的 chromium/chrome → macOS 本机 Chrome；找不到就报错退出。
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

NO_BROWSER = "找不到浏览器：设 CHROME_BIN 指向 Chromium 或 Chrome 的可执行文件后重跑"


def _playwright_path():
    """Playwright 自己报告的 Chromium 路径：不依赖缓存目录的命名，升级 Playwright 也不会失效。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
        return path if path and os.path.exists(path) else None
    except Exception:
        return None


def find_chrome():
    c = os.environ.get("CHROME_BIN")
    if c and os.path.exists(c):
        return c
    c = _playwright_path()
    if c:
        return c
    pw = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.expanduser(
        "~/Library/Caches/ms-playwright" if sys.platform == "darwin" else "~/.cache/ms-playwright")
    for pat in ("chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",   # Playwright 1.5x
                "chromium_headless_shell-*/chrome-*/headless_shell",                         # 旧版
                "chromium-*/chrome-linux*/chrome",
                "chromium-*/chrome-mac*/*.app/Contents/MacOS/*"):
        hits = sorted(glob.glob(os.path.join(pw, pat)))
        if hits:
            return hits[-1]
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome", "chrome-headless-shell"):
        p = shutil.which(name)
        if p:
            return p
    c = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    return c if os.path.exists(c) else None


def launch(p):
    """用 Playwright 起 Chromium：自带的浏览器起不来（没装、版本对不上）就用 find_chrome 找到的那个。"""
    try:
        return p.chromium.launch()
    except Exception:
        chrome = find_chrome()
        if not chrome:
            raise
        return p.chromium.launch(executable_path=chrome)


PROBE = r"""
<script>
(function () {
  var st = document.querySelector('.stage');
  document.querySelectorAll('.stage').forEach(function (s) { s.style.zoom = 1; });
  var out = { stage: st ? { w: Math.round(st.scrollWidth), h: Math.round(st.scrollHeight) } : null, gaps: [], extra: [], uneven: [] };
  var wb = document.querySelector('.stage .window, .stage .item-page');
  if (wb) out.winH = Math.round(wb.getBoundingClientRect().height);
  var BOTTOM = 48, RIGHT = 120;
  var SKIP = /\b(stage|window|mk-float|shell-side|tree|win-body|main|mk-callout|hscroll|kanban-group|kanban-columns|w-card|comp|widget|kanban-item|record-card|field|f-value|modal|grid|page-header|item-page|item-page-scroll|item-page-canvas|screen|screen-grid|duo|phone|conn|procedure_task|button|tabs|chart_table|chart)\b/;
  document.querySelectorAll('*').forEach(function (e) {
    var cls = typeof e.className === 'string' ? e.className : '';
    if (e === document.body || e === document.documentElement || SKIP.test(cls) || !e.children.length) return;
    if (e.closest('.phone')) return;         // 手机屏固定 812 高，内容短时下方留白是真实样子，不算空隙
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
  // 单指标：卡太窄时标签会被省略号截掉、数值会溢出去压住火花线
  out.statcut = [];
  document.querySelectorAll('.w-card.chart_single').forEach(function (c) {
    var lb = c.querySelector('.st-lb'), vl = c.querySelector('.st-vl');
    var what = [];
    if (lb && lb.scrollWidth > lb.clientWidth + 1) what.push('标签「' + lb.textContent.trim() + '」');
    if (vl && vl.scrollWidth > vl.clientWidth + 1) what.push('数值「' + vl.textContent.trim() + '」');
    if (what.length) out.statcut.push({ w: Math.round(c.getBoundingClientRect().width), what: what.join('、') });
  });
  var win = document.querySelector('.window.cut');
  if (win && win.scrollHeight > win.clientHeight + 4) out.extra.push({ kind: 'clipped', over: win.scrollHeight - win.clientHeight });
  if (st) {
    var sr = st.getBoundingClientRect();
    document.querySelectorAll('.mk-float').forEach(function (fl) {
      var fr = fl.getBoundingClientRect();
      out.floatBox = { w: Math.round(fr.width), h: Math.round(fr.height) };
      if (fr.bottom > sr.bottom + 2) out.extra.push({ kind: 'float-out', over: Math.round(fr.bottom - sr.bottom) });
      if (fr.top < sr.top - 2) out.extra.push({ kind: 'float-out', over: Math.round(sr.top - fr.top) });
      var base = st.querySelector('.window, .item-page');
      if (base) {
        var br = base.getBoundingClientRect();
        var ox = Math.max(0, Math.min(br.right, fr.right) - Math.max(br.left, fr.left));
        var oy = Math.max(0, Math.min(br.bottom, fr.bottom) - Math.max(br.top, fr.top));
        out.floatCover = Math.round(ox * oy / (br.width * br.height) * 100) / 100;
      }
    });
  }
  document.title = 'PROBE' + JSON.stringify(out);
})();
</script>
"""


def probe(path, chrome=None):
    """渲染探针：返回 dict；找不到浏览器或探针没跑出结果返回 None。"""
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


def _png_size(text, info):
    full = 'class="fullbleed"' in text
    st = info.get("stage") or {}
    h = st.get("h") or 1000
    w = st.get("w") or 1640
    return full, ((w, h) if full else (w + 64, h + 96))   # 画布模式：body 左右 padding 32×2、上下留白


def _out_path(path, out=None):
    return out or str(Path(path).with_name(Path(path).stem + "@2x.png"))


def export_png(path, out=None):
    chrome = find_chrome()
    if not chrome:
        sys.stderr.write(NO_BROWSER + "\n")
        return 2
    text = Path(path).read_text(encoding="utf-8")
    full, (w, h) = _png_size(text, probe(path, chrome) or {})
    size = f"{w},{h}"
    bg = [] if full else ["--default-background-color=00000000"]
    out = _out_path(path, out)
    cmd = [chrome, "--headless", f"--screenshot={out}", f"--window-size={size}", "--force-device-scale-factor=2",
           "--hide-scrollbars", "--virtual-time-budget=3000", *bg, f"file://{os.path.abspath(path)}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not os.path.exists(out):
        sys.stderr.write(f"PNG 未生成：{r.stderr[-400:]}\n")
        return 1
    sys.stderr.write(f"已导出：{out}（{size} ×2）\n")
    return 0


def _load(pg, path):
    pg.goto(Path(path).resolve().as_uri(), wait_until="load")
    pg.evaluate("document.fonts ? document.fonts.ready.then(() => 1) : 1")
    pg.wait_for_timeout(150)


def export_batch(paths):
    """整批只起一次浏览器：每张图先量画布（同一段探针），再按量出的尺寸截 2x 图。没装 Playwright 时逐张走命令行。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return max((export_png(x) for x in paths), default=0)
    js = PROBE.strip().removeprefix("<script>").removesuffix("</script>")
    rc = 0
    with sync_playwright() as p:
        try:
            b = launch(p)
        except Exception as e:
            sys.stderr.write(f"浏览器起不来：{str(e)[:300]}\n{NO_BROWSER}\n")
            return 2
        for path in paths:
            text = Path(path).read_text(encoding="utf-8")
            pg = b.new_page(viewport={"width": 1704, "height": 1200})
            _load(pg, path)
            pg.add_script_tag(content=js)
            m = re.match(r"PROBE(.*)", pg.title(), re.S)
            pg.close()
            full, (w, h) = _png_size(text, json.loads(m.group(1)) if m else {})
            out = _out_path(path)
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
            _load(pg, path)
            pg.screenshot(path=out, omit_background=not full)
            pg.close()
            if os.path.exists(out):
                sys.stderr.write(f"已导出：{out}（{w},{h} ×2）\n")
            else:
                sys.stderr.write(f"PNG 未生成：{path}\n")
                rc = 1
        b.close()
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.out and len(a.files) > 1:
        ap.error("--out 只能配一张图")
    if a.probe:
        r = probe(a.files[0])
        if r is None:
            sys.stderr.write("渲染探针没跑出结果：" + (NO_BROWSER if not find_chrome() else "页面加载失败") + "\n")
            return 2
        print(json.dumps(r, ensure_ascii=False))
        return 0
    if a.png:
        return export_png(a.files[0], a.out) if a.out else export_batch(a.files)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
