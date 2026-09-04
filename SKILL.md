---
name: huoban-image-design
description: 生成伙伴云系统界面示意图，画面忠于伙伴云真实产品组件。当用户要画伙伴云界面示意图/mockup（列表页、详情页、表单、工作台、看板、门户、手机端），给报告/方案配系统图，或 huoban-solution-report 给出图需求单时，必须使用本 skill。不用于：海报/朋友圈营销图、流程图（hb-flowchart）、ER 图（hb-er-draw）、网站（hb-website-creator）。
---

# 伙伴云系统界面示意图

产出"长得像伙伴云产品"的界面示意图：拼装真实产品实测组件，不自由发挥。输入是出图需求或 huoban-solution-report 的图需求单；输出 `图名@2x.png` ＋ `源文件/图名.html`（可再导出的源稿）。只画伙伴云产品界面，海报/流程图/ER 图/网站不在本 skill。

核心资产三层：**结构**（assets/c1～c4 实测架构，唯一结构真相源）＋**骨架样式**（base.css，尺寸取自实测）＋**皮肤**（assets/skins/ 纯色彩 token，8 套）。

## 页面类型路由（唯一真相源）

**结构不整读 c 文件**：有宏的块直接写宏（`expand.py --list` 看目录、`--doc` 取语法），其余用脚本按名提取（先 `--list` 看目录，再精确取）：

```bash
python3 scripts/extract_templates.py assets/c3-page-detail.html \
  --architecture "独立自定义详情页" --component "记录功能区" --component "标题卡片"
```

| 用户说的 | 从哪几份提取 | 用哪个架构 |
| --- | --- | --- |
| 列表页（网格/卡片/看板/甘特/日历/任务/透视） | c1 ＋ c2 | 产品壳层 ＋ 列表页主内容 ＋ 对应视图 |
| 详情页 / 详情界面 | c3（带字段再加 c2 字段类组件） | 独立自定义详情页。不套产品壳与弹窗遮罩；顶部记录功能区默认包含 |
| 编辑态 / 标准表单 / 字段录入 | c1 ＋ c2 | 标准表单编辑态（仅用户明确要求时） |
| 弹窗详情 | c1 ＋ c3（widget 卡字段再加 c2 字段类组件） | 记录详情弹窗（仅用户明确要求时） |
| 工作台 / 看板页 / 数据分析页 | c1 ＋ c3 | 工作台或数据分析页 |
| 企业门户 | c1 ＋ c3 | 企业门户 |
| 手机端 | 只提 c4（2026-09-03 H5 实测；重复块优先用手机端宏） | 手机单屏/双屏对照。壳 375 宽即画布，不要 `.window`／左侧导航／一级顶栏；列表默认三槽卡片，记录页字段平铺（label 在上、值框 40 高），审批走流程任务列表＋任务办理页，没有审批流程条 |

提取出的 `<template>` 是独立架构或组件，不是整页范例——按 data-* 属性和结构注释识别用途。c1 的 `.main` 是页面内容插槽，把 c2/c3 的页面内部结构放进去，不再嵌套第二个 `.main`。

## 设计原则路由（步骤 4、5 按任务读，不整目录读）

| 任务类型 | 必读（references/principles/） | 条件读取 |
| --- | --- | --- |
| 所有界面 | visual-four-principles、visual-components | 无 |
| 多张营销配图 | 同上 | anti-sameness |
| 工作台 | 同上 | interaction-principles；涉及管理洞察再读 dashboard-data-story |
| 看板/数据分析页 | 同上＋dashboard-data-story、dashboard-chart-selection | anti-sameness |
| 表单/编辑态 | 同上＋interaction-principles | visual-layout |
| 自定义详情页 | 同上＋visual-layout | 有操作设计时读 interaction-principles |
| 新造或调整皮肤 | visual-color | 页面原则仍按页面类型读 |

## 执行步骤

### 1. 判输入，定样式

按 [references/skin/routing.md](references/skin/routing.md) 判定输入物、选皮肤、定壳层主题；仅在沿用已有样式提色值或新造皮肤时再读 [references/skin/custom-skin.md](references/skin/custom-skin.md)。

### 2. 判用途，定画布

问一句"这图用来干什么"，分两类，读对应那一份：

- **营销类**（放进报告／给客户讲解／宣传）→ [references/canvas/marketing.md](references/canvas/marketing.md)。
- **产品设计类**（用户照着搭建）→ [references/canvas/product-design.md](references/canvas/product-design.md)。

画布统一宽 **1640px**（`.stage`），高度按内容实测回填，禁止大片空白也禁止溢出；内容多时窗口高度截到主要内容展示完为止，底部被窗口边缘自然切断是正常的。

### 3. 确认图需求单

动工前和用户对齐（来自 huoban-solution-report 的调用也是这个格式）：

- **页面类型**（路由表的"用户说的"一列）与**端**：PC（默认）／手机端。手机端另确认屏数（单屏/双屏对照）、要不要企微会话那一屏；手机竖图嵌进报告时要限宽居中（约 360px），否则会被版心拉得巨大。
- **要呈现的字段和数据**：用用户业务的真实字段名，数据编得像真的——编号有规则、金额有零头、人名像人名。
- **自定义页面另加**（工作台/看板/数据分析页）：层次要白底描边还是浅底白卡。营销类另加：浮层要突出什么。

多张图一起做时列个清单让用户确认一次，不逐张打断。

### 4. 拼装

1. 写两个中间文件到 scratchpad：`.stage` 内容和本图补充样式。内容里的重复块——产品壳与导航、视图页签、工具栏、表格行、统计表、单指标、待办、快捷方式、筛选、横幅、柱/折/环图、看板与卡片视图、详情页信息区与步骤条、手机端各屏——一律写 `<hb-*>` 宏，build.py 会展开成结构正本里的组件。宏语法**按需取，不整读**：

   ```bash
   python3 scripts/expand.py --list                    # 通用写法＋宏目录，先定这张图用哪几个
   python3 scripts/expand.py --doc hb-shell hb-nav hb-views hb-tools hb-grid   # 只取要用的
   ```

   宏没覆盖的组件（浮层内容、标题卡片标题区、流程页签、门户内容组件等）才按路由表用 extract_templates.py 提取模板手写。
2. 组装交给脚本（固定顺序拼皮肤、base.css、icons.svg、fit.js，改过公共资产后重跑即可重拼）：

   ```bash
   python3 scripts/build.py --skin dawn-blue --content stage.html --extra-style page.css \
     --output "源文件/图名.html" --title "图名"    # 产品设计类加 --fullbleed
   ```

3. 图标一律 `<svg class="ico"><use href="#i-名称"/></svg>`，着色用 `ic-*`／`tone-*` 工具类；缺的图标先补进 icons.svg 再用，不内联 path。
4. 内容数据按 anti-sameness 编：带零头、有非理想态、行数不取整、同批图版式错开。
5. 图表类型按 dashboard-chart-selection 选；柱/折/环图写 `hb-bar`/`hb-line`/`hb-donut` 宏由脚本算坐标，其余类型才用内联 SVG 手绘。SVG 里禁止写死色值：主系列 `var(--primary)`（同系第二层加 `opacity=".45"`）、状态色 `var(--c-green/red/orange/blue/purple)`、轴线 `var(--line)`、轴标字 `var(--ink-45)`；图例色块用 `<rect>` 着色，别用 ■ 字符——字符是文字色，着不上。
6. 工作台/看板/数据分析页第一屏必须放横幅部件：页面名称＋一句话介绍（规则见 c3 横幅部件注释）。介绍学产品官方口吻，说清这页管什么、给谁用，20 字上下，不堆形容词，不加「阵地/平台/门户」帽子（例：实现客户、商机与任务排期的集中管理）。

### 5. 对照判据

拼完按「设计原则路由」读对应文件过一遍：状态标签用红绿灯语义色、按钮分主/次/警示/置灰、表单列数一致。

### 6. 验证与交付

按 [references/canvas/verify-export.md](references/canvas/verify-export.md) 执行：

1. `python3 scripts/check.py 图.html`——检查写死色值、自造组件、缺失图标、导出前置，并渲染量空隙。**Blocker 必须清零**；empty-gap 逐条处理。
2. 浏览器渲染核对：高度贴合、无溢出、组件不走样，回填 `.stage` 高度（改补充样式后重跑 build.py）。
3. 出 2x PNG；嵌报告场景另读 [references/canvas/report-embed.md](references/canvas/report-embed.md) 走 SVG 管线。

Chrome 渲染环境按需获取：脚本自动探测本机 Chrome，Linux 沙箱没有时才下载一次并缓存复用，报找不到时读 [references/chrome-env.md](references/chrome-env.md)。

## 输出物落点

**PNG 在外、HTML 进 `源文件/` 子文件夹**——PNG 给人看和嵌报告，HTML 是可再导出的源稿。

| 场景 | PNG | HTML |
| --- | --- | --- |
| 独立出图 | 当前工作目录 `图名@2x.png` | `源文件/图名.html` |
| 报告配图 | 报告项目 `figures/` | `figures/源文件/` |

渲染中间产物（preview 截图）放 scratchpad，不留在交付目录。

## 硬约束

| 约束 | 内容 |
| --- | --- |
| 不自造组件 | 伙伴云没有的控件、布局、交互形态一律不画。要画组件名录（18 类 70 项，来自产品组件预览图库，与结构文件里的 `data-component` 不是同一份计数）里有但结构文件未收录的形态，先告知用户该组件尚未实测采集，确认后按注释里的实测尺寸就近仿写；名录里没有的不画 |
| 结构与皮肤分离 | 改色只动皮肤 token，不改结构和骨架样式里的尺寸 |
| 尺寸是实测的 | 顶栏 56、侧栏 248、行高 35、标签 20、按钮 32/24 来自真实产品，改了就不像 |
| 层次也是实测的 | 是"白卡浮在灰底上"还是"透明融进容器"，以结构文件的 `data-measured` 注释为准；没有注释的组件先去产品实测再画，不许猜（猜错过四次：工具栏透灰底、看板列臆造灰底、筛选部件融背景、底部合计堆成左下角一行文字而不是与列对齐的 tfoot） |
| 自定义页面层次二选一 | ①白底描边（`.page` 加 `flat`）＝页底白、组件白底＋1px 很浅外框、无投影；②浅底白卡（不加类）＝页底浅灰、组件纯白浮起。没指定时默认 ①。**只用于自定义页面**，列表页的视图区白卡浮灰底是实测强特征，不参与切换 |
| 组件底色优先级 | 纯白 ＞ 很浅的背景色 ＞ 深色块。深色只留给一级顶栏、状态标签这类要强调的地方 |
| 详情页标题卡片不放按钮 | 只管自定义详情页的标题卡片——它是信息摘要不是操作区，按钮只能放在记录功能区。工作台/看板的横幅不受此限，但按钮也不进横幅内部 |
| 自定义详情页独立存在 | 默认交付＝记录功能区＋页面内容画布；禁止套记录弹窗、一级顶栏、左侧导航或底部栏。只有用户明确要求产品壳/弹窗时才调用对应架构 |
| 营销浮层不得重复 | 浮层必须补充底层没有的真实组件或信息，禁止把底层卡片、字段、统计或表格复制放大一遍。不得遮住关键内容，也不得靠裁短底层窗口造成页面底部缺失 |
| 标注气泡不默认加 | 只有用户明确要求业务价值标注时才用 |
| Skill 资产是唯一结构真相源 | 新实采的界面结构直接沉淀到对应的 `assets/c1～c4` 和必要的 `assets/base.css` |
| 只写业务结论 | 示意图内容不留设计过程的痕迹 |
