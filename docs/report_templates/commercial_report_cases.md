# Commercial Report Cases

公开样例只取目录、章节组织和判断标准，不复制付费正文。

## 来源可信度与使用边界

本文件只把出版方公开页、样章或官方方法论文档作为结构依据。搜索摘要、媒体转述、付费正文不可见内容不能驱动 RivalLens 的 section 契约。

- QY Research: publisher page, visible `Description` / `Table of Contents`, accessed 2026-06-21.
  - URL: https://www.qyresearch.com/reports/5784969/ai-smart-glasses
  - 可用：report scope、市场规模/区域/类型/应用/竞争格局/公司画像/产业链/渠道/市场动态/结论的章节顺序。
  - 不可用：付费正文中的具体判断、厂商份额、销量细节。
- ResearchAndMarkets: publisher page, visible `Table of Contents`, accessed 2026-06-21.
  - URL: https://www.researchandmarkets.com/reports/6223284/smart-glasses-market-insights-analysis
  - 可用：scope/methodology、market status、type/application/region、technology、industry chain、competitive landscape、player profiles 的章节组织。
  - 不可用：付费正文中的 market estimates 和 vendor SWOT 结论。
- MarketsandMarkets: publisher page, visible summary / scope / `Table of Contents`, accessed 2026-06-21.
  - URL: https://www.marketsandmarkets.com/Market-Reports/smart-glasses-market-148134046.html
  - 可用：key takeaways、market dynamics、drivers/restraints/opportunities/challenges、ecosystem、pricing analysis、technology analysis、segments、regional coverage。
  - 不可用：独家数据表、付费样章以外的页内细节。
- IDC MarketScape: IDC official methodology/guideline plus public excerpt, accessed 2026-06-21.
  - URLs: https://www.idc.com/eu/promo/idc-marketscape/ ; https://www.idc.com/wp-content/uploads/2025/05/IDC_MarketScape_External_Use_PR_Guidelines-2025.pdf ; https://www.qualtrics.com/m/assets/au/wp-content/uploads/2023/08/IDC-MarketScape-Report-2023.pdf
  - 可用：vendor assessment 的 inclusion criteria、buyer advice、vendor profile、strengths/challenges、methodology/scoring 结构。
  - 不可用：作为市场规模类 landscape 报告的主目录来源。
- Market.us: publisher page, visible report features / coverage, accessed 2026-06-21.
  - URL: https://market.us/report/ai-smart-glasses-market/
  - 可用：市场指标、coverage、competitive landscape、company ranking 这些快速报告元素。
  - 不可用：单独决定完整报告目录。

若后续新增案例没有 publisher URL、访问日期和可用边界，必须放入“未验证参考”，不得作为代码重构依据。

## Smart Glasses / AI Smart Glasses

| 来源 | 公开结构 | RivalLens 可复用部分 |
|---|---|---|
| QY Research, `Global AI Smart Glasses Sales Market Report, Competitive Analysis and Regional Opportunities 2026-2032` | Report scope；segment-level executive summary；market size and growth by region；competitive landscape by sales, revenue, pricing, market share, rankings, M&A/expansion plans；type/application segmentation；manufacturer profiles；industry chain；sales channels；market dynamics；key findings | `landscape` 先定义市场与细分，再讲竞争格局和关键玩家；竞品矩阵只能服务于竞争格局，不做报告开头 |
| ResearchAndMarkets, `Smart Glasses Market Insights, Analysis and Forecast 2026-2031` | Market size and growth；regional market analysis；market segmentation and types；value chain and supply chain；key market players and competitive landscape；opportunities；challenges；table of contents | 适合 AI 硬件/智能眼镜类报告：市场定义、区域、类型、价值链、玩家组、机会/挑战是主线 |
| MarketsandMarkets, `Smart Glasses Market Report 2024-2030` | Market summary；key takeaways；drivers；restraints；opportunities；challenges；ecosystem analysis；segments by technology/application/industry/region；recent developments；key players | `executive_summary` 应写 key takeaways，而不是复述证据；机会/挑战必须和 driver/restraint 分开 |
| Market.us, `Global AI Smart Glasses Market Size and Forecast` | Market value；forecast revenue；CAGR；historic period；report coverage；competitive landscape；company ranking | 快速报告也需要市场指标和 coverage，不应只给定性趋势 |

## Vendor Assessment

| 来源 | 公开结构 | RivalLens 可复用部分 |
|---|---|---|
| IDC MarketScape vendor assessment samples | IDC opinion；market trends；vendor inclusion criteria；advice for technology buyers；vendor summary profiles；strengths/challenges；vendors to watch；methodology；strategy/capability criteria | 如果用户要“选供应商/对比竞品”，先声明 inclusion criteria 和评分维度，再给 vendor profiles |

## 成熟报告的共同骨架

| 顺序 | Section | 作用 |
|---|---|---|
| 1 | Executive takeaways | 3-5 条用户要带走的判断 |
| 2 | Market definition and scope | 定义本报告算什么、不算什么 |
| 3 | Market size, growth, and drivers | 规模、增速、驱动、约束 |
| 4 | Segmentation | 按类型、应用、区域或客户场景拆市场 |
| 5 | Competitive landscape | 玩家组、市场份额/地位、进入节奏、近期动作 |
| 6 | Key player analysis | 只分析命中目标品类的玩家 |
| 7 | Value chain / ecosystem | 上游组件、中游制造、下游渠道/生态 |
| 8 | Opportunities and challenges | 机会、风险、落地约束 |
| 9 | Strategic implications | 给 PM、战略、销售、投资者的动作 |
| 10 | Methodology and evidence boundaries | 收录标准、排除标准、数据缺口 |

## 当前错误形态

| 错误 section | 为什么不适合作为一级标题 |
|---|---|
| 竞品分层地图 | 内部分类结果，不是用户购买报告时要先读的市场判断 |
| 逐竞品画像 | 适合附录或 vendor profile 章节，不适合作为市场报告第二节 |
| 功能/定价/口碑矩阵 | 缺真实品类证据时会变成“未知”表格；应作为 appendix 或竞争格局支撑表 |
| 2x2 定位图 | 没有量化维度和评分方法时只是伪图表 |

## 对 AI 硬件 / AI 眼镜的收录规则

| 公司证据 | 是否进入主分析 |
|---|---|
| 发布或销售 AI 眼镜、AR 智能眼镜、可穿戴 AI 硬件 | 可以 |
| 明确参与上游光学、SoC、传感器、ODM/OEM | 进入价值链，不进入终端玩家主矩阵 |
| 只有手机、云服务、企业存储、通用 AI 软件证据 | 不进入主玩家分析 |
| 只有传闻或媒体猜测 | 进入 watchlist，并标证据等级 |
