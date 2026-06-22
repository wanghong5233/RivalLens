# RivalLens

> AI 驱动的竞品分析与追踪系统：对话式开题 → 多 Agent 调研 → 商业报告 → 竞品知识库 → 持续监控。

![Demo](https://img.shields.io/badge/demo-live-brightgreen)
![Python](https://img.shields.io/badge/python-3.11-blue)
![Frontend](https://img.shields.io/badge/frontend-React%2BVite-61dafb)
![Orchestration](https://img.shields.io/badge/agents-LangGraph-orange)
![License](https://img.shields.io/badge/license-MIT-green)

## Demo

在线体验：**<https://rival-lens.vercel.app>**（无需登录）

演示录屏：**<https://vai39ofzgbz.feishu.cn/file/Lldzb2H6zosbP4xLiv8ceE7Fn0f?from=from_copylink>**

体验路径：首页输入分析需求 → Agent 多轮澄清 → 确认任务计划 → Live 页实时观察执行 → 查看报告 / 竞品知识 / 证据溯源 / 追踪面板。

## 目录

- [Background](#background)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Tech Stack](#tech-stack)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Background

传统竞品分析（信息搜集 → 功能对比 → 评价整理 → SWOT → 报告）重复性高、信息源分散、依赖个人行业认知。RivalLens 用多 Agent 调研链路把一句自然语言需求转成可执行计划，自动完成竞品发现、公开证据采集、跨竞品分析、商业报告写作与后续追踪；报告结论绑定证据来源，关键 Agent 决策可回放审计。

## Features

- **对话式开题**：Intake Agent 多轮澄清 + 建议答案，补齐用户角色、分析意图、赛道范围与竞品发现方式
- **双报告形态**：支持 `comparison` 竞品对比与 `landscape` 赛道全景；Writer 按章节深度写作，避免短列表报告
- **产品实例建模**：竞品按“赛道 → 产品 → 功能 / 定价 / 人群 / 反馈”组织，区分产品、公司与上游供应商
- **证据优先采集**：Bocha / Serper / Tavily 搜索路由 + Jina Reader 全文兜底，遵守 `robots.txt` 与站点限速
- **质量反馈闭环**：QA 规则 + LLM 语义审查，拦截无证数字、占位正文、旧模板章节和证据覆盖不足
- **竞品追踪**：把报告中的产品加入 watchlist，持续刷新 profile、近期变化、洞察和下次追踪建议
- **全链路溯源**：报告 citation 一键跳转 Evidence Console，查看来源、正文片段与采集阶段
- **实时可观测**：SSE Live 页展示 Agent 步骤、工具调用、合规跳过、Trace DAG 与 token 消耗

## Architecture

```mermaid
flowchart TB
    User([用户 · 一句话竞品分析需求])

    subgraph HITL["① 需求澄清 + 计划确认 · HITL"]
        direction LR
        Intake[Intake Agent<br/>多轮澄清] --> Planner[Planner Agent<br/>生成任务树 PlanTree]
    end

    subgraph Loop["② 执行编排 · LangGraph 多 Agent 协作"]
        Sup{{Supervisor<br/>运行时 LLM 工具委派}}
        Discovery[Discovery<br/>竞品发现]
        Researcher[Researcher ×K<br/>ReAct 并行调研]
        Analyst[Analyst<br/>跨竞品结论矩阵]
        Writer[Writer<br/>逐章节报告写作]
        QA{{QA Reviewer<br/>规则 + 语义双层}}

        Sup --> Discovery & Researcher & Analyst & Writer
        Writer --> QA
        QA -->|reject_to 精准打回| Sup
    end

    Collector[/采集通道<br/>Bocha · Serper · Tavily · Jina Reader/]
    PG[(PostgreSQL<br/>evidence · conclusions · knowledge · watchlist)]
    Watch[Watchlist<br/>定时刷新 + 变更监控]
    Curator[/Skill Curator<br/>异步沉淀技能/]
    Report([商业报告 · 竞品知识 · 全链路溯源])

    User --> Intake
    Planner -->|用户确认| Sup
    Researcher <-->|robots / 限速 / 脱敏| Collector
    Loop --> PG
    Sup -->|Finalize| Report
    PG --> Watch
    PG -.-> Curator -.->|人工审核生效| Sup
```

| Agent | 职责 |
|---|---|
| Intake | 多轮澄清，补齐角色 / 意图 / 竞品范围（HITL） |
| Planner | 生成任务树 PlanTree，等用户确认（HITL） |
| Supervisor | 执行期 LLM 工具委派，唯一调度中枢 |
| Discovery / Replanner | 竞品自动发现 / 执行期计划修订 |
| Researcher ×K | ReAct 子图并行采集、全文抓取、证据结构化 |
| Analyst | 跨竞品结论矩阵（每条 ≥1 证据） |
| Writer | 生成全景报告 / 对比报告，按章节深化正文 |
| QA Reviewer | 规则审查 + 语义审查 + 多目标 rejection 路由 |
| Skill Curator | run 后异步沉淀技能候选，人工审核生效 |

## Quick Start

```bash
# 1. 后端（Docker）
cd backend
cp .env.dev.example .env.dev        # 填入 LLM / 搜索 API Key
docker compose -f docker-compose.dev.yml up -d rivallens_db rivallens_api
docker compose -f docker-compose.dev.yml exec -T rivallens_api alembic upgrade head

# 2. 前端
cd ../frontend
npm install
npm run dev                          # http://localhost:5173
```

后端默认 `http://localhost:8010`，健康检查 `GET /health`。

## Tech Stack

| 层 | 技术 |
|---|---|
| 前端 | React 18 · Vite · TypeScript · Tailwind · shadcn/ui · @xyflow/react（Trace DAG） |
| 后端 | FastAPI · SQLAlchemy · Pydantic v2 · LangGraph（checkpoint-postgres） |
| LLM | Qwen / Doubao / OpenAI 多 provider，slot→tier→catalog 分档路由，JSON mode + repair prompt |
| 检索 | Bocha / Serper / Tavily 搜索路由，Jina Reader 全文兜底，robots.txt 合规 + 站点限速 |
| 存储 | PostgreSQL 16（runs / steps / llm_calls / evidence / conclusions / run_knowledge / watchlist / competitor_diffs） |
| 部署 | Docker Compose + Cloudflare Tunnel（API 公网）+ Vercel（前端） |

## Documentation

- 赛题背景：[`docs/0-problem-background.md`](./docs/0-problem-background.md)
- 架构决策：[`docs/2-architecture-decision.md`](./docs/2-architecture-decision.md)
- 多 Agent 架构：[`docs/2.5-agent-architecture.md`](./docs/2.5-agent-architecture.md)
- Schema 与协议：[`docs/3-schema-and-protocol.md`](./docs/3-schema-and-protocol.md)
- 测试用例：[`docs/7-test-cases.md`](./docs/7-test-cases.md)
- 合规声明：[`docs/6-compliance-statement.md`](./docs/6-compliance-statement.md)

## Contributing

欢迎提 Issue 或 PR。提交前执行 `cd frontend && npm run type-check` 与后端容器内 `pytest`。

## License

MIT
