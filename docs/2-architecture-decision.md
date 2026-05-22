# RivalLens 架构与技术栈决策

> 本文是工程边界文件。每条决策服务于答辩演示、评分命中和三周内稳定交付。

## 1. 总体原则

- Demo-first：从答辩画面反推工程能力，优先做评委能看见的 DAG、Trace、Evidence 和 QA 打回。
- Local-first：作品支持本地 localhost 演示，不做公网部署、域名、HTTPS 和云资源。
- Trace-first：每个 Agent 的输入、输出、Prompt、token、latency、错误和 artifact 都必须可追踪。
- Schema-first：Agent 之间不传纯自然语言闲聊，统一传结构化消息和 evidence refs。
- Reuse-first：优先使用 MIT / Apache-2.0 / BSD 依赖，不整体二开大型平台。

## 2. 系统总图

```text
docker compose（本地 localhost）
│
├─ postgres:16
│   ├─ runs / steps / llm_calls / evidence / reports / artifacts
│   └─ langgraph_checkpoints（langgraph-checkpoint-postgres 官方包）
│
├─ backend（Python 3.11 + FastAPI + LangGraph）
│   ├─ API Layer (FastAPI)
│   │   ├─ Run / Step / Evidence / Report / Trace API
│   │   ├─ Artifact Manager
│   │   └─ Desensitization Middleware
│   ├─ LLM Client（默认豆包 Doubao-Seed-2.0-lite + 配置式多模型预留）
│   ├─ LangGraph Orchestrator
│   │   ├─ Collector Agent（按竞品 fan-out 节点级并行）
│   │   ├─ Extractor Agent（按竞品并行）
│   │   ├─ Analyst Agent（按 feature 维度并行）
│   │   ├─ Writer Agent
│   │   └─ QA Agent（结构化 rejection + 规则 DSL）
│   └─ Bind mount → ./data/artifacts/
│
└─ frontend（Node 20 + Vite + React + TS）
    ├─ DAG Run View（@xyflow/react）
    ├─ Evidence Console
    ├─ Report Viewer（Battlecard 风格）
    └─ Trace Timeline
```

## 3. 技术决策表

| 决策项 | 选择 | 理由 | 许可证 / 风险 |
|---|---|---|---|
| 编排框架 | LangGraph | 与赛题中 DAG、多 Agent 编排、状态流转、反馈闭环高度一致 | MIT |
| 后端框架 | FastAPI | Python 生态适配 LangGraph / Pydantic / LLM SDK，开发速度快 | MIT |
| 数据校验 | Pydantic | 直接作为 Schema 和 Agent 协议的代码实现 | MIT |
| 数据库 | PostgreSQL 16 | docker compose 一行启动；JSONB 索引便于 Trace 与 artifact 元数据查询；与"节点级并行 + 任务级并发"叙事自洽；LangGraph checkpoint 工业级首选后端 | PostgreSQL License (BSD-style) |
| ORM | SQLAlchemy + Alembic | 稳定、支持迁移与版本化 schema | MIT |
| 前端框架 | React + Vite + TypeScript | 快速搭建交互界面和状态视图 | MIT |
| UI 组件 | shadcn/ui + Tailwind CSS | 适合快速做专业后台界面 | MIT |
| DAG 可视化 | React Flow / @xyflow/react | 展示 Agent DAG 和节点状态 | MIT |
| LLM 默认模型 | 豆包 Doubao-Seed-2.0-lite | 课题官方提供账号；EP 与 API Key 走环境变量 | 不入仓库 |
| LLM 调用层 | 自研 `llm_client.py` + 配置式多模型 | 借鉴 Open Deep Research：summarization / research / compression / qa / writer 各自可指定模型，默认全部回落到豆包；统一记录 token、latency、error；全局信号量限流 | 避免散落 SDK 调用，预留多模型切换叙事 |
| LangGraph checkpoint | `langgraph-checkpoint-postgres` | 官方 PG checkpoint 实现，支持任务级并发与中断恢复 | MIT |
| Trace | 自研最小 Trace 表 | 比接入完整观测平台更轻，足够答辩演示 | 后续可迁移 Langfuse |
| Secrets 管理 | `.env` + `pydantic-settings` + `.env.example` | 豆包 API Key / DB 连接串通过 `.env` 注入，`.env.example` 仅含占位符，`.env` 入 `.gitignore` | 满足赛题"API Key 不写入仓库"要求 |
| 部署 | docker compose + localhost | 符合导师"本地部署即可"的信号 | 不做公网 |

## 4. 不引入清单

第一版明确不引入：

- Redis：不做复杂异步队列，先用 PostgreSQL 行级锁与 LangGraph checkpoint 控制状态。
- Milvus / 向量库：第一版以证据表和结构化引用为主，不做大规模 RAG。
- S3 / OSS：artifact 直接落本地目录。
- Kafka / RabbitMQ：三周内不做分布式消息系统。
- MCP 网关：借鉴工具聚合思想，但内部直接 function call / LangGraph message。
- Serverless / NAS：本地部署即可，不复制 dcccloud 的生产部署复杂度。
- 公网域名 / HTTPS：导师确认 localhost 可提交，避免部署耗时。
- 多租户 / 权限系统：比赛演示不需要。

## 5. dcccloud 架构借鉴边界

| dcccloud 做法 | RivalLens 决策 |
|---|---|
| 每个能力是独立 Agent / 节点 | 借鉴。Collector / Extractor / Analyst / Writer / QA 拆成独立节点 |
| LLM 调用走统一网关 | 借思想。用 `llm_client.py` 统一模型调用、token、latency、错误 |
| 中间产物落盘给下游消费 | 借鉴。每个 Agent 输出 artifact，关键结论绑定 evidence |
| 前端只调统一入口 | 借鉴。前端只调 FastAPI，不直接调 Agent |
| Trace / 计费 / 数据分析独立服务 | 借思想。Trace 做成后端内部表，不做计费服务 |
| MCP 网关聚合 Agent | 不借。比赛版本不引入额外协议解释成本 |
| Serverless + NAS + 多仓库 | 不借。单仓库 monorepo + docker compose |
| LobeHub fork 做前端 | 不借。许可证和二开成本不适合比赛主线 |

## 6. 通用核心与行业包边界

### 通用核心

- LangGraph DAG。
- AgentMessage 协议。
- Competitor Knowledge Schema 基座。
- Evidence 模型和 conclusion-evidence 绑定。
- QA 规则引擎。
- Trace 数据模型。
- Report 生成流程。
- 脱敏流程。

### 行业包

- 竞品对象列表。
- 数据源模板。
- Schema 扩展字段。
- 报告章节模板。
- QA 规则参数。
- 演示数据集。

第一版行业包：

```text
industry_packs/ai_coding_tools/
```

## 7. 数据脱敏架构

所有写入 evidence 表的文本字段必须经过脱敏处理。

接口契约：

```python
def desensitize_text(text: str) -> str:
    """Remove or mask personal identifiers before storing evidence."""
```

最低规则：

- 邮箱替换为 `[EMAIL]`
- 手机号替换为 `[PHONE]`
- URL 中明显头像资源替换为 `[AVATAR_URL]`
- 公开评论用户名替换为 `[USER]`
- 真实姓名可疑模式替换为 `[NAME]`

调用时机：

```text
Collector raw text
  → desensitize_text
  → evidence.sanitized_text
  → Extractor / Analyst / Writer
```

规则：

- raw 原文可以作为本地 artifact 暂存，但默认不进报告。
- 报告只展示 sanitized_text 或短 quote。
- README 和答辩材料必须说明数据来源与脱敏策略。

## 8. 可观测数据模型

详细字段语义见 `docs/3-schema-and-protocol.md`。本节只定义表边界。

### runs

| 字段 | 类型 |
|---|---|
| id | string |
| title | string |
| industry_pack | string |
| target_roles | json |
| status | string |
| created_at | datetime |
| updated_at | datetime |

### steps

| 字段 | 类型 |
|---|---|
| id | string |
| run_id | string |
| agent_name | string |
| status | string |
| input_artifact_id | string |
| output_artifact_id | string |
| rejection_reason | string |
| started_at | datetime |
| ended_at | datetime |

### llm_calls

| 字段 | 类型 |
|---|---|
| id | string |
| run_id | string |
| step_id | string |
| model | string |
| prompt_hash | string |
| input_tokens | integer |
| output_tokens | integer |
| latency_ms | integer |
| error | string |
| created_at | datetime |

### evidence

| 字段 | 类型 |
|---|---|
| id | string |
| run_id | string |
| source_url | string |
| source_type | string |
| quote | string |
| sanitized_text | text |
| span | json |
| collector_id | string |
| collected_at | datetime |

### reports

| 字段 | 类型 |
|---|---|
| id | string |
| run_id | string |
| title | string |
| content_json | json |
| content_markdown | text |
| status | string |
| created_at | datetime |

### artifacts

| 字段 | 类型 |
|---|---|
| id | string |
| run_id | string |
| step_id | string |
| kind | string |
| path | string |
| schema_version | string |
| created_at | datetime |

## 9. 并发设计：节点级并行 + 任务级并发

并发不是"高并发"。竞品分析是慢任务（单 run 5–15 分钟），追求 QPS 没有意义。RivalLens 的并发亮点分两层，对应 Q&A 信号"导师说支持并发更好"的加分项。

### 9.1 节点级并行（demo 主力画面）

利用 LangGraph 的 Send / map-reduce 机制，单 run 内多个子节点并行：

- Collector：按竞品 fan-out，每个竞品一个子图，并行抓取官网 / 文档 / 定价页 / 公开评论。
- Extractor：按竞品并行进行结构化抽取，每个产出独立 CompetitorKnowledge 分片。
- Analyst：按 feature 维度或 SWOT 维度并行做差异分析。
- Writer / QA：保持串行或受控重试，避免状态混乱。

录屏可见效果：DAG 视图里多条边同时点亮，子节点状态条同步推进。该画面直接命中评分 35% 多 Agent 可视化与 25% 工程完整度。

### 9.2 任务级并发

后端接口与数据模型从一开始就支持多 run 同时运行：

- 每个 run 拥有独立 `run_id`、artifact 目录、Trace 上下文。
- PostgreSQL 行级锁保证并发写 evidence / steps 不冲突。
- LangGraph PostgreSQL checkpoint 保证多 run 中断恢复隔离。
- 前端 Run List 支持同时展示多个进行中的 run。

录屏可加分镜头：同时启动两个不同任务，DAG 视图并排显示。

### 9.3 设计原则

- 并行只在 fan-out 边上做，merge 边汇聚后再串行交给下游。
- 失败重试限定子图作用域，不污染主流程状态。
- LLM 并发受 `llm_client.py` 全局信号量约束，防止超出豆包账号 QPS 配额。
- 答辩口径：用"基于 LangGraph 的并行子图编排"描述，不用"高并发"包装。

## 10. Prior Art 借鉴策略

第一版不重复造轮子。底座层借鉴成熟开源，原创层放在评分核心。详细调研、许可证记录、答辩话术见 `docs/5-prior-art-and-leverage.md`。

### 10.1 必看的开源近亲

| 项目 | 许可证 | 借鉴维度 |
|---|---|---|
| `langchain-ai/open_deep_research` | MIT | LangGraph supervisor 状态机骨架、配置式多 LLM、DAG 可视化形态 |
| `assafelovic/gpt-researcher` | Apache-2.0 | Reviewer + Revisor 反馈闭环模式、LangGraph Send 并行 subtopic 调研 |

### 10.2 商业产品形态

| 产品 | 借鉴维度 |
|---|---|
| Klue | Battlecard 卡片形态、紧凑型竞品摘要 UI |
| Crayon Leadership Reports | 报告章节模板（功能 / 定价 / 用户反馈 / 差异化 / SWOT） |

### 10.3 借鉴边界

- 允许：阅读源码、抄结构、改造 prompt、参考产品形态。
- 禁止：整体 fork 改名提交、复制 8 Agent 全套角色、引入 GPL / AGPL 源码。
- 必做：在 README 与答辩材料中主动声明参考开源项目与许可证。

### 10.4 原创层（评分核心 60%+）

- 竞品知识 Schema 与行业包扩展机制（赛题 35%）。
- Evidence 与 Conclusion 结论级溯源（赛题 35% + 业务 20%）。
- 结构化 QA rejection 协议与轻量规则 DSL（赛题 35% "非伪闭环"）。
- 数据脱敏架构（合规 10%）。
- TRAE / Cursor 协作工程化痕迹（代码质量 10%）。
- 节点级并行 + 任务级并发设计（工程完整度 25%）。

## 11. 可靠性、错误恢复与幻觉抑制

直接命中评分 25% "异常处理、超时重试、降级机制完备"与"上下文管理、错误恢复、幻觉抑制有明确策略（自一致性校验、引用强制、超长上下文分片）"。

### 11.1 错误恢复与重试

| 失败场景 | 策略 |
|---|---|
| LLM 调用失败 / 超时 | `llm_client.py` 指数退避，max_retry=2，记录每次 error 到 `llm_calls` 表 |
| LLM 输出 Schema 校验失败 | Pydantic 校验失败 → 自动触发 QA 打回，要求 Agent 重新输出，与正常 QA rejection 共用通道 |
| Collector 单数据源抓取失败 | 单源失败不阻塞 fan-out，记录 failed evidence 并降级，继续其他源 |
| LangGraph 节点失败 | 限定子图作用域，不污染主流程；可从 `langgraph_checkpoints` 恢复 |
| 数据库写入失败 | SQLAlchemy 事务回滚，记录到结构化日志，对外返回 500 + run_id |

### 11.2 降级机制

- LLM 持续失败：超过 max_retry 后切 fallback prompt（简化任务），仍失败则跳过节点并标记 step 为 `degraded`
- 在线采集失败：自动切换到预置数据集，避免录屏卡死，前端显示 `data_source=demo_fallback`
- 模型超额：受全局信号量约束，请求排队不抛错
- 并行子节点失败：单 Agent 失败不影响其他并行子节点，最终 merge 节点按"已成功子集"汇聚

### 11.3 幻觉抑制（命中评分关键词）

| 机制 | 实现位置 | 命中评分关键词 |
|---|---|---|
| 引用强制 | QA 规则 `conclusion_requires_evidence`，每条 conclusion ≥ 1 evidence_id | "引用强制" |
| 自一致性校验 | QA 可选规则：跨竞品同字段冲突检测，冲突 → 降级为 `confidence=low` 或要求补采 | "自一致性校验" |
| 超长上下文分片 | 借鉴 Open Deep Research 的 compression model 模式：Collector 输出长文本按 token 阈值切 chunk + 用 compression 模型压缩后再喂下游 | "超长上下文分片" |
| Schema 强约束 | 所有 Agent 输出走 Pydantic 校验，结构化失败立即重试或打回 | "结构化输出一致性" |
| Evidence 与 Conclusion 强绑定 | 报告渲染时无 evidence 的 conclusion 直接过滤，不允许进入最终 report | "信息溯源完整" |

### 11.4 演示口径

录屏旁白与答辩话术统一："错误恢复、幻觉抑制都做了三件事：引用强制、自一致性校验、超长上下文分片"，逐字命中评分原文。

## 12. 合规、安全与 Secrets 管理

直接命中评分 10% 合规与赛题原文"API Key 不写入项目文档与代码仓库"要求。

### 12.1 信息采集合规

- Collector 抓取前用 `urllib.robotparser` 检查 robots.txt，被禁的路径直接跳过并记录 `skipped_by_robots`
- HTTP User-Agent 标识：`RivalLens-Researcher/0.1 (+research; bytedance-ai-fullstack-challenge)`
- 单站点 QPS ≤ 1，通过 `asyncio.Semaphore` 限制
- 所有 evidence 必须记录 `source_url` 与 `collected_at`，作为合规证据
- README 与 `docs/compliance-statement.md`（待建）列出数据来源、抓取时间、许可条件

### 12.2 API Key 与 Secrets

- 豆包 EP、API Key 等敏感配置全部放 `.env`
- 仓库根目录提供 `.env.example`，仅含字段名占位符
- `.env` 强制加入 `.gitignore`
- backend 通过 `pydantic-settings` 的 `BaseSettings` 读取，未配置必填项直接启动失败
- docker compose 通过 `env_file: .env` 注入容器
- pre-commit hook（推荐 `gitleaks` 或简化版正则扫描）阻止 Key 误提交

### 12.3 Prompt Injection 防护

- 系统 prompt 与用户/采集内容物理隔离，不同 LLM message role
- 公开评论先过脱敏函数，再过 prompt-injection 关键词清洗（去除常见越狱指令模式）
- LLM 输出强制 Pydantic 校验，结构化失败即视为异常并拒绝写入下游
- Collector 不允许执行采集到的脚本 / 命令 / 外链跳转

### 12.4 运行时安全

- docker compose 自定义 network，postgres 不暴露端口给 host，仅 backend 可访问
- backend 端口仅绑定 `127.0.0.1`，演示机不开公网
- 所有外部 HTTP 调用走 `httpx.AsyncClient` 统一配置 timeout 与 SSL 验证


