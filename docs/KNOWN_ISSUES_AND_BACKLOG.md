# Known Issues & Backlog

最后更新: 2026-05-24

> 每条任务都标明 **Entry Files**（独立目录/独立文件），原则上互不重叠，便于队友并行认领、降低合并冲突。
> 跨模块改动须显式声明在 "Cross-cutting" 段，避免隐式抢同一个文件。

## Active Issues 索引

| ID | type | 问题 | 优先级 | 状态 | 主入口模块 | 当前阶段下一步 |
|---|---|---|---|---|---|---|
| ORCH-001 (M1) | improvement | Collector framework 缺失，Researcher 工具集仅 `pack_lookup` | P0 | planned | `service/collector/` + `agents/tools/` | 输出 channel 协议草案,队友认领 |
| OBS-001 | improvement | 关键路径结构化日志几乎为零,bug 难定位 | P0 | planned | `utils/logger.py` + 各 Agent/服务文件 | 定义日志事件清单与字段约定,各模块认领埋点 |
| SCH-001 | improvement | Conclusion/Feature/Pricing/UserFeedback/Persona 仅有 Pydantic,无持久化表 | P0 | planned | `models/conclusion.py` 等 + Alembic | 评审是否需要表化 or 维持 JSONB 内嵌 |
| ING-001 (M3) | improvement | `desensitize_text` 函数与 Researcher 边界调用未实装 | P1 | investigating | `service/desensitize/` | 先补违规样本与失败分布 |
| ORCH-002 (M4) | improvement | 无 SSE 进度流,长 run 只能轮询 | P1 | blocked-by:M1 | `router/run_rt.py` + 前端 hooks | 主干先用 polling,等 SSE 事件 schema 定稿 |
| EXT-001 | improvement | 行业包扩展 schema 注册机制缺失,Pack 只有 yaml | P1 | triaging | `service/industry_pack/extensions.py` | 定义 extension_schema 加载契约 |
| SEC-001 | security | 无 gitleaks pre-commit,Key 误提交风险敞口 | P1 | planned | `.gitleaks.toml` + `.pre-commit-config.yaml` | 选定 hook 工具与规则集 |
| SEC-002 | security | Prompt injection 关键词清洗未实装 | P1 | triaging | `service/prompt_safety/` | 收集越狱模式样本 |
| COMP-001 | doc | `docs/compliance-statement.md` 待建 | P2 | planned | `docs/compliance-statement.md` | 整理数据源 + 抓取约束清单 |
| ORCH-003 (M5) | improvement | Skill Curator 同步版已落地,缺异步化与 approved 写回 pack | P2 | triaging | `agents/nodes/skill_curator.py` + `router/skill_rt.py` | 明确异步触发点与写回冲突策略 |
| CUR-001 | improvement | Skill Curator 三类候选生成未拆分工具,仅单一 prompt | P2 | triaging | `service/skill_curator/generators/` | 评估是否拆 generator 后质量提升 |
| MSG-001 | improvement | AgentMessage schema 已定义但编排未使用,节点间走 dict state | P2 | triaging | `schemas/agent_message.py` + 各节点 | 评估表化必要性 or 仅做逻辑契约 |
| ORCH-004 (M6) | improvement | 仅支持 resume B1,缺 reset_to 阶段重放 | P2 | triaging | `router/run_rt.py` + `agents/graph.py` | 明确 checkpoint 与业务 trace 一致性策略 |
| API-002 (M7) | improvement | 缺 token/cost 护栏,运行成本不可控 | P2 | triaging | `service/llm/` + 配置 | 先补 slot 级成本基线与告警阈值 |
| ORCH-005 (M8) | improvement | 缺 golden eval 集,回归质量难量化 | P2 | triaging | `backend/app/tests/golden/`(新) | 先定义评测样本结构与通过阈值 |

---

## ORCH-001 (M1) Collector framework

- type: improvement
- status: planned
- priority: P0
- owner: _unassigned_

### Current Behavior

Researcher subgraph 当前工具集仅有 `pack_lookup`(`backend/app/agents/tools/pack_lookup.py`),证据源固定为本地行业包快照。

### Limitation

`docs/2.5-agent-architecture.md` §3.2 要求 Researcher 支持 `fetch_url / search_web / parse_page / extract_structured / lookup_offline_snapshot`。当前实现无法接入真实采集渠道,信息源单一,阻塞质量提升。

### Trigger Condition

联调主干稳定后,需并行推进真实采集能力(配合 ING-001 的脱敏边界一起上)。

### Options Considered

1. 直接在 researcher 节点硬编码渠道(实现快,但扩展差)。
2. 先定义 `CollectorChannel` 协议 + registry(可并行、可替换)。

### Entry Files

- `backend/app/service/collector/`(新目录,channel 注册中心)
- `backend/app/agents/tools/<channel>.py`(每个 channel 一个文件,互不冲突)
- `backend/app/agents/subgraphs/researcher.py`(仅注入 channel,不写业务)

### Interface Contract

- `CollectorChannel.collect(query, context) -> list[EvidenceDraft]`
- registry 按 `channel_id` 路由,统一错误语义 + 超时 + 单站 QPS ≤ 1(`docs/2-architecture-decision.md` §11.1)
- channel 输出必须经 `desensitize_text`(见 ING-001)再落 evidence

### Acceptance Criteria

- 至少 1 个 stub channel 可被 researcher 调用
- channel 失败不阻塞主 run(可降级到 pack_lookup)
- trace 中可区分 `source_type`

### DoD

- 单测覆盖 registry 路由与错误分支
- smoke 中至少一条 evidence 来源于 channel stub

### Suggested Effort

~1.5 人日

### Next Step

输出 collector 协议草案 + 一个 stub channel 实现并由队友认领扩充。

---

## OBS-001 Structured logging instrumentation

- type: improvement
- status: planned
- priority: P0
- owner: _unassigned_

### Current Behavior

`backend/app/utils/logger.py` 已配置 `structlog` JSON 输出 + `request_id` contextvar 自动绑定,但**全工程仅 `app_main.py` 有 3 处埋点**(service_start / service_stop / unhandled_exception)。Supervisor / Researcher / Analyst / Writer / QA / Skill Curator 6 个节点、LLM Client、QA Engine、Industry Pack Registry、Resume API、Skill Review API **全部零日志埋点**。

### Limitation

- AI/人调试只能靠 PG 表 + traceback,**不抛异常的降级路径几乎不可观测**(LLM fallback prompt 命中、Writer fallback 模式、QA semantic 跳过、Supervisor max_iter 兜底 finalize、Send fan-out 实际并发度)。
- 关键决策点缺日志,`bind_request_id` 价值无法兑现。
- 复合 bug(跨节点状态错位)需要按 `run_id` grep 日志才能快速串起来,目前缺这条线。

### Trigger Condition

立即,这是其它任务的前置基础设施(后续任何调试都依赖)。

### Mandatory Log Events(最小集,所有埋点必须包含 `run_id`/`step_id`/`iteration`)

| 模块 | 事件名 | 字段(除 request_id/run_id 外) | 必要级别 |
|---|---|---|---|
| Supervisor | `supervisor.decision` | `iteration`、`chosen_tool`、`triggered_by`、`fanout_k`、`reasoning_summary_len` | info |
| Supervisor | `supervisor.iter_limit_hit` | `iteration`、`max`、`pending_tools` | warning |
| Researcher | `researcher.subgraph.start` | `competitor_id`、`research_topic`、`focus_dimensions` | info |
| Researcher | `researcher.tool_call` | `tool`、`args_summary`、`latency_ms`、`error` | info |
| Researcher | `researcher.compress` | `compression_count`、`prompt_tokens`、`reason` | info |
| Researcher | `researcher.subgraph.finish` | `evidence_count`、`coverage`、`status` | info |
| Analyst | `analyst.start` / `analyst.finish` | `fragment_count`、`conclusion_count` | info |
| Writer | `writer.start` / `writer.finish` | `template_id`、`section_count`、`fallback_used` | info |
| QA | `qa.decision` | `route`(approved/rejected)、`reject_to`、`failed_rule_ids`、`semantic_used` | info |
| QA | `qa.rule_engine.fail_open` | `rule_id`、`error` | warning |
| Skill Curator | `skill_curator.candidates` | `candidate_count`、`by_type` | info |
| LLM Client | `llm.call` | `model_slot`、`model`、`latency_ms`、`prompt_tokens`、`completion_tokens`、`error`、`fallback_used` | info |
| LLM Client | `llm.retry` | `model_slot`、`attempt`、`error` | warning |
| Pack Registry | `pack.loaded` / `pack.reload` | `pack_id`、`competitors_count`、`rules_count` | info |
| API | `api.run.create` / `api.run.resume` | `run_id`、`industry_pack`、`competitor_count` | info |

### Entry Files

- `backend/app/utils/logger.py`(扩展辅助 helper,如 `bind_run(run_id, step_id)`)
- 各模块各自的实现文件(**每个文件独立认领,互不冲突**):
  - `backend/app/agents/nodes/supervisor.py`
  - `backend/app/agents/nodes/analyst.py`
  - `backend/app/agents/nodes/writer.py`
  - `backend/app/agents/nodes/qa.py`
  - `backend/app/agents/nodes/skill_curator.py`
  - `backend/app/agents/subgraphs/researcher.py`
  - `backend/app/service/llm/client.py`
  - `backend/app/service/qa/engine.py`
  - `backend/app/service/industry_pack/registry.py`
  - `backend/app/router/run_rt.py`
  - `backend/app/router/skill_rt.py`

### Interface Contract

- 不允许 `log.info(f"...")` 字符串拼接,必须 `log.info("event.name", key=value, ...)` 结构化形式
- 不打印 prompt 原文、API Key、JWT、完整证据 quote;只打长度/哈希/截断前 N 字符
- error 路径用 `log.exception(...)` 保留 traceback;预期失败用 `log.warning(...)`
- 与 `core/config.py::LOG_LEVEL` 联动,本地默认 INFO,生产可降为 WARNING

### Acceptance Criteria

- 按 `run_id` 在容器日志里 `rg "run_xxx"` 能完整还原一次 run 的决策路径
- 至少覆盖上表全部事件
- 单测验证 supervisor decision 与 qa decision 至少产生一条结构化日志(stub stdout 捕获)

### DoD

- `docs/impl/<n>-logging-conventions.md` 记录事件清单与字段约束,后续新增日志须更新该文档
- README 或 dev 文档说明如何按 `run_id` 过滤日志
- 单测覆盖核心事件 emit 路径

### Suggested Effort

~1.5 人日(分到各模块每人 1-2 文件)

### Next Step

1. 先在 `utils/logger.py` 加 `bind_run()` helper
2. 写 `docs/impl/<n>-logging-conventions.md` 锁事件清单
3. 按 Entry Files 分发给队友并行落埋点

---

## SCH-001 Business entity persistence

- type: improvement
- status: planned
- priority: P0
- owner: _unassigned_

### Current Behavior

`docs/3-schema-and-protocol.md` §2 定义了 Feature / Pricing / Persona / UserFeedback / Conclusion / CompetitorKnowledgeFragment 全套 Pydantic 模型(`backend/app/schemas/business.py`);但 ORM 层只持久化了 `runs / steps / llm_calls / evidence / report / artifact / supervisor_decision / skill_candidate` 8 张表。Conclusion / Feature / Pricing 等**没有独立表**,仅以 JSON 嵌入 `report.content_json` 与 `step.payload`。

### Limitation

- `docs/3-schema-and-protocol.md` §9 "Evidence ↔ Conclusion 多对多双向溯源"在数据库层无法直接表达,只能通过解析 markdown / JSON 字段间接实现。
- QA 规则若要按 `selector: conclusions[*]` 跨 run 复用历史 conclusion 做语义校验,目前必须从 JSONB 反序列化。
- Skill Curator 反思时无法直接按 SQL 聚合 conclusion-evidence 关系,只能解析 trace。
- 业务实体级 GIN 索引、维度过滤都用不上。

### Trigger Condition

- ORCH-001 接入真实采集后 evidence 量级上升,需要结构化查询
- 或 Skill Curator 反思路径需要跨 run 聚合(配合 CUR-001)

### Options Considered

1. **维持 JSONB 内嵌**:简单,延迟决策;但放弃了上述能力。
2. **完整表化**:为 5 类业务实体 + agent_messages(可选)各开一张表,补 Alembic 迁移,Writer/Analyst 节点同步双写。
3. **折中**:只表化 Conclusion(报告核心结构),Feature/Pricing 维持 fragment JSON 内嵌。

### Entry Files

- `backend/app/models/conclusion.py`(新)
- `backend/app/models/feature.py`(新,可选)
- `backend/app/models/pricing.py`(新,可选)
- `backend/app/models/user_feedback.py`(新,可选)
- `backend/app/models/persona.py`(新,可选)
- `backend/db/migrations/versions/<timestamp>_add_business_entities.py`(新 Alembic 迁移)
- `backend/app/agents/nodes/analyst.py`(双写 conclusion)
- `backend/app/agents/nodes/writer.py`(从 conclusion 表读)
- 每张表独立文件,**Alembic 版本号按时间戳生成自动避免冲突**

### Interface Contract

- 新表不允许向后破坏:`reports.content_json` 仍保留完整 JSON 作为冗余
- 业务实体表外键到 `runs.id`,必须索引
- evidence_ids 维持 list[str](JSONB),GIN 索引按需开

### Acceptance Criteria

- Conclusion 表可被 SQL 直接查询并 join evidence
- Writer 渲染逻辑可从 conclusion 表读结构化数据再渲染 markdown
- smoke 验证 conclusion 与 evidence 的多对多关系可通过 SQL 还原

### DoD

- Alembic 迁移 up/down 都成立
- 单测覆盖 conclusion 与 evidence 多对多查询

### Suggested Effort

~2 人日(全表化)/ ~0.5 人日(仅 Conclusion 表化,推荐第一版)

### Next Step

先决策"折中方案 vs 完整表化",再开迁移。

---

## ING-001 (M3) Desensitization pipeline

- type: improvement
- status: investigating
- priority: P1
- owner: _unassigned_

### Current Behavior

`backend/app/schemas/business.py` 中 `Evidence.desensitized: bool` 已保留;但 **`desensitize_text(text) -> str` 函数完全不存在**,Researcher 输出落 evidence 时也没有强制脱敏边界调用。`docs/2-architecture-decision.md` §6.3-§6.4 要求的 "raw → desensitize → evidence" 边界目前是空契约。

### Limitation

- 一旦 ORCH-001 接入真实渠道,原始内容会绕过脱敏直接落 evidence
- 当前没有任何 PII 替换规则、对抗用例、单测,合规说明无依据

### Trigger Condition

ORCH-001 接入真实数据前必须升级,否则不允许联调真实 channel。

### Options Considered

1. 沿用布尔值(短期简单,但 ORCH-001 触发即破)
2. 引入规则化脱敏函数 + 痕迹字段 + 单测集

### Entry Files

- `backend/app/service/desensitize/`(新目录,独立模块)
  - `__init__.py`、`engine.py`(规则集)、`patterns.py`(正则)
- `backend/app/agents/subgraphs/researcher.py`(在 evidence 落表前调用,**不与 ORCH-001 抢同一文件区域**)
- `backend/app/tests/test_desensitize.py`(新)

### Interface Contract

```python
def desensitize_text(text: str) -> tuple[str, list[dict]]:
    """Return sanitized text + masked spans for audit trail."""
```

- 失败时不静默,直接抛 `DesensitizeError`(架构红线)
- 覆盖最小集:邮箱 / 手机号 / 中国身份证 / 信用卡号 / 用户名 @mention / 头像 URL

### Acceptance Criteria

- 提供 ≥15 条对抗样本单测全部 pass
- Researcher 边界强制调用,`Evidence.desensitized` 由函数结果决定而不是写死 `True`

### DoD

- 单测覆盖每条规则
- `docs/compliance-statement.md`(见 COMP-001)中引用本规则集

### Suggested Effort

~1 人日

### Next Step

先补三类高风险样本(邮箱、手机号、用户名),明确规则边界后再进入 planned。

---

## ORCH-002 (M4) SSE run progress

- type: improvement
- status: blocked-by:M1
- priority: P1
- owner: _unassigned_

### Current Behavior

前端 `useRunDetail / useRunTrace` 每 2 秒轮询 `/api/runs/{id}` 与 `/api/runs/{id}/trace`,主干联调可用。

### Limitation

长任务体验差,且轮询对后端有重复请求开销。`docs/2-architecture-decision.md` §4 已定方案是 PG `LISTEN/NOTIFY` + SSE,目前未实装。

### Entry Files

- `backend/app/router/run_rt.py`(新增 SSE endpoint)
- `backend/app/service/event_bus/`(新目录,基于 PG LISTEN/NOTIFY)
- `frontend/src/api/hooks.ts`(替换 polling 为 EventSource)
- `frontend/src/pages/RunViewPage.tsx`

### Acceptance Criteria

- 关键事件(step.start/finish、supervisor.decision、qa.outcome、run.finish)能从后端实时推送到前端
- 断线自动重连,且 trace 表 append-only 兜底重放
- p95 刷新延迟 < 1s

### DoD

- 明确 SSE 事件最小 schema 并落 `docs/impl/<n>-sse-events.md`
- 前端不再轮询(保留兜底超时刷新)

### Trigger Condition

M2 页面稳定后,轮询负载或用户等待明显上升。

### Suggested Effort

~2 人日

### Next Step

先收集轮询频率、请求量和用户等待时间基线,再设计 SSE 事件 schema。

---

## EXT-001 Industry pack extension schema

- type: improvement
- status: triaging
- priority: P1
- owner: _unassigned_

### Current Behavior

`industry_packs/<pack>/` 当前仅有 `competitors.yaml` / `report_template.yaml` 等 YAML 文件;`docs/3-schema-and-protocol.md` §10.1 要求的 `extension_schema.py`(领域 Pydantic 扩展模型,如 `AICodingExtension`)与 `researcher_tools/`(领域专用工具目录)**未实装注册机制**。

### Limitation

- "Extensible" 红线只在文档里成立,代码层尚未提供加载 pack Python 扩展的契约
- 新行业接入时只能改 yaml,无法接入领域工具/扩展字段

### Entry Files

- `backend/app/service/industry_pack/extensions.py`(新,扩展模型注册中心)
- `backend/app/service/industry_pack/registry.py`(增加 `load_extension_schema(pack_id)`)
- `industry_packs/<pack>/extension_schema.py`(新,每个 pack 独立文件)
- `industry_packs/<pack>/researcher_tools/`(新,可选)

### Interface Contract

- pack 通过 `entrypoint` 或动态 import 注入扩展模型,core 永远不直接 import pack 内部模块
- 扩展字段不允许污染 core schema,只能挂在 `*_extension` 字段下

### Acceptance Criteria

- AI Coding pack 注册 `AICodingExtension`,Researcher fragment 输出可携带扩展字段
- 单测验证未注册 pack 不影响其它 pack 加载

### DoD

- 文档 `docs/impl/<n>-industry-pack-extension.md` 记录扩展契约
- 至少一个 pack 提供 extension_schema 示例

### Trigger Condition

需要接入第二个行业包(非 ai_coding_tools)或现行业要求领域字段。

### Suggested Effort

~1 人日

### Next Step

定义 extension_schema 加载契约,选定 entrypoint vs 动态 import。

---

## SEC-001 gitleaks pre-commit hook

- type: security
- status: planned
- priority: P1
- owner: _unassigned_

### Current Behavior

`.gitignore` 已排除 `.env`,但仓库无任何静态扫描,人工失误风险敞口。

### Limitation

`docs/2-architecture-decision.md` §11.2 明确建议接入 `gitleaks`,目前未落地。Doubao / OpenAI / Qwen Key 误提交风险存在。

### Entry Files

- `.gitleaks.toml`(新)
- `.pre-commit-config.yaml`(新)
- `scripts/install_hooks.sh`(新,可选)
- `docs/impl/<n>-secrets-hygiene.md`(新)

### Interface Contract

- 阻止包含已知 Key 前缀(`sk-`、`ak_`、Doubao endpoint 模式)的 commit
- 不扫 `data/`、`docs/private/`(白名单)

### Acceptance Criteria

- 本地 commit 含模拟 Key 字符串被拒
- CI 上同步运行 gitleaks(选配 GitHub Actions)

### DoD

- README 增加 pre-commit 安装步骤

### Suggested Effort

~0.5 人日

### Next Step

选定 hook 工具(`pre-commit` + `gitleaks`)并写规则文件。

---

## SEC-002 Prompt injection sanitization

- type: security
- status: triaging
- priority: P1
- owner: _unassigned_

### Current Behavior

`docs/2-architecture-decision.md` §11.3 要求 "公开评论先过脱敏函数,再过 prompt-injection 关键词清洗",当前**关键词清洗层完全不存在**。Researcher 抓取到的文本会直接进入 LLM context(经脱敏后)。

### Limitation

公开评论 / 论坛帖子可能携带 "Ignore previous instructions" 类越狱指令,LLM 可能被诱导跳过 QA 或泄露 prompt。

### Entry Files

- `backend/app/service/prompt_safety/`(新目录)
  - `__init__.py`、`sanitizer.py`、`patterns.py`
- `backend/app/agents/subgraphs/researcher.py`(在 desensitize 之后追加调用)
- `backend/app/tests/test_prompt_safety.py`(新)

### Interface Contract

```python
def neutralize_injection_signals(text: str) -> tuple[str, list[str]]:
    """Strip or quote known jailbreak patterns; return cleaned text + matched pattern ids."""
```

- 清洗结果与 desensitize 一样落 audit trail(`prompt_safety_findings` 字段或并入 evidence.span)

### Acceptance Criteria

- 覆盖至少 10 类常见越狱模式样本
- 命中模式时在 evidence trace 上有明确标记

### DoD

- 单测覆盖每类模式
- `SEC-002` 落 `docs/impl/<n>-prompt-safety.md`

### Trigger Condition

ORCH-001 接入真实公开评论数据前必须上线。

### Suggested Effort

~1 人日

### Next Step

收集越狱模式样本与对抗用例。

---

## COMP-001 compliance statement

- type: doc
- status: planned
- priority: P2
- owner: _unassigned_

### Current Behavior

`docs/2-architecture-decision.md` §11.1 已声明 "`docs/compliance-statement.md`(待建)",文件目前不存在。

### Limitation

无对外可引用的合规说明文档,采集行为缺统一披露。

### Entry Files

- `docs/compliance-statement.md`(新,**独立文件,无冲突**)

### Acceptance Criteria

- 列出每个 channel 的数据来源、抓取约束、robots 策略、User-Agent
- 引用 ING-001 / SEC-002 的脱敏与清洗规则集
- 标注 evidence `collected_at` / `source_url` 字段语义

### DoD

- README 末尾链接到本文档

### Suggested Effort

~0.5 人日

### Next Step

等 ORCH-001 与 ING-001 落地后整理实际采集约束。

---

## ORCH-003 (M5) Skill Curator async reflection

- type: improvement
- status: triaging
- priority: P2
- owner: _unassigned_

### Current Behavior

Skill Curator 已在主流程中同步执行(`backend/app/agents/nodes/skill_curator.py`),并提供 `GET/POST /api/skill-candidates*` 审批 API 与前端审核页(`frontend/src/pages/SkillStagingPage.tsx`)。

### Limitation

- Curator 仍是同步节点,主 run 完成时间受其影响
- `approved` 候选尚未自动写回 `industry_packs/<pack>/skills/` 生效池
- 与 `docs/2.5-agent-architecture.md` §6.1 "不阻塞主 loop" 的目标偏离

### Entry Files

- `backend/app/agents/graph.py`(qa-approved 后异步触发改造)
- `backend/app/agents/nodes/skill_curator.py`
- `backend/app/router/skill_rt.py`(approved 写回路径)
- `industry_packs/<pack>/skills/`(目标目录)

### Acceptance Criteria

- Curator 从主图拆为异步任务,失败不影响主 run 完成时间
- `approved` 候选可写回 `industry_packs/<pack>/skills/` 并保留可审计变更记录

### Trigger Condition

主流程 wall-clock 受反思阶段影响,或出现需要自动生效 skill 的明确需求。

### DoD

- 异步触发不影响 run 完成时间
- 写回路径有 Git diff 级审计

### Suggested Effort

~1.5 人日

### Next Step

先定义异步触发点、写回冲突策略和 reviewer 兜底机制。

---

## CUR-001 Skill Curator generators split

- type: improvement
- status: triaging
- priority: P2
- owner: _unassigned_

### Current Behavior

`backend/app/service/skill_curator/engine.py` 通过**单一通用 prompt**让 LLM 同时产出三类候选(qa_rule / prompt_template / source_routing)。

### Limitation

`docs/2.5-agent-architecture.md` §3.6 列出 4 个独立工具(`extract_rejection_patterns / evaluate_prompt_effectiveness / rank_source_routing / generate_candidate`),目前混在一起。三类候选的 trace 视角不同,合并 prompt 让 LLM 难以专注,质量不稳。

### Entry Files

- `backend/app/service/skill_curator/generators/`(新目录,每个候选类型一个文件)
  - `qa_rule.py`、`prompt_template.py`、`source_routing.py`
- `backend/app/service/skill_curator/engine.py`(改为 generator dispatcher,**仅入口改动,主体逻辑下沉**)

### Interface Contract

```python
class BaseCandidateGenerator(Protocol):
    candidate_type: str
    async def generate(self, run_traces: list[RunTrace]) -> list[SkillCuratorCandidate]: ...
```

### Acceptance Criteria

- 三个 generator 互不耦合,可独立替换
- 至少一个 generator 用历史 rejection 模式驱动(`extract_rejection_patterns`)

### DoD

- 单测验证 generator 输出 schema 与 engine 聚合输出一致
- Curator 的 trace 中可看到每类候选来自哪个 generator

### Suggested Effort

~1 人日

### Next Step

评估是否拆 generator 后候选质量提升,先做 A/B 一次 run 对比。

---

## MSG-001 AgentMessage usage in orchestration

- type: improvement
- status: triaging
- priority: P2
- owner: _unassigned_

### Current Behavior

`backend/app/schemas/agent_message.py` 已定义 `AgentMessage` Pydantic 模型,但 LangGraph 编排中**未被使用**:节点之间通过 `AgentState`(TypedDict)dict 传递,supervisor decision / qa rejection 已有独立表,evidence_batch 走 state delta。

### Limitation

- `docs/3-schema-and-protocol.md` §4 定义的 `payload_type` 枚举与示例在代码里没有对应实例
- 若要支持跨 run / 跨服务的 message replay,目前没有统一入口

### Options Considered

1. **维持现状**:AgentMessage 仅作为契约文档存在,节点继续用 state dict + 独立表覆盖可观测
2. **物理表化**:新增 `agent_messages` 表统一持久化,所有节点输出走 AgentMessage 构造
3. **仅逻辑契约**:节点输出统一包装成 AgentMessage Pydantic 对象(不入表),前端按 message 视角渲染

### Entry Files

- `backend/app/schemas/agent_message.py`(契约校准)
- 各节点输出适配:**当前不要改主体逻辑,只在 step.payload 落 AgentMessage dump**
- (可选)`backend/app/models/agent_message.py` + Alembic 迁移

### Trigger Condition

需要跨 run 的 message replay,或前端 Trace Timeline 要按 AgentMessage 视角统一渲染时。

### DoD

- 评审纪要明确 "维持现状 / 仅逻辑契约 / 物理表化" 的最终选择
- 选定方案后落 `docs/impl/<n>-agent-message-runtime.md`

### Suggested Effort

~0.5 人日(仅逻辑契约)/ ~1.5 人日(表化)

### Next Step

评审是否需要 message 级 replay 能力,再决定方案 1/2/3。

---

## ORCH-004 (M6) Resume B2 reset_to replay

- type: improvement
- status: triaging
- priority: P2
- owner: _unassigned_

### Current Behavior

已支持 `/api/runs/{id}/resume`(B1),仅 thread 级恢复,不支持阶段重放。

### Limitation

无法对特定阶段精确重试(如只重跑 writer)。

### Entry Files

- `backend/app/router/run_rt.py`
- `backend/app/agents/graph.py`(配合 checkpoint reset_to)
- `backend/app/service/checkpoint/`(可选新模块)

### DoD

- checkpoint 与业务 trace 的一致性方案达成评审

### Trigger Condition

出现明确的阶段性重放需求且 B1 不足。

### Suggested Effort

~1.5 人日

### Next Step

梳理 `update_state` 与历史 steps 清理策略的冲突点。

---

## API-002 (M7) LLM cost guardrails

- type: improvement
- status: triaging
- priority: P2
- owner: _unassigned_

### Current Behavior

`llm_calls` 表已记录 token / latency,但缺预算上限与自动降级策略。

### Limitation

成本不可预测,难支撑持续迭代与多 run 对比。

### Entry Files

- `backend/app/service/llm/budget.py`(新)
- `backend/app/service/llm/client.py`(在 call 前检查)
- 配置:`core/config.py` 增加 slot 级预算字段

### DoD

- 每个 model_slot 有成本预算与超限动作

### Trigger Condition

多 run 压测下 token 波动超过可接受阈值。

### Suggested Effort

~1 人日

### Next Step

先给出 slot 级 token / latency 成本基线。

---

## ORCH-005 (M8) Golden eval set

- type: improvement
- status: triaging
- priority: P2
- owner: _unassigned_

### Current Behavior

回归主要靠 smoke 与人工观察,无标准化黄金集。

### Limitation

质量回归无法快速定位,版本对比缺客观基准。

### Entry Files

- `backend/app/tests/golden/`(新目录)
  - `cases/*.yaml`、`runner.py`、`assertions.py`
- `scripts/run_golden.sh`(新)
- CI(可选)

### DoD

- 定义最小黄金样本集(query + expected assertions)
- 可复跑脚本和通过阈值

### Trigger Condition

迭代频率提升后需要自动化质量门禁。

### Suggested Effort

~2 人日

### Next Step

先确定 10 条核心场景与统一断言口径。

---

## Highlights for v2(评审亮点候选,非主干阻塞)

| ID | 方向 | 触发条件 | 入口文件 |
|---|---|---|---|
| HLT-001 | DAG Run View(`@xyflow/react`) | 需要把 Agent 拓扑直观展示给评审 | `frontend/src/pages/RunTracePage.tsx` |
| HLT-002 | Battlecard 卡片网格视图 | 需要一屏展示多竞品结论卡片 | `frontend/src/pages/RunViewPage.tsx` |
| HLT-003 | Prospect Voice 主题视图 | 需要突出真实用户声音与情感分布 | `frontend/src/pages/RunVoicePage.tsx`(新) |
| HLT-004 | Compare 跨竞品矩阵 | 需要横向比较 feature / pricing 差异 | `frontend/src/pages/RunComparePage.tsx`(新) |
| HLT-005 | Skill Curator 真异步化 | 主流程耗时受 Curator 影响或需要脱耦 | `backend/app/agents/nodes/skill_curator.py` |
| HLT-006 | approved 候选写回 `industry_packs` | 需要完成 skill 生效闭环并可审计 diff | `backend/app/router/skill_rt.py`、`industry_packs/*/skills/` |
| HLT-007 | Battlecard freshness + importance 视觉系统 | 演示阶段需要更强业务可读性 | `frontend/src/components/StatusBadge.tsx`、`frontend/src/pages/RunViewPage.tsx` |
