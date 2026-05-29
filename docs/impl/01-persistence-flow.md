# RivalLens 实现细节：持久化层与第一条可观测数据流

## 1. 文档定位

- `docs/0-5`：稳定的顶层约束（架构边界、Agent 边界、协议契约、团队协作）。
- `docs/impl/*`：按每一刀代码落地沉淀的实现细节（可随实现演进快速更新）。
- 本文只记录 `db-persistence-layer` 这一刀的工程实现，不重复顶层原则论证。

交叉引用：

- 架构边界：`docs/2-architecture-decision.md`（§3.4 / §3.5 / §7）
- Agent 边界：`docs/2.5-agent-architecture.md`
- Schema 与协议：`docs/3-schema-and-protocol.md`（§5.2 / §8）

## 2. 数据流时序（`/api/runs`）

```mermaid
sequenceDiagram
  participant FE as POST /api/runs
  participant RT as run_rt
  participant LG as LangGraph
  participant SN as supervisor_node
  participant DB as PostgreSQL

  FE->>RT: payload(competitors, domain_hint, reference_urls, target_roles)
  RT->>DB: INSERT runs(status=running)
  RT->>LG: ainvoke(state{run_id, session_factory})
  LG->>SN: invoke
  SN->>DB: INSERT steps(agent_name=supervisor)
  SN->>DB: INSERT supervisor_decisions(chosen_tool=Finalize)
  SN->>DB: UPDATE steps(status=completed)
  LG-->>RT: state(decisions, status)
  RT->>DB: UPDATE runs(status=completed, finished_at=now)
  RT-->>FE: 200 {run_id, status=completed}
```

## 3. 表关系（8 张业务表）

```mermaid
erDiagram
  RUNS ||--o{ STEPS : contains
  STEPS ||--o{ LLM_CALLS : records
  RUNS ||--o{ SUPERVISOR_DECISIONS : records
  RUNS ||--o{ EVIDENCE : collects
  RUNS ||--o{ REPORTS : renders
  STEPS ||--o{ ARTIFACTS : emits
  RUNS ||--o{ SKILL_CANDIDATES : reflects

  RUNS {
    string run_id PK
    string status
    jsonb target_roles
    jsonb competitors
    timestamptz started_at
    timestamptz finished_at
    timestamptz created_at
  }
  STEPS {
    string step_id PK
    string run_id FK
    string agent_name
    string status
    int retry_count
    jsonb payload
    timestamptz started_at
    timestamptz finished_at
  }
  LLM_CALLS {
    bigint id PK
    string step_id FK
    string model_slot
    string prompt_hash
    int prompt_tokens
    int completion_tokens
    int latency_ms
    text error
    timestamptz created_at
  }
  SUPERVISOR_DECISIONS {
    string id PK
    string run_id FK
    int iteration
    string chosen_tool
    jsonb tool_args
    text reasoning_summary
    string outcome
    timestamptz outcome_recorded_at
    timestamptz created_at
  }
  EVIDENCE {
    string id PK
    string run_id FK
    string source_type
    text sanitized_text
    jsonb span
    bool desensitized
    timestamptz collected_at
    timestamptz created_at
  }
  REPORTS {
    string report_id PK
    string run_id FK
    string status
    jsonb content_json
    text content_markdown
    timestamptz created_at
  }
  ARTIFACTS {
    string artifact_id PK
    string step_id FK
    string kind
    text uri
    string sha256
    int size_bytes
    timestamptz created_at
  }
  SKILL_CANDIDATES {
    string id PK
    string applies_to
    jsonb tags
    string candidate_type
    jsonb payload
    jsonb supporting_run_ids
    string confidence
    string status
    timestamptz reviewed_at
    timestamptz created_at
  }
```

## 4. 事务边界与不变量

### 4.1 为什么传 `session_factory`，不传 `AsyncSession`

- `LangGraph state` 需要可在节点边界安全传递；长生命周期 `AsyncSession` 容易跨节点泄漏事务上下文。
- 传 `session_factory` 可以让每个节点自行打开短事务：边界清晰、失败回滚范围小。
- 该策略与 `docs/2` 的 fail-fast 原则一致：`session_factory` 缺失直接抛错，不静默降级。

### 4.2 为什么节点内开短事务

- `supervisor_node` 的本刀职责是写入最小可观测轨迹（`steps` + `supervisor_decisions`）。
- 节点内单次事务提交，保证这两类记录在同一决策单元内原子可见。
- 避免把事务控制扩散到 router / graph 编排层，减少隐式耦合。

### 4.3 append-only 约束

- append-only 表：`evidence` / `llm_calls` / `artifacts` / `supervisor_decisions`
- 工程约束：这些表只允许 `INSERT`，不做业务语义 `UPDATE`，用于回放与审计。
- 可变状态集中在 `runs` / `steps` / `reports` / `skill_candidates.status`，与顶层文档一致。

## 5. 当前刀的验收口径

- Alembic 初始迁移可创建 8 张业务表。
- `POST /api/runs` 后，数据库至少出现：
  - 1 行 `runs`
  - 1 行 `steps`
  - 1 行 `supervisor_decisions`
- `supervisor_decisions.chosen_tool` 为 `Finalize`，用于证明最小决策链路已经持久化。
