# 旅迹 LVJI 比赛演示 · 设计方案

## 全局约定

### ① 画布与安全区
- 画布 1280×720，padding 上下 60 / 左右 60
- 内容区 1160×600（y 60–660）
- 页脚 y = 670，字号 15，全篇固定
- 封面 / 封底 / 章节页允许出血；内容页不越界

### ② 配色（沿用产品自身视觉系统，保证 PPT 与界面同源）
| 槽位 | 色值 | 用途 |
|---|---|---|
| 主色 | `#0C3B3C` 墨绿 | 标题、主视觉底、编号、图表主系列 |
| 辅色 | `#F4EFE7` 浅米 | 分区底、表格斑马纹、图表第二系列底 |
| 强调色 | `#D8623B` 砖红 | 关键数字、提升量、对照系 |
| 底色 | `#FBF8F3` 米白 | 页面主背景 |
| 正文色 | `#12211F` | 标题与正文 |
| 辅助文字 | `#435B57` / `#7C918D` | 说明与注释 |
| 线 | `#E4DCD0` / `#D3C8B8` | 分隔线、表格线 |
| 语义 | `#B8862B` 金 | 半定量标签 |

面积纪律：主色 ≤60% / 辅色 ≤30% / 强调色 ≤10%

### ③ 字体系统
- 中文：微软雅黑（Microsoft YaHei）
- 西文：Helvetica Neue / Arial
- 字号阶梯：封面主标 64 / 章节大字 44 / 巨型数据 96 / 页面主标 34 / 卡片小标 22 / 正文 18 / 注释与表格 15
- 全篇两种字体家族，仅靠字号字重拉层级

### ④ 视觉母题
- 主标题左上方一枚 8×8 墨绿方块 + 主标题，作为全篇唯一的分区标识（不下放到卡片）
- 页脚左侧「旅迹 LVJI · 一日行程编排」，右侧页码

### ⑤ 配图清单
| 文件 | 用途 | 生成方式 | 真实内容 | 使用页 |
|---|---|---|---|---|
| `assets/ui-matrix.png` | 证据 | 产品截图 | 九维评分矩阵界面 | P5 |
| `assets/ui-solver.png` | 证据 | 产品截图 | 收敛曲线 + 最优性验证表 | P6 |
| `assets/ui-timeline.png` | 证据 | 产品截图 | 一天时间轴（长辈组） | P8 |
| `assets/ui-route.png` | 证据 | 产品截图 | 按经纬度绘制的多站点路线 | P8 |

封面与封底走主色纯色底 + SVG 细线经纬网格，不生图（避免 AI 图风格漂移）。

---

## 逐页设计

### P1 封面
- type: cover / role: hero / rhythm: peak
- layout: 墨绿出血底 + 细线网格，左对齐巨字标题
- visual: SVG 经纬网格装饰（低频、低对比）
- density: 字数约 40 / 图片 0 / 留白约 45%
- anti_pattern: 禁止居中对称排版；禁止在封面放页脚与页码；禁止叠加 AI 生成的实景照片
- description: 主标题「一句话，排好一天。」副标题说明把模糊需求变成可执行时间轴。品牌「旅迹 LVJI」与挑战 2 标识

### P2 为什么这件事不简单
- type: content / role: supporting / rhythm: valley
- layout: 左定义 + 右组合爆炸数字
- visual: 巨字「40,320」与公式标注
- density: 字数约 180 / 图片 0 / 留白约 30%
- anti_pattern: 禁止用三列等分卡片罗列难点；禁止只写「NP-hard」不解释
- description: 把它定义成 TOPTW：选哪些点、按什么顺序、每个点必须落在开放窗内、当天时间预算内总价值最大。8 个景点只有 40320 种排列，14 个景点是 87 亿

### P3 两层算法：先构造，再搜索
- type: content / role: supporting / rhythm: valley
- layout: 上下两段流程，配因果说明
- visual: SVG 流程图（构造 → 评估 → 邻域 → 接受）
- density: 字数约 220 / 图片 0 / 留白约 25%
- anti_pattern: 禁止四格并列；禁止把两层做成左右对称双栏
- description: 第一层贪心构造给出可行解；第二层在访问顺序的排列空间做 ILS，交换 / 移动 / 引入候选点，只接受更优

### P4 九个维度，三种性质
- type: content / role: supporting / rhythm: valley
- layout: 表格（维度 / 性质 / 权重 / 判定依据）
- visual: 表格 + 右侧性质分布说明
- density: 字数约 300 / 图片 0 / 留白约 20%
- anti_pattern: 禁止把九维画成九宫格图标；禁止只给权重不给口径
- description: 定量 5 项（口碑、排队、路上、门票）、半定量 2 项（天气、步行）、定性 2 项（兴趣、人群、无障碍）

### P5 界面把每个影响因素摊开
- type: content / role: supporting / rhythm: valley
- layout: 大图为主 + 下方三条解读
- visual: `assets/ui-matrix.png` 占内容区约 65%
- density: 字数约 150 / 图片 1 张 / 留白约 15%
- anti_pattern: 禁止图左文右对半开；禁止在图上下各堆一段说明
- description: 每个景点一行、九个维度一列，格子深浅代表得分绝对值；右侧标出「硬约束出局」与「评分未入选」两类落选原因

### P6 最优性验证（核心页）
- type: content / role: hero / rhythm: peak
- layout: 顶部巨字数据带 + 底部验证表
- visual: 巨字「0.00%」+ `assets/ui-solver.png` 局部
- density: 字数约 160 / 图片 1 张 / 留白约 30%
- anti_pattern: 禁止把 0.00% 塞进卡片角落；禁止用装饰图标代替数字
- description: 6 个点 720 种排列全穷举，3/3 组命中可证明最优；n=8 时穷举 1391.8ms，本方案 18.5ms，75 倍

### P7 与「让大模型直接写行程」的差别
- type: content / role: supporting / rhythm: valley
- layout: 对比表（四行三列）
- visual: 表格，我方列用主色提亮
- density: 字数约 240 / 图片 0 / 留白约 25%
- anti_pattern: 禁止使用「更强 / 更优 / 领先」这类无数据托底的词；禁止对我方打勾对方打叉的符号化对比
- description: 时间可行性、约束满足、结果可复现、失败可解释四个轴，逐格给可度量的值

### P8 一个真实案例讲透
- type: content / role: supporting / rhythm: valley
- layout: 左时间轴截图 + 右路线图与前后数字
- visual: `assets/ui-timeline.png` + `assets/ui-route.png`
- density: 字数约 200 / 图片 2 张 / 留白约 15%
- anti_pattern: 禁止把两张图做成等大并排；禁止只讲成果不讲约束冲突
- description: 轮椅奶奶 + 两个孩子，自动拆两组、午餐同店汇合、撞点错峰；构造 91.9 分 → 搜索后 98.1 分，多排出 1 个景点

### P9 七项要求逐条落地
- type: content / role: supporting / rhythm: valley
- layout: 两列表格（要求 / 实现位置）
- visual: 表格
- density: 字数约 320 / 图片 0 / 留白约 15%
- anti_pattern: 禁止每条后面跟一句形容词式自评；禁止只写「已实现」
- description: 逐条写清对应的函数或界面模块名，可当场指认

### P10 这不止是出差工具
- type: content / role: hero / rhythm: peak
- layout: 巨字主张 + 场景清单
- visual: 竖排场景清单，主色渐进
- density: 字数约 180 / 图片 0 / 留白约 35%
- anti_pattern: 禁止九宫格场景图标墙；禁止「多场景覆盖」这类空话标题
- description: 同一套约束引擎，换成不同的约束集就是不同产品：陪爸妈复诊、带娃周末、朋友聚会、无障碍出行、外国朋友来华

### P11 数据与技术
- type: content / role: supporting / rhythm: valley
- layout: 三段纵向架构 + 右侧接口清单
- visual: SVG 分层架构
- density: 字数约 230 / 图片 0 / 留白约 25%
- anti_pattern: 禁止画成三层等宽色块；禁止用云朵图标表示服务
- description: 自建前端 + 本地数据集 + 本地 mock API，7 个接口全部记录调用耗时与返回行数

### P12 收尾
- type: ending / role: hero / rhythm: peak
- layout: 墨绿出血底，居中一句主张 + 演示地址
- visual: 与封面同款网格母题
- density: 字数约 50 / 图片 0 / 留白约 50%
- anti_pattern: 禁止在封底写「谢谢观看」；禁止放页脚
- description: 主张句 + 现场可复跑的验证入口
