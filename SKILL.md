---
name: huoban-image-design
description: 生成伙伴云系统界面示意图，画面忠于伙伴云真实产品组件。当用户要画伙伴云界面示意图/mockup（列表页、详情页、表单、工作台、看板、大屏、手机端），给报告/方案配系统图，或 huoban-solution-report 给出图需求单时，必须使用本 skill。不用于：海报/朋友圈营销图、流程图（hb-flowchart）、ER 图（hb-er-draw）、网站（hb-website-creator）。
---

# 伙伴云系统界面示意图

## 目标、输入、输出、边界

- 目标：产出"长得像伙伴云产品"的界面示意图，用骨架宏拼装真实产品实测组件，不自由发挥。
- 输入：用户的出图需求，或 huoban-solution-report 给出的图需求单。
- 输出：单文件 HTML（`源文件/图名.html`，离线可开、自适应）；PNG／SVG 只在用户或报告明确要时另出。
- 边界：只画伙伴云产品界面；海报、流程图、ER 图、网站不在本 skill。

## 页面类型路由（唯一真相源）

先判页面类型，在下表找到对应行，取它的骨架 kind 和必读页面原则。所有图都读 references/principles/ 的 visual-four-principles 与 visual-color；多张营销配图另读 anti-sameness。

| 用户说的 | `<hb-page kind>` | 必读页面原则（references/principles/） | 说明 |
| --- | --- | --- | --- |
| 列表页（网格/看板/卡片/甘特/日历/任务/透视） | list | list-view | 视图页签 → 视图区白卡（工具栏 → 视图）；甘特/日历/任务/透视用 extract_templates.py 提模板放在视图位 |
| 表单编辑页 / 字段录入 | 手写（c1 ＋ c2 模板） | form | 仅用户明确要求时；弹窗随视口减 48 宽减 60 高，字段区一到四列等分 |
| 详情页 / 详情界面 | detail | item-detail | 记录功能区默认包含；不套壳不套弹窗；弹窗详情仅明确要求时用 c3 模板手写 |
| 工作台 | workbench | workbench | 横幅 → 单指标 → 按钮组与待办 → 页签 |
| 数据看板 | dashboard | dashboard | 横幅 → 筛选 → 单指标 → 图表行 → 明细 |
| 数据大屏 | screen | screen（组件与数据规则同 dashboard） | 体内只放 hb-screen；不套壳、无浮层 |
| 手机端（上面任一页面的手机版） | mobile | 对应页面篇＋c4 注释 | 单屏或 2～3 屏流程；不套产品壳，用手机宏 |

要选图表类型或拿不准该用哪个组件时再读 component-guide；新造或调整皮肤时另读 visual-color 与 [references/skin/custom-skin.md](references/skin/custom-skin.md)。

## 执行流程

追问并确认需求单 → 写骨架片段 → 拼装 → 对照判据 → 检查与验收 → 交付

## 执行步骤

### 1. 追问并确认需求单（闸门）

- 按 [references/intake.md](references/intake.md) 追问：第 1 轮问出图需求，拟需求单初稿，第 2 轮逐图补细节（超过 3 张分小轮问），更新需求单让用户确认。
- 每轮的题一次发完（选择框工具装得下整轮才用，否则文字版一条消息）；发出后结束本轮回复，等用户答完再继续。
- 完成标准：用户确认需求单。**没拿到确认，不进入步骤 2。**

### 2. 写骨架片段

- 按需求单的画布类型读 [references/canvas/marketing.md](references/canvas/marketing.md) 或 [references/canvas/product-design.md](references/canvas/product-design.md)。
- 看槽位表，只取要用的宏的语法：

```bash
python3 scripts/expand.py --page workbench            # 该页面类型的槽位表、可用宏、最小示例
python3 scripts/expand.py --doc hb-nav hb-stats hb-row hb-tasks hb-tabcard   # 只取要用的宏
```

- 把片段写到 scratchpad 的 `stage.html`：最外层是 `<hb-page kind="…" canvas="…" ws="…" page="…">`，体内按槽位顺序写宏。
- 并排用 `<hb-row spans="16|8">`；营销浮层用 `<hb-float top="…" w="…">`，体内放 bare 模式的宏。
- 外壳、画布高度、浮层定位、栅格都由宏产出；片段里只有 hb-page 和它体内的宏与内容。
- 没有宏的组件（`registry.py --list <kind>` 里宏一列为空的，如日历、快捷表单、甘特／日历／任务／透视视图）按名提取模板后手写在对应槽位；c 文件只通过这条命令按名取，不整读：

```bash
python3 scripts/extract_templates.py assets/c2-table-form.html --list
python3 scripts/extract_templates.py assets/c2-table-form.html --component "甘特视图"
```

- 组件选取与数量按页面原则文档；数据按 anti-sameness 编：带零头、有非理想态、行数不取整、同批图版式错开。
- 图表写 `hb-bar`／`hb-line`／`hb-donut`／`hb-area`／`hb-hbar`／`hb-biaxial`／`hb-funnel`／`hb-scatter`／`hb-map`，坐标由脚本算；地图不画国界，用网点阵占位或客户提供的地图图片。
- 表单编辑页和弹窗详情走手写外壳：片段最外层是 c1 的 `.stage`，`.stage` 必须写死 height；本图补充样式另写 `page.css`，步骤 3 用 `--extra-style` 传入。
- 完成标准：每张图一个片段；`python3 scripts/expand.py stage.html` 没有报错、提示都处理过。

### 3. 拼装

```bash
python3 scripts/build.py --skin dawn-blue --content stage.html --output "源文件/图名.html" --title "图名"
python3 scripts/build.py --skin dawn-blue --content stage.html --extra-style page.css --output "源文件/图名.html" --title "图名"   # 手写外壳时
```

- 脚本按固定顺序拼皮肤、base.css、icons.svg、内容、fit.js；`canvas="product"` 自动全屏。
- 展开失败会指出第几行、缺什么、可用什么，照提示改片段重跑。
- "提示："开头的是规模与顺序建议，不阻断。
- 改过公共资产后重跑即重拼。
- 完成标准：拼装成功，输出文件存在。

### 4. 对照判据

- 按页面类型路由里的必读页面原则，逐条过该篇的"检查清单"一节。
- 完成标准：每条写出"通过／改过（改了什么）"。

### 5. 检查与验收

```bash
python3 scripts/check.py "源文件/图名.html"             # 静态：色值、组件与 token 存在性、结构禁令、规模上限
python3 scripts/check.py "源文件/图名.html" --render    # 有 Chrome 时加渲染检查；没有会明说"渲染检查未执行"
python3 scripts/check.py "源文件/图名.html" --acceptance # 起草十条人工验收表
```

- Blocker 必须清零。
- High 逐条处理；本图样式里的新类默认 High，确属一次性布局加 `--allow-local`。
- 按 [references/canvas/verify-export.md](references/canvas/verify-export.md) 的人工验收表逐图回报十条结论。
- 完成标准：十条全过；有一条没过不交付。

### 6. 交付

- 默认交付 `源文件/图名.html`，回复正文附交付说明（模板见下）。
- 用户或报告明确要 PNG／SVG 时：

```bash
python3 scripts/export.py "源文件/图名.html" --png     # 2x PNG；找不到 Chrome 会给手动命令，不下载
python3 scripts/export.py "源文件/图名.html" --svg     # 嵌报告用矢量，不需要 Chrome
```

- 导出细节与沙箱降级见 [references/canvas/export.md](references/canvas/export.md)。

## 输出物模板

需求单模板在 [references/intake.md](references/intake.md)「需求单」一节，对内对外同一格式。

交付说明（回复正文里的一段，每张图一行）：

```
库管工作台.html：库管一进来就能扫码出入库、发起盘点，看到待审批的出库单；皮肤晨光蓝；进度条按实测仿写。
出库审批.html：主管在企微里收到待办，点开核对明细后一键通过；皮肤晨光蓝；企微会话流为仿写，未实测。
```

输出物落点：

| 场景 | HTML（默认交付） | PNG／SVG（可选） |
| --- | --- | --- |
| 独立出图 | 当前工作目录 `源文件/图名.html` | 当前工作目录 `图名@2x.png`／`图名.svg` |
| 报告配图 | 报告项目 `figures/源文件/` | 报告项目 `figures/` |

片段与探针中间产物放 scratchpad，不留在交付目录。

## 写作规则

页面级规则（横幅写角色不写人、页头卡片不放按钮、浮层只放底层没有的内容、标注气泡只在用户要求时加、页面底色二选一）写在各页面原则和 references/canvas/marketing.md 里；这里只列跨页面的硬约束。

| 约束 | 内容 |
| --- | --- |
| 不自造组件 | 只画登记表里有的组件；`registry.py --list workbench`（kind 值或中文页面类型；表单编辑页不走登记表，按 c2 模板）看该页可用组件与采集状态 |
| 未核与仿写要告知 | 登记表标"未核"的形态先告知用户，确认后按注释就近仿写；标"仿写"的在交付说明里注明；名录外的不画 |
| 结构与皮肤分离 | 改色只动皮肤 token，不改结构和骨架样式里的尺寸 |
| 哪些尺寸照实测 | 组件内部尺寸（顶栏 56、侧栏 248、行高 35、标签 20、按钮 32/24）照真实产品，改了就不像 |
| 组件宽高自适应 | 组件占几栏、多高按布局和画面自适应；实测记录里的 w×h 只是样板的一次配置 |
| 层次也是实测的 | "白卡浮在灰底上"还是"透明融进容器"，以结构文件 `data-measured` 为准；没有注释的先实测再画 |
| 组件底色优先级 | 纯白 ＞ 很浅的背景色 ＞ 深色块；深色只留给一级顶栏、状态标签 |
| 只写业务结论 | 示意图内容不留设计过程的痕迹 |
| Skill 资产是唯一结构真相源 | 新实采的界面结构直接沉淀到对应的 assets/c1～c5、base.css 和 registry.json |
