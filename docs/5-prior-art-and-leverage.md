# RivalLens Prior Art 调研与借鉴策略

> 本文回答两个问题：已经有哪些类似的开源 / 商业系统？RivalLens 借什么、不借什么、答辩怎么讲？
> 目的：不重复造轮子，把工程精力集中在评分核心的原创层。

## 1. 调研结论

竞品分析 / 自动调研 Agent 领域已经有两个 LangGraph 多 Agent 成熟开源项目和两款商业 SaaS 头部产品，RivalLens 在它们的肩膀上做差异化。

| 维度 | 已有 | RivalLens 自做 |
|---|---|---|
| LangGraph DAG 骨架 | Open Deep Research | 不重写，借鉴 supervisor + state machine 模式 |
| 多 Agent 反馈闭环 | GPT Researcher Reviewer + Revisor | 不重写，借鉴 prompt 与消息结构，改造为结构化 rejection 协议 |
| 报告章节模板 | Crayon Leadership Report、Klue Battlecard | 不重写，借鉴章节结构 |
| 竞品知识 Schema | 无成熟开源 | 自研，赛题硬性要求 |
| Evidence 结论级溯源 | 开源仅段落级引用 | 自研，赛题硬性要求 |
| QA 规则 DSL | 开源仅自然语言判断 | 自研，赛题"非伪闭环"杀手锏 |
| 数据脱敏 | 开源不强调 | 自研，命中评分 10% 合规 |
| 行业包配置 | 开源是通用调研 | 自研，赛题"通用核心 + 场景配置" |

## 2. 必看的开源近亲

### 2.1 `langchain-ai/open_deep_research`

- 仓库：<https://github.com/langchain-ai/open_deep_research>
- 许可证：MIT
- Stars：约 11.4K
- 维护方：LangChain 官方
- 评测排名：Deep Research Bench Leaderboard 第 6（0.4344），对标 OpenAI / Anthropic / Perplexity 商业 deep research

架构：

```text
LangGraph Supervisor Agent
  ├─ Scope（澄清研究范围 + 生成 brief）
  ├─ Research（按 supervisor 策略调研）
  └─ Write（生成最终报告）
```

配置式 LLM：summarization、research、compression、final_report 各自指定模型。支持多搜索工具与 MCP server。LangGraph Studio UI 提供 DAG 可视化。

借鉴维度：

- supervisor agent 状态机模式
- 三阶段 → 五阶段（Collector / Extractor / Analyst / Writer / QA）的同构改造
- 配置式 LLM 选型（不同 Agent 用不同模型）
- LangGraph Studio 风格的前端 DAG 可视化

不借鉴：

- 通用 web search，RivalLens 演示用预置数据集
- 论文型报告输出，RivalLens 是结构化竞品知识 + battlecard 风格

### 2.2 `assafelovic/gpt-researcher`

- 仓库：<https://github.com/assafelovic/gpt-researcher>
- 许可证：Apache-2.0
- Stars：约 27K
- 8 个专职 Agent：Chief Editor / Researcher / Editor / Reviewer / Revisor / Writer / Publisher / Human
- 工作流：Planning → Parallel data collection on subtopics → Review/Revision → Writing → Publication

借鉴维度：

- **Reviewer + Revisor 反馈闭环模式**是 QA 打回的成熟实现，借鉴其 prompt 模板与反馈消息结构
- "Parallel research on subtopics" = 节点级并行的现成参考，借鉴 LangGraph Send / map-reduce 用法
- 五阶段流程的 DAG 节点切分思路

不借鉴：

- 8 Agent 全套，RivalLens 收敛到 5 个（Collector / Extractor / Analyst / Writer / QA），删除 Chief Editor / Publisher / Human
- Reviewer 的自然语言反馈，RivalLens 改造为结构化 rejection JSON + 规则 DSL
- 通用研究主题，RivalLens 专注竞品分析

## 3. 商业 SaaS 产品形态参考

### 3.1 Klue（<https://klue.com>）

竞品情报赛道第一品牌。核心形态：

- **Battlecards**：单张卡片浓缩一个竞品的弱点、定价、销售话术
- 浏览器扩展从社交媒体、新闻、网站采集 intel
- Intel Digests 定期分发洞察
- Compete Agent 提供实时销售情报

借鉴维度：

- 报告页 UI：每个竞品一张可点击展开的紧凑 battlecard，比长文本报告专业得多
- "Intel 采集 → 结构化 → 分发"的产品叙事链路

### 3.2 Crayon（<https://www.crayon.co>）

竞品情报赛道第二品牌。核心形态：

- 四块结构：Analyze / Enable / Compete / Measure
- **Leadership Reports**：聚合 1-2 年时间窗口的 call clips / win-loss / CRM / 产品更新 / 社交媒体 / 新闻
- AI 新闻总结 + AI 重要性评分

借鉴维度：

- 报告章节模板：功能对比 → 定价对比 → 用户反馈 → 差异化分析 → SWOT → 战略建议
- 重要性评分 / confidence 字段的产品化呈现

## 4. 借鉴清单（按层级）

### 4.1 底座层（节省约 50% 开发量）

| 借鉴自 | 借什么 | 落到 RivalLens 哪里 |
|---|---|---|
| Open Deep Research | LangGraph supervisor 状态机骨架 | `backend/agents/orchestrator.py` |
| Open Deep Research | 配置式多 LLM 模型选型 | `backend/llm/llm_client.py` |
| GPT Researcher | Reviewer + Revisor 反馈闭环 prompt 模板 | `backend/agents/qa_agent.py` |
| GPT Researcher | LangGraph Send / map-reduce 并行 subtopic 模式 | `backend/agents/collector_agent.py`、`extractor_agent.py` |
| LangGraph 1.0+ | checkpoint（PG 后端）、interrupt、time-travel | `backend/orchestration/checkpoint.py` |
| LangGraph Studio | DAG 可视化交互范式 | `frontend/src/components/DagRunView.tsx` |

### 4.2 报告与 UI 层

| 借鉴自 | 借什么 | 落到 RivalLens 哪里 |
|---|---|---|
| Klue Battlecard | 单竞品紧凑卡片 UI | `frontend/src/components/CompetitorCard.tsx` |
| Crayon Leadership Report | 报告章节模板 | `industry_packs/ai_coding_tools/report_template.yaml` |
| Crayon | confidence / importance 评分呈现 | Schema 的 `Conclusion.confidence` 字段 |

### 4.3 禁止动作

- 整体 fork 任一开源项目改名提交。评委一眼能看出。
- 复制 GPT Researcher 的 8 Agent 角色到 RivalLens。角色冗余且和评分不对齐。
- 引入 GPL / AGPL / SSPL / Community License 的源码或前端。
- 抄 Klue / Crayon 的具体页面像素级 UI（截图照搬有侵权风险）。

## 5. 原创层（评分核心 60%+）

这些是 RivalLens 必须自己设计且评分直接对应的部分：

| 模块 | 评分对齐 | 文档位置 |
|---|---|---|
| 竞品知识 Schema + 行业包扩展机制 | 35% 多 Agent 可信度 | `docs/3-schema-and-protocol.md` 第 2–3、7 节 |
| Evidence 与 Conclusion 多对多结论级溯源 | 35% 多 Agent 可信度 + 业务体验 20% | `docs/3-schema-and-protocol.md` 第 5 节 |
| 结构化 QA rejection 协议 + 轻量规则 DSL | 35% "非伪闭环"杀手锏 | `docs/3-schema-and-protocol.md` 第 4、6 节 |
| 数据脱敏架构 | 10% 合规 | `docs/2-architecture-decision.md` 第 7 节 |
| TRAE / Cursor 协作工程化痕迹 | 10% 代码质量 | `docs/4-team-ownership.md` 第 5 节 |
| 节点级并行 + 任务级并发设计 | 25% 工程完整度 + 35% 可视化 | `docs/2-architecture-decision.md` 第 9 节 |

## 6. 许可证记录与合规

第一版依赖 + 许可证清单（动态维护，最终在 `README.md` 与提交材料中固化）：

| 依赖 | 用途 | 许可证 |
|---|---|---|
| langgraph | DAG 编排 | MIT |
| langgraph-checkpoint-postgres | LangGraph PG checkpoint | MIT |
| langchain-core | LLM 调用基础 | MIT |
| fastapi | 后端框架 | MIT |
| pydantic | 数据校验 | MIT |
| pydantic-settings | Secrets / 配置读取 | MIT |
| sqlalchemy | ORM | MIT |
| alembic | DB 迁移 | MIT |
| asyncpg | PG 异步驱动 | Apache-2.0 |
| psycopg2-binary | PG 同步驱动 | LGPL（仅 driver，不影响项目协议） |
| httpx | HTTP 客户端 | BSD-3-Clause |
| reppy / urllib.robotparser | robots.txt 解析 | MIT / Python 标准库 |
| react | 前端 | MIT |
| vite | 前端构建 | MIT |
| typescript | 前端语言 | Apache-2.0 |
| @xyflow/react | DAG 可视化 | MIT |
| shadcn/ui | UI 组件 | MIT |
| tailwindcss | CSS | MIT |

参考但不引入源码的项目：

| 项目 | 许可证 | 状态 |
|---|---|---|
| Open Deep Research | MIT | 阅读源码，借鉴架构，不复制代码 |
| GPT Researcher | Apache-2.0 | 阅读源码，借鉴 prompt 与反馈结构，不复制代码 |
| Klue / Crayon | 闭源 | 仅看产品形态，不抄 UI |

