# 导出 PNG（只在用户或报告明确要时读）

默认交付物是单文件 HTML，本页只管"要图片文件"的情况。

## PNG

```bash
python3 <skill>/scripts/export.py "{客户或项目名}/图名.html" --png      # 同目录出 图名@2x.png
python3 <skill>/scripts/export.py "{客户或项目名}/图名.html" --png --out figures/图名@2x.png
python3 <skill>/scripts/export.py "{客户或项目名}/"*.html --png         # 批量，每张出在各自同目录；--out 只能配一张
```

- 脚本自己量画布高度（渲染探针），营销类透明底、`1704×(高+96)`，产品设计类边到边 `1640×高`，都是 2 倍图。
- 装了 Playwright 时，批量和单张导出都用 Playwright 起浏览器，整批只起一次；它自带的 Chromium 起不来就改用下面探测到的浏览器。没装 Playwright 时逐张走 Chrome 命令行。
- 浏览器探测顺序：`CHROME_BIN` → Playwright 自己报告的 Chromium 路径 → Playwright 缓存目录（`PLAYWRIGHT_BROWSERS_PATH` 或默认位置，新旧两种目录结构都认）→ PATH 里的 chromium / chromium-browser / google-chrome / chrome / chrome-headless-shell → macOS 本机 Chrome。找不到就报错退出，设 `CHROME_BIN` 后重跑。

## 渲染探针（check.py 的渲染检查用）

```bash
python3 <skill>/scripts/export.py "{客户或项目名}/图名.html" --probe   # JSON：画布尺寸、空隙、裁切、浮层出界、并排不齐
```

`check.py` 默认调它，`--no-render` 关；探针没跑出结果时 check.py 报 Blocker `render-failed`。
