# RivalLens 架构与技术栈决策

> 本文是 RivalLens 的工程边界文件，定义系统结构、关键技术选型、数据模型、并发与可靠性策略。
>
> **系统定位（不可妥协的红线）**：RivalLens 是 agentic multi-agent system，不是 fixed workflow。所有架构决策必须服务于三条特性：
>
> - **Agent-driven**：LLM 动态决策流程、Agent 选择与工具使用，而非 if-else 预定义路径。参考 Anthropic 《Building Effective Agents》对 workflow 与 agent 的区分——前者结构写死，后者由 LLM 在运行时编排。
> - **Extensible**：Agent 角色、工具集、行业包、Schema 字段、QA 规则全部开放扩展。禁止把"当前实现的角色清单 / 工具清单 / 字段清单"写成代码闭集。
> - **Self-improving**：系统从每次 run 的反思中沉淀新 skill（QA 规则、prompt template、source routing 偏好），形成长期能力进化闭环。这是 RivalLens 区别于一次性 workflow 的核心。
>
> 每条决策都从问题本身推导，可独立回答"为什么不选另一个候选方案"。**任何选项若违反上述三条特性中的任一条，必须在文档中显式标注权衡理由，否则不允许写入。**
>
> 多 Agent 架构的具体设计（Agent 边界、委派协议、QA 多目标路由、Skill 进化闭环）见 `docs/2.5-agent-architecture.md`。本文只描述系统层面的工程边界。

## 1. 设计原则

RivalLens 是一个 agentic multi-agent system，输入为竞品对象列表与目标用户角色，输出为结构化竞品报告 + 端到端可追溯性 + 系统级反思沉淀。下列五条原则与文档顶部的三条不可妥协特性正交：三条特性约束**做什么**，五条原则约束**怎么做**。

- **Evidence-grounded**：每条分析结论必须绑定可定位的 `evidence_id`，无证据来源的输出不进入最终报告。这是任何辅助决策类系统的可信度底线。
- **Local-deployable**：单机 `docker compose up` 即可完整运行，不依赖云资源或外部托管。降低用户上手成本，并保证开发、测试、演示三套环境完全一致。
- **Observable-by-default**：每个 Agent 的输入、输出、Prompt、token 消耗、延迟、错误、**LLM 决策路径**与中间 artifact 必须全链路可追踪。Agentic 系统的 LLM 决策不可见性比 workflow 高一个量级，可观测性必须前置内建——尤其是 Supervisor 的每次工具委派、Researcher 的每次 ReAct 步、QA 的每次 rejection 路由。
- **Schema-driven**：Agent 之间交换结构化消息和 evidence 引用，不传自由文本。Pydantic 校验放在 Agent 边界，结构化失败即视为异常。Supervisor 的工具委派协议、QA 的多目标 rejection 协议、Skill Curator 的候选输出**全部**强 schema。
- **Reuse-over-build**：基础设施层优先复用 MIT / Apache-2.0 / BSD 生态成熟方案，工程投入集中在系统原创层（Supervisor 委派协议、多目标 QA 路由、Skill 进化闭环、Schema、Evidence 模型）。

## 2. 系统总图

```text
docker compose（本地 localhost）
│
├─ postgres:16
│   ├─ runs / steps / llm_calls / evidence / reports / artifacts
│   ├─ supervisor_decisions / skill_candidates
│   └─ langgraph_checkpoints（langgraph-checkpoint-postgres 官方包）
│
├─ backend（Python 3.11 + FastAPI + LangGraph）
│   ├─ API Layer (FastAPI)
│   │   ├─ Run / Step / Evidence / Report / Trace API
│   │   ├─ Skill Candidate Review API
│   │   ├─ Artifact Manager
│   │   └─ Desensitization Middleware
│   ├─ LLM Client（默认豆包 Doubao-Seed-2.0-lite，配置式多模型路由）
│   ├─ LangGraph Orchestrator（agentic, LLM-driven；详见 docs/2.5-agent-architecture.md）
│   │   ├─ Supervisor Agent（LLM tool calling 动态委派；max_iterations 兜底）
│   │   ├─ Researcher Agent × N（ReAct subgraph；被 Supervisor 通过 Send fan-out）
│   │   ├─ Analyst Agent（LLM-driven 跨竞品分析）
│   │   ├─ Writer Agent（半确定性，模板化组装）
│   │   ├─ QA Reviewer Agent（规则 DSL + LLM 语义混合；多目标 rejection 路由）
│   │   └─ Skill Curator（异步，run 完成后启动；沉淀进化候选到 staging）
│   └─ Bind mount → ./data/artifacts/
│
└─ frontend（Node 20 + Vite + React + TS）
    ├─ DAG Run View（@xyflow/react；含 Supervisor 决策节点高亮）
    ├─ Evidence Console
    ├─ Report Viewer（Battlecard 风格）
    ├─ Trace Timeline（含 Supervisor decision trace）
    └─ Skill Staging Console（Curator 候选审核入口）
```

数据流方向：

- 前端只调 FastAPI，不直接触达 LangGraph；
- LangGraph 节点之间通过结构化消息 + checkpoint state 通信，不传自由文本；
- **Supervisor 通过工具调用（`ConductResearch` / `Analyze` / `Write` / `Finalize`）动态委派下游 Agent**，每次委派决策与 outcome 落 `supervisor_decisions` 表；
- 所有 Agent 输出落 artifact 表，所有 conclusion 引用 `evidence_id`；
- run 结束后 Skill Curator 异步消费完整 trace，产出进化候选到 `skill_candidates` 表（status=staging），等待人工审核进 industry pack 生效池。

## 3. 关键技术决策

> 决策原则：每条选型必须能独立回答"换一个候选方案为什么不行"。

### 3.1 编排框架：LangGraph

RivalLens 的核心交互模式是 agentic state graph，不是固定 pipeline：

- **Supervisor LLM 通过工具委派**下游 Agent（`ConductResearch` / `Analyze` / `Write` / `Finalize`），fan-out 度由 LLM 在运行时决定，不是代码硬编码；
- **Researcher 是 ReAct subgraph**，被 Supervisor 通过 LangGraph `Send` 批量委派并行执行；
- **QA Reviewer 多目标 rejection**，可打回 Researcher / Analyst / Writer 或回到 Supervisor 重新规划；
- 单 run 持续 5–15 分钟，节点中断恢复需要 checkpoint。

具备 `StateGraph + LLM tool calling + Send fan-out + Subgraph + checkpoint backend` 完整组合的开源编排框架，LangGraph 是唯一选择。CrewAI 的角色协作模型偏向 free-form multi-agent 对话，对显式 DAG + 状态回边 + 委派 tool 协议支持较弱；自研 DAG 在 checkpoint、中断恢复、Send 语义上需要重复造轮子。许可证 MIT。

### 3.2 后端框架：FastAPI

LangGraph、langgraph-checkpoint-postgres、httpx、SQLAlchemy 2.x 均为 async-native；豆包及其它 LLM SDK 也以 async 客户端为主。FastAPI 是 Python 生态中 async-first、Pydantic-native、与上述异步栈同构的 Web 框架，避免在 sync/async 之间桥接。许可证 MIT。

### 3.3 数据校验：Pydantic v2

Pydantic v2 既作为 FastAPI 的 request/response 校验层，也作为 Agent 间结构化消息协议的代码实现（Competitor Knowledge Schema、AgentMessage、QA Rejection 都以 Pydantic Model 落地）。Schema 即代码避免协议文档与运行时校验脱节。许可证 MIT。

### 3.4 数据库：PostgreSQL 16

系统中存在四类并发写：① Supervisor Send fan-out 出的 K 个 Researcher subgraph 并行写 `evidence`；② 各 Agent 的 LLM 调用并发写 `llm_calls`；③ 多 run 同时进行时 `steps` 与 `supervisor_decisions` 的状态更新交错发生；④ Skill Curator 异步任务在主 run 完成后写 `skill_candidates`，与下一轮 run 重叠。

- **SQLite 不适配的核心原因**：即使在 WAL 模式下也是单写者串行，在 Supervisor 决定 fan-out 到 5–10 个 Researcher 时会成为瓶颈，并强迫上层引入排队逻辑。PostgreSQL 的 MVCC + 行级锁让这四类写互不阻塞，与 LangGraph Send 的并行语义自然贴合。
- **JSONB 索引**：Trace 数据以 JSON payload 为主（prompt、tool args、错误栈、token usage），PostgreSQL 的 JSONB + GIN 索引让"按 prompt_hash / source_type / status 过滤回放"成为索引查询；SQLite 的 JSON1 是解析时函数。
- **LangGraph checkpoint backend**：`langgraph-checkpoint-postgres` 是 LangGraph 官方推荐的生产级实现，在长任务中断恢复与多 run 隔离上的语义比 SQLite 版本更明确。

许可证 PostgreSQL License (BSD-style)。

### 3.5 ORM 与迁移：SQLAlchemy 2.x + Alembic

Async SQLAlchemy 2.x 与 FastAPI / LangGraph 的 async 栈一致；Alembic 提供版本化 schema migration，覆盖开发期与后续维护期的迁移需求。许可证 MIT。

### 3.6 前端：React + Vite + TypeScript + shadcn/ui + Tailwind

需要呈现的核心界面：DAG 实时状态视图、Trace 时间线、Evidence 卡片、Battlecard 风格报告。这类信息密集型内部控制台界面，React + shadcn/ui + Tailwind 是当下事实标准，组件直接来源于设计系统，无 wrapper 二开成本。Vite 提供毫秒级 HMR，开发反馈循环短。TypeScript 在 API 边界与 store 边界提供静态校验，降低跨人协作错误。许可证全部 MIT。

### 3.7 DAG 可视化：@xyflow/react (React Flow)

React Flow 是 React 生态中 DAG / node-edge 视图最成熟的开源方案，支持自定义节点、handle、edge、可控布局，且与 Tailwind 兼容良好。可视化层通过 SSE / WebSocket 订阅 LangGraph 节点状态更新。许可证 MIT。

### 3.8 LLM 接入：豆包 Doubao-Seed-2.0-lite + 配置式多模型路由

默认模型选择豆包 Doubao-Seed-2.0-lite，其在中文场景的指令遵循、JSON 输出稳定性、调用延迟对本系统的工作负载（中文为主、结构化输出、5–15 分钟级长任务）匹配度高。

`llm_client.py` 借鉴 Open Deep Research 的路由模式：将 `summarization / research / compression / qa / writer` 五类调用解耦为独立模型槽位，每个槽位独立配置（默认全部回落豆包，但可针对特定阶段切换），统一记录 token / latency / error 至 `llm_calls` 表，通过全局 `asyncio.Semaphore` 限制并发避免上游限流。

模型 EP、API Key 通过 `.env` + `pydantic-settings` 注入，绝不入仓库。

### 3.9 LangGraph Checkpoint：`langgraph-checkpoint-postgres`

与 §3.4 选型一致。该 checkpoint 实现支持任务级并发隔离与节点级中断恢复，符合长任务系统的可靠性需求。许可证 MIT。

### 3.10 Trace 与可观测：自研最小 Trace 表 + 结构化日志

引入 Langfuse / OpenTelemetry collector / Phoenix 等完整观测平台会带来额外的部署组件（采集器、存储后端、UI），且与上述 Postgres 数据模型重复。本系统的 Trace 维度（`runs / steps / llm_calls / artifacts`）字段固定、查询模式简单，自研表 + JSONB 即可覆盖；外加 `structlog` 结构化日志写文件。前端 Trace Timeline 直接从这些表渲染。

后续若需迁移到 Langfuse 或 OTel，由于数据模型已结构化，迁移成本可控。

### 3.11 Secrets 管理：`.env` + `pydantic-settings`

豆包 API Key / 数据库连接串 / 第三方服务 token 全部通过 `.env` 注入。仓库根目录提供 `.env.example` 仅含字段名占位符；`.env` 强制写入 `.gitignore`。`pydantic-settings` 的 `BaseSettings` 在启动时校验必填项，缺失立即 fail-fast，避免运行时才发现配置缺失。

### 3.12 部署：docker compose + localhost

docker compose 是单机一次性起整套服务（postgres + backend + frontend）的标准方案，开发者环境一致性最高、首次跑通成本最低。生产化迁移到 K8s / Nomad 时，compose 文件可直接作为参考清单。

## 4. 不引入清单（YAGNI）

下列组件在当前用户场景与流量量级下无明确收益，引入将增加部署复杂度、维护成本与心智负担。

| 不引入 | 推迟到 |
|---|---|
| Redis | 当前任务级状态用 PG 行锁 + LangGraph checkpoint 已足够。仅在出现真实的缓存命中率需求或跨进程任务队列需求时引入 |
| Milvus / 向量库 | 当前 evidence 数量级 < 10^4，结构化 SQL 查询足够定位证据。本系统的检索语义是 `evidence-by-id`，而非 semantic search |
| S3 / OSS | artifact 体积可控（单 run 量级 < 10 MB），本地目录挂载满足；引入对象存储需要 IAM、SDK、bucket 管理，无收益 |
| Kafka / RabbitMQ | 单机单进程后端，无跨服务消息总线场景 |
| MCP 网关 | 内部 Agent 通过 LangGraph 消息直接通信，当前无第三方工具消费方需要 MCP 协议聚合 |
| Serverless | 部署形态固定为单机 docker compose，无 burst 流量与按调用计费需求 |
| 公网域名 / HTTPS / CDN | 当前为单机分析工具，无远程访问需求；引入证书与反代复杂度无收益 |
| 多租户 / 权限系统 | 当前为单用户或团队内部工具，无租户隔离与精细授权需求 |

后续若用户场景演进出真实需求（如多人协作、远程访问、跨服务异步），按需逐项引入，不预先建设。

## 5. 通用核心与行业包边界

系统能力按"可迁移性"分两层。该划分决定了任一变更的影响范围与版本兼容性边界：

- **通用核心 (core)**：跨行业稳定不变的机制与协议。修改 core 等于跨所有 pack 的兼容性变更。
- **行业包 (industry pack)**：按竞品类型可替换的领域配置。新增或替换 pack 不应触及 core 代码。

### 5.1 划分原则

| 维度 | 在 core 内 | 在 pack 内 |
|---|---|---|
| 编排范式 | Supervisor LLM 委派协议、ReAct subgraph 骨架、多目标 QA 路由 | — |
| 节点角色 | Supervisor / Researcher / Analyst / Writer / QA / Skill Curator 六类基础角色 | 角色可叠加领域特化版本（如 `Researcher.ai_coding_tools`） |
| 协议与 Schema | AgentMessage、Supervisor 委派 schema、多目标 Rejection schema、Skill 候选 schema | Schema 行业相关扩展字段 |
| 业务流 | 打回 / 重试 / max_iterations / Skill 进化闭环等通用机制 | 行业相关的 QA 规则参数、Skill 候选审核口径 |
| 输出 | 报告渲染骨架 | 行业相关的章节模板 |
| 数据 | Evidence / Conclusion 绑定逻辑、脱敏流水线、Trace 与决策数据模型 | 数据源模板、竞品对象列表、初始 Skill 集 |

具体的 core 类型清单与 pack 文件结构属于实现期约定，见 `backend/core/`、`industry_packs/<pack>/` 实现及 `docs/2.5-agent-architecture.md`、`docs/3-schema-and-protocol.md`。

### 5.2 扩展契约

- 行业包以独立目录提供：`industry_packs/<pack_name>/`；
- core 通过依赖注入或注册中心加载 pack，**禁止 core 直接 import pack 内部模块**；
- 不同 pack 之间互不感知，可独立迭代与替换；
- pack 版本与 schema 版本绑定，schema 变更可能要求 pack 同步升级。

第一版 pack：`industry_packs/ai_coding_tools/`。

## 6. 数据脱敏架构

### 6.1 设计动机

竞品分析的原始输入包含公开评论、用户访谈文本等可能携带个人可识别信息 (PII) 的内容。即使采集来源合规，下游使用方（报告读者、归档系统）的暴露范围与采集时不一致，必须在数据进入持久层之前做边界过滤。

### 6.2 不变量

- raw 文本仅作为 Researcher 工具调用（fetch_url / parse_page）的本地中间 artifact 暂存；
- 跨 Agent 边界传递与写入 `evidence` 表的文本必须经过脱敏函数；
- 报告与对外接口只读 `sanitized_text`，不直接暴露 raw；
- 合规声明文档必须列出数据来源、采集时间、脱敏策略。

### 6.3 数据流位置

```text
Researcher tool raw output
  ↓
  desensitize_text   ← 强制边界（Researcher subgraph 内置）
  ↓
evidence.sanitized_text
  ↓
Analyst / Writer / Report
```

### 6.4 接口契约

```python
def desensitize_text(text: str) -> str:
    """Mask personal identifiers before evidence crosses storage boundary."""
```

架构层只约束"边界位置 + 不变量"。具体覆盖的 PII 模式（邮箱、手机号、用户名、头像 URL、姓名等）、替换占位符格式、对抗用例与单元测试集属于实现层，见后续 `backend/agents/desensitize.py` 与相关测试。脱敏规则集合的修改属于安全相关变更，必须随实现演进并补充测试用例。

## 7. 数据模型

> 本节只定义表的存在边界、相互关系、生命周期不变量。完整字段、类型、约束、索引、迁移见 `docs/3-schema-and-protocol.md`（业务知识层 Pydantic 模型）与实现期 `backend/db/models.py` + Alembic 迁移（持久化层）。架构阶段不锁字段。

### 7.1 表分类

| 表 | 类别 | 用途 |
|---|---|---|
| `runs` | 业务实体 | 一次完整的竞品分析任务 |
| `steps` | 执行轨迹 | run 内每个 Agent 节点的一次执行 |
| `llm_calls` | 可观测 | 每次 LLM 调用的 token / latency / error |
| `supervisor_decisions` | Agentic 可观测 | Supervisor 每次工具委派的 input / chosen_tool / args / outcome；LLM 决策路径的核心证据 |
| `evidence` | 业务实体 | 经脱敏的原始证据，所有 conclusion 引用的最小单元 |
| `reports` | 业务实体 | Writer Agent 产出的结构化报告 |
| `artifacts` | 中间产物 | Agent 节点之间传递的中间结果文件元数据 |
| `skill_candidates` | 进化沉淀 | Skill Curator 产出的候选项（新 QA 规则 / prompt template / source routing），含 `status` ∈ {staging, approved, rejected} |
| `langgraph_checkpoints` | 框架托管 | LangGraph 自管理的节点状态快照，业务层不直接读写 |

### 7.2 关键关系

```text
runs (1) ──< steps (N) ──< llm_calls (N)
                       ├──< artifacts (N)
                       └──< supervisor_decisions (N)
runs (1) ──< evidence (N)
runs (1) ──< reports (1..N)
runs (1) ──[reflection, async]──> skill_candidates (0..N)   (Curator 异步产出, status=staging)
reports ──[ref]──> evidence   （conclusion-evidence 双向绑定，由 Writer 维护）
skill_candidates ──[approved by reviewer]──> industry_packs/<pack>/skills/   （审核通过后落盘进生效池）
```

### 7.3 生命周期不变量

- `evidence` / `llm_calls` / `artifacts` / `supervisor_decisions` 四表 append-only，行写入后不再修改；`artifacts` 指向的文件本身也不覆写；
- `runs` / `steps` / `reports` 允许状态字段更新，但状态机由后端服务约束，不依赖数据库触发器；
- `skill_candidates` 允许 `status` 从 `staging` 单向迁移到 `approved` 或 `rejected`，不允许回退；其他字段写入后不变；
- `langgraph_checkpoints` 由 LangGraph 框架自管理，业务代码不直接操作；
- 所有 `*_id` 外键列必须有索引；JSONB 列按真实查询模式补 GIN 索引（具体清单在迁移期决定）。

## 8. 并发设计：节点级并行 + 任务级并发

竞品分析是慢任务，单 run 持续 5–15 分钟，QPS 不是有意义的指标。并发设计针对两类真实场景：① 单 run 内部多个竞品同时调研，端到端时间从串行 N×T 压缩到 max(T)；② 多个用户/任务同时运行，互不阻塞。两类对应不同的实现层次。

### 8.1 节点级并行：Supervisor 动态委派 + LangGraph Send fan-out

并行**不由代码硬编码触发**，而由 Supervisor 通过 LLM tool calling 动态决定。这是 agentic 与 workflow 的核心差异——后者把"按 N 个竞品 fan-out"写死，前者由 LLM 决定 fan-out 的时机、度与目标。

- **Supervisor**：在每个决策点判断"是否需要并行委派 Researcher"，并产出 K 个 `ConductResearch(research_topic=...)` tool call（K 由 Supervisor 决定，典型 3–8，受 `max_concurrent_researchers` 上限约束）；
- **LangGraph Send**：将 K 个 tool call 转换为 K 个 Researcher subgraph 实例并行执行；
- **Researcher**（每个）：独立 ReAct subgraph，自主决定工具调用顺序、何时压缩长上下文、何时停止；产出独立的 evidence batch + `CompetitorKnowledgeFragment`；
- **Analyst**：在 Supervisor 决定"已采集足够"后启动，对全部 Researcher fragments 做跨竞品分析。Analyst 自身也可分维度并行（如按 feature / pricing / SWOT），同样由 Send 触发；
- **Writer / QA Reviewer**：串行或受控重试，避免状态混乱；
- **Skill Curator**：run 完成后**异步**启动（不参与主图并行），消费完整 trace 产出候选。

典型的 agentic 行为：Supervisor 可以"先调研 3 个核心竞品，根据返回结果决定是否补调研 2 个边缘竞品"——这种动态决策能力 workflow 模式无法实现。

并行子图的失败被限定在子图作用域内，merge 节点按已成功子集汇聚；缺失项在结果中显式标注并回传 Supervisor，由 Supervisor 决定是否补调研。

### 8.2 任务级并发：多 run 隔离

后端接口与数据模型从第一行代码就支持多 run 同时运行：

- 每个 run 拥有独立的 `run_id`、artifact 目录、Trace 上下文；
- PostgreSQL 行级锁保证并发写 `evidence` / `steps` 不冲突；
- `langgraph-checkpoint-postgres` 保证多 run 中断恢复隔离；
- 前端 Run List 支持同时展示多个进行中的 run。

### 8.3 设计原则

- 并行只在 fan-out 边上做，merge 边汇聚后再串行交给下游；
- 失败重试限定子图作用域，不污染主流程状态；
- LLM 并发受 `llm_client.py` 全局 `asyncio.Semaphore` 约束，防止超出上游 QPS 配额；
- 不追求高 QPS，追求端到端 wall-clock 压缩与多 run 隔离。

## 9. Prior Art 借鉴策略

基础设施层与编排骨架优先复用开源成熟方案；工程投入集中在系统原创层（结构化 Schema、Evidence 模型、QA 反馈协议、并发编排）。详细调研与许可证清单见 `docs/5-prior-art-and-leverage.md`。

### 9.1 开源借鉴

| 项目 | 许可证 | 借鉴维度 |
|---|---|---|
| `langchain-ai/open_deep_research` | MIT | LangGraph supervisor 状态机骨架、配置式多 LLM 路由、DAG 可视化形态 |
| `assafelovic/gpt-researcher` | Apache-2.0 | Reviewer + Revisor 反馈闭环模式、LangGraph Send 并行 subtopic 调研 |

### 9.2 商业产品形态借鉴

| 产品 | 借鉴维度 |
|---|---|
| Klue | Battlecard 卡片形态、紧凑型竞品摘要 UI |
| Crayon Leadership Reports | 报告章节模板（功能 / 定价 / 用户反馈 / 差异化 / SWOT） |

### 9.3 借鉴边界

- **允许**：阅读源码、参考结构、改造 prompt、参考产品形态；
- **禁止**：整体 fork 改名、复制角色全套、引入 GPL / AGPL 源码；
- **必做**：在 README 与依赖清单中声明参考开源项目与许可证。

### 9.4 原创层

本系统在以下机制上自研而非借鉴：

- **Supervisor LLM 动态委派协议**（区别于 GR `multi_agents` 的代码 Chief Editor 编排，详见 `docs/2.5-agent-architecture.md`）；
- **多目标 QA 路由协议**（`reject_to ∈ {supervisor, researcher, analyst, writer}`，区别于 GR 的单环 Reviewer/Revisor）；
- **Skill Curator 反思与进化闭环**（QA 规则 / prompt template / source routing 候选自动沉淀，HITL 审核进生效池）；
- 竞品知识 Schema 与行业包扩展机制；
- Evidence 与 Conclusion 的结论级双向溯源；
- 结构化 QA Rejection 协议与轻量规则 DSL；
- 数据脱敏架构与流水线；
- Supervisor 动态决定 fan-out 度的节点级并行 + 任务级并发工程实现。

## 10. 可靠性、错误恢复与幻觉抑制

多 Agent 长任务系统的核心可靠性挑战有三：① 单节点失败不能拖垮整 run；② LLM 输出的非确定性必须被结构化约束；③ 上游不可用必须有降级路径。

### 10.1 错误恢复与重试

| 失败场景 | 策略 |
|---|---|
| LLM 调用失败 / 超时 | `llm_client.py` 指数退避，`max_retry=2`，每次 error 写 `llm_calls` 表 |
| LLM 输出 Schema 校验失败 | Pydantic 校验失败 → 自动触发 QA 打回，要求 Agent 重新输出，与正常 QA rejection 共用通道 |
| Researcher 单数据源抓取失败 | 单源失败不阻塞 fan-out，记录 failed evidence 并降级，继续其他源 |
| LangGraph 节点失败 | 限定子图作用域，不污染主流程；可从 `langgraph_checkpoints` 恢复 |
| 数据库写入失败 | SQLAlchemy 事务回滚，记录到结构化日志，对外返回 500 + run_id |
| **Supervisor 决策死循环** | Supervisor 每次决策的 iteration 计数被 checkpoint，超过 `max_supervisor_iterations`（默认 10）强制 finalize 当前已有产出，标记 run 为 `degraded` |
| **Researcher ReAct 死循环** | 单 Researcher subgraph 的 tool call 计数被限制为 `max_researcher_iterations`（默认 6），超限触发强制 compress 并 return |
| **QA 反馈死循环** | QA rejection 的 `retry_count` 写入 step；同一 step 被打回超过 `max_qa_rejections`（默认 3）后强制 finalize 该 step 为 `degraded`，不再继续打回 |
| **Skill Curator 任务失败** | Curator 是异步任务，失败不影响主 run 结果；失败记录到 `skill_candidates.error` 字段供后续重跑 |

### 10.2 降级机制

- **LLM 持续失败**：超过 max_retry 后切 fallback prompt（简化任务），仍失败则跳过节点并标记 step 为 `degraded`；
- **在线采集失败**：自动切换到预置数据集，前端显式标注 `data_source=offline_snapshot`，让读者知晓数据非实时；
- **模型超额**：受全局 `asyncio.Semaphore` 约束，请求排队不抛错；
- **并行子节点失败**：单 Agent 失败不影响其他并行子节点，最终 merge 节点按已成功子集汇聚，并在结果中标注缺失项；
- **Supervisor 多次委派均失败**：Supervisor 在 trace 中观察到 K 个 Researcher 子图全部失败时，自动切到 fallback 路径（直接读 offline_snapshot 跳过研究阶段），并在 final report 中标注 `mode=fallback`。

### 10.3 幻觉抑制

| 机制 | 实现位置 |
|---|---|
| 引用强制 | QA 规则 `conclusion_requires_evidence`：每条 conclusion 必须 ≥ 1 个 `evidence_id`，否则打回 |
| 自一致性校验 | QA 规则：跨竞品同字段冲突检测，冲突 → 降级为 `confidence=low` 或要求补采 |
| 超长上下文分片 | 借鉴 Open Deep Research 的 compression 模式：Researcher subgraph 内置 compress 节点，长 trace 按 token 阈值切 chunk + compression 模型压缩后再回传 Supervisor |
| Schema 强约束 | 所有 Agent 输出走 Pydantic 校验，结构化失败立即重试或打回 |
| Evidence-Conclusion 强绑定 | 报告渲染时无 evidence 的 conclusion 直接过滤，不允许进入最终 report |
| Supervisor 决策可审计 | 每次工具委派写 `supervisor_decisions`，含 `reasoning_summary` 字段，便于事后审查"为什么 LLM 做了这个决定" |

## 11. 合规、安全与 Secrets 管理

### 11.1 信息采集合规

- Researcher 的 `fetch_url` 工具在每次调用前用 `urllib.robotparser` 检查 robots.txt，被禁路径直接跳过并记录 `skipped_by_robots`；
- HTTP User-Agent 标识：`RivalLens-Researcher/0.1 (+research)`；
- 单站点 QPS ≤ 1，通过 `asyncio.Semaphore` 限制（与 Researcher 并发上限独立）；
- 所有 evidence 必须记录 `source_url` 与 `collected_at`，作为合规证据；
- `docs/compliance-statement.md`（待建）列出数据来源、抓取时间、许可条件。

### 11.2 API Key 与 Secrets

- 豆包 EP / API Key 等敏感配置全部放 `.env`；
- 仓库根目录提供 `.env.example` 仅含字段名占位符；
- `.env` 强制加入 `.gitignore`；
- backend 通过 `pydantic-settings` 的 `BaseSettings` 读取，未配置必填项直接启动失败；
- docker compose 通过 `env_file: .env` 注入容器；
- 建议接入 `gitleaks` pre-commit hook 阻止 Key 误提交。

### 11.3 Prompt Injection 防护

- 系统 prompt 与用户/采集内容物理隔离，使用不同 LLM message role；
- 公开评论先过脱敏函数，再过 prompt-injection 关键词清洗（去除常见越狱指令模式）；
- LLM 输出强制 Pydantic 校验，结构化失败即视为异常并拒绝写入下游；
- Researcher 的工具集不包含 shell / eval / 任意 URL 跳转执行；fetch_url 工具只下载内容，不执行采集到的脚本 / 命令 / 外链跳转。

### 11.4 运行时安全

- docker compose 自定义 network，postgres 不暴露端口给 host，仅 backend 可访问；
- backend 端口仅绑定 `127.0.0.1`，不开公网；
- 所有外部 HTTP 调用走 `httpx.AsyncClient` 统一配置 timeout 与 SSL 验证。
