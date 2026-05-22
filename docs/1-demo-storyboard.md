# RivalLens 答辩演示剧本

> 本文定义 RivalLens 第一版的答辩演示主线。架构、Schema、分工和开发优先级都从这份剧本反推。

## 1. 演示定位

### 主演示行业

RivalLens 第一版锁定 **AI Agent 产品赛道**，主演示子集为 **AI Coding 工具**。

主演示竞品：

- Cursor
- Windsurf
- TRAE
- Claude Code

选择理由：

- 与导师举例的“通用类型的 Agent 有哪些产品”高度贴合，降低评委理解成本。
- 竞品官网、文档、定价页、用户评论和产品讨论公开资料丰富。
- 评委大概率熟悉 AI Coding 工具，可以现场判断分析结论是否可信。
- 与比赛要求使用 TRAE 等 AI 编程工具形成叙事闭环：RivalLens 分析的对象之一就是 AI Coding 工具。

### 目标用户

第一版只服务两类用户：

- 产品经理 / 产品负责人：关注功能树、差异化、定价、用户反馈、可借鉴点。
- 创业者 / CEO / 项目负责人：关注市场机会、定位、商业模式、风险和 SWOT。

暂不进入主演示：

- 销售话术型竞品分析。
- 投资研究型深度报告。
- UX 标杆拆解。
- 增长投放素材分析。

## 2. 演示数据集策略

录屏和答辩演示使用 **预置数据集 + 可选在线刷新** 的方式。

### 数据来源类型

- 官方来源：官网首页、产品文档、定价页、功能介绍页、更新日志。
- 公开评论：Product Hunt、G2、Reddit、X 等公开讨论。
- 补充材料：公开访谈、公开测评、开发者博客。

### 数据处理规则

- 不使用公司内部、私域群聊、非授权访谈内容。
- 公开评论进入 evidence 表前必须脱敏，去除用户名、头像、邮箱、手机号等可识别信息。
- 录屏时优先读取本地预置数据，避免外网抖动影响演示。
- 每条报告结论必须可追溯到 evidence 记录，evidence 记录必须包含来源 URL 或本地文档引用。

### 数据集目录建议

```text
data/demo/ai_coding/
  sources.yaml
  raw/
  sanitized/
  seeds/
  expected_failures/
```

## 3. 录屏时间轴

目标录屏长度：7 到 8 分钟。

| 时间 | 画面 | 要证明的能力 |
|---|---|---|
| 0:00-0:30 | 首页输入任务：“分析 AI Coding 工具赛道，竞品 Cursor / Windsurf / TRAE / Claude Code，目标用户为产品经理和创业者” | 范围收敛，贴合真实业务场景 |
| 0:30-1:20 | 创建 run，DAG 视图展开：4 个并行 Collector 子节点（按竞品 fan-out）+ Extractor（按竞品并行）+ Analyst（按 feature 维度并行）+ Writer + QA | 多 Agent 角色清晰，DAG 可视化，节点级并行结构一眼可见 |
| 1:20-2:30 | 4 个 Collector 子节点同时点亮并完成，evidence 数量随抓取实时累加，左侧来源清单滚动刷新 | 节点级并行采集，来源可查 |
| 2:30-3:30 | Extractor 按竞品并行 fan-out，逐个产出 feature tree / pricing / persona / feedback 结构化分片 | 竞品知识 Schema，结构化输出，并行抽取 |
| 3:30-4:30 | Analyst 按 feature 维度并行差异分析，merge 节点聚合 SWOT，右侧 evidence refs 同步绑定 | 分析结论与证据绑定，并行收敛 |
| 4:30-5:30 | QA 节点变红，打回 Analyst：pricing 结论缺少证据 | 真实反馈闭环，非伪闭环 |
| 5:30-6:20 | Analyst 重跑补齐 pricing evidence，QA 变绿，Writer 生成报告 | 打回后输出有改善 |
| 6:20-7:10 | 报告页点击任意结论，展开证据链、原文片段、来源 URL | 结论级溯源 |
| 7:10-7:50 | Trace 时间线展示 Prompt、输入、输出、token、latency、错误重试 | 可观测性 |
| 7:50-8:00 | 切换行业包配置，展示同一 DAG 可迁移到通用 Agent 产品分析 | 通用核心 + 场景配置 |

## 4. QA 打回主线

主演示采用 **证据缺失型打回**。

选择理由：

- 与评分项“每条分析结论可定位到原始数据源”直接对齐。
- 失败条件可控，录屏稳定。
- 打回前后差异清晰，评委容易判断不是伪闭环。

### 预埋失败案例

第一次 Analyst 输出中故意包含如下问题：

```text
结论：Windsurf 在团队协作定价上比 Cursor 更适合企业团队。
问题：没有绑定 pricing page 或公开报价证据。
```

QA Agent 输出结构化 rejection message：

```json
{
  "status": "rejected",
  "target": "analyst",
  "reason": "pricing conclusion lacks evidence",
  "required_fields": ["pricing_model", "source_url", "quote"],
  "evidence_refs": [],
  "retry_policy": {
    "max_retry": 1,
    "next_agent": "analyst"
  }
}
```

重跑后 Analyst 必须补齐：

- pricing_model
- source_url
- quote 或 sanitized_text
- evidence_id

QA 再次检查通过：

```json
{
  "status": "approved",
  "target": "writer",
  "reason": "pricing conclusion now has traceable evidence",
  "evidence_refs": ["ev_pricing_windsurf_001"]
}
```

### 扩展打回类型

第二优先级，可在系统里保留但不作为主演示：

- 跨竞品冲突型：同一字段在不同来源中互相冲突，需要降级为“不确定”并要求补采。
- 幻觉抑制型：模型生成了 evidence 中不存在的功能点，QA 拒绝并要求删除或补证据。

## 5. 评分项映射

| 评分维度 | 演示画面 |
|---|---|
| 多 Agent 协作与输出可信度 35% | DAG 节点、结构化 AgentMessage、QA 打回、Schema 输出、结论溯源 |
| 技术深度与工程完整度 25% | FastAPI 后端、LangGraph 编排、Trace 时间线、token/latency、错误重试 |
| 业务价值与产品体验 20% | 报告页、证据跳转、产品经理 / 创业者视角、可迁移行业包 |
| 代码质量与文档 10% | README、架构文档、Schema 文档、TRAE / Cursor 协作记录 |
| 合规、材料与答辩 10% | 数据来源清单、脱敏记录、许可证清单、本地部署录屏 |

## 6. 任务级并发加分镜头（可选）

如时间允许，在主线录屏外加一段 30 秒"任务级并发"加分镜头：

- 同时启动两个不同 run：一个分析 AI Coding 工具赛道，一个分析企业 Agent 平台赛道。
- Run List 页面并排展示两个进行中的 DAG，状态条同步推进。
- 旁白说明："每个 run 拥有独立 run_id、artifact 目录与 Trace 上下文，PostgreSQL 行级锁与 LangGraph PostgreSQL checkpoint 支撑多任务隔离。"
- 答辩口径：用"基于 LangGraph 的并行子图编排，节点级 + 任务级双层并发"描述，不用"高并发"包装。

该镜头直接吃下 Q&A 信号"导师说支持并发更好"的加分项。

## 7. 可迁移性镜头

演示最后不再跑完整第二行业，只展示“行业包配置”切换。

示例：

```yaml
industry_pack: ai_agent_products
focus_roles:
  - product_manager
  - founder
schema_extensions:
  - agent_autonomy_level
  - tool_ecosystem
  - enterprise_security
data_source_templates:
  - official_docs
  - pricing_page
  - public_reviews
qa_rules:
  - conclusion_requires_evidence
  - pricing_requires_source_url
```

说明口径：

> RivalLens 的 DAG、Agent 协议、Evidence 模型、Trace 和 QA 规则引擎是通用核心。行业包只替换数据源模板、扩展字段、报告章节和质检参数。

## 8. 录屏底线

- 录屏前必须有完整预置数据，不依赖实时外网。
- 所有 loading 状态必须有进度反馈。
- QA 打回必须真实触发，并在数据库中留下 rejected step。
- 点击任一报告结论必须能看到 evidence。
- 录屏粗剪不晚于 2026-06-05 完成。
