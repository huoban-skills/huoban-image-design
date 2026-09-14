---
name: huoban-image-design
description: 生成伙伴云系统界面示意图，画面忠于伙伴云真实产品组件。当用户要画伙伴云界面示意图/mockup（列表页、详情页、表单、工作台、看板、大屏、手机端），给报告/方案配系统图，或 huoban-solution-report 给出图需求单时，必须使用本 skill。不用于：海报/朋友圈营销图、流程图（hb-flowchart）、ER 图（hb-er-draw）、网站（hb-website-creator）。
---

# 伙伴云系统界面示意图

产出"长得像伙伴云产品"的界面示意图：用骨架宏拼装真实产品实测组件，不自由发挥。输入是出图需求或 huoban-solution-report 的图需求单；**交付物是单文件 HTML**（`源文件/图名.html`，离线可开、自适应），PNG／SVG 只在用户或报告明确要时用 export.py 另出。只画伙伴云产品界面，海报/流程图/ER 图/网站不在本 skill。

核心资产：**登记表**（assets/registry.json，官方组件 type ↔ 类名 ↔ 宏，唯一名录）＋**结构**（assets/c1～c5 实测架构，模板带官方 `data-type`）＋**骨架样式**（base.css）＋**皮肤**（assets/skins/ 纯色彩 token，9 套）＋**宏**（scripts/expand.py，模型只填内容）。

## 页面类型路由（唯一真相源）

先判页面类型，再按这一行取骨架 kind 和必读原则。所有图都读通用两篇：visual-four-principles、visual-color；多张营销配图另读 anti-sameness。

| 用户说的 | `<hb-page kind>` | 必读原则（references/principles/） | 说明 |
| --- | --- | --- | --- |
| 列表页（网格/看板/卡片/甘特/日历/任务/透视） | list | list-view | 视图页签 → 视图区白卡（工具栏 → 视图）；甘特/日历/任务/透视用 extract_templates.py 提模板放在视图位 |
| 表单弹窗 / 编辑态 / 字段录入 | 手写（c1 ＋ c2 模板） | form | 仅用户明确要求时；弹窗与编辑态尺寸未实测，交付说明注明 |
| 详情页 / 详情界面 | detail | item-detail、component-guide | 记录功能区默认包含；不套壳不套弹窗；弹窗详情仅明确要求时用 c3 模板手写 |
| 工作台 | workbench | workbench、component-guide | 横幅 → 单指标 → 快捷方式与待办 → 页签 |
| 数据看板 | dashboard | dashboard、component-guide | 横幅 → 筛选 → 单指标 → 图表行 → 明细 |
| 数据大屏 | screen | dashboard（大屏一节）、component-guide | 体内只放 hb-screen；不套壳、无浮层 |
| 手机端 | mobile | 对应页面篇＋c4 注释 | hb-phone 单屏或 hb-screens 多屏流程（2～3 屏）；不套 .window |

新造或调整皮肤时另读 visual-color 与 skin/custom-skin。

## 执行步骤

### 1. 追问并确认需求单（闸门）

按 [references/intake.md](references/intake.md) 分三轮追问：第 1 轮画布类型、出哪几张图、样式；第 2 轮逐张图先定角色再按页面类型问那一支；第 3 轮问浮层、横幅与层次、数据文案。每轮用 intake 的选择题格式发出后**结束本轮回复，等用户答完再问下一轮**；第 1 轮的三项是决定不是事实，材料再详细也要问，用户在对话里明说过的才跳过。不把三轮压成一条，不跳过追问直接给需求单。三轮问完汇成需求单，**没拿到用户确认，不进入步骤 2。**

### 2. 写骨架片段

先看槽位表，再只取要用的宏的语法：

```bash
python3 scripts/expand.py --page workbench            # 该页面类型的槽位表、可用宏、最小示例
python3 scripts/expand.py --doc hb-nav hb-stats hb-row hb-tasks hb-tabcard   # 只取要用的宏
```

把片段写到 scratchpad 的 `stage.html`：最外层是 `<hb-page kind="…" canvas="…" ws="…" page="…">`，体内按槽位顺序写宏；并排用 `<hb-row spans="16|8">`；营销浮层用 `<hb-float top="…" w="…">`，体内放 bare 模式的宏。外壳、画布高度、浮层定位、栅格都由宏产出；片段里只有 hb-page 和它体内的宏与内容。

宏没覆盖的组件（甘特/日历/任务/透视视图、表单弹窗、流程页签细节）按名提取模板后手写在对应槽位；c 文件只通过这条命令按名取，不整读：

```bash
python3 scripts/extract_templates.py assets/c2-table-form.html --list
python3 scripts/extract_templates.py assets/c2-table-form.html --component "甘特视图"
```

写内容时按页面原则文档定选取与数量；数据按 anti-sameness 编：带零头、有非理想态、行数不取整、同批图版式错开。图表柱/折/环写 `hb-bar`/`hb-line`/`hb-donut` 由脚本算坐标；其余图表类型未采集，先告知用户。

### 3. 拼装

```bash
python3 scripts/build.py --skin dawn-blue --content stage.html --output "源文件/图名.html" --title "图名"
```

固定顺序拼皮肤、base.css、icons.svg、内容、fit.js；`canvas="product"` 自动全屏。展开失败会指出第几行、缺什么、可用什么，照提示改片段重跑；"提示："开头的是规模与顺序建议，不阻断。改过公共资产后重跑即重拼。

### 4. 对照判据

拼完按页面类型路由里的必读原则，逐条过该篇的"检查清单"一节。

### 5. 检查与验收

```bash
python3 scripts/check.py "源文件/图名.html"             # 静态：色值、组件与 token 存在性、结构禁令、规模上限
python3 scripts/check.py "源文件/图名.html" --render    # 有 Chrome 时加渲染检查；没有会明说"渲染检查未执行"
python3 scripts/check.py "源文件/图名.html" --acceptance # 起草十条人工验收表
```

**Blocker 必须清零**，High 逐条处理（本图样式里的新类默认 High，确属一次性布局加 `--allow-local`）。然后按 [references/canvas/verify-export.md](references/canvas/verify-export.md) 的人工验收表逐图回报十条结论，有一条没过不交付。

### 6. 交付

默认交付 `源文件/图名.html`。用户或报告明确要 PNG／SVG 时：

```bash
python3 scripts/export.py "源文件/图名.html" --png     # 2x PNG；找不到 Chrome 会给手动命令，不下载
python3 scripts/export.py "源文件/图名.html" --svg     # 嵌报告用矢量，不需要 Chrome
```

细节见 [references/canvas/export.md](references/canvas/export.md)。

## 输出物落点

| 场景 | HTML（默认交付） | PNG／SVG（可选） |
| --- | --- | --- |
| 独立出图 | 当前工作目录 `源文件/图名.html` | 当前工作目录 `图名@2x.png`／`图名.svg` |
| 报告配图 | 报告项目 `figures/源文件/` | 报告项目 `figures/` |

片段与探针中间产物放 scratchpad，不留在交付目录。

## 硬约束

页面级规则（横幅写角色不写人、页头卡片不放按钮、浮层只放底层没有的内容、标注气泡只在用户要求时加、自定义页面层次二选一）写在各页面原则和 canvas/marketing.md 里，这里只列跨页面的：

| 约束 | 内容 |
| --- | --- |
| 不自造组件 | 只画登记表（assets/registry.json）里有的组件；`registry.py --list workbench`（kind 值或中文页面类型）看该页可用组件与采集状态。登记表标"未核"或"未采集"的形态先告知用户，确认后按注释就近仿写；名录外的不画 |
| 结构与皮肤分离 | 改色只动皮肤 token，不改结构和骨架样式里的尺寸 |
| 尺寸是实测的 | 顶栏 56、侧栏 248、行高 35、标签 20、按钮 32/24 来自真实产品，改了就不像 |
| 层次也是实测的 | "白卡浮在灰底上"还是"透明融进容器"，以结构文件 `data-measured` 为准；没有注释的先实测再画 |
| 组件底色优先级 | 纯白 ＞ 很浅的背景色 ＞ 深色块；深色只留给一级顶栏、状态标签 |
| 只写业务结论 | 示意图内容不留设计过程的痕迹 |
| Skill 资产是唯一结构真相源 | 新实采的界面结构直接沉淀到对应的 assets/c1～c5、base.css 和 registry.json |
