# RivalLens 团队分工与协作流程

> 本文用于保证三人都有清晰模块、真实贡献和可写进简历的项目成果。

## 1. 分工原则

- 每个人负责一个能独立展示的模块，而不是只做零散任务。
- 核心接口统一引用 `docs/3-schema-and-protocol.md`，避免口头同步字段。
- 队长掌握主链路，但不把所有可见成果都收在自己手里。
- 基础较弱成员负责低风险但高展示价值的模块，确保能在简历中讲清楚。

## 2. 模块所有权

| 成员 | 负责模块 | 主要交付 |
|---|---|---|
| 队长 | Agent 核心引擎 | LangGraph DAG、Collector / Extractor / Analyst / Writer / QA Agent、LLM Client、QA 规则引擎、整体联调 |
| Java 后端同学 | 任务与证据后端 | FastAPI 路由、PostgreSQL 表与 Alembic 迁移、Run / Step / Evidence / Report CRUD、Trace API、LangGraph PG checkpoint 接入、接口测试、Dockerfile、docker compose（含 postgres:16 服务） |
| 基础弱同学 | Evidence Console + Demo Dataset Curator | 证据卡片、来源清单、citation popover、报告引用展示、演示数据集整理、脱敏检查、录屏脚本草稿 |

## 3. 每人可写进简历的成果

### 队长

项目描述关键词：

- Multi-Agent Orchestration
- LangGraph DAG（节点级并行 + 任务级并发）
- QA Feedback Loop（结构化 rejection + 规则 DSL）
- Structured Agent Protocol
- Traceable AI Workflow
- LLM Gateway
- Prior-Art Engineering（开源借鉴与差异化）

简历表述示例：

```text
负责 RivalLens 多 Agent 核心引擎，基于 LangGraph 设计 Collector / Extractor / Analyst / Writer / QA 的 DAG 编排，利用 Send / map-reduce 实现节点级并行采集与按 feature 并行分析，自研结构化 QA rejection 协议与轻量规则 DSL 实现真闭环打回。借鉴 Open Deep Research 与 GPT Researcher 的成熟模式，原创竞品知识 Schema、Evidence 结论级溯源、行业包配置三大差异化模块。
```

### Java 后端同学

项目描述关键词：

- FastAPI Backend
- Evidence Store
- Trace API
- PostgreSQL Data Model（含 JSONB 索引）
- Alembic Migration
- LangGraph Checkpoint
- Artifact Management
- Docker Compose

简历表述示例：

```text
负责 RivalLens 任务与证据后端，基于 PostgreSQL 与 Alembic 设计 runs / steps / llm_calls / evidence / reports / artifacts 六张表，对接 LangGraph PostgreSQL checkpoint 支撑节点级并行与任务级并发，实现 Agent 执行记录、证据溯源、报告查询与本地 docker compose 一键部署。
```

### 基础弱同学

项目描述关键词：

- Evidence Review Console
- Source Traceability
- Citation UI
- Demo Dataset Curation
- Data Desensitization
- AI Product Analysis

简历表述示例：

```text
负责 RivalLens Evidence Console 与演示数据集，完成竞品公开资料整理、脱敏检查、证据卡片与报告引用交互，支持结论到来源片段的可视化溯源。
```

## 4. 接口契约

所有模块只认以下契约：

- 竞品知识 Schema：见 `docs/3-schema-and-protocol.md` 第 2 至 3 节。
- AgentMessage：见 `docs/3-schema-and-protocol.md` 第 4 节。
- Evidence：见 `docs/3-schema-and-protocol.md` 第 2 和第 5 节。
- QA 规则：见 `docs/3-schema-and-protocol.md` 第 6 节。

禁止在前端、后端、Agent 中私自新增未登记字段。

## 5. TRAE / Cursor 协作流程

评分项要求 AI 编程工具使用痕迹清晰，团队统一保留以下材料。

### 本地使用要求

- 每个成员使用 TRAE 或 Cursor 完成自己模块的至少一个 PR。
- 每个 PR 描述中写明使用了哪些 AI coding prompt。
- 关键 prompt 和截图放入：

```text
docs/ai-collaboration/
  member-lead/
  member-backend/
  member-evidence-console/
```

### Commit message 规范

```text
feat(agent): add QA rejection message model
feat(evidence): add evidence card and citation popover
docs(schema): define pricing evidence rule
test(api): cover run detail endpoint
```

如工具支持，保留：

```text
Co-Authored-By: TRAE AI <ai-coding@example.com>
```

### PR 模板

```markdown
## What

## How AI Coding Was Used

## Screenshots / Trace

## Test

## Related Schema
```

## 6. Definition of Done

### Agent 核心引擎

- LangGraph 能跑通 Collector → Extractor → Analyst → Writer → QA。
- Collector / Extractor 实现按竞品 fan-out 的节点级并行，DAG 可视化呈现多边同时点亮。
- LangGraph PostgreSQL checkpoint 工作正常，演示 run 可在中断后从 checkpoint 恢复。
- QA 能真实打回一次，并生成 `rejected` step。
- 重跑后 QA 能通过，并生成最终 report。
- 所有 LLM 调用经过 `llm_client.py`，受全局信号量约束。
- 每个 Agent 输出 artifact。

### 任务与证据后端

- PostgreSQL 16 通过 `docker compose up` 一键启动。
- Alembic 迁移可前进 / 回退。
- 六张表可初始化（runs / steps / llm_calls / evidence / reports / artifacts）。
- 支持创建 run、查询 run、查询 steps、查询 evidence、查询 report。
- 接入 LangGraph PostgreSQL checkpoint，支持任务级并发。
- `llm_calls` 能展示 token、latency、error。
- artifact 可按 run_id 和 step_id 查询。

### Evidence Console + Demo Dataset

- 能展示至少 5 条 evidence 记录。
- 点击 report conclusion 能展开对应 evidence cards。
- evidence card 显示 source_type、source_url、quote、desensitized。
- 公开评论数据已脱敏。
- 录屏脚本能覆盖 QA 打回、报告溯源、Trace 回放三个镜头。

## 7. 里程碑

### 2026-05-21 至 2026-05-24

- 冻结五份立项文档（含 `docs/5-prior-art-and-leverage.md`）。
- 冻结 schema v0.1。
- 队长完成 `langchain-ai/open_deep_research` 与 `assafelovic/gpt-researcher` 源码阅读，更新 `docs/5-prior-art-and-leverage.md` 借鉴清单与许可证记录。
- 创建前后端项目骨架，docker compose 含 `postgres:16` 服务能起来。
- 准备 AI Coding demo 数据源清单。

### 2026-05-25 至 2026-05-31

- 跑通 PostgreSQL + Alembic 六张表迁移。
- 跑通 LangGraph 最小 DAG，含 PostgreSQL checkpoint。
- 跑通 Collector 按竞品 fan-out 节点级并行采集。
- 跑通 evidence 入库与脱敏。
- 前端展示 DAG 节点（含并行子节点）与 evidence 列表。

### 2026-06-01 至 2026-06-05

- 完成 QA 打回与重跑（基于结构化 rejection 协议）。
- 完成 Extractor / Analyst 节点级并行。
- 完成报告页和 citation popover。
- 完成 Trace 时间线。
- 完成第一次录屏粗剪（含节点级并行画面与 QA 打回案例）。

### 2026-06-06 至 2026-06-09

- 修复录屏暴露的问题。
- 打磨 UI loading / error 状态。
- 完成 README、许可证清单、合规声明、答辩 PPT。
- 完成最终录屏。

### 2026-06-10

- 提交作品。

## 8. 演示日角色

| 角色 | 负责人 | 工作 |
|---|---|---|
| 主讲 | 队长 | 讲解系统价值、Agent 架构、QA 闭环 |
| 演示操作 | 队长或后端同学 | 控制录屏或现场页面 |
| 后端兜底 | Java 后端同学 | 解释数据模型、Trace、部署方式 |
| 证据与合规兜底 | Evidence Console 负责人 | 解释数据来源、脱敏、证据跳转 |

## 9. 风险与兜底

| 风险 | 兜底 |
|---|---|
| 在线采集不稳定 | 录屏使用本地预置数据集 |
| LangGraph 接入延期 | 保留单 run 的固定 DAG，先保证可演示 |
| LangGraph PostgreSQL checkpoint 适配延期 | 临时降级为内存 checkpoint，仅录屏 demo 用，演示后再补 PG 持久化 |
| 节点级并行实现复杂 | 先实现单 Collector 串行版本，DAG 可视化预留并行节点位，并行实现作为第 2 周加分项 |
| 前端 React Flow 延期 | 用静态 DAG 状态图替代复杂交互 |
| LLM 输出不稳定 | 对 demo run 使用固定 seed artifact 或缓存结果 |
| 基础弱成员开发受阻 | 队长提供页面骨架，她负责 evidence 数据、文案、样式和交互补齐 |

## 10. 队长检查清单

- 每个成员都有明确 issue。
- 每个成员每周至少有一次可展示产出。
- 每个成员的模块都能在录屏中出现。
- 每个成员的工作都能映射到评分项。
- 每个成员最后都能写出真实、有细节的简历项目经历。
