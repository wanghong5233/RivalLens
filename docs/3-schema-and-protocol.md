# RivalLens 数据 Schema 与 Agent 通信协议

> 本文是 RivalLens 三人协作的数据契约源头。后端模型、Agent 输入输出、前端 Evidence Console 与报告渲染、Skill Curator 候选审核全部对齐本文。
>
> **系统定位（不可妥协的红线，与 `docs/2-architecture-decision.md` / `docs/2.5-agent-architecture.md` 同步）**：
>
> - **Agent-driven**：Schema 服务于 LLM 在运行时做出的动态决策，Schema 设计必须支持开放式工具委派与多目标路由，禁止把决策路径编进字段语义。
> - **Extensible**：所有枚举值（payload_type / reject_to / source_type / candidate_type 等）必须保留扩展空间；版本演变机制是 schema 的第一公民。
> - **Self-improving**：Skill Curator 的候选输出必须有强 schema，便于机器消费、版本管理与 HITL 审核。
>
> 本文只描述**数据契约字段语义**。Agent 角色边界推导、委派拓扑、决策权限属于 `docs/2.5-agent-architecture.md`；系统级工程边界属于 `docs/2-architecture-decision.md`。

## 1. 通用约定

### 1.1 版本

当前版本：`schema_v0.3`

变更历史：

- `schema_v0.1`：初版，5 个 Agent (Collector/Extractor/Analyst/Writer/QA)，单目标 QA 路由。
- `schema_v0.2`：升级到 6 Agent agentic 架构（合并 Collector+Extractor → Researcher，新增 Supervisor 与 Skill Curator），引入 Supervisor 委派工具协议、多目标 QA 路由、Skill 候选 schema。
- `schema_v0.3`（当前）：升级到 7 + 1 Agent agentic 架构（核心闭环新增 Intake / Planner，异步进化保持 Skill Curator），引入 (1) `RunIntakeDraft` / `IntakeClarifyRequest` / `IntakeUserReply` / `IntakeExchange` 等 chat intake 契约；(2) `PlanTree` / `PlanTask`（含 `source` / `priority` 字段）/ `PlanConfirmRequest` 计划编制契约；(3) `FollowUpRequest` / `FollowUpEntry` 运行中追加指令契约；(4) 11 类 RunEvent 流式事件（`intake.*` / `plan.*` / `tool.*` / `evidence.collected` / `followup.received` / `supervisor.decision` 扩 `plan_task_ids + consumed_follow_up_ids`）。架构推导见 `docs/2.5-agent-architecture.md`，端到端时序见 `docs/2.7-agent-native-intake-and-live-run.md`。

### 1.2 字段演变规则

- 任何字段**删除**或语义改变必须升级 schema 版本。
- 新增**可选字段**可以保持当前版本，但必须在本文补充说明。
- 任何枚举值（Literal）新增必须在本文显式列出。
- Agent 输出的顶层对象必须包含 `schema_version` 字段，便于跨版本兼容性识别。
- 前端不得依赖未在本文登记的字段。

### 1.3 ID 命名约定

- 所有 ID 形如 `<prefix>_<slug>_<seq>`，如 `ev_cursor_pricing_001` / `concl_pricing_diff_001`。
- prefix 必须固定：`run_` / `step_` / `ev_` / `concl_` / `comp_` / `feat_` / `price_` / `feedback_` / `msg_` / `decision_` / `rejection_` / `skill_` / `artifact_` / `plan_` / `ptask_` / `fu_`（后三者为 `schema_v0.3` 新增）。

## 2. 业务领域对象

### 2.1 Competitor

```python
class Competitor(BaseModel):
    id: str
    name: str
    website: str | None = None
    category: str
    positioning: str | None = None
    target_users: list[str] = []
    evidence_ids: list[str] = []
```

- `category` 是产品类别（开放字符串契约），例如 `ai_coding_tool` / `knowledge_base` / `crm`。
- `positioning` 必须来自 evidence 或分析推断，并在结论中绑定证据。
- 竞品按"赛道（segment）→ 产品实例 → 三件套"建模：同一赛道（如"AI 眼镜"）下并列多个**产品实例**（如华为 / Rokid / 小米的眼镜产品），而非公司。发现阶段的产品级字段——`segment`（子赛道）、`vendor`（厂商/品牌）、`introduction`（一句话简介）、`candidate_role`（角色）——由 `DiscoveryCompetitorCandidate` 承载（`backend/app/schemas/agent_outputs_pipeline.py`），抽取后进入竞品 profile 与 watchlist 追踪视图，前端据 `segment` 做赛道分组。

### 2.2 Feature

```python
class Feature(BaseModel):
    id: str
    competitor_id: str
    name: str
    parent_id: str | None = None       # 支持功能树
    description: str | None = None
    maturity: Literal["unknown", "basic", "advanced", "leading"] | None = None
    evidence_ids: list[str]            # 至少 1 条
```

### 2.3 Pricing

```python
class Pricing(BaseModel):
    id: str
    competitor_id: str
    model: str                          # 如 "freemium" / "per_seat" / "usage_based" / "unknown"
    tiers: list[dict] = []
    free_plan: bool | None = None
    enterprise_plan: bool | None = None
    evidence_ids: list[str]
```

- 定价相关结论必须绑定官方定价页或可信公开来源。
- 不确定价格必须写 `model="unknown"`，禁止编造。

### 2.4 Persona

```python
class Persona(BaseModel):
    id: str
    competitor_id: str                  # persona 绑定到具体竞品（产品实例），随三件套一起抽取
    name: str
    role: str
    pain_points: list[str] = []
    jobs_to_be_done: list[str] = []
    evidence_ids: list[str]             # 至少 1 条
```

第一版默认 Persona（来自 `docs/0-qna-signals.md` 信号"产品经理 / 创业者"）：

- 产品经理 / 产品负责人
- 创业者 / CEO / 项目负责人

### 2.5 UserFeedback

```python
class UserFeedback(BaseModel):
    id: str
    competitor_id: str
    sentiment: Literal["positive", "neutral", "negative", "mixed"]
    topic: str
    summary: str
    evidence_ids: list[str]
```

- 公开评论必须使用脱敏后的文本。

### 2.6 Evidence

```python
class Evidence(BaseModel):
    id: str
    run_id: str
    source_type: str                    # 通用字符串契约，运行时校验 ^[a-z][a-z0-9_]{1,31}$
    source_url: str | None = None
    source_title: str | None = None
    quote: str
    sanitized_text: str
    span: dict | None = None
    collected_by: str                   # researcher subgraph instance id
    collected_at: str
    desensitized: bool                  # 必须 true 才能进入下游
```

- `quote` 不放敏感个人信息。
- `desensitized` 必须为 `true` 后才能进入报告或被其他 Agent 引用。
- `source_type` 为开放字符串契约，可在运行时直接使用新值（如 `github_release` / `github_issue`），无需提前注册；领域偏好通过 `applies_to=source_routing` 的 SKILL.md 表达。

### 2.7 Conclusion

```python
class Conclusion(BaseModel):
    id: str
    section: str                        # 报告章节标识
    claim: str
    confidence: Literal["low", "medium", "high"]
    competitor_ids: list[str]
    evidence_ids: list[str]             # 至少 1 条
    risk_flags: list[str] = []
```

- 没有 evidence 的 claim 不允许进入最终报告。
- `confidence` 由 Analyst 评估，QA Reviewer 可降级（如冲突 → `low`）。
- SCH-001（C1）已落地物理表：`conclusions(conclusion_id, run_id, step_id, section, claim, confidence, competitor_ids JSONB, risk_flags JSONB, created_at)` 与 `conclusion_evidence(conclusion_id, evidence_id, relevance_rank, created_at)`；关系表主键为 `(conclusion_id, evidence_id)`。

### 2.8 RunIntakeDraft（`schema_v0.3` 新增）

由 Intake Agent 与用户多轮对话后产出的结构化需求草稿。落库于 `runs.intake_draft` JSONB 列，前端 Intake Checklist 实时反映其完整度。

```python
UserRole = Literal["pm", "founder", "sales", "investor"]
FocusDimension = str   # 运行时字符串契约，不闭集

class RunIntakeDraft(BaseModel):
    user_query: str                                # 必填，用户首句
    user_role: UserRole | None = None
    analysis_intent: str | None = None             # Agent 归一化后的意图概述
    competitors_explicit: list[str] = []           # 用户显式给出的竞品名
    competitors_discovery_mode: bool = False       # 是否让 Agent 自行发现竞品
    domain_hint: str | None = None
    focus_dimensions: list[FocusDimension] = []    # 由 Planner 派生，不进入 is_complete 判定
    report_depth: Literal["debug", "quick", "deep"] = "quick"   # debug 为内部低成本档，分析档位见 docs/2.7-analysis-tiers.md
    reference_urls: list[str] = []

    @computed_field
    @property
    def is_complete(self) -> bool:
        """user_role + analysis_intent + (competitors_explicit ∨ competitors_discovery_mode) 齐全。"""
        ...

class IntakeClarifyRequest(BaseModel):
    question: str
    field_targets: list[str]                       # 这个问题想填的字段名
    suggested_options: list[str] | None = None     # 给用户的快速选项（推荐 2–4 个）

class IntakeUserReply(BaseModel):
    text: str = ""
    selected_options: list[str] = []
    # model_validator 强制 text 或 selected_options 至少一个非空

class IntakeExchange(BaseModel):
    """一轮已完成的 clarify+reply，进 AgentState.intake_history。
    
    取代 Plan 原文的 list[tuple]——tuple 过 AsyncPostgresSaver checkpoint
    JSON 反序列化会降级为 list、类型全丢；与 SupervisorDecision / Evidence
    一样走 Pydantic 模型确保类型守恒。
    """
    clarify: IntakeClarifyRequest
    reply: IntakeUserReply                         # 必填，无 None default：in-flight clarify 住在 pending_clarify
```

- `is_complete` 是 `@computed_field` 只读，禁止字段独立设置，避免 LLM patch 与计算结果漂移。
- Intake LLM 输出契约（不是上面的对象，是 LLM 自己产的 JSON）：`{action: "ask"\|"complete", clarify_request?: IntakeClarifyRequest, draft_patch: dict, reasoning_summary: str}`，`draft_patch` 经 `_sanitize_patch` 白名单（8 字段）二次裁剪后才 merge 到 `intake_draft`。

### 2.9 PlanTree / PlanTask（`schema_v0.3` 新增）

由 Planner Agent 产出的可视化执行计划。落库于 `runs.plan_tree` JSONB 列，前端 PlanConfirmPage 渲染并允许用户勾选 / 添加任务。

```python
PlanTaskStage = Literal["discover", "research", "analyze", "write"]
PlanTaskSource = Literal["agent", "user"]
PlanTaskPriority = Literal["normal", "user_pinned"]

class PlanTask(BaseModel):
    task_id: str                                   # make_id("ptask_")
    stage: PlanTaskStage
    title: str
    description: str = ""
    competitor_id: str | None = None               # research stage 必填
    focus_dimensions: list[str] = []
    source: PlanTaskSource = "agent"               # Phase β：user-injected 强制 "user"
    enabled: bool = True                           # 用户在 PlanConfirm 阶段可勾掉
    priority: PlanTaskPriority = "normal"          # user-injected 强制 "user_pinned"

class PlanTree(BaseModel):
    plan_id: str                                   # make_id("plan_")
    tasks: list[PlanTask]
    rationale: str                                 # Planner Agent 给的整体计划说明
    version: int = 1                               # 每次用户修改 +1
    confirmed_at: str | None = None                # ISO timestamp，planning → executing 的唯一信号

class PlanConfirmRequest(BaseModel):
    disabled_task_ids: list[str] = []              # 用户取消勾选；必须全部命中 pending plan
    additional_tasks: list[PlanTask] = []          # Phase β：user-injected task，上限 5 条
```

- `PlanTree.confirmed_at` 是 phase 推断的唯一数据源（`_derive_run_phase` 读这一字段），不引入额外 `Run.plan_confirmed_at` 列。
- `_normalize_user_tasks` server-side 强制规则：拒 `discover` stage（Agent 专属）/ research 必须有 `competitor_id` / title 1..60 / description ≤ 500 / 强制 `source="user"`, `priority="user_pinned"`, `enabled=True`, 新发 `ptask_` id。
- `disabled_task_ids` 必须全部命中 pending plan 的 `task_id` 集合，否则 `planner_wait_node` 抛错让 bg task 失败（防止 FE 用 stale plan 静默丢弃任务）。
- user-pinned research task 的 `competitor_id` 在 `planner_wait_node` 中作为 `competitors_diff` 返回，借 `AgentState.competitors` 的 `operator.add` reducer 追加进 state，supervisor 下游 hard-constraint 放行新竞品。

### 2.10 FollowUpRequest / FollowUpEntry（`schema_v0.3` 新增）

运行中用户追加的"再多关注 X / 把焦点调整到 Y"等指令。**走 DB inbox 模式**：HTTP 端点 append 到 `runs.follow_ups` JSONB 数组，Supervisor 每轮入口拉未消费记录注入 prompt，决策后写回 `consumed_at`。Supervisor 不在 interrupt 上，对 running thread 调 `aupdate_state` 是 LangGraph 官方明确警示的 race 路径——故采用 lock-free DB inbox。

```python
class FollowUpRequest(BaseModel):
    """HTTP 端点入参。"""
    text: str = Field(min_length=1, max_length=1000)
    applies_to_stage: PlanTaskStage | None = None

class FollowUpEntry(BaseModel):
    """落 runs.follow_ups JSONB 的单条记录。"""
    id: str                                        # make_id("fu_")
    text: str
    applies_to_stage: PlanTaskStage | None = None
    received_at: str                               # ISO timestamp
    consumed_at: str | None = None                 # supervisor 消费后盖戳
    consumed_in_iteration: int | None = None       # 被哪一轮 supervisor decision 吃掉
```

- `POST /api/runs/{run_id}/follow-up` 守卫四态：404 RUN_NOT_FOUND / 409 FOLLOWUP_RUN_NOT_RUNNING（终态）/ 409 FOLLOWUP_NOT_EXECUTING（`plan_tree.confirmed_at` 缺失）/ 409 FOLLOWUP_GRAPH_PAUSED（graph 在 `intake_wait` / `planner_wait`）。
- 仅 supervisor 的 LLM 决策分支消费 follow-up；qa-driven / max-iter 分支保留 pending，下轮再处理（避免在没召唤 LLM 的路径上"吃掉"用户意图）。

## 3. 中间产物

### 3.1 CompetitorKnowledgeFragment（单竞品分片）

单个 Researcher 实例产出的结构化分片：

```python
class CompetitorKnowledgeFragment(BaseModel):
    schema_version: str = "schema_v0.2"
    run_id: str
    competitor_id: str
    researcher_step_id: str             # 产出该分片的 Researcher 实例
    competitor: Competitor
    features: list[Feature]
    pricings: list[Pricing]
    feedback: list[UserFeedback]
    coverage: dict                      # {"feature": "complete", "pricing": "partial", "feedback": "missing"}
    notes: str | None = None            # Researcher 自陈"未覆盖的维度 / 限制条件"
```

`coverage` 字段让 Analyst 与 Supervisor 知道哪些维度数据不足，决定是否要补调研。

### 3.2 CompetitorKnowledgeAggregate（聚合视图）

Analyst 输入的聚合视图，由后端从所有 fragments 自动合成：

```python
class CompetitorKnowledgeAggregate(BaseModel):
    schema_version: str = "schema_v0.2"
    run_id: str
    domain_hint: str | None             # 用户输入的领域自由文本，作为 Analyst / Writer 软提示
    reference_urls: list[str] = []      # 用户额外指定的参考站点（Researcher 优先 fetch）
    fragments: list[CompetitorKnowledgeFragment]
    personas: list[Persona]             # run 级别，非单竞品
    coverage_summary: dict              # 跨竞品维度覆盖率
```

### 3.3 最小合格标准

`CompetitorKnowledgeAggregate` 必须满足：

- 每个竞品至少有 3 个 feature（或在 `coverage` 中显式标注"insufficient_data"）；
- 每个竞品至少有 1 条 pricing 记录或 `model="unknown"`；
- 每个最终 conclusion 至少绑定 1 条 evidence；
- 报告至少覆盖 feature / pricing / user feedback / differentiation / SWOT 五维之一。

### 3.4 Runtime `run_knowledge` 合同（`schema_v0.3` 补充）

`run_knowledge` 是评审面向的三件套事实视图，和 `AnalystOutput` 叙事层分离：

```python
class RunKnowledgePayload(TypedDict):
    schema_version: str
    features: list[Feature]
    pricings: list[Pricing]
    personas: list[Persona]
    coverage: dict[str, dict[str, Literal["complete", "partial", "insufficient_data", "missing"]]]
```

生成规则：

- 由 `service/knowledge/extractor.py` 负责从 `evidence_briefs + competitors + focus_dimensions + analysis_archetype` 抽取，不再要求 analyst LLM 直接产出三件套字段。
- `analysis_archetype="comparison"`：必须尝试抽取三件套；研究维度会自动补齐底座 `feature/pricing/user_feedback` 后再执行。
- `analysis_archetype="landscape"`：不强制逐竞品三件套；允许空三件套并通过 `coverage=insufficient_data` 诚实表达。
- 所有三件套条目必须引用已有 `evidence_id`；非法 evidence 引用在抽取阶段直接过滤。

QA 路由规则（`rule_knowledge_schema_conformance`）：

- `no_evidence` / `insufficient_evidence` → `reject_to=researcher`
- `extraction_empty` / `malformed_fields` / `dishonest_coverage` → `reject_to=analyst`
- `extraction_empty` 在 analyst 首次重试后降级 warning，避免无解循环导致 `degraded`

接口补充：

- `GET /api/runs/{run_id}/knowledge` 返回 `analysis_archetype`，前端据此区分空态文案（`landscape 不适用` vs `comparison 待补采/待抽取`）。

## 4. AgentMessage 通信协议

> 设计参考：rejection / approval 形态借鉴 `assafelovic/gpt-researcher`（Apache-2.0）的 Reviewer + Revisor 反馈闭环模式，但 GR 用自然语言反馈，我们改造为结构化 JSON + 规则 ID 引用 + 多目标路由，便于 QA 规则引擎机器判断。详见 `docs/5-prior-art-and-leverage.md` 与 `docs/2.5-agent-architecture.md` §7。

### 4.1 AgentMessage

```python
class AgentMessage(BaseModel):
    message_id: str
    run_id: str
    step_id: str
    trace_id: str
    source_agent: Literal["intake", "planner", "supervisor", "researcher", "analyst", "writer", "qa", "skill_curator", "user"]
    target_agent: Literal["intake", "planner", "supervisor", "researcher", "analyst", "writer", "qa", "skill_curator", "user"]
    status: Literal["pending", "running", "completed", "rejected", "approved", "degraded", "failed"]
    payload_type: str                   # 见 §4.2
    payload: dict
    evidence_refs: list[str] = []
    artifact_refs: list[str] = []
    created_at: str
```

### 4.2 payload_type 枚举

| payload_type | 通常方向 | 描述 |
|---|---|---|
| `delegation_request` | supervisor → researcher/analyst/writer | Supervisor 工具委派（payload 为 ConductResearch / ConductResearchBatch / Analyze / Write） |
| `evidence_batch` | researcher → supervisor | Researcher 完成调研，返回 evidence + fragment |
| `competitor_knowledge_fragment` | researcher → analyst | 结构化分片（通常通过 supervisor 中转） |
| `analysis_result` | analyst → writer | Analyst 产出的 Conclusion[] |
| `report_draft` | writer → qa | Writer 产出待审报告 |
| `qa_rejection` | qa → {supervisor, researcher, analyst, writer} | 结构化 rejection（payload 为 Rejection） |
| `qa_approval` | qa → supervisor | 通过审查 |
| `supervisor_decision` | supervisor → (trace) | 决策记录（payload 为 SupervisorDecision，含 `plan_task_ids` + `consumed_follow_up_ids`） |
| `intake_clarify_request` | intake → user | Agent 抛出的澄清提问（payload 为 IntakeClarifyRequest） |
| `intake_user_reply` | user → intake | 用户回复（payload 为 IntakeUserReply） |
| `intake_complete` | intake → (trace) | RunIntakeDraft 已满足 is_complete，准备进 Planner |
| `plan_published` | planner → user | Planner 产出 PlanTree 等待用户确认 |
| `plan_confirmed` | user → planner | 用户确认 PlanTree（payload 含 disabled_task_ids + additional_tasks + user_task_count） |
| `followup_received` | user → supervisor (via DB inbox) | 运行中追加指令落库通知 |
| `skill_candidate` | skill_curator → (staging) | Curator 产出的候选 |

枚举为开放集，可通过新增 Agent 协议消息类型扩展，但 core 必须支持上述全部。

### 4.2bis RunEvent 流式事件清单（`schema_v0.3` 新增）

`backend/app/service/event_bus/bus.py::RunEventType` 是前端 SSE 订阅的事件流契约。下表是当前实现的全集（按 phase 时序）：

| RunEventType | phase | payload 关键字段 | 消费者 |
|---|---|---|---|
| `intake.clarify_request` | intake | `question`, `field_targets`, `suggested_options` | NewRunChatPage |
| `intake.user_reply` | intake | `text`, `selected_options` | NewRunChatPage（自映对话历史） |
| `intake.complete` | intake → planning | `intake_draft` 终态、跳转目标 | NewRunChatPage 触发 navigate |
| `plan.published` | planning | 完整 `PlanTree` | PlanConfirmPage |
| `plan.confirmed` | planning → executing | `disabled_task_ids`, `additional_tasks`, `user_task_count` | LiveRunPage |
| `plan.task.start` / `plan.task.finish` | executing | （**未实现，YAGNI**）由 supervisor.decision + step.finish 推断 | — |
| `supervisor.decision` | executing | `chosen_tool`, `tool_args`, `reasoning_summary`, `plan_task_ids`, `consumed_follow_up_ids` | LiveRunPage 左栏 PlanTree 状态、follow-up chip 擦除 |
| `tool.start` / `tool.finish` | executing | `tool`, `competitor_id`, `dimension`, `turn`, `args_summary`, `latency_ms`, `success`, `snippet_count`, `error` | LiveRunPage 右上工具调用面板 |
| `evidence.collected` | executing | `evidence_id`, `competitor_id`, `dimension`, `source_type`, `source_title`, `source_url`, `desensitized` | LiveRunPage 右下证据流 + Evidence Console |
| `followup.received` | executing | `follow_up_id`, `text`, `applies_to_stage`, `received_at` | LiveRunPage chip（未消费态） |
| `step.start` / `step.finish` | * | `step_id`, `agent_name`, `competitor_id`, `status` | LiveRunPage（research task 按 competitor_id 精准完成） |
| `run.finish` | done | `status`, `report_id?` | LiveRunPage 终态延迟跳转 |
| `heartbeat` | * | 现实现是 SSE 注释行 `: keepalive\n\n`，无 enum 值（YAGNI，避免空 consumer） | — |

> 事件 schema 是 additive：所有 payload 字段新增对老订阅者透明，老前端遇到未知字段自动忽略（EventSource 默认行为）。任何字段语义改变必须升 `schema_version`。

### 4.3 evidence_batch 示例

```json
{
  "message_id": "msg_researcher_cursor_001",
  "run_id": "run_ai_coding_001",
  "step_id": "step_researcher_cursor_001",
  "trace_id": "trace_001",
  "source_agent": "researcher",
  "target_agent": "supervisor",
  "status": "completed",
  "payload_type": "evidence_batch",
  "payload": {
    "competitor_id": "comp_cursor",
    "evidence_ids": ["ev_cursor_pricing_001", "ev_cursor_features_001"],
    "fragment_id": "frag_cursor_001",
    "coverage": {"feature": "complete", "pricing": "complete", "feedback": "partial"}
  },
  "evidence_refs": ["ev_cursor_pricing_001", "ev_cursor_features_001"],
  "artifact_refs": ["artifact_researcher_cursor_001"],
  "created_at": "2026-05-23T20:00:00+08:00"
}
```

### 4.4 qa_rejection 示例（多目标路由）

```json
{
  "message_id": "msg_qa_reject_001",
  "run_id": "run_ai_coding_001",
  "step_id": "step_qa_001",
  "trace_id": "trace_001",
  "source_agent": "qa",
  "target_agent": "researcher",
  "status": "rejected",
  "payload_type": "qa_rejection",
  "payload": {
    "rejection_id": "rejection_001",
    "reject_to": "researcher",
    "failed_rule_ids": ["rule_pricing_requires_evidence"],
    "semantic_findings": ["pricing claim for Windsurf references a forum post instead of official source"],
    "required_fields": ["pricing.evidence with source_type=pricing_page or official_site"],
    "retry_policy": {
      "max_retry": 3,
      "current_retry": 1,
      "fallback_action": "finalize_degraded"
    },
    "severity": "blocking"
  },
  "evidence_refs": [],
  "artifact_refs": ["artifact_researcher_windsurf_v1"],
  "created_at": "2026-05-23T20:05:00+08:00"
}
```

## 5. Supervisor 委派工具协议

Supervisor 在每个决策点调用以下工具之一。工具 schema 即委派协议。

### 5.1 工具集 Pydantic 模型

```python
class DiscoverCompetitors(BaseModel):
    """Search the web to discover competitors in a given track/domain."""
    search_queries: list[str] = Field(min_length=1, max_length=5)
    domain_context: str
    max_results: int = Field(default=8, ge=1, le=15)

class ConductResearch(BaseModel):
    """Delegate one Researcher subgraph to study a single research topic."""
    research_topic: str                 # 单个竞品名 + 关注维度
    competitor_id: str
    focus_dimensions: list[str]         # 通用字符串契约，运行时校验 ^[a-z][a-z0-9_]{1,31}$
    max_iterations: int = 6
    fallback_to_offline: bool = True

class Analyze(BaseModel):
    """Trigger Analyst over collected fragments."""
    focus_dimensions: list[str] | None = None
    parallel_by_dimension: bool = False
    require_cross_competitor: bool = True

class Write(BaseModel):
    """Trigger Writer to assemble final report."""
    template_id: str | None             # 可为空；为空时由 Writer 生成默认模板 ID
    sections: list[str] | None = None

class Finalize(BaseModel):
    """Signal that the run is complete."""
    completion_reason: Literal[
        "all_dimensions_covered",
        "max_iterations_hit",
        "fallback_path",
        "user_requested_stop"
    ]
    notes: str | None = None
```

### 5.2 SupervisorDecision（决策可观测）

每次工具委派必须落一行：

```python
class SupervisorDecision(BaseModel):
    id: str
    run_id: str
    iteration: int                      # 第几次决策
    chosen_tool: Literal["DiscoverCompetitors", "ConductResearch", "ConductResearchBatch", "Analyze", "Write", "Finalize"]
    tool_args: dict                     # 工具调用的完整参数（与上述 Pydantic 模型对应）
    reasoning_summary: str              # LLM 自陈"为什么做这个决定"，必填
    triggered_by: Literal[
        "user_query",
        "researcher_completion",
        "analyst_completion",
        "writer_completion",
        "qa_rejection",
        "qa_approval",
        "iteration_advance"
    ] | None = None
    outcome: Literal["dispatched", "rejected_by_qa", "succeeded", "failed"] | None = None
    outcome_recorded_at: str | None = None
    created_at: str
```

`reasoning_summary` 是 agentic 系统决策可观测性的核心，前端 Trace Timeline 必须展示。

## 6. QA Reviewer 协议

### 6.1 Rejection / Approval

```python
class RetryPolicy(BaseModel):
    max_retry: int                      # 该 rejection 在此 step 上的最大重试次数
    current_retry: int = 0
    fallback_action: Literal["finalize_degraded", "skip"] = "finalize_degraded"

class Rejection(BaseModel):
    rejection_id: str
    step_id: str                        # 被打回的 step
    reject_to: Literal["supervisor", "researcher", "analyst", "writer"]
    failed_rule_ids: list[str]          # fast path 触发
    semantic_findings: list[str]        # slow path（LLM 语义审查）发现的问题
    required_fields: list[str]          # 需要补充的字段
    retry_policy: RetryPolicy
    severity: Literal["blocking", "warning"]
    reviewer_step_id: str               # QA 实例 step id
    created_at: str

class Approval(BaseModel):
    approval_id: str
    step_id: str                        # 被通过的 step
    passed_rule_ids: list[str]
    semantic_audit_passed: bool
    reviewer_step_id: str
    created_at: str
```

### 6.2 多目标路由含义

| reject_to | 触发场景 | 上游 Agent 应做的修正 |
|---|---|---|
| `researcher` | evidence 不足 / source 不可信 / 字段缺失 | 重新调研某些维度（Supervisor 重新发 ConductResearch） |
| `analyst` | 结论无据 / 自相矛盾 / 维度不全 | 重新分析（Supervisor 重新发 Analyze） |
| `writer` | 报告结构错误 / 引用断裂 / 模板不符 | 重新组装（Supervisor 重新发 Write） |
| `supervisor` | 单点修复无效，需要整体重新规划（如 `domain_hint` 与 evidence 偏离、fan-out 度不足） | Supervisor 重新决策路径 |

路由目标不可自由组合，必须与 `failed_rule_ids` / `semantic_findings` 的内容一致。

## 7. QA 规则 DSL（fast path）

第一版规则以 `applies_to=qa_rule` 的 SKILL.md 承载，frontmatter 给出元数据、body 中的 ```yaml``` 代码块给出可被 fast path 直接消费的 DSL；启动时由 `SkillStore.list_by_applies_to('qa_rule')` 全量加载。LLM 语义审查（slow path）的 prompt 由 `applies_to=prompt_template` 且 `tags=['qa-semantic']` 的 SKILL.md 提供。

```yaml
- id: rule_conclusion_requires_evidence
  selector: conclusions[*]
  requires:
    - evidence_ids.min_length >= 1
  severity: blocking
  reject_to: analyst
  message: Every conclusion must cite at least one evidence item.

- id: rule_pricing_requires_evidence
  selector: pricings[*]
  requires:
    - evidence_ids.min_length >= 1
    - referenced_evidence.source_type intersects ["pricing_page", "official_site", "docs"]
  severity: blocking
  reject_to: researcher
  message: Pricing claims require official or reliable public evidence.

- id: rule_evidence_must_be_desensitized
  selector: evidence[*]
  requires:
    - desensitized == true
  severity: blocking
  reject_to: researcher
  message: Evidence must be desensitized before downstream analysis.

- id: rule_no_cross_competitor_contradiction
  selector: conclusions[*]
  requires:
    - cross_competitor_consistency_check passed
  severity: warning
  reject_to: analyst
  message: Cross-competitor conflict detected; downgrade confidence or fetch more evidence.
```

领域 QA 规则通过新增 `backend/skills/qa_rule/<id>/SKILL.md` 注册，启动时自动并入 fast path 规则集。Skill Curator 产出的 `qa_rule_candidate` 在审核通过后由 `service/skill_promotion` 写回同路径，下一轮 run 启动即生效。

## 8. Skill Curator 输出协议

### 8.1 SkillCandidate

```python
class SkillCandidate(BaseModel):
    id: str
    candidate_type: Literal["qa_rule", "prompt_template", "source_routing"]
    applies_to: Literal["qa_rule", "prompt_template", "source_routing"]  # 与 candidate_type 对齐
    tags: list[str]                     # Curator 推断的领域 / 角色 / 维度标签
    payload: dict                       # 按 candidate_type 不同的具体内容，见 §8.2
    rationale: str                      # Curator LLM 解释为什么提议这个候选
    supporting_run_ids: list[str]       # 支持该候选的历史 run 证据
    confidence: Literal["low", "medium", "high"]
    status: Literal["staging", "approved", "rejected"] = "staging"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    error: str | None = None            # Curator 任务失败时填
    created_at: str
```

### 8.2 三类 payload schema

```python
class QARuleCandidatePayload(BaseModel):
    """candidate_type=qa_rule"""
    rule_yaml: str                      # 完整 YAML 规则定义，可被 fast path 直接消费
    triggered_failures_count: int       # 历史 run 中该模式触发次数
    similar_existing_rules: list[str]   # 已存在的相近规则 ID

class PromptTemplateCandidatePayload(BaseModel):
    """candidate_type=prompt_template"""
    target_agent: Literal["supervisor", "researcher", "analyst", "writer", "qa"]
    template_name: str
    template_body: str
    replaces_template_id: str | None    # 替换哪个现有 template
    evidence_quality_delta: float       # 替换后的预期 evidence quality 变化
    rejection_rate_delta: float         # 替换后的预期 rejection 率变化

class SourceRoutingCandidatePayload(BaseModel):
    """candidate_type=source_routing"""
    source_type: str
    competitor_category: str
    priority_delta: int                 # +1 / -1 等
    quality_score_sample: list[float]   # 历史质量分样本
```

### 8.3 审核流程

1. Curator 异步产出 → `status=staging`
2. 前端 Skill Staging Console 列出 staging 候选
3. 人工 review → `approved` 或 `rejected`，记录 `reviewed_by` 与 `reviewed_at`
4. `approved` 候选自动写入对应 `backend/skills/<applies_to>/<id>/SKILL.md` 文件（P1 范围）
5. 下一轮 run 启动时重新加载 skill 集

## 9. Evidence ↔ Conclusion 关系

关系类型：多对多。

```text
Conclusion.evidence_ids[] → Evidence.id
Evidence.id → 可被多个 Conclusion 复用
```

对应数据库 join 关系为：

```text
conclusions.conclusion_id = conclusion_evidence.conclusion_id
conclusion_evidence.evidence_id = evidence.id
```

`conclusion_evidence.relevance_rank` 保留 Analyst 输出的 evidence 顺序，按 `conclusions.created_at ASC, relevance_rank ASC` 可还原稳定引用顺序。

前端展示规则：

- 报告中每条 conclusion 显示 evidence 数量；
- 点击 conclusion 展开 evidence cards；
- evidence card 显示 `source_type` / `source_url` / `quote` / `collected_at` / `desensitized`；
- 若 `desensitized=false`，前端必须标红并禁止该 evidence 进入最终报告。

## 10. 技能库 (Skill Library) 扩展机制

### 10.1 目录结构

```text
backend/skills/
├── qa_rule/
│   └── <skill_id>/SKILL.md           # 领域 QA 规则（fast path）
├── prompt_template/
│   └── <skill_id>/SKILL.md           # 章节模板 / Agent 提示模板 / QA 语义 prompt（按 tags 区分）
└── source_routing/
    └── <skill_id>/SKILL.md           # 数据源优先级偏好

backend/demo_fixtures/
└── competitors_seed.yaml             # 演示用竞品种子（仅作前端 autocomplete 提示，不构成约束集）
```

启动时由 `SkillStore.scan()` 全量扫描，按 `applies_to` 索引。Agent 通过 `load_skill(skill_id)` / `read_skill_file(skill_id, slot?)` 两个 Collector Channel 按需 progressive disclosure 加载。

### 10.2 SKILL.md 文件结构

每个技能一个 SKILL.md，YAML frontmatter 给元数据，Markdown body 给可被 Agent 直接消费的内容。

frontmatter 通用字段（与 `service/skill_store/models.py::SkillMetadata` 对齐）：

```yaml
---
name: <human-readable id, 与目录名一致>
description: <一句话说明该技能解决什么问题>
version: <SemVer，body 变更需 bump>
applies_to: qa_rule | prompt_template | source_routing
tags: [<领域 / 角色 / 维度 标签>]
dependencies: [<其它 skill_id>]  # 可选，加载顺序约束
---
```

#### 10.2.1 `applies_to: qa_rule`

body 含一个 ```yaml``` 代码块，提供 fast path DSL（v1 算子）：

```yaml
id: <rule_id>
when:
  section_title_contains: [<str>]    # 命中章节才评估
require:
  section_has_evidence_refs: bool
  has_evidence_with:
    source_type_in: [<str>]
    collected_within_days: int
  evidence_refs_count_gte: int
  section_content_min_chars: int
severity: blocking | warning
reject_to: supervisor | researcher | analyst | writer
message: <人类可读说明>
```

解析失败的规则降级 warning（`parse_error`），不阻塞主 run；trace 中保留 `promoted_qa_rule_ids`、`promoted_qa_enforced_count`、`promoted_qa_parse_error_count`、`promoted_qa_blocked_rule_ids`。

#### 10.2.2 `applies_to: prompt_template`

body 为完整 prompt 主体（自然语言 + 可选 Jinja-like 变量占位）。`tags` 决定消费方：

| 典型 tag 组合 | 消费方 |
|---|---|
| `[writer, report]` | Writer 选作章节模板 |
| `[analyst, dimension]` | Analyst 选作分析维度指南 |
| `[qa-semantic]` | QA Reviewer 语义审查 prompt |

#### 10.2.3 `applies_to: source_routing`

body 描述该 `source_type` 的匹配条件、优先级理由与质量样本（自由 Markdown）。Curator 推断的样本数据可放在 body 的 metadata block。

### 10.3 扩展规则

- 扩展技能**不得污染核心 Schema**（core schema 文件不允许 import 任何 SKILL.md）；
- 新增技能 = 新建一个目录 + 一个 SKILL.md + `alembic upgrade` 无关——**不改 Agent 主流程**；
- 多技能之间互不感知；版本通过 frontmatter `version` 承载；
- 选取由 `domain_hint` 与 `tags` 软匹配完成，不做强枚举；
- 全部可注册扩展点见 `docs/2.5-agent-architecture.md` §9，promotion 工程实现见 `docs/impl/13-skill-library.md`。

## 11. Agent 数据输入输出总表

> Agent 角色边界、决策权限、护栏阈值见 `docs/2.5-agent-architecture.md`。本节只列每个 Agent 的数据 I/O 契约。

| Agent | 主要输入 | 主要输出 | 通信协议 payload_type |
|---|---|---|---|
| Intake | 用户首句 + intake_history + 当前 `RunIntakeDraft` | LLM JSON `{action, clarify_request?, draft_patch?}`；ask 写 `pending_clarify`，complete 切 `phase="planning"` | `intake_clarify_request` / `intake_user_reply` / `intake_complete` |
| Planner | 已 is_complete 的 `RunIntakeDraft` | `PlanTree`（含 `tasks/rationale/version/confirmed_at`），落 `Run.plan_tree` JSONB | `plan_published` / `plan_confirmed` |
| Supervisor | 已确认的 RunIntakeDraft + PlanTree（含 source/priority） + Researcher fragments + QA rejection/approval + 未消费 `runs.follow_ups` + user_pinned task 投影 | `DiscoverCompetitors` / `ConductResearch` / `ConductResearchBatch` / `Analyze` / `Write` / `Finalize` tool call；每次落 `SupervisorDecision`（含 `plan_task_ids` + `consumed_follow_up_ids`） | `delegation_request` / `supervisor_decision` / `followup_received` |
| Researcher | `ConductResearch` 委派（research_topic + focus_dimensions） | `Evidence[]` + `CompetitorKnowledgeFragment` | `evidence_batch` / `competitor_knowledge_fragment` |
| Analyst | `CompetitorKnowledgeAggregate`（由后端合成） | `Conclusion[]`、维度分析 | `analysis_result` |
| Writer | `Conclusion[]` + Evidence 引用 + `prompt_template` SKILL.md（按 `domain_hint + tags` 选取） | `Report`（content_json + content_markdown） | `report_draft` |
| QA Reviewer | 任一 Agent 的 artifact + 全量 evidence + 规则集 + 语义 prompt | `Approval` 或 `Rejection`（多目标） | `qa_approval` / `qa_rejection` |
| Skill Curator | 完整 run trace（runs + steps + llm_calls + supervisor_decisions + evidence + rejection 记录） | `SkillCandidate[]`（status=staging） | `skill_candidate` |

## 12. Schema 版本演变机制

- Schema 变更必须先改本文，再改 Pydantic 模型代码；
- 后端、前端、Agent 任一方需要新增字段，必须写清字段语义和是否必填；
- 任何强约束枚举新增必须更新本文；运行时开放字段（如 `focus_dimensions` / `source_type` / `section_id`）按字符串契约演进；
- 任何 Agent 输出的顶层对象必须带 `schema_version`，便于跨版本兼容性识别；
- 每次发布前冻结 schema 版本，避免临时改字段导致前端崩溃；
- Skill Curator 产出的 `qa_rule_candidate` 在审核通过自动写入 pack 时，**不改变 schema 版本**（属于规则集变更，不是 schema 变更）。
