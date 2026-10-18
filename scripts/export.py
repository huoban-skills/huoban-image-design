#!/usr/bin/env python3
"""可选导出：PNG（要 Chrome）、渲染探针（给 check.py 的渲染检查用）。

用法：
    python3 <skill>/scripts/export.py 图.html --png                 # 出 图@2x.png（同目录）
    python3 <skill>/scripts/export.py 图.html --png --out 路径.png
    python3 <skill>/scripts/export.py 配图/*.html --png             # 批量：装了 Playwright 时整批只起一次浏览器
    python3 <skill>/scripts/export.py 配图/*.html --png --layers    # 另出底图、各浮层单图和 图名.layers.json（方案演示稿点图放大用）
    python3 <skill>/scripts/export.py 图.html --probe               # 渲染探针 JSON（空隙、裁切、浮层出界、并排不齐）

默认交付物是 HTML，本脚本只在用户或报告明确要 PNG 时用。营销画布的 PNG 默认按透明边界裁边、四周留 40 像素（--no-trim 不裁）。
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
    if (e.closest('.dlg, .dlg-print')) return;   // 交互界面跟着窗口高，表格和纸张下方留白是真实样子
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
    out.floatBoxes = []; out.floatCover = 0;
    document.querySelectorAll('.mk-float').forEach(function (fl) {
      // 浮层本身的宽高（斜放不算外接框）；出界和遮挡按外接框量
      var fr = fl.getBoundingClientRect();
      out.floatBoxes.push({ w: fl.offsetWidth, h: fl.offsetHeight, phone: fl.classList.contains('mk-float-phone'), dlg: fl.classList.contains('mk-float-dlg') });
      if (fr.bottom > sr.bottom + 2) out.extra.push({ kind: 'float-out', over: Math.round(fr.bottom - sr.bottom) });
      if (fr.top < sr.top - 2) out.extra.push({ kind: 'float-out', over: Math.round(sr.top - fr.top) });
      if (fr.right > sr.right + 2) out.extra.push({ kind: 'float-out', over: Math.round(fr.right - sr.right) });
      if (fr.left < sr.left - 2) out.extra.push({ kind: 'float-out', over: Math.round(sr.left - fr.left) });
      var base = st.querySelector('.window, .item-page');
      if (base) {
        var br = base.getBoundingClientRect();
        var ox = Math.max(0, Math.min(br.right, fr.right) - Math.max(br.left, fr.left));
        var oy = Math.max(0, Math.min(br.bottom, fr.bottom) - Math.max(br.top, fr.top));
        out.floatCover = Math.round((out.floatCover + ox * oy / (br.width * br.height)) * 100) / 100;   // 两个浮层合计
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


TRIM_MARGIN = 40      # 裁边后四周留的透明边（PNG 像素）
ALPHA_MIN = 8         # 透明度低于这个算空白：投影最外圈的极淡像素不算进图里


def _alpha_box(png, margin=TRIM_MARGIN, keep_width=False):
    """按透明边界算出要保留的区域（含四周留边）；没装 Pillow 或整张透明时返回 None。
    keep_width：只裁上下、左右保留整图宽度（演示尺寸每页图一样宽，放进 PPT 后窗口大小一致）。"""
    try:
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(png).convert("RGBA")
    bb = im.getchannel("A").point(lambda v: 255 if v > ALPHA_MIN else 0).getbbox()
    if not bb:
        return None
    w, h = im.size
    if keep_width:
        return (0, max(0, bb[1] - margin), w, min(h, bb[3] + margin))
    return (max(0, bb[0] - margin), max(0, bb[1] - margin), min(w, bb[2] + margin), min(h, bb[3] + margin))


def _is_slide(text):
    return bool(re.search(r'class="stage[^"]*\bslide\b', text))


def _crop(png, box, dst=None):
    from PIL import Image
    Image.open(png).crop(box).save(dst or png)


def trim(png, keep_width=False):
    """营销画布导出后按透明边界裁边，四周留 TRIM_MARGIN（演示尺寸只裁上下）；返回裁剪框（裁前坐标），没裁返回 None。"""
    box = _alpha_box(png, keep_width=keep_width)
    if box:
        _crop(png, box)
    return box


# 分层导出（--layers）：合成图之外，底图、每个浮层各出一张完整单图，再写位置清单 layers.json，供演示稿点哪块放大哪块
LAYER_JS = r"""(mode) => {
  const st = document.querySelector('.stage');
  const base = st.querySelectorAll('.window, .item-page');
  const fl = [...st.querySelectorAll('.stage-body > .mk-float')];
  const show = (els, on) => els.forEach(e => e.style.visibility = on ? '' : 'hidden');
  if (mode === 'all') { show([...base], true); show(fl, true); return fl.length; }
  if (mode === 'base') { show([...base], true); show(fl, false); return 0; }
  const i = +mode; show([...base], false); fl.forEach((e, k) => show([e], k === i));
  const f = fl[i], m = (f.getAttribute('style') || '').match(/--float-tilt:\s*(-?[\d.]+)deg/);
  return { at: f.classList.contains('at-l') ? 'left' : 'right', kind: f.classList.contains('mk-float-phone') ? 'phone' : 'pc',
           tilt: m ? +m[1] : 0 };
}"""


def _layers(pg, out, comp_box, omit):
    """在已加载好的页面上逐层截图：只留这一层可见，按它自己的透明边界裁边；box 换算成在合成图上的百分比。"""
    stem = out[:-len(".png")] if out.endswith(".png") else out
    cw, ch = comp_box[2] - comp_box[0], comp_box[3] - comp_box[1]
    n = pg.evaluate(LAYER_JS, "all")
    plan = [("base", "base", None)] + [(f"float-{i + 1}", str(i), i) for i in range(n)]
    layers = []
    for lid, mode, _ in plan:
        meta = pg.evaluate(LAYER_JS, mode)
        f = f"{stem}.{lid}.png"
        pg.screenshot(path=f, omit_background=omit)
        box = _alpha_box(f)
        if not box:
            os.unlink(f)
            continue
        _crop(f, box)
        # 单图在合成图上的位置：两张图来自同一个视口，减去合成图的裁剪原点即可
        x, y = box[0] - comp_box[0], box[1] - comp_box[1]
        item = {"id": lid, "file": Path(f).name,
                "box": [round(x / cw * 100, 2), round(y / ch * 100, 2),
                        round((box[2] - box[0]) / cw * 100, 2), round((box[3] - box[1]) / ch * 100, 2)]}
        if isinstance(meta, dict):
            item.update(meta)
        layers.append(item)
    pg.evaluate(LAYER_JS, "all")
    stem_name = Path(out).name
    stem_name = stem_name[:-len("@2x.png")] if stem_name.endswith("@2x.png") else Path(out).stem
    doc = {"composite": Path(out).name, "w": cw, "h": ch, "layers": layers}
    jp = Path(out).with_name(stem_name + ".layers.json")
    jp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return jp


def export_png(path, out=None, trim_ok=True):
    chrome = find_chrome()
    if not chrome:
        sys.stderr.write(NO_BROWSER + "\n")
        return 2
    text = Path(path).read_text(encoding="utf-8")
    full, (w, h) = _png_size(text, probe(path, chrome) or {})
    if not full:
        h += 160          # 命令行无头模式的视口比 --window-size 矮约 90，偏高的图底部会被截掉；多留的透明边随后裁掉
    size = f"{w},{h}"
    bg = [] if full else ["--default-background-color=00000000"]
    out = _out_path(path, out)
    cmd = [chrome, "--headless", f"--screenshot={out}", f"--window-size={size}", "--force-device-scale-factor=2",
           "--hide-scrollbars", "--virtual-time-budget=3000", *bg, f"file://{os.path.abspath(path)}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not os.path.exists(out):
        sys.stderr.write(f"PNG 未生成：{r.stderr[-400:]}\n")
        return 1
    if trim_ok and not full:
        trim(out, _is_slide(text))
    sys.stderr.write(f"已导出：{out}（{size} ×2）\n")
    return 0


def _load(pg, path):
    pg.goto(Path(path).resolve().as_uri(), wait_until="load")
    pg.evaluate("document.fonts ? document.fonts.ready.then(() => 1) : 1")
    pg.wait_for_timeout(150)


def export_batch(paths, out=None, trim_ok=True, layers=False):
    """整批只起一次浏览器：每张图先量画布（同一段探针），再按量出的尺寸截 2x 图。没装 Playwright 时逐张走命令行。
    营销画布默认按透明边界裁边；layers=True 时另出底图、各浮层单图和 layers.json。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if layers:
            sys.stderr.write("--layers 要用 Playwright：pip install playwright 后重跑\n")
            return 2
        return max((export_png(x, out, trim_ok) for x in paths), default=0)
    if layers:
        try:
            import PIL  # noqa: F401
        except ImportError:
            sys.stderr.write("--layers 要用 Pillow 量每一层的边界：pip install pillow 后重跑\n")
            return 2
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
            dst = _out_path(path, out)
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
            _load(pg, path)
            pg.screenshot(path=dst, omit_background=not full)
            if not os.path.exists(dst):
                pg.close()
                sys.stderr.write(f"PNG 未生成：{path}\n")
                rc = 1
                continue
            box = None
            if not full and (trim_ok or layers):
                keep = _is_slide(text)
                box = _alpha_box(dst, keep_width=keep) if layers else trim(dst, keep)
            note = ""
            if layers and box and 'class="mk-float' in text:
                jp = _layers(pg, dst, box, not full)
                _crop(dst, box)
                note = f"；分层 {jp.name}"
            elif layers and box:
                _crop(dst, box)
                note = "；没有浮层，不分层"
            elif layers:
                note = "；全屏产品图不分层"
            pg.close()
            sys.stderr.write(f"已导出：{dst}（{w},{h} ×2{'，已裁边' if box else ''}{note}）\n")
        b.close()
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--png", action="store_true")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--no-trim", action="store_true", help="营销画布导出后不按透明边界裁边")
    ap.add_argument("--layers", action="store_true", help="另出底图、各浮层单图和位置清单 图名.layers.json（方案演示稿点图放大用）")
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
        return export_batch(a.files, a.out, not a.no_trim, a.layers)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
