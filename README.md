# RivalLens

> AI 驱动的竞品分析 Agent 协作系统 — 2026 字节跳动 AI 全栈挑战赛参赛作品

## 项目概览

RivalLens 是一个多 Agent 协作的自动化竞品分析系统。给定一组竞品对象，系统通过 Collector / Extractor / Analyst / Writer / QA 五个专职 Agent 的 DAG 编排，自动完成"公开信息采集 → 结构化抽取 → 差异分析 → 报告撰写 → 质检反馈"的全链路工作。

核心特性：

- 多 Agent DAG 编排（LangGraph + Send/map-reduce 节点级并行 + 任务级并发）
- 自定义竞品知识 Schema（功能树 / 定价模型 / 用户画像 / SWOT）与 Pydantic 强约束
- 结构化 QA rejection 协议 + 轻量规则 DSL，真闭环打回（非伪闭环）
- 结论级证据溯源：每条 conclusion 必须绑定 ≥1 evidence_id，支持一键跳转原始来源
- 全链路 Trace：`runs / steps / llm_calls / evidence / reports / artifacts` 六表 + LangGraph PostgreSQL checkpoint
- 通用核心 + 行业包配置：演示行业 AI Coding 工具（Cursor / Windsurf / TRAE / Claude Code），架构支持平移到任意行业
- 数据脱敏架构 + robots.txt 合规 + Prompt Injection 防护

## 项目状态

立项完成 → 第 1 周开发启动。

提交截止：2026-06-10。详细时间线见下方与 [`docs/4-team-ownership.md`](./docs/4-team-ownership.md) 第 7 节。

## 技术栈

| 层 | 选型 |
|---|---|
| 编排 | LangGraph + `langgraph-checkpoint-postgres` |
| 后端 | FastAPI + Pydantic + SQLAlchemy + Alembic + Python 3.11 |
| 数据库 | PostgreSQL 16 |
| LLM | 豆包 Doubao-Seed-2.0-lite（配置式多模型预留） |
| 前端 | React + Vite + TypeScript + shadcn/ui + Tailwind + `@xyflow/react` |
| 部署 | docker compose + localhost |

完整决策、许可证清单、不引入清单见 [`docs/2-architecture-decision.md`](./docs/2-architecture-decision.md)。

## 文档导览

| 文档 | 用途 |
|---|---|
| [`docs/0-problem-background.md`](./docs/0-problem-background.md) | 赛题事实源（官方原文，禁改） |
| [`docs/0-qna-signals.md`](./docs/0-qna-signals.md) | 导师答疑信号与对项目的影响 |
| [`docs/1-demo-storyboard.md`](./docs/1-demo-storyboard.md) | 答辩演示剧本（一切倒推于此） |
| [`docs/2-architecture-decision.md`](./docs/2-architecture-decision.md) | 架构与技术栈决策 |
| [`docs/3-schema-and-protocol.md`](./docs/3-schema-and-protocol.md) | 竞品知识 Schema 与 Agent 通信协议 |
| [`docs/4-team-ownership.md`](./docs/4-team-ownership.md) | 团队分工与协作流程 |
| [`docs/5-prior-art-and-leverage.md`](./docs/5-prior-art-and-leverage.md) | Prior Art 调研与借鉴策略 |

## 快速开始

> 项目处于立项 → 开发启动阶段。`docker compose` 与代码骨架在第 1 周末（2026-05-24）完成。

```bash
# 1. 配置环境变量
cp .env.example .env
# 填入 DOUBAO_EP / DOUBAO_API_KEY（见飞书原文 / 私有环境）

# 2. 启动（待第 1 周末实现）
docker compose up

# 3. 访问
# 前端：http://localhost:5173
# 后端：http://localhost:8000
# API 文档：http://localhost:8000/docs
```

## 团队

| 角色 | 模块 |
|---|---|
| 队长 | Agent 核心引擎、LangGraph DAG、QA 规则引擎、LLM Client、整体联调 |
| 后端 | FastAPI API、PostgreSQL 数据模型、Alembic 迁移、Trace API、Artifact 管理、docker compose |
| 前端 + 数据 | Evidence Console、Report Viewer、Citation Popover、演示数据集与脱敏、录屏脚本 |

详细分工、接口契约、Definition of Done 见 [`docs/4-team-ownership.md`](./docs/4-team-ownership.md)。

## 决策与方法论

本项目所有架构决策与范围裁剪均落到 `docs/` 文档，不口头同步：

- 写代码前：先读 `docs/1-demo-storyboard.md` 对齐评分对应画面
- 改 Schema：先改 `docs/3-schema-and-protocol.md`，再改 Pydantic 模型
- 加依赖：必须为 MIT / Apache-2.0 / BSD 协议，更新 `docs/5-prior-art-and-leverage.md` 第 6 节许可证清单
- 借鉴开源：必须为只读参考，不复制源码，借鉴维度写入 `docs/5-prior-art-and-leverage.md` 第 4 节

## Prior Art 致谢

RivalLens 在以下开源项目的肩膀上做差异化，借鉴架构与模式但不复制代码：

- [`langchain-ai/open_deep_research`](https://github.com/langchain-ai/open_deep_research) — MIT — 借鉴 LangGraph supervisor 状态机骨架、配置式多 LLM、compression model 处理长上下文
- [`assafelovic/gpt-researcher`](https://github.com/assafelovic/gpt-researcher) — Apache-2.0 — 借鉴 Reviewer + Revisor 反馈闭环模式、LangGraph Send 并行 subtopic 调研

商业产品形态参考：Klue Battlecard、Crayon Leadership Reports。

完整借鉴清单、原创层差异化、答辩话术见 [`docs/5-prior-art-and-leverage.md`](./docs/5-prior-art-and-leverage.md)。

## 合规

- 信息采集遵守目标站点 robots.txt 与服务条款（架构文档第 12.1 节）
- 公开评论入库前统一脱敏，去除 PII（架构文档第 7 节、第 12.3 节）
- API Key 走 `.env` 注入，不入仓库（`.env` 在 `.gitignore`）
- 第三方依赖许可证全部记录（`docs/5-prior-art-and-leverage.md` 第 6 节）

## 项目时间线

| 时间 | 节点 |
|---|---|
| 2026-05-20 | 开营，立项启动 |
| 2026-05-24 | 立项文档冻结，仓库骨架就绪，Prior Art 阅读笔记完成 |
| 2026-05-31 | 后端六表 + LangGraph 最小 DAG + 节点级并行 Collector 跑通 |
| 2026-06-05 | QA 闭环、报告页、Trace 时间线、第一次录屏粗剪 |
| 2026-06-09 | 最终录屏、README / 合规声明 / 答辩 PPT 完成 |
| 2026-06-10 | 提交作品 |
| 2026-06-12 ~ 06-19 | 入围答辩 |

## 许可证

参赛期间为私有仓库。比赛结束后将根据团队决定公开并采用 MIT 或 Apache-2.0 协议（待定）。
