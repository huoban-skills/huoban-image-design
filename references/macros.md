# 宏语法

本文件由 `python3 scripts/expand.py --doc all` 生成，改语法请改 expand.py 的 DOCS，不要手改这里。
出图时不整读本文件：先 `--list` 看目录，再 `--doc 宏名…` 只取要用的几条。

通用写法
- 宏体按行写，一行一条；行内用 | 分列，\| 表示字面竖线；空行和 // 开头的行忽略。
- 值后缀 :red :blue :green :orange :teal :purple :yellow :gray 把该值做成彩色标签（:gray 是灰底标签）。
- 值前缀 ~ 做成次要灰字（空值、备注）；值前缀 = 表示后面是写好的 HTML 原样放入；含 < 的值也按 HTML 原样放。
- 宏可嵌套，内层先展开。列数不对、图标名不存在、工具名没图标都会报错并指出行，改完重跑。
- 宏只消灭机械重复，不替你做设计决策：用哪种视图、放不放浮层、字段怎么排、数据编成什么样，仍按 SKILL.md 和设计原则定。
- 没有对应宏的组件：`python3 scripts/registry.py --list 页面类型` 里「宏」一列是 — 的那些，按 SKILL.md 路由表用 extract_templates.py 提取模板手写。

## 页面骨架（先写它，外壳由它产出）

### hb-page
页面骨架：kind=list|workbench|dashboard|detail|screen|mobile；产出画布与外壳，体内按槽位放宏；--page kind 看槽位表

```
整页骨架。属性 kind（必填）list/workbench/dashboard/detail/screen/mobile；canvas=marketing（默认，一张图，可放 hb-float）/product（照着搭，全屏无浮层）；产品壳属性 ws（PC 页必填）/page/nav/me/theme/logo/bottom 同 hb-shell；level=flat（默认）/card；cut=高度 px（把窗口截到主要内容为止）。
size=full（默认，整页全貌）/slide（演示尺寸：放进 PPT 这类窄位置，窗口 1200 宽、窗口高 800 以内，由 check.py `slide-height` 检查；底图按完整一页画，必有组件和整页一样不能少，超高了减明细行数、压图表高度，不删骨架组件；浮层宽 400～640 且不缩小；看板视图各列均分宽度；只用于营销类电脑端页面）。选 full 还是 slide 看载体，整图比例两档通用，都见 references/canvas/marketing.md「先按载体选画布尺寸」「整图比例：一屏原则」。
体内直接写各槽位的宏，不再写 .stage/.window/.page/.item-page；先 python3 scripts/expand.py --page kind 看槽位表与最小示例。
```

### hb-row
24 栅格一行：属性 spans=16|8（加起来 24）；体内并排放组件宏，最多 4 个

```
24 栅格一行。属性 spans="16|8"（各段跨度，加起来必须 24；不写则等分）。体内并排放组件宏（hb-shortcuts、hb-tasks、hb-bar、hb-donut、hb-pivot、hb-tabcard…），最多 4 个；一段里要叠两个组件就包一层 hb-col。
例：
<hb-row spans="16|8">
<hb-line title="趋势" labels="1|2|3">出库 | 1,2,3 | blue</hb-line>
<hb-donut title="构成">酒品 | 60 | red</hb-donut>
</hb-row>
```

### hb-col
hb-row 某一段里竖叠 2～3 个组件：矮组件（按钮组件、多项统计、进度条）别单独占一栏被拉高

```
一栏里竖叠组件。只放在 hb-row 的某一段里，体内按上下顺序放 2～3 个组件宏，算 hb-row 的一个组件。
并排时同一行各栏会被拉到等高：一栏只有一张矮卡（按钮组件 3～6 个、多项统计 3 行、进度条）而邻栏是长列表或字段组时，矮卡会被拉高、卡里空一大块。这时用 hb-col 把矮组件叠在一起，或叠一个待办／统计在下面。
例：
<hb-row spans="8|16">
<hb-col>
<hb-shortcuts title="快捷方式">
新建巡检计划 | check-s
飞行检查派单 | warn
</hb-shortcuts>
<hb-multistats title="待办">
待我审核的整改 | 12 | orange
超期未整改 | 3 | red
</hb-multistats>
</hb-col>
<hb-tasks title="待我审核的整改">
…
</hb-tasks>
</hb-row>
```

### hb-float
营销浮层（一张图一个，固定在底图右下角）：属性 w=480～920（无标题）；体内用 hb-row／hb-col 排一块小画面，至少两块 PC 组件

```
营销浮层，一张图只放一个，固定在整张底图的右下角，右边缘探出画布 200，没有位置属性。属性 w（宽 480～920，默认 640；演示尺寸 400～640）；不带浮层标题，要说明的话写在体内组件卡片的 title 上。
浮层是一块小画面：体内和页面一样用 hb-row／hb-col 排版，放另一个页面的完整画面或一块局部，至少两块组件，推荐三四块排两行；外面自动套一道细窗口框，内容按 0.8 倍显示。盖住底图的面积不超过四分之一（check.py `float-cover`）。只放 PC 组件；手机宏（hb-ocards、hb-rec 等）样式只在 hb-phone 里生效，放进来会散成裸文字，expand 会报错。不复制底层已有内容。
例：
<hb-float w="640">
<hb-row spans="12|12">
<hb-list title="整改超期门店" nock noidx count="9">
门店 | 督导 | 超期:tag
味捷·北京朝阳大悦城店 | 张伟 | 6 天:red
味小捷·天津和平路店 | 刘洋 | 4 天:red
味捷·石家庄万象城店 | 张伟 | 2 天:orange
味捷·北京西单店 | 陈立 | 3 天:orange
味捷·廊坊万达店 | 刘洋 | 1 天:orange
味小捷·保定万博店 | 陈立 | 1 天:orange
</hb-list>
<hb-line title="近 6 月整改完成率" labels="4月|5月|6月|7月|8月|9月">
完成率 | 72,78,81,76,85,88 | blue
</hb-line>
</hb-row>
</hb-float>
```

### hb-screens
手机流程壳（2～3 屏）：体内 hb-phone 与 hb-conn 交替，一步一屏

```
手机流程壳：体内 hb-phone、hb-conn、hb-phone（、hb-conn、hb-phone）交替，一步一屏，2～3 屏；每个 hb-phone 加 fix。hb-page kind=mobile 按屏数把画布设成 1100／1640 宽；超过 3 步拆成两张图。企微那一屏放在第一个 hb-phone 里：应用推给本人的用 hb-wxapp，发进群的用 hb-wxgroup。
```


## 产品壳（PC）

### hb-shell
PC 产品壳：左侧导航＋一级顶栏，体内先写 <hb-nav>，其后是 .main 里的页面内容

```
属性：ws 工作区名（必填）、logo（默认取 ws 首字）、page 顶栏当前页名、nav 图标行高亮项 home/table/doc/flow（默认 table）、me 头像字、theme band/side/full/light（默认 band）、bottom（默认 管理|成员）。
体内先写 <hb-nav>，其后是放进 .main 的页面内容（视图页签、view-box、.page 等）。
.stage、has-float、.mk-float 浮层、补充样式仍由你写；hb-shell 只产出 .window 到 .main 顶栏为止的壳。
例：
<div class="stage">
<hb-shell ws="云图贸易" page="物资档案" nav="table" me="周">
<hb-nav>…</hb-nav>
…页面内容…
</hb-shell>
</div>
```

### hb-nav
左侧导航树：# 分组；名称 | 图标 | 颜色，* 前缀＝当前页；> 文件夹，- 子项

```
行：# 分组名；名称 | 图标 | 颜色（图标默认 app-s，颜色给 ic-* 类）；* 前缀＝当前页；> 文件夹名 | 子项数；- 前缀＝文件夹下的子项。
例：
# 物资台账
* 物资档案 | app-s
库存明细 | grid-s | green
> 归档资料 | 3
- 2025 年台账 | doc
# 出入库
出库单 | check-s | orange
```


## 列表页

### hb-views
视图页签行：名称 | 图标，* 前缀＝当前视图

```
行：名称 | 图标，图标默认 grid-s（看板 board-s、日历 f-date、甘特 chart-s）；* 前缀＝当前视图。自动补「创建视图」和溢出入口，noadd 去掉创建。
例：
* 全部物资
按品类查看
珍藏品专区 | board-s
```

### hb-tools
工具栏：字段|筛选:1|排序|导入|自定义:图标；属性 search、new

```
工具用 | 分开；内置图标的工具名：字段 分组 筛选 排序 冻结 行高 导入 导出 打印 分享；筛选:1＝激活态并显示条数；其他工具写 名称:图标名。
属性 search 搜索框占位文字、new 新建按钮文字（nodd 去掉分裂箭头）。放在 <div class="view-box"> 里、hb-grid 之前。
例：
<hb-tools search="搜索品名或编号" new="新建物资">字段 | 筛选:1 | 排序 | 导入 | 打印二维码:print</hb-tools>
```

### hb-grid
网格表格：首行表头（列名:类型 / :sum=值），其后每行一条记录；# 分组行，! 选中行

```
首行表头，列名后可接类型 :tag（彩色选项）:tags（多值，值用 / 分）:user（人员，多人用 / 分）:ops（行内按钮，名:图标:颜色，多个用 / 分）；统计 :sum=值 :avg= :max= :min= :count=。
其后每行一条记录，列数必须与表头一致。# 分组值:颜色 插分组行；! 前缀＝选中行。
属性 total="1,217条" 出底部合计行（有统计列时自动出）；nock 去勾选列、noidx 去行号列；bare 只出 .grid（放进 w-card、浮层、标签页内时用），默认带 .table-view.view-grid 和横向滚动条。
例：
<hb-grid total="1,217条">
物资编号 | 品名 | 品类:tag | 当前库存:sum=4,386 | 建档人:user | 操作:ops
WZ-JS-0106 | 茅台飞天 53° 500ml | 酒品:red | 36 | 周敏 | 打印:print:teal / 出库:arrow-right:blue
# 茶叶:green
WZ-CY-0412 | 武夷山大红袍 | 茶叶:green | 24 | 陈晓东 | ~
</hb-grid>
```

### hb-kanban
看板视图：# 分组:颜色 | 数量 开列，其后每行「标题 | 字段=值; 字段=值」

```
# 分组名:颜色 | 数量 开一列，其后每行 标题 | 字段=值; 字段=值。
例：
# 待审核:orange | 3
SO-2026-0901 | 客户=杭州云图; 金额=¥12,480.00
# 已完成:green | 12
SO-2026-0812 | 客户=上海博远; 金额=¥7,650.00
```

### hb-cards
卡片视图：标题 | 字段=值; 字段=值 | 操作:图标:颜色

```
卡片视图，每行 标题 | 字段=值; 字段=值 | 操作:图标:颜色。
例：
杭州云图 | 行业=制造; 年采购=¥1,204,000 | 拜访:arrow-right:blue
```


## 自定义页面组件（工作台 / 数据看板）

### hb-cover
页面封面：属性 title、sub、icon；放页面最前，封面 280 高＋80 图标＋40 号大标题

```
页面封面（官方 cover 元素，不是组件）。属性 title（必填，页面标题）、sub、icon（图标名，默认 app-s）。
放页面最前：封面 280 高、取内容区全宽；页面图标 80×80 圆角 8 压在封面下沿；标题 40 号 / 56 行高 / 500 粗（2026-09-14 实测）。
list 之外的 hb-page 都能用，一页只放一个。
例：
<hb-cover title="库存分析" sub="按仓库与品类查看库存结构、周转与预警" icon="chart-s"></hb-cover>
```

### hb-banner
横幅（富文本大标题预设）：第一行页面名称，第二行一句话介绍；属性 solid；card 出背景图卡片式（date、time、img）

```
横幅（富文本大标题预设）。第一行页面名称，第二行一句话介绍（口吻规则见 references/principles/workbench.md）；属性 solid 铺纯色背景。
属性 card 出背景图卡片式（120 高白卡，实测工作台常用）：date="2026年09月04日"、time="16:51:17" 出日期时间行；img 出右侧图片位（值写 <img src="…"> 放客户配图，空值留渐变占位）。卡片式不放介绍句。
例：
<hb-banner>库管工作台
实现物资出入库与盘点的集中管理</hb-banner>
<hb-banner card date="2026年09月04日" time="16:51:17" img>任务工作台</hb-banner>
```

### hb-filters
筛选组件：筛选文本 | 图标

```
行：筛选文本 | 图标，图标默认 f-select（日期用 f-date）。
例：
统计月份：2026 年 8 月 | f-date
存放点：全部
```

### hb-stats
单指标一行：指标名 | 值 | 单位 | spark:1,2,3 或 trend:red；mode=center|strip

```
每行 指标名 | 值 | 单位 | 附加。mode="center"（默认，居中大数）或 mode="strip"（左文右图，附加写 spark:数,数,… 自动画走势线）；居中大数的附加可写 trend 或 trend:red 出底部趋势条。4～6 个时自动加 stats-N。
例：
<hb-stats>
在库总量 | 4,386
本月出库 | 217 | 件
库存预警品种 | 6 | | trend:red
</hb-stats>
<hb-stats mode="strip">
今日扫码开单 | 14 | spark:28,22,25,14,17,9,6
</hb-stats>
```

### hb-shortcuts
按钮组件（快捷方式版式）：名称 | 图标；属性 title

```
按钮组件（快捷方式版式）。行：名称 | 图标；属性 title 出标题栏。按钮宽度自适应内容、文字不折行，一行排不下自动换第二行（2026-09-04 实测）。
例：
<hb-shortcuts title="常用">
扫码出入库 | f-barcode
发起盘点 | chart-s
</hb-shortcuts>
```

### hb-tasks
待办子区：标题 | 时间 | 节点说明；属性 title

```
行：标题 | 时间 | 节点说明 | 按钮名（缺省「办理」，写 - 去掉）；属性 title 出子区标题。任务行右侧固定有办理按钮（2026-09-04 实测）。
例：
<hb-tasks title="待我办理的流程">
出库审批 · CK-20260824-0037 | 1.4 小时前 | 陈晓东 扫码创建 · 待仓库主管审批
</hb-tasks>
```

### hb-multistats
多项统计：每行「名称 | 数值 | 颜色」，右侧彩色胶囊；属性 title、span

```
多项统计（官方 multi_stats，工作台「待办」那一类）。属性 title、span。
每行 名称 | 数值 | 颜色（缺省按 orange/green/red/yellow/purple/blue 六色轮转，实测就是按条目顺序轮转）。
条 40 高，右侧数值是 20 高、圆角 10 的彩色胶囊——这是它和分类汇总最直观的差别。
例：
<hb-multistats title="待办" span="8">
待我审批的出库单 | 3
待确认的入库单 | 7
超期未盘点品种 | 2 | red
</hb-multistats>
```

### hb-procs
我发起的：每行「流程名 | 单据 | 当前节点 | 状态:颜色 | 时间」；属性 title、span

```
我发起的（官方 procedure_process）。属性 title、span。
每行 流程名 | 单据 | 当前节点 | 状态:颜色 | 时间，行 80 高、三行字号 14/12/12；一行都不写时画「暂无」空态。
例：
<hb-procs title="我发起的" span="8">
出库审批 | CK-20260824-0037 领用出库 | 仓库主管审批 | 审批中:orange | 1.4 小时前
采购申请 | CG-20260820-0012 | 财务复核 | 已完成:green | 8月20日
</hb-procs>
```

### hb-list
表格列表：体内同 hb-grid（首行表头）；属性 title、span、tools、count

```
表格列表（官方 table_item_list，工作区里用得最多的组件）。属性 title、span、tools（工具图标，| 分：搜索/新建/新增/导出/导入/更多/筛选/打印/分享/设置）、count（记录数，出底部「共 N 条」）、nock / noidx / total 透传给表体。
体内就是 hb-grid 的写法：首行表头（列名:类型 / :sum=值），其后每行一条记录。
外壳实测：标题行 40、表头 32、数据行 35、底部分页条 40，白卡圆角 9。
例：
<hb-list title="出库记录" tools="搜索|新建|导出" count="1,217" span="12">
出库单号 | 物资 | 数量 | 领用人:user | 状态:tag
CK-20260824-0037 | 茅台飞天 53° | 12 | 周敏 | 待审批:orange
CK-20260823-0036 | 武夷山大红袍 | 6 | 陈晓东 | 已出库:green
</hb-list>
```

### hb-progress
进度条：每行「名称 | 完成值 | 目标值 | 颜色」；属性 title、span、style=bar|text

```
进度条（官方 progress_bar），一个组件里可以放多条。属性 title、span、style：
- style="bar"（默认，产品 newStyle）：条 32 高圆角 6，名称与百分比嵌在条内，进度覆盖到的那段文字转白。
- style="text"（产品 normal）：文字行 24（名称左、百分比右）＋ 下方 4 高圆角 10 的细条。
两种形态每条都占 40 高。每行 名称 | 完成值 | 目标值 | 颜色（缺省按 blue/green/yellow/purple/orange/teal 轮转），百分比＝完成值/目标值。
例：
<hb-progress title="计划完成进度" style="bar" span="8">
9 月生产计划 | 8200 | 10000 | purple
9 月发货计划 | 6400 | 10000
</hb-progress>
```

### hb-subtotal
分类汇总：首行是合计，其后每行「名称 | 数值」；属性 title、span

```
分类汇总（官方 subtotal）。属性 title、span。首行是合计行（加粗），其后每行 名称 | 数值。
条目 40 高，右侧是纯文本、没有胶囊，顶部多一条合计行——与多项统计的区别就在这两点。
例：
<hb-subtotal title="分品类库存金额" span="6">
共计 | 5,076.8 k
酒品 | 2,841.2 k
茶叶 | 1,320.4 k
礼盒 | 915.2 k
</hb-subtotal>
```

### hb-bar
柱状图卡：labels=横轴|…；每行「系列名 | 值,值,… | 颜色」

```
属性 title、labels（横轴，| 分）、max（不给自动取整）、ticks（默认 4）、h（配合本图补充样式改 .chart .wc-bd 高度时同步给）。
每行 系列名 | 值,值,… | 颜色；系列值用逗号分隔，不写千分位。颜色缺省：第一系列主色，第二系列主色 45% 透明，再往后状态色；显式给颜色用状态色。图例自动生成。默认 w-card chart 卡，bare 只出 svg＋图例，plain 去掉卡片外壳只留 40 高标题行（产品 common 样式）。
例：
<hb-bar title="近 6 个月出入库趋势" labels="3 月|4 月|5 月|6 月|7 月|8 月">
出库 | 135,165,115,185,212,217
入库 | 82,102,70,135,117,143
</hb-bar>
```

### hb-line
折线图卡：同 hb-bar；属性 plain 去掉卡片外壳

```
折线图，属性和行格式同 hb-bar（同样支持 bare / plain）。
例：
<hb-line title="近 5 周签约额" labels="W31|W32|W33|W34|W35">
签约额 | 42,55,38,61,70
目标 | 50,50,50,50,50 | orange
</hb-line>
```

### hb-donut
环图卡：每行「名称 | 值 | 颜色」；属性 center=标签|值

```
每行 名称 | 值 | 颜色（值可带千分位；颜色缺省按 red/blue/purple/teal/green/orange 轮转）；center="标签|值" 出中心文字；百分比自动算，图例画在右侧。默认 w-card chart 卡，bare 只出 svg，plain 去掉卡片外壳只留标题行。
例：
<hb-donut title="各存放点库存占比" center="在库总量|4,386">
城建大厦酒窖 | 1,842
北京办公室 | 1,097
</hb-donut>
```

### hb-area
面积图卡：同 hb-line 语法，折线下 20% 透明填充

```
面积图，属性和行格式同 hb-bar；折线下方铺 20% 透明的同色面积（2026-09-14 实测 chart_area）。
加 plain 去掉卡片外壳（产品的 common 样式：无底、无边、无影，只剩 40 高标题行）。
例：
<hb-area title="近 6 个月库存水位" labels="3 月|4 月|5 月|6 月|7 月|8 月">
在库总量 | 3820,4010,3960,4180,4290,4386 | teal
</hb-area>
```

### hb-hbar
条形图卡（横向条）：每行「名称 | 值 | 颜色」，标签在左、数值在右

```
条形图（官方 chart_bar_y，横向条）。每行 名称 | 值 | 颜色（颜色缺省按 red/blue/purple/teal/green/orange 轮转）；属性 title、span、max（不给按最大值取整）、plain。
标签在左、条在中、数值在右；条长按 值/max 算。
例：
<hb-hbar title="各存放点在库量" plain>
城建大厦酒窖 | 1,842 | blue
北京办公室 | 1,097 | teal
上海仓 | 764 | green
</hb-hbar>
```

### hb-biaxial
双轴图卡：labels=横轴|…；两行「系列名 | 值,值,… | bar」柱走左轴、「… | line」折线走右轴

```
双轴图（官方 chart_biaxial）。属性 title、labels（横轴，| 分）、span、max（左轴上限，柱）、max2（右轴上限，线）、ticks（默认 4）、plain、bare、w、h。
体内正好两行：第一行「系列名 | 值,值,… | bar」画柱走左轴，第二行「系列名 | 值,值,… | line」画折线走右轴；两轴刻度各自算，图例两项。
颜色按实测走：柱次色、线主色（大屏里自动换成大屏系列色），第四列可显式给状态色。量纲不同的两组数（金额与数量、件数与达成率）才用双轴，同量纲就用 hb-bar 多系列。
例：
<hb-biaxial title="近 6 个月出库量与周转天数" labels="3 月|4 月|5 月|6 月|7 月|8 月">
出库量 | 135,165,115,185,212,217 | bar
周转天数 | 48,45,51,43,40,42 | line
</hb-biaxial>
```

### hb-funnel
漏斗图卡：每行「阶段名 | 值」，自上而下逐级收窄，右侧标转化率

```
漏斗图（官方 chart_funnel）。属性 title、span、plain、bare。每行「阶段名 | 值」，至少两段，自上而下逐级收窄；右侧标原值与对首段的转化率，颜色是主色由深到浅。
讲一条链路一级级掉下来的量才用它（线索→商机→报价→签约）；并列的几类量用 hb-bar 或 hb-hbar。
例：
<hb-funnel title="销售漏斗">
线索 | 1,240
商机 | 486
报价 | 214
签约 | 96
</hb-funnel>
```

### hb-scatter
散点图卡：属性 x、y 轴名；每行「名称 | x 值 | y 值 | 大小(可省)」

```
散点图（官方 chart_scatter）。属性 title、x（横轴名）、y（纵轴名）、xmax、ymax、ticks（默认 4）、span、plain、bare、w、h。
每行「名称 | x 值 | y 值 | 大小(可省)」：给了第四列就按它定点的大小（气泡图），点用主色半透明。
看两个指标之间有没有关系才用它（客单价与复购率、库龄与周转），只有一个维度时用柱图。
例：
<hb-scatter title="客户库龄与周转" x="平均库龄（天）" y="周转次数">
城建大厦酒窖 | 42 | 8.6 | 1842
高新库 | 61 | 5.2 | 1097
经开区备件库 | 28 | 11.4 | 764
</hb-scatter>
```

### hb-map
地图卡：每行「地点 | 值」，网点阵＋标记点（不画轮廓）；属性 img 放客户提供的地图图片

```
地图（官方 chart_map）。属性 title、span、plain、bare、w、h、img（客户提供的地图图片路径，给了就直接放图）。
每行「地点 | 值」：网点阵底上按值定标记点大小，右侧列成地点小表。**不画任何国家或省份轮廓**（审图号与边界准确性），要真实地图就让客户给图走 img。
例：
<hb-map title="各仓库在库分布">
城建大厦酒窖 | 1,842
高新库 | 1,097
经开区备件库 | 764
临时周转库 | 310
</hb-map>
```

### hb-pivot
透视表（维度 × 指标的统计，做数据分析用）：首行表头，其后数据行，值是数字；一条条记录用 hb-list

```
透视表（官方 chart_table），做数据分析用：首列是维度（区域、产品、月份、人员），其余列是该维度下的数字指标，值可带 :red 做成标签。合并单元格：格子写 ^ 并入上方、写 < 并入左侧（同一维度连着几行时，首列只写一次，下面几行写 ^）。单元格底色：值::颜色 给整格铺浅色底，如 85%::green、延期::red，进度表、达成表用它标高低。它不是记录列表，编号、门店、负责人、日期、状态这种一条条的记录用 hb-list（表格列表）；列里带 :user/:tag、或大部分格子是文字时会报错。属性 title、icon、tint（yellow/blue/teal 标题栏底色）、dim（首列维度灰底）、bare 只出 <table>。
例：
<hb-pivot title="分存放点库存统计" dim>
存放点 | 品种数 | 在库数量
城建大厦酒窖 | 486 | 1,842
</hb-pivot>
<hb-pivot title="各工序周进度" dim>
工序 | 小组 | 计划 | 完成 | 达成率
折弯 | 樊组 | 420 | 398 | 95%::green
^ | 红组 | 380 | 266 | 70%::orange
焊接 | 森组 | 300 | 171 | 57%::red
</hb-pivot>
```


## 独立自定义详情页

### hb-itembar
详情页记录功能区：属性 title；体内快捷按钮「名:solid|名:line|名:line:dis」

```
记录功能区（自定义详情页默认自带，56 高）。属性 title 记录主标题（必填）、nosys 不出右侧系统操作。
体内快捷按钮用 | 分开：名:solid（主色实底）、名:line（线框）、再接 :dis 置灰或 :green/:orange/:teal 实底色。
例：
<hb-itembar title="出库单 CK-20260824-0037">确认出库:solid | 驳回修改:line | 打印出库单:line:dis</hb-itembar>
```

### hb-hcard
详情页页头卡片：属性 title、sub；体内每行「字段名 | 值 | 类型」，类型 user/tag/tags 可选

```
页头卡片（信息摘要，不放按钮）。属性 title 主标题（必填）、sub 副标题或编号、span（默认 24）。体内 1～4 行关键字段：字段名 | 值 | 类型（user/tag/tags，缺省文本；值带 :颜色 自动成标签）。
例：
<hb-hcard title="领用出库 · 城建大厦酒窖" sub="CK-20260824-0037 · 共 8 个品种 / 14 瓶">
出库类型 | 领用出库:orange
出库仓库 | 城建大厦酒窖
申请人 | 陈晓东 | user
申请日期 | 2026-08-24
</hb-hcard>
```

### hb-fields
字段组：# 开分组；每行「字段名 | 值 | 类型」；属性 title、cols（默认 2）、span

```
字段组（官方 field_group，详情页最常用的组件）。属性 title、cols=1～4（每行字段数，默认 2）、span、icon、tint。
体内：# 分组名 开一组（分组标题行 40 高，三种浅色底轮转）；其余每行 字段名 | 值 | 类型。
类型：缺省文本；user 人员（多人用 / 分）、tag 彩色选项、tags 多选项（/ 分）；multi 多行文本、file 附件、image 图片是不定高类型，自动独占一行；
tiles 选项字段平铺，值写「选项 / *当前:颜色 / 选项」，独占一行、行高照常 69，放在分组的首行或末行，免得上一行空半格。选项字段平铺只能这样写在字段组里，不能单独成一块。
字段行 69 高＝标签 24 ＋ 值框 32 ＋ 上下内距（2026-09-14 实测）。
例：
<hb-fields title="订单详情" cols="2" tint="blue">
# 基本信息
订单编号 | SO-2026-0901
客户 | 杭州云图 | tag
# 交付与回款
负责人 | 周敏 | user
交付状态 | 已发货:green
备注 | 客户要求分两批发货，第二批下月初 | multi
</hb-fields>
```

### hb-steps
状态条：步骤 | *当前 | 步骤，箭头式（status_bar）；选项字段平铺写进 hb-fields 的 tiles 字段

```
状态条（官方 status_bar），* 标当前步骤；属性 span（默认 24）。
箭头式分段，整条 40 高、白卡圆角 9；段间重叠 10px 咬合，已过段主色 25% 底＋ink-45 字，当前段主色实底白字，未到段透明底＋ink-85 字。
选项字段平铺（全圆角胶囊）不是组件，是字段的展示样式：写在 <hb-fields> 里，类型 tiles，单独用 pill 会报错。
例：
<hb-steps>提交申请 | *仓库主管审批 | 行政总监审批 | 已出库</hb-steps>
```

### hb-tabcard
标签页：属性 tabs=*页签|页签、span；pill 出工作台胶囊式（一律居中）；体内放已展开的内容

```
标签页。属性 tabs="*出库明细|历史出入库|现场照片"（* 当前页签，必填）、span（给了就外包一层 .span-N 栅格）。体内放页签内容：hb-grid bare、字段、hb-flow、form-hint 等。
默认是详情页的下划线页签，靠左；工作台/看板要胶囊式页签（选中主色 20% 底条）写 pill，胶囊只在居中时成立，pill 一律居中；页签按角色工作流程从左到右或按业务分类编排。
例：
<hb-tabcard tabs="*出库明细|历史出入库|现场照片" span="16">
<hb-grid bare nock>
品名 | 库位 | 本次出库:sum=14 | 领用人:user
七燕酒庄干红 750ml | 3 号酒柜 2 层 | 2 瓶 | 徐慧敏
</hb-grid>
<div class="form-hint">审批状态变为「已出库」时库存自动扣减。</div>
</hb-tabcard>
<hb-tabcard tabs="*流程|动态|评论" span="8">
<hb-flow …>…</hb-flow>
</hb-tabcard>
<hb-tabcard tabs="*进行中任务|已完成任务|工作报告|跟进汇总" pill>
<hb-grid bare nock>…</hb-grid>
</hb-tabcard>
```

### hb-flow
流程执行记录时间线：属性 name、by；每行「节点名 | 状态:颜色 | 日期 | 耗时 | 链接」

```
流程执行记录时间线（放在 tabs="*流程|动态|评论" 的 hb-tabcard 里）。属性 name 流程名（必填）、by="发起人 · 时间"、foot（默认「查看详细记录」）、nocancel 不出「撤销流程」。
每行一个节点，倒序（最新在上）：节点名 | 状态文本:颜色 | 日期 | 耗时 | 链接；颜色 orange 执行中（缺省）/ green 同意 / red 驳回 / gray 未开始；启动事件写「启动事件 | 事件描述 | 日期」。
例：
<hb-flow name="出库审批" by="陈晓东 · 8月24日 09:12">
仓库主管审批 | 周敏 执行中 | 8月24日 09:40 | 1.4小时 | 催办
启动事件 | 陈晓东 扫码创建了「CK-20260824-0037 领用出库单」 | 8月24日 09:12
</hb-flow>
```

### hb-stream
动态：每行「人名 | 时间 | 内容」，人名写 sys:名 出系统动态；属性 span

```
动态（官方 stream）。属性 span。没有标题行——实测该组件 is_name_show 为 false。
每行 人名 | 时间 | 内容，内容可以再用 | 续写成多行（一个字段变更一行，实测多字段变更就是这么排的）。
人名写成 sys:名 出系统动态：左侧画铅笔图标而不是头像，用来表示自动化、自动计算这类系统来源。
单行条目 40 高、三行 72 高，条间距 16。
例：
<hb-stream span="24">
周敏 | 12 分钟前 | 订单状态：待审批 → 审批中
sys:自动化 | 1 小时前 | 订单总额：修改为 941 | 待回款金额：修改为 941 | 订单总利润：修改为 0
</hb-stream>
```

### hb-comment
评论：每行「人名 | 时间 | 内容」，无行出空态；属性 title、span

```
评论（官方 comment）。属性 title、span。每行 人名 | 时间 | 内容，内容可用 | 续写多行。
一行都不写时画空态：48 圆图标＋「暂无评论」。底部固定一条 68 高的发布条。
例：
<hb-comment title="评论" span="8">
陈晓东 | 昨天 17:06 | 第二批发货时间已与客户确认
</hb-comment>
<hb-comment title="评论" span="8"></hb-comment>
```


## 数据大屏（2026-09-14 实测官方六张样板，c5-screen.html）

### hb-screen
数据大屏画布：属性 title、sub、logo、date、week、time、theme=cyan|blue|gold|red|light；体内放 hb-scol/hb-scard/hb-svisual

```
数据大屏画布（不套产品壳）。属性 title 页面名（必填）、sub 副题、logo 左上企业名、date/week/time 右上日期星期时间、
theme 配色 cyan 深青未来（默认）/blue 蓝色科技/gold 黑金金融/red 红色党建/light 青色自然（浅色）；背景由主题自带的网格纹理和顶部光带产出。
大屏就是普通的 24 栅格页面，不缩放：列宽、行高、20 间距与其他页面一致，h 行的组件高 20h−20。画布 1640 宽，官方骨架排下来 1440 高。
体内按官方骨架放：标题行和分隔条由本宏自动产出，其后依次是左列 hb-scol（6）、中间 hb-svisual（12）、右列 hb-scol（6），最后底部两张 hb-scard（12＋12）。
例：见 python3 scripts/expand.py --page screen 的最小示例（可直接 build）。
```

### hb-scol
大屏主体分栏：属性 span（默认 6）、rs（默认 38）；体内竖着放 hb-skpi/hb-scard，各组件 rs 之和等于本列 rs

```
大屏主体分栏。属性 span 列宽（默认 6）、rs 列高行数（默认 38）。体内竖着放 hb-skpi、hb-scard，
列内各组件的 rs 之和要等于本列的 rs，三列才等高（左 6＝6＋16＋16，右 6＝6＋12＋20，中 12＝38；左右两列顶部都放大屏指标框或都不放）。
例：
<hb-scol span="6" rs="38">
<hb-skpi rs="6">在库总量 | 4,386 | 件
本月出库 | 217 | 件</hb-skpi>
<hb-scard title="近 12 个月出库量" rs="16"><hb-area bare labels="…">…</hb-area></hb-scard>
<hb-scard title="库存构成" rs="16"><hb-donut bare center="在库|4,386">…</hb-donut></hb-scard>
</hb-scol>
```

### hb-skpi
大屏指标框：每行「指标名 | 值 | 单位 | up/down」，一行 2 个；属性 span（默认 6）、rs（默认 6）

```
大屏指标框，每行「指标名 | 值 | 单位 | up/down」（up 绿 down 红）。一行 2 个（官方左列是两个 3×6 的单指标），最多 3 个。
属性 span（默认 6）、rs（默认 6，高 100）。指标名 14 白 45% 在上，值 32/500 白 85% 在下，居中。
例：
<hb-skpi rs="6">
在库总量 | 4,386 | 件
本月出库 | 217 | 件 | up
</hb-skpi>
```

### hb-scard
大屏组件卡：属性 title、span（默认 6）、rs（默认 16）；体内放 hb-area/line/bar/donut 的 bare 输出、hb-sbars 或 hb-list

```
大屏组件卡：40 高标题条（左侧斜切铭牌）＋ 内容区。属性 title 组件名（必填）、span 列宽（默认 6）、rs 行数（默认 16，高 20rs−20）。
体内放 hb-area / hb-line / hb-bar / hb-donut / hb-biaxial / hb-funnel / hb-scatter / hb-map 的 bare 输出、hb-sbars 进度条、hb-list 表格列表或手绘 SVG；图表系列色自动走大屏固定配色。
例：
<hb-scard title="近 30 日出入库趋势" span="12" rs="26">
<hb-line bare labels="1|5|10|15|20|25|30">
出库 | 12,18,15,22,19,25,21
入库 | 9,14,11,17,16,19,18
</hb-line>
</hb-scard>
```

### hb-sbars
大屏进度条：每行「名称 | 百分比」，条底色蓝/橙/绿/红轮转

```
大屏进度条（放进 hb-scard 体内），每行「名称 | 百分比」。条底色按蓝／橙／绿／红轮转（官方实测色序）。
例：
<hb-sbars>
城建大厦酒窖 | 92%
高新库 | 74%
</hb-sbars>
```

### hb-svisual
大屏中央视觉位：属性 span（默认 12）、rs（默认 38）、title、img=客户图片路径、map=网点阵占位；空则线框地球

```
大屏中央视觉位（12 栏，跨整个主体高度）。属性 span（默认 12）、rs（默认 38）、title 标题（给了就出标题条）、
img 客户图片路径（地图、3D 厂区图、产品图；本地文件 build.py 会内嵌进单文件）、map 网点阵占位（标题默认「区域分布」）。
都不给时画线框地球。三种形态都不画国家或省份轮廓（边界准确性与审图号）。
例：
<hb-svisual map span="12" rs="38"/>
<hb-svisual span="12" rs="38" title="厂区实时状态" img="素材/厂区3D.png"/>
```


## 手机端（2026-09-03 H5 实测结构，壳 375 宽）

### hb-phone
手机壳＋顶栏：属性 title、fix、nobar；体内放页面内容

```
手机壳＋顶栏 44。属性 title（顶栏标题：表名/流程名/企业名·应用名）、fix（固定 812 高，hb-screens 里必加）、nobar（不要顶栏，门户页用，顶栏改放 hb-ptop）、nodots（顶栏右侧不出 ···，个人中心这类系统页用）。体内按页面形态放手机端其他宏。
.stage 宽度由 hb-page 按屏数给（单屏 520、两屏 1100、三屏 1640）。
例：
<div class="stage">
  <div class="duo">
<hb-phone title="纳承国际 · 存货管理"><hb-wxapp>…</hb-wxapp></hb-phone>
<hb-conn>…</hb-conn>
<hb-phone title="客户存货单" fix><hb-vbar view="未取完" count="12"/><hb-ocards fab>…</hb-ocards><hb-mtool/></hb-phone>
  </div>
</div>
```

### hb-mhome
工作区首页：属性 tabs=表格|*流程…；每行一个分组，- 前缀为展开的表

```
工作区首页＝页签行＋搜索＋分组列表。属性 tabs="*表格|流程|页面|动态|库管工作台"（* 当前）、search 占位、head（默认「全部表格」）；每行一个分组名如 产品库存(3)，- 前缀是展开后的表名。
例：
<hb-mhome tabs="*表格|流程|页面|动态|库管工作台">
产品库存(3)
- 物品资料表
- 库存表
出库(2)
</hb-mhome>
```

### hb-vbar
列表页视图条：属性 view、count、icon、nosearch

```
列表页视图条 48。属性 view 视图名、count 条数、icon（默认 grid-s）、nosearch。自闭合写法。
例：
<hb-vbar view="全部数据" count="11"/>
```

### hb-ocards
三槽卡片列表：标题 | 副标题 | 字段=值; 字段=值; 字段=值 | 按钮:图标 | img；属性 fab、pager、bare

```
手机专用，只放在 hb-phone 里。三槽卡片列表（产品默认卡片形态，最多 3 个字段）。每行 标题 | 副标题 | 字段=值; 字段=值; 字段=值 | 按钮名:图标 | img；副标题可留空；值后缀 :gray 做灰底标签、:orange 等做彩色选项标签；第四列省略则无按钮；第五列写 img 出右侧图片位。
属性 fab 出悬浮新建钮、pager="20 行/页" 出分页条、bare 只出卡片不带列表底。
例：
<hb-ocards fab>
王丽娟：8 件｜朝阳门店 | 2026-08-12 下单 · 收款 ¥3,680 | 未取件数=8 件; 状态=部分取货:orange; 经手=李明 | 登记取货:check
孙国强：0 件｜朝阳门店 | | 库位=A-03-02-02:gray; 当前库存数量=0; 库存下限=1
</hb-ocards>
```

### hb-mtool
底部 56 栏：mode=list（列表工具栏，默认）/ obar（记录操作条）/ app（应用页签栏）；体内可自定义项

```
底部 56 栏。mode="list"（默认：列统计/字段设置/分组/筛选/排序）、mode="obar"（记录详情操作条：上一条置灰/下一条/编辑/评论/更多）、mode="app"（企业级应用页签：空间/*流程/通知/我的）；体内写 名:图标 | 名 可自定义，* 前缀高亮，:dis 置灰。
例：
<hb-mtool/>
<hb-mtool mode="obar"/>
<hb-mtool>列统计 | 筛选 | 排序</hb-mtool>
```

### hb-rec
记录页：属性 title、edit、noqr、elapsed；# 分组；字段名 | 值 | 类型(text/sel/opt/mem/rel/img/num:单位)；! 前缀高亮；> 子表页签

```
记录页（详情/编辑/新建/任务办理共用）。属性 title（记录标题；新建写表名）、edit（编辑态白值框）、noqr、elapsed="1.7天"（任务页顶部耗时条）。
体内：# 分组名 出居中分组标题；字段名 | 值 | 类型——类型缺省文本，sel 带下拉箭头，opt 选项并排（值写 当前值:blue / 其他 / 其他），mem 成员胶囊（多人 / 分），rel 关联（值写 主行 / 副行），img 图片（值写张数），num:元 数值带单位；值前缀 ~ 出占位灰字（「请先选择：仓库」「保存后显示计算结果」）；字段名前缀 ! 整块青绿高亮（计算字段、本节点可编辑字段）；> 页签1 | 页签2 | 来自 出库明细 的数据 · 共 1 条 出子表页签。
例：
<hb-rec title="CK_20260902_001 直接出库" elapsed="1.7天">
!出库状态 | 待审批:blue / 已出库 / 已驳回 / 作废 | opt
出库单号 | CK_20260902_001
# 出库信息
出库仓库 | 澄川珍藏物品库 / 联系电话 | rel
申请人 | 詹达富 | mem
出库拍照 | 1 | img
> 出库明细 | 辅助字段 | 来自 出库明细 的数据 · 共 1 条
</hb-rec>
```

### hb-fbar
表单保存条：属性 cancel、save、more

```
编辑/新建底部保存条 57。属性 cancel、save、more（新建页左侧方钮）。
例：
<hb-fbar more/>
```

### hb-taskbar
任务办理区：属性 who、sub；体内按钮名 | 按钮名

```
任务办理区，任务页底部 100 高。属性 who="詹达富 · 出库审批"、sub 记录标题；体内 按钮名 | 按钮名。任务页＝hb-rec elapsed ＋ hb-taskbar，本节点可改字段加 !。
例：
<hb-taskbar who="詹达富 · 出库审批" sub="CK_20260902_001 直接出库">确认出库 | 驳回修改</hb-taskbar>
```

### hb-ptasks
流程任务列表：属性 tabs、count、dot、app；每行「发起人 | 时间 | 流程名 · 记录标题 | 节点名 | 按钮」

```
企业级流程任务列表。属性 tabs（默认 我发起的|*我处理的|发起流程）、count="筛选出 1990 条/共 17842 条"、dot（当前页签红点）、app（带底部应用页签栏）；每行 发起人 | 时间 | 流程名 · 记录标题 | 节点名 | 按钮（按钮缺省「办理 ▾」，可写「领取任务」）。
例：
<hb-ptasks count="筛选出 1990 条/共 17842 条" dot app>
詹达富 | 昨天 19:28 | 付款审批 · 待审批-啥都有集团 | 财务审批 | 领取任务
詹达富 | 昨天 01:37 | 出库审批 · CK_20260902_001 直接出库 | 出库审批
</hb-ptasks>
```

### hb-wpage
手机工作台：# 页面名；sc: 名:图标 | …；tabs: *页签 | 页签；sub: 子区名 | 全部 | *待执行 | 已完成

```
手机工作台。# 页面名 横幅；sc: 库存看板:pie-s | 出库管理:check-s 快捷方式两列；tabs: *出入库情况 | 仓库报表 标签页；sub: 出库审批 | 全部 | *待执行 | 已完成 流程任务子区（空态）。
例：
<hb-wpage>
# 库管工作台
sc: 库存看板:pie-s | 出库管理:check-s | 入库管理:trend-s | 库存盘点:chart-s
tabs: *出入库情况 | 仓库报表
sub: 出库审批 | 全部 | *待执行 | 已完成
</hb-wpage>
要在工作台里放一段明细，直接嵌一个 <hb-ocards bare>（手机端没有表格，不要放 hb-list／hb-pivot）。
```

### hb-wxapp
企业微信应用消息（发给个人）：@时间；[标签] 标题 开一条消息；k = v；> 链接；其余为正文

```
企业微信应用消息：应用推给某个人的通知，会话里只有这一个应用在说话，不出头像和发送者名（微信端样式，未实测）。群里的机器人消息用 hb-wxgroup。
@时间 出时间戳；[标签] 标题 开一条带标签的消息，! 标题 开一条无标签消息；字段 = 值（等号两边有空格）出键值行；> 文字 出底部链接；其余行是正文。
例：
@今天 09:21
[取货审批 · 待办] 王丽娟 的取货申请待你确认
门店 = 朝阳门店 · 经手 李明
> 去确认
@昨天 17:06
! 本周配货已确认
8 家门店的配货申请已由库管确认，合计 76 件。
```

### hb-wxgroup
企业微信群消息：@时间；!机器人名 开一条；^小标题 / #大标题 / *大数字 / ~灰底块 / "引用 / k = v / >查看详情

```
企业微信群消息：群里的机器人卡片（2026-09-21 按群消息截图比例换算，非 DOM 实测）。
每条消息左边是机器人头像、上面一行发送者名，卡片里按需要放这几种行：
  @15:20            居中时间戳
  !跟进助手          开一条新消息，写发这条的机器人名；要换头像图标写 !跟进助手:bell
  ^ 💡 服务资源通知   卡片顶部小灰标题，下面自动带一条虚线
  # 服务包消费记录    卡片大标题
  * -0 工时 | 2026-09-21   居中大数字，第二段是副行
  ~ 服务记录已自动归档     灰底提示块
  " 咨询陪玩系统，要看演示  引用块（左侧竖线）
  客户名称 = 老苞米电竞     字段行；值写成 18204580942:link 出蓝色
  > 查看详情          卡片底部链接行
属性 chips="事项管理:linkout | 添加:plus" 出输入条上方的群机器人快捷入口；input 改输入框占位；noinput 不画输入条。
例：
<hb-phone title="商机跟进群(7)">
<hb-wxgroup chips="事项管理:linkout | 添加:plus">
@15:20
!跟进助手
# ⭐ 客户分配通知
客户分配至 = 礼礼互娱
客户名称 = 老苞米电竞
联系人电话 = 18204580942:link
" 咨询陪玩系统，要看演示
> 查看详情
</hb-wxgroup>
</hb-phone>
```

### hb-conn
屏间中缝说明：每行「步骤标题 | 一句说明」，行间自动加箭头

```
屏间中缝，每行 步骤标题 | 一句说明，行间自动加大箭头。
例：
企业微信收到待办 | 不用另装 App，消息点进去就能办
进入本人工作台 | 销售只看得到自己名下的客户与存货
```

手机上没有独立的「审批流程条」组件：审批走流程任务列表（hb-ptasks）和记录页＋任务办理区（hb-rec ＋ hb-taskbar），不要画 PC 那种时间线。
手机端没有表格形态：列表页、自定义页面里的明细，一律用 hb-ocards 画成三槽卡片；hb-grid／hb-list／hb-pivot／hb-kanban／hb-cards 放进 hb-phone 会报错。


## 手机端 · 门户（2026-09-21 实测）

### hb-ptop
门户顶栏：属性 name（门户名）、user（登录人姓名，出头像）、login（未登录时的按钮名）

```
门户顶栏 44，替代 hb-phone 自带的返回顶栏（外层写 <hb-phone nobar>）。属性 name（门户名，必填）、user（登录人姓名，右侧出 24 圆头像）、login（未登录时右侧按钮名，默认「登录」）。自闭合写法。
未登录出登录按钮，登录后出头像；两者不同时出现。
例：
<hb-ptop name="伙伴生态合作" user="周敏"/>
<hb-ptop name="伙伴生态合作"/>
```

### hb-pnav
门户导航条：一级页签，* 前缀＝当前，名后缀 :g ＝分组页签；属性 fill、scroll

```
门户一级导航条 44＋1px 底线，紧跟 hb-ptop。体内一行写完所有页签，* 前缀＝当前页签，名后缀 :g ＝分组页签（带 ▾，排在最后，点开是 hb-pmenu）。
页签 3 个以内平分整宽；再多就按内容宽从左排、整条横向滚动（右侧渐隐），也可用属性 fill／scroll 指定。选中态只有下方 30×2 主色横条，文字不变色。
例：
<hb-pnav>
工作台 | *生态帮助手册 | 客户管理 | 年费管理 | 物料库:g
</hb-pnav>
```

### hb-pmenu
门户分组菜单：分组页签展开的面板＋蒙层；每行 名称:图标

```
分组页签展开后的面板，紧跟 hb-pnav：面板从导航条垂下来（导航条下压一条 2px 主色线），面板以下整屏盖 45% 黑蒙层。每行「名称:图标」，图标用表或页面自己的图标。
只在讲「门户里怎么找到这一页」时画；平时不画展开态。
例：
<hb-pnav>*生态帮助手册 | 物料库:g</hb-pnav>
<hb-pmenu>
自定义组件:app-s
产品功能边界:doc
</hb-pmenu>
```

### hb-plogin
门户登录页：属性 name、wechat、bg、phone、captcha、code、submit

```
门户登录页，整屏一块，外层写 <hb-phone nobar>。属性 name（门户名，必填）、wechat（出微信登录按钮，可给文案）、bg（铺门户自配的品牌底图；不给就是默认白底）、phone／captcha（两个输入框的占位，默认「手机号」「验证码」）、code（默认「获取验证码」）、submit（默认「登录」）。
登录按钮画成未填写的浅色态，卡底固定带 Powered by 伙伴云 ｜ 免责声明 ｜ 投诉。
例：
<hb-phone nobar fix><hb-plogin name="伙伴生态合作" wechat/></hb-phone>
```

### hb-pme
个人中心：属性 who、out；每行 字段名 | 值 | 右侧操作，-- 另起一张卡

```
个人中心（点门户顶栏头像进，是独立页不是浮层）。外层写 <hb-phone title="个人中心" nodots>。属性 who（登录人姓名，必填）、out（底部按钮名，默认「退出登录」）。
体内每行「字段名 | 值 | 右侧操作(可选)」，-- 单起一行表示另起一张卡。
例：
<hb-phone title="个人中心" nodots fix>
<hb-pme who="周敏">
手机号 | 138****6021 | 更换
微信 | 周敏
--
语言 | 简体中文 ▾
</hb-pme>
</hb-phone>
```

手机上没有独立的「审批流程条」组件：审批走流程任务列表（hb-ptasks）和记录页＋任务办理区（hb-rec ＋ hb-taskbar），不要画 PC 那种时间线。
手机端没有表格形态：列表页、自定义页面里的明细，一律用 hb-ocards 画成三槽卡片；hb-grid／hb-list／hb-pivot／hb-kanban／hb-cards 放进 hb-phone 会报错。

