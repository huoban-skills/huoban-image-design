# huoban-image-design

生成伙伴云系统界面示意图。产出单文件 HTML（默认交付）；PNG／SVG 按需导出。画面忠于真实产品组件，里面跑的是客户自己的字段和数据。

给客户讲方案时需要一张"系统长什么样"的图，手绘不像、真去搭一遍太慢、截图又没有客户的业务数据。这个 skill 用真实产品实测出的组件结构，通过骨架宏拼装示意图。

## 两种产出

| | 产品设计类 | 营销类 |
|---|---|---|
| 用途 | 用户照着在平台里搭建 | 放进报告、给客户讲解 |
| 画面 | 纯界面，撑满窗口 | 底层界面＋浮层补充说明 |
| 约束 | 每个元素都必须能在伙伴云搭出来 | 浮层只能补充底层没有的内容，不复制放大 |

## 用法

直接说要画什么即可，skill 会依次和你确认皮肤、图需求单，然后写骨架片段、拼装、检查、验收、交付。

```
画一张排产工作台的界面示意图
给这个方案配一张订单列表页的图，营销版
```

交付物落在当前工作目录 `源文件/图名.html`；要图片时 `python3 scripts/export.py 图.html --png`（要 Chrome）或 `--svg`（不要）。

## 架构

```
登记表  assets/registry.json      官方部件 type ↔ 类名 ↔ 宏 ↔ 栅格默认尺寸 ↔ 采集状态（唯一名录，registry.py 校验）
结构    assets/c1-shell.html       产品壳、顶栏、导航            ┐
        assets/c2-table-form.html  表格、字段、表单、业务视图      │ 模板带 data-type（官方部件）
        assets/c3-page-detail.html 详情页、弹窗、工作台/看板部件   │ 与 data-measured（实测注释）
        assets/c4-mobile.html      手机端 H5                    │
        assets/c5-screen.html      数据大屏                     ┘
骨架样式 assets/base.css            尺寸布局，无颜色
皮肤    assets/skins/*.css         纯色彩 token，9 套
宏      scripts/expand.py          <hb-page> 页面骨架 ＋ 39 个组件宏；模型只填内容，外壳与栅格由脚本产出
```

配套脚本：`build.py`（组装单文件 HTML，自动展开宏、自动全屏、打印规模提示）、`check.py`（纯标准库静态检查；`--render` 有 Chrome 时加渲染检查；`--acceptance` 起草验收表）、`export.py`（PNG／SVG／渲染探针，不自动下载 Chrome）、`registry.py`（登记表校验与查询）、`extract_templates.py`（宏没覆盖的组件按名提取模板）、`migrate_classes.py`（1.x 类名迁到 2.0）。

## 皮肤

9 套：报告同名皮肤（与 huoban-solution-report 同名同气质）＋功能皮肤（产品原生蓝、科技暗黑）。选型在 `references/skin/routing.md`，清单以 `assets/skins/` 为准；客户有品牌色时按 `references/skin/custom-skin.md` 现造。

## 三条硬约束

- **不自造组件**：只画登记表里有的部件，未采集的先告知用户。
- **尺寸是实测的**：顶栏 56、侧栏 248、行高 35、标签 20 来自真实产品。
- **颜色不写死**：一律走皮肤 token，`check.py` 把写死色值列为 Blocker。

## 云端沙箱

只有 Python 标准库、没有 Chrome 也能跑完整流程：build → check（静态）→ 验收表 → 交付 HTML。渲染类检查与 PNG 明确标为"未执行"，不下载、不报错。

## 文档

- `references/principles/` — 五类页面各一篇原则（列表、表单、详情页、工作台、看板/大屏）＋组件选取＋通用原则；索引在其 README
- `references/canvas/` — 画布规范（营销/产品设计）、检查与验收、导出
- `references/skin/` — 皮肤选型与制作
- `references/macros.md` — 宏语法全文（由 `expand.py --doc all` 生成，出图时按需 `--page`／`--doc` 取，不整读）
- `references/measured/` — 实测记录
- `tests/` — 回归片段与基线（`scripts/regress.py`）
- `CHANGELOG/` — 版本记录
