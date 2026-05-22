# RivalLens 竞品知识 Schema 与 Agent 通信协议

> 本文是三人协作的契约源头。后端模型、Agent 输出、前端 Evidence Console 和报告渲染都必须对齐本文。

## 1. 版本约定

当前版本：`schema_v0.1`

规则：

- 任何字段删除或语义改变必须升级 schema 版本。
- 新增可选字段可以保持当前版本，但必须在本文补充说明。
- Agent 输出必须包含 `schema_version`。
- 前端不得依赖未登记字段。

## 2. 核心对象

### Competitor

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

语义：

- `category` 是行业包内的产品类别，例如 `ai_coding_tool`。
- `positioning` 必须来自 evidence 或分析推断，并在结论中绑定证据。

### Feature

```python
class Feature(BaseModel):
    id: str
    competitor_id: str
    name: str
    parent_id: str | None = None
    description: str | None = None
    maturity: str | None = None
    evidence_ids: list[str]
```

规则：

- `evidence_ids` 至少 1 条。
- `maturity` 可选值建议为 `unknown / basic / advanced / leading`。

### Pricing

```python
class Pricing(BaseModel):
    id: str
    competitor_id: str
    model: str
    tiers: list[dict] = []
    free_plan: bool | None = None
    enterprise_plan: bool | None = None
    evidence_ids: list[str]
```

规则：

- 定价相关结论必须绑定官方定价页或可信公开来源。
- 不确定价格必须写 `unknown`，不能编造。

### Persona

```python
class Persona(BaseModel):
    id: str
    name: str
    role: str
    pain_points: list[str]
    jobs_to_be_done: list[str]
    evidence_ids: list[str] = []
```

第一版默认 Persona：

- 产品经理 / 产品负责人。
- 创业者 / CEO / 项目负责人。

### UserFeedback

```python
class UserFeedback(BaseModel):
    id: str
    competitor_id: str
    sentiment: str
    topic: str
    summary: str
    evidence_ids: list[str]
```

规则：

- `sentiment` 可选值：`positive / neutral / negative / mixed`。
- 公开评论必须使用脱敏后的文本。

### Evidence

```python
class Evidence(BaseModel):
    id: str
    run_id: str
    source_type: str
    source_url: str | None = None
    source_title: str | None = None
    quote: str
    sanitized_text: str
    span: dict | None = None
    collector_id: str
    collected_at: str
    desensitized: bool
```

规则：

- `source_type` 可选值：`official_site / docs / pricing_page / public_review / article / local_note`。
- `quote` 不放敏感个人信息。
- `desensitized` 必须为 `true` 后才能进入报告。

### Conclusion

```python
class Conclusion(BaseModel):
    id: str
    section: str
    claim: str
    confidence: str
    competitor_ids: list[str]
    evidence_ids: list[str]
    risk_flags: list[str] = []
```

规则：

- `evidence_ids` 至少 1 条。
- `confidence` 可选值：`low / medium / high`。
- 没有证据的 claim 不允许进入最终报告。

## 3. 竞品知识包

```python
class CompetitorKnowledge(BaseModel):
    schema_version: str = "schema_v0.1"
    run_id: str
    industry_pack: str
    competitors: list[Competitor]
    features: list[Feature]
    pricings: list[Pricing]
    personas: list[Persona]
    feedback: list[UserFeedback]
    conclusions: list[Conclusion]
```

最小合格标准：

- 每个竞品至少有 3 个 feature。
- 每个竞品至少有 1 条 pricing 记录或明确 `unknown`。
- 每个最终 conclusion 至少绑定 1 条 evidence。
- 报告至少覆盖 feature / pricing / user feedback / differentiation / SWOT。

## 4. Agent 间消息协议

> 设计参考：rejection / approval 消息形态借鉴 `assafelovic/gpt-researcher`（Apache-2.0）的 Reviewer + Revisor 反馈闭环模式，在其自然语言反馈基础上改造为结构化 JSON + 规则 ID 引用，便于 QA 规则引擎机器判断。详见 `docs/5-prior-art-and-leverage.md` 第 4.1 节。

### AgentMessage

```python
class AgentMessage(BaseModel):
    message_id: str
    run_id: str
    step_id: str
    trace_id: str
    source_agent: str
    target_agent: str
    status: str
    payload_type: str
    payload: dict
    evidence_refs: list[str] = []
    artifact_refs: list[str] = []
    created_at: str
```

`status` 可选值：

- `pending`
- `running`
- `completed`
- `rejected`
- `approved`
- `failed`

`payload_type` 可选值：

- `collection_plan`
- `evidence_batch`
- `competitor_knowledge`
- `analysis_result`
- `report_draft`
- `qa_rejection`
- `qa_approval`

### evidence batch 示例

```json
{
  "message_id": "msg_collector_001",
  "run_id": "run_ai_coding_001",
  "step_id": "step_collector_001",
  "trace_id": "trace_001",
  "source_agent": "collector",
  "target_agent": "extractor",
  "status": "completed",
  "payload_type": "evidence_batch",
  "payload": {
    "items": ["ev_cursor_docs_001", "ev_windsurf_pricing_001"]
  },
  "evidence_refs": ["ev_cursor_docs_001", "ev_windsurf_pricing_001"],
  "artifact_refs": ["artifact_collector_output_001"],
  "created_at": "2026-05-21T20:00:00+08:00"
}
```

### rejection message 示例

```json
{
  "message_id": "msg_qa_reject_001",
  "run_id": "run_ai_coding_001",
  "step_id": "step_qa_001",
  "trace_id": "trace_001",
  "source_agent": "qa",
  "target_agent": "analyst",
  "status": "rejected",
  "payload_type": "qa_rejection",
  "payload": {
    "reason": "pricing conclusion lacks evidence",
    "failed_rule_ids": ["rule_pricing_requires_evidence"],
    "required_fields": ["pricing_model", "source_url", "quote"],
    "retry_policy": {
      "max_retry": 1,
      "next_agent": "analyst"
    }
  },
  "evidence_refs": [],
  "artifact_refs": ["artifact_analysis_v1"],
  "created_at": "2026-05-21T20:05:00+08:00"
}
```

### approval message 示例

```json
{
  "message_id": "msg_qa_approve_001",
  "run_id": "run_ai_coding_001",
  "step_id": "step_qa_002",
  "trace_id": "trace_001",
  "source_agent": "qa",
  "target_agent": "writer",
  "status": "approved",
  "payload_type": "qa_approval",
  "payload": {
    "passed_rule_ids": [
      "rule_conclusion_requires_evidence",
      "rule_pricing_requires_evidence"
    ]
  },
  "evidence_refs": ["ev_windsurf_pricing_001"],
  "artifact_refs": ["artifact_analysis_v2"],
  "created_at": "2026-05-21T20:07:00+08:00"
}
```

## 5. Evidence 与 Conclusion 关系

关系类型：多对多。

```text
Conclusion.evidence_ids[] → Evidence.id
Evidence.id → 可被多个 Conclusion 复用
```

前端展示规则：

- 报告中的每条 conclusion 都显示 evidence 数量。
- 点击 conclusion 展开 evidence cards。
- evidence card 显示 source_type、source_url、quote、collected_at、desensitized。
- 若 `desensitized=false`，前端必须标红并禁止进入最终报告。

## 6. 轻量 QA 规则 DSL

第一版规则使用 JSON / YAML 配置，不引入复杂规则引擎。

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
  reject_to: analyst
  message: Pricing claims require official or reliable public evidence.

- id: rule_evidence_must_be_desensitized
  selector: evidence[*]
  requires:
    - desensitized == true
  severity: blocking
  reject_to: collector
  message: Evidence must be desensitized before downstream analysis.
```

## 7. AI Coding 行业包扩展

行业包名称：

```text
ai_coding_tools
```

扩展字段示例：

```python
class AICodingExtension(BaseModel):
    competitor_id: str
    ide_integration: list[str] = []
    model_provider_list: list[str] = []
    repo_context_capability: str | None = None
    terminal_agent: bool | None = None
    code_review_support: bool | None = None
    enterprise_security: list[str] = []
    evidence_ids: list[str] = []
```

规则：

- 扩展字段不得污染核心 Schema。
- 报告可以读取扩展字段生成行业章节。
- 换行业时新增另一个 extension model，不改 Agent 主流程。

## 8. Agent 职责边界

| Agent | 输入 | 输出 | 不负责 |
|---|---|---|---|
| Collector | 竞品列表、数据源模板 | Evidence[] | 不做商业分析 |
| Extractor | Evidence[] | CompetitorKnowledge 草稿 | 不写最终报告 |
| Analyst | CompetitorKnowledge | Conclusion[]、SWOT、差异分析 | 不采集新数据，除非被 QA 打回要求补采 |
| Writer | QA 通过的分析结果 | Report JSON / Markdown | 不新增无证据结论 |
| QA | 所有 artifact 和 evidence | approval / rejection | 不替代 Analyst 写结论 |

## 9. 字段演变机制

- Schema 变更必须先改本文，再改 Pydantic 模型。
- 后端、前端、Agent 任一方需要新增字段，必须写清字段语义和是否必填。
- 每次录屏前冻结 schema 版本，避免临时改字段导致前端崩溃。
