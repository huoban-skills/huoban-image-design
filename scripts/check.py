#!/usr/bin/env python3
"""界面示意图产出物检查。纯标准库；空隙检查会调一次本机 Chrome，没有就自动跳过。

用法：
    python3 scripts/check.py 图.html            # 人读的分级报告
    python3 scripts/check.py 图.html --json     # 机读
    python3 scripts/check.py 图.html --no-render  # 只跑文本检查，不启动浏览器

检查的是"该由机器判定、肉眼容易漏"的项：色值有没有写死、有没有用不存在的
组件类、导出前置条件、几条踩过坑的结构禁令，以及渲染后组件有没有留下大片
空白。剩下的对齐与观感仍然要自己看截图，见 references/canvas/verify-export.md 的验证清单。

退出码：有 Blocker 返回 1，其余返回 0。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"

# 允许写死颜色的地方：皮肤文件自己定义 token，以及 #fff 这种中性值
HEX = re.compile(r'#[0-9A-Fa-f]{3,8}\b')
RGB = re.compile(r'\brgba?\(')
ALLOW_LITERAL = {"#fff", "#ffffff", "#000", "#000000"}


def load_known_classes():
    """base.css 里定义过的 class，作为"组件是否存在"的判据。"""
    css = (ASSETS / "base.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return set(re.findall(r"\.([A-Za-z][\w-]*)", css))


def load_known_icons():
    svg = (ASSETS / "icons.svg").read_text(encoding="utf-8")
    return set(re.findall(r'<symbol id="i-([\w-]+)"', svg))


def split_doc(text):
    """拆成 <style> 段和 body 段：style 里出现色值是正常的，body 里不是。"""
    styles = re.findall(r"<style[^>]*>(.*?)</style>", text, flags=re.S)
    body = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.S)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    return "\n".join(styles), body


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


# 国内环境 npmmirror 镜像比 Google CDN 快，按序尝试，最后官方兜底
CHS_PATH = "152.0.7977.54/linux64/chrome-headless-shell-linux64.zip"
CHS_URLS = (
    "https://registry.npmmirror.com/-/binary/chrome-for-testing/" + CHS_PATH,
    "https://cdn.npmmirror.com/binaries/chrome-for-testing/" + CHS_PATH,
    "https://storage.googleapis.com/chrome-for-testing-public/" + CHS_PATH,
)


def _download_chrome():
    """Linux 下按 CHS_URLS 顺序下载 chrome-headless-shell 到 ~（约 120MB，会话内缓存复用），
    成功返回二进制路径。详见 references/chrome-env.md。"""
    if not sys.platform.startswith("linux"):
        return None
    import pathlib
    import urllib.request
    import zipfile
    dest = pathlib.Path(os.path.expanduser("~/chrome-headless-shell-linux64"))
    binp = dest / "chrome-headless-shell"
    tmpzip = pathlib.Path(tempfile.mkdtemp()) / "chs.zip"
    for url in CHS_URLS:
        try:
            urllib.request.urlretrieve(url, tmpzip)
            break
        except Exception:
            continue
    else:
        return None
    with zipfile.ZipFile(tmpzip) as z:
        z.extractall(dest.parent)
    tmpzip.unlink()
    for root, _, files in os.walk(dest):
        for f in files:
            os.chmod(os.path.join(root, f), 0o755)
    return str(binp) if binp.exists() else None


def find_chrome():
    """按顺序找可用 Chrome；Linux 上都没有时自动从 CDN 下载；
    仍找不到返回 None（渲染类检查自动跳过）。"""
    import shutil
    cands = [
        os.environ.get("CHROME_BIN"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "chrome-headless-shell-linux64/chrome-headless-shell",
        "work/chrome-headless-shell-linux64/chrome-headless-shell",
        os.path.expanduser("~/chrome-headless-shell-linux64/chrome-headless-shell"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    for name in ("chrome-headless-shell", "google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    try:
        return _download_chrome()
    except Exception:
        return None


CHROME = find_chrome()

# 渲染后量空隙：内容没填满容器时画面上会出现空洞，静态文本看不出来。
# 注入到图的副本里跑一遍，结果写进 <title>，再用 --dump-dom 取回。
PROBE = r"""
<script>
(function () {
  var BOTTOM = 48, RIGHT = 120;
  // 只查布局层（组件之间、组件到画布边缘）。组件内部的留白由数据量决定（图片格、
  // 列表行数、卡片字段多少），不是病，一律跳过；画布/窗口/浮层/导航按设计留边也跳过。
  var SKIP = /\b(stage|window|float|side|tree|win-body|main|callout|hscroll|kanban-group|kanban-columns|w-card|comp|widget|kanban-item|record-card|field|f-value|modal|grid|page-header)\b/;
  document.querySelectorAll('.stage').forEach(function (s) { s.style.zoom = 1; });
  var out = [];
  document.querySelectorAll('*').forEach(function (e) {
    var cls = typeof e.className === 'string' ? e.className : '';
    if (SKIP.test(cls) || !e.children.length) return;
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
    var hit = { cls: cls.slice(0, 44) || e.tagName.toLowerCase(),
                box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] };
    if (gapB > BOTTOM) hit.bottom = gapB;
    if (gapR > RIGHT && r.width > 500) hit.right = gapR;
    if (hit.bottom || hit.right) out.push(hit);
  });
  // 父子同时留空时只报最外层，免得一处空白刷十条
  out = out.filter(function (a) {
    return !out.some(function (b) {
      return b !== a
        && b.box[1] <= a.box[1] && b.box[1] + b.box[3] >= a.box[1] + a.box[3]
        && b.box[0] <= a.box[0] && b.box[0] + b.box[2] >= a.box[0] + a.box[2]
        && Math.abs((b.bottom || 0) - (a.bottom || 0)) < 8;
    });
  });
  // 并排组件底部不齐：同一栅格行里两栏高度差过大，短的那栏下方会空出一块。
  // 这一项 SKIP 名单管不着——空白不在组件内部，而在组件之间，靠目检容易被“左右等高很整齐”的错觉盖过去。
  var uneven = [];
  document.querySelectorAll('.item-page-grid, .value, .pains, .phase').forEach(function (g) {
    var rows = {};
    [].forEach.call(g.children, function (c) {
      var r = c.getBoundingClientRect();
      if (r.height === 0) return;
      var k = Math.round(r.top / 5);
      (rows[k] = rows[k] || []).push({
        cls: (typeof c.className === 'string' ? c.className : c.tagName.toLowerCase()).slice(0, 40),
        h: Math.round(r.height), bottom: Math.round(r.bottom)
      });
    });
    Object.keys(rows).forEach(function (k) {
      var arr = rows[k];
      if (arr.length < 2) return;
      arr.sort(function (a, b) { return a.bottom - b.bottom; });
      var d = arr[arr.length - 1].bottom - arr[0].bottom;
      if (d > 24) uneven.push({ diff: d, short: arr[0].cls, shortH: arr[0].h,
                                tall: arr[arr.length - 1].cls, tallH: arr[arr.length - 1].h });
    });
  });

  var extra = [];
  var win = document.querySelector('.window'), st = document.querySelector('.stage');
  if (win && win.scrollHeight > win.clientHeight + 4)
    extra.push({ kind: 'clipped', over: win.scrollHeight - win.clientHeight });
  if (st) {
    var sr = st.getBoundingClientRect();
    document.querySelectorAll('.float').forEach(function (fl) {
      var fr = fl.getBoundingClientRect();
      if (fr.bottom > sr.bottom + 2) extra.push({ kind: 'float-out', over: Math.round(fr.bottom - sr.bottom) });
      if (fr.top < sr.top - 2) extra.push({ kind: 'float-out', over: Math.round(sr.top - fr.top) });
    });
  }
  document.title = 'GAPS' + JSON.stringify({ gaps: out, extra: extra, uneven: uneven });
})();
</script>
"""


def measure_gaps(path, text):
    """返回空隙列表；Chrome 不可用或页面没跑起来时返回 None。"""
    if not CHROME:
        return None
    m = re.search(r"\.stage \{ height: (\d+)px", text)
    height = int(m.group(1)) + 96 if m else 1200
    d = os.path.dirname(os.path.abspath(path))
    tmp = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir=d, encoding="utf-8")
    tmp.write(text + PROBE)
    tmp.close()
    try:
        r = subprocess.run([CHROME, "--headless", "--dump-dom", "--virtual-time-budget=3000",
                            f"--window-size=1704,{height}", "--hide-scrollbars", tmp.name],
                           capture_output=True, text=True, timeout=90)
        m = re.search(r"<title>GAPS(.*?)</title>", r.stdout, re.S)
        return json.loads(m.group(1)) if m else None
    except Exception:
        return None
    finally:
        os.unlink(tmp.name)


def check(path, render=True):
    text = Path(path).read_text(encoding="utf-8")
    styles, body = split_doc(text)
    findings = []

    def add(level, rule, msg, line=None):
        findings.append({"level": level, "rule": rule, "msg": msg, "line": line})

    # ── Blocker：色值写死 ───────────────────────────────────────────
    # body 里的 fill/stroke/color/background 属性值
    for m in re.finditer(r'(?:fill|stroke|stop-color)="([^"]+)"', body):
        v = m.group(1).strip()
        if v.lower() in ALLOW_LITERAL or v in ("none", "currentColor") or v.startswith("url("):
            continue
        if HEX.match(v) or RGB.match(v):
            add("Blocker", "hardcoded-color",
                f'SVG 属性写死颜色 {v}，应改 var(--...)；换皮肤时这里不会跟着变', line_of(body, m.start()))
    # body 里 style="" 中的颜色
    for m in re.finditer(r'style="([^"]*)"', body):
        for cm in re.finditer(r"(?:background|color|fill|stroke|border)[^;:]*:\s*([^;\"]+)", m.group(1)):
            v = cm.group(1).strip()
            if v.lower() in ALLOW_LITERAL or v.startswith("var(") or v.startswith("url("):
                continue
            if HEX.search(v) or RGB.search(v):
                add("Blocker", "hardcoded-color",
                    f'行内 style 写死颜色 {v}，应改 var(--...)', line_of(body, m.start()))
    # 本图补充样式段（最后一个 style 块）里的裸色值
    tail = styles.split("/* ── 本图布局 ── */")[-1] if "/* ── 本图布局 ── */" in styles else ""
    for m in re.finditer(r"(?:background|color|fill|stroke)\s*:\s*([^;{}]+)", tail):
        v = m.group(1).strip()
        if v.lower() in ALLOW_LITERAL or "var(" in v or v.startswith("url("):
            continue
        if HEX.search(v) or RGB.search(v):
            add("High", "hardcoded-color",
                f'本图补充样式里写死颜色 {v}；确属一次性微调可忽略，否则应加进皮肤 token')

    # ── 组件存在性：base.css 有 / 只在本图样式里有 / 哪都没有 ──────
    known = load_known_classes()
    local = set(re.findall(r"\.([A-Za-z][\w-]*)", styles))
    used = set()
    for m in re.finditer(r'class="([^"]+)"', body):
        used.update(c for c in m.group(1).split() if c)
    for c in sorted(used):
        if c.startswith(("i-", "sw-", "c-", "tint-", "bg-")) or c in known:
            continue
        if c in local:
            add("Nit", "local-only-class",
                f'.{c} 只在本图补充样式里定义：一次性布局可以，但若多张图都要用应沉淀进 base.css')
        else:
            add("High", "unknown-component",
                f'.{c} 在 base.css 和本图样式里都没有定义：自造组件（违反硬约束）或漏写样式')

    # ── High：引用了不存在的图标 ───────────────────────────────────
    icons = load_known_icons()
    for m in re.finditer(r'<use href="#i-([\w-]+)"', body):
        if m.group(1) not in icons:
            add("High", "unknown-icon",
                f'#i-{m.group(1)} 不在 icons.svg 里', line_of(body, m.start()))
    if "<use href=" in body and 'id="i-' not in text:
        add("Blocker", "missing-sprite",
            "用了 <use> 但没把 assets/icons.svg 拼进文件，图标会全部空白")

    # ── SVG 导出前置条件（嵌报告时必踩；导出脚本会统一补，这里聚合提示） ──
    n_noxmlns = len(re.findall(r"<svg(?![^>]*xmlns)[^>]*>", body))
    if n_noxmlns:
        add("Medium", "svg-no-xmlns",
            f"{n_noxmlns} 处内嵌 <svg> 缺 xmlns：出 PNG 无影响；走 SVG/foreignObject 嵌报告前须按 canvas/report-embed.md 统一补齐")
    n_br = len(re.findall(r"<br\s*>", body))
    if n_br:
        add("Medium", "br-not-closed",
            f"{n_br} 处 <br> 未自闭合：嵌报告导出前须转 <br/>（foreignObject 是 XML）")

    # ── Medium：结构禁令（踩过的坑） ───────────────────────────────
    if re.search(r'class="[^"]*\bico\b[^"]*"[^>]*>\s*<path', body):
        add("Medium", "inline-icon-path",
            "图标仍在内联 path，应改 <use href=\"#i-...\"/>（图标清单以 assets/icons.svg 为准）")
    if "■" in body or "●" in body:
        add("Medium", "legend-char",
            "图例用了 ■/● 字符：字符只能着文字色，无法与系列色一致，应改 <rect>/<circle>")
    if re.search(r'class="[^"]*\bstage\b', body) and "class=\"window\"" in body:
        if not re.search(r"\.stage\s*\{[^}]*height", "\n".join([styles])):
            add("High", "stage-no-height",
                ".stage 没设 height：画布高度必须按渲染实测回填，否则导出会截断或留白")

    # ── Medium：渲染后组件留下大片空白 ─────────────────────────────
    if render:
        r = measure_gaps(path, text)
        gaps = (r or {}).get("gaps", [])
        for e in (r or {}).get("extra", []):
            if e["kind"] == "clipped":
                add("High", "content-clipped",
                    f"窗口内容比窗口高 {e['over']}px，底部被裁掉：整图观感偏下。把 .stage 高度按内容实高回填")
            else:
                add("High", "float-out",
                    f"浮层探出画布 {e['over']}px：会被导出裁掉或压住窗口边缘。调浮层 top 或加高 .stage")
        for u in (r or {}).get("uneven", []):
            add("Medium", "column-uneven",
                f"并排组件底部不齐：.{u['short']} 高 {u['shortH']}，.{u['tall']} 高 {u['tallH']}，"
                f"相差 {u['diff']}px。短的那栏下方会空出一块，"
                "给短栏补数据行（分组行、明细行）或调整两栏栅格宽度")
        if gaps:
            for g in gaps:
                part = []
                if g.get("bottom"):
                    part.append(f"底部空 {g['bottom']}px")
                if g.get("right"):
                    part.append(f"右侧空 {g['right']}px")
                x, y, w, h = g["box"]
                add("Medium", "empty-gap",
                    f".{g['cls']} {'，'.join(part)}（{w}×{h}，位置 x{x} y{y}）："
                    "内容没填满容器，画面上会看到空洞。补内容或把容器高度收到贴合")

    # ── 汇总 ───────────────────────────────────────────────────────
    order = {"Blocker": 0, "High": 1, "Medium": 2, "Nit": 3}
    findings.sort(key=lambda f: (order[f["level"]], f["rule"], f["line"] or 0))
    return findings


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        print(__doc__)
        return 2
    findings = check(args[0], render="--no-render" not in sys.argv)
    if as_json:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    else:
        if not findings:
            print("✓ 检查通过（颜色 token、组件存在性、导出前置、结构禁令、空隙）")
            print("  注意：对齐与观感仍需看截图，见 canvas/verify-export.md 验证清单")
        else:
            counts = {}
            for f in findings:
                counts[f["level"]] = counts.get(f["level"], 0) + 1
            print("　".join(f"{k} {v}" for k, v in counts.items()))
            print()
            for f in findings:
                loc = f"  第{f['line']}行" if f["line"] else ""
                print(f"[{f['level']}] {f['rule']}{loc}\n    {f['msg']}")
    return 1 if any(f["level"] == "Blocker" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
