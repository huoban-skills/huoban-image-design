# huoban-image-design

生成伙伴云系统界面示意图。产出单文件 HTML 源 ＋ 2x PNG，画面忠于真实产品组件。

给客户讲方案时需要一张"系统长什么样"的图，手绘不像、真去搭一遍太慢、截图又没有客户的业务数据。这个 skill 用真实产品实测出的组件结构拼装示意图，看起来就是伙伴云本身，但里面跑的是客户自己的字段和数据。

## 两种产出

| | 产品设计类 | 营销类 |
|---|---|---|
| 用途 | 用户照着在平台里搭建 | 放进报告、给客户讲解 |
| 画面 | 纯界面，撑满窗口 | 底层界面＋浮层补充说明 |
| 约束 | 每个元素都必须能在伙伴云搭出来 | 浮层只能补充底层没有的内容，不复制放大 |

## 用法

直接说要画什么即可，skill 会依次和你确认皮肤、用途、图需求单，然后拼装、渲染自检、导出。

```
画一张排产工作台的界面示意图
给这个方案配一张订单列表页的图，营销版
```

产出物落在当前工作目录：`图名@2x.png` 在外，源稿进 `源文件/图名.html`。PNG 给人看和嵌报告，HTML 是可再导出的源稿。

## 架构

三层分离，改一层不影响另两层：

```
结构（PC 端真实产品 DOM 实测） assets/c1-shell.html       产品壳、顶栏、导航
                              assets/c2-table-form.html  表格、字段、表单、业务视图
                              assets/c3-page-detail.html 详情页、弹窗、工作台部件、门户
结构（手机端 H5 真实 DOM 实测）  assets/c4-mobile.html      手机壳、三槽卡片、记录页、流程任务、工作台、企微会话
结构（数据大屏，三类大屏页实测） assets/c5-screen.html      深色画布、标题条、指标框、图表卡、装饰框、中央视觉位
        ↓
骨架样式（尺寸布局，无颜色）   assets/base.css
        ↓
皮肤（纯色彩 token）          assets/skins/*.css         8 套
```

配套：`assets/screens/`（四张 SVG 大屏背景，build.py 按 bg-* 类注入）、`assets/icons.svg`（图标雪碧图）、`assets/fit.js`（画布自适应）、`scripts/extract_templates.py`（按需提取结构模板）、`scripts/expand.py`（把片段里的 `<hb-*>` 宏展开成组件 HTML；`--list` 看目录、`--doc 宏名` 按需取语法，`references/macros.md` 是 `--doc all` 生成的全文）、`scripts/build.py`（确定性组装单文件 HTML，组装前自动展开宏）、`scripts/check.py`（静态检查）。

## 皮肤

8 套，分两组：**报告同名皮肤** 6 套（与 huoban-solution-report 的皮肤同名同气质）＋ **功能皮肤** 2 套（产品原生蓝、科技暗黑）。行业分工表在 `references/skin/routing.md`，清单以 `assets/skins/` 目录为准。

客户有品牌色时可现造一套：复制原生蓝改 6 个主色 token 即可，中性系和状态色语义不动。取色深浅关系按 `references/skin/custom-skin.md` 里的 Radix 12 级尺子。

与 huoban-solution-report 的报告皮肤**同名同气质**——报告选定皮肤后，配图用同名皮肤，两者自动同色系。

## 三条硬约束

- **不自造组件**。伙伴云没有的控件、布局、交互形态一律不画。
- **尺寸是实测的**。顶栏 56、侧栏 248、行高 35、标签 20 这些值来自真实产品，改了就不像了。
- **颜色不写死**。一律走 CSS 变量，写死十六进制会导致换皮肤时那块不跟着变。`check.py` 把这条列为 Blocker。

## 检查

```bash
python3 scripts/check.py 图.html
```

零依赖静态检查，分级报告：写死色值（Blocker）、用了不存在的组件（High）、本图独有的一次性类（Nit）、SVG 导出前置条件（Medium）。Blocker 清零才能交付。

对齐和观感仍需看渲染截图，检查清单在 `references/canvas/verify-export.md`。

## 文档

- `references/macros.md` — 宏语法全文（由 expand.py 生成，出图时按需 `--doc` 取，不整读）
- `references/canvas/` — 画布规范（按用途分产品设计/营销）、验证与导出、SVG 嵌报告
- `references/skin/` — 皮肤选型（routing）与制作（custom-skin）
- `references/principles/` — 设计判据（视觉四原则、交互三原则、看板数据故事、图表选型、防千篇一律等 8 份）
- `CHANGELOG/` — 版本记录，一个版本一份
