# 导出 PNG（只在用户或报告明确要时读）

默认交付物是单文件 HTML，本页只管"要图片文件"的情况。

## PNG

```bash
python3 <skill>/scripts/export.py "{客户或项目名}/图名.html" --png      # 同目录出 图名@2x.png
python3 <skill>/scripts/export.py "{客户或项目名}/图名.html" --png --out figures/图名@2x.png
python3 <skill>/scripts/export.py "{客户或项目名}/"*.html --png         # 批量，每张出在各自同目录；--out 只能配一张
```

- 脚本自己量画布高度（渲染探针），营销类透明底、`1704×(高+96)`，产品设计类边到边 `1640×高`，都是 2 倍图。
- 营销类导出后按透明边界裁边，四周留 40 像素，投影保留；演示尺寸只裁上下、左右保留整图宽度，每页图放进演示稿后窗口一样大。`--no-trim` 不裁。裁边要 Pillow，没装就不裁。
- 装了 Playwright 时，批量和单张导出都用 Playwright 起浏览器，整批只起一次；它自带的 Chromium 起不来就改用下面探测到的浏览器。没装 Playwright 时逐张走 Chrome 命令行。
- 浏览器探测顺序：`CHROME_BIN` → Playwright 自己报告的 Chromium 路径 → Playwright 缓存目录（`PLAYWRIGHT_BROWSERS_PATH` 或默认位置，新旧两种目录结构都认）→ PATH 里的 chromium / chromium-browser / google-chrome / chrome / chrome-headless-shell → macOS 本机 Chrome。找不到就报错退出，设 `CHROME_BIN` 后重跑。

## 分层导出（方案演示稿点图放大用）

```bash
python3 <skill>/scripts/export.py "{客户或项目名}/"*.html --png --layers
```

合成图之外，每张带浮层的图另出几张完整单图和一份位置清单，和合成图放在同一目录：

| 文件 | 内容 |
| --- | --- |
| `NN-图名@2x.png` | 合成图（裁边后） |
| `NN-图名@2x.base.png` | 只有底图，浮层全部隐藏，底图保持合成图里的宽度；方案演示稿封面要的「去浮层底图」也用它 |
| `NN-图名@2x.float-1.png`、`float-2.png` | 每个浮层一张，只留这一块、透明底，倾斜和投影原样保留；按叠放顺序从下往上编号 |
| `NN-图名.layers.json` | 位置清单 |

```json
{"composite": "NN-图名@2x.png", "w": 3200, "h": 2100,
 "layers": [{"id": "base", "file": "NN-图名@2x.base.png", "box": [0, 0, 85.4, 78.1]},
            {"id": "float-1", "file": "NN-图名@2x.float-1.png", "box": [60.2, 48.5, 39.8, 51.5],
             "at": "right", "kind": "phone", "tilt": 3}]}
```

- `w`、`h` 是合成图像素；`box` 是 [左, 上, 宽, 高]，相对合成图的百分比，按裁边后的坐标算；斜放的浮层给外接框（含投影）。
- `layers` 从底到顶，底图在第一个；`at` 取 left／right，`kind` 取 phone（手机单屏）或 pc，`tilt` 是度数。
- 每张单图按自己的透明边界裁边，四周留 40 像素。没有浮层的图不分层，全屏产品图不分层。
- 要 Playwright 和 Pillow，缺哪个脚本会直接说。

## 渲染探针（check.py 的渲染检查用）

```bash
python3 <skill>/scripts/export.py "{客户或项目名}/图名.html" --probe   # JSON：画布尺寸、空隙、裁切、浮层出界、并排不齐
```

`check.py` 默认调它，`--no-render` 关；探针没跑出结果时 check.py 报 Blocker `render-failed`。
