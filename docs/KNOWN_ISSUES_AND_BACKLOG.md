# RivalLens 实现 TODO

最后更新: 2026-05-29

对照 `docs/2-architecture-decision.md` / `docs/2.5-agent-architecture.md` / `docs/3-schema-and-protocol.md`，列出尚未实现的功能点。按 P0-P3 排序，完成打勾。新增条目按已有格式：设计引用 + 现状 + 入口 + 验收。

---

## P0（阻塞主干 / 致命缺失）

### [x] OBS-001 关键路径结构化日志

- **设计**：docs/2 §3.10 `structlog` 结构化日志写文件 + Observable-by-default 原则
- **现状**：已落地 three-layer 本地埋点：Layer1 `bind_run/bind_step` contextvars；Layer2 `service/llm/client.py` 的 `llm.call.start/retry/fallback/finish`；Layer3 `supervisor.decision` / `qa.outcome` / `researcher.tool_call|compress|finalize` / `skill_curator.candidate` / `pack.load.*` / `api.run.*` / `api.skill.*`
- **入口**：`backend/app/utils/logger.py`（加 `bind_run(run_id, step_id)` helper） + `agents/nodes/*.py` + `agents/subgraphs/researcher.py` + `service/llm/client.py` + `service/qa/engine.py` + `service/industry_pack/registry.py` + `router/run_rt.py` + `router/skill_rt.py`
- **埋点最小集**：Supervisor decision / Researcher tool_call+compress / LLM call+retry+fallback / QA outcome（含 reject_to） / Skill Curator candidate count / Pack load / Run API 入口
- **约束**：不打 prompt 原文 / API Key / 完整 evidence quote；只打长度、哈希、截断前 N 字
- **验收**：`run_2e3be66d95c3` 已在容器日志回放通过，可见 `api.run.create.start → node.start → llm.call.* → supervisor.decision → researcher.tool_call/finalize → qa.fast_path/slow_path/outcome → skill_curator.candidate`

---

## P1（质量 / 联调体验）

### [x] ORCH-002 SSE 进度推送

- **设计**：docs/2 §4 PG `LISTEN/NOTIFY` + SSE / EventSource 自动重连
- **现状**：已落地 `service/event_bus`（PG `LISTEN/NOTIFY` + 进程内 fan-out）与 `/api/runs/{run_id}/events` SSE，前端 `useRunEvents` 事件驱动 invalidation；轮询降到 10s 作为 fallback
- **入口**：`backend/app/service/event_bus/bus.py` + `backend/app/router/run_rt.py` + `frontend/src/api/sse.ts` + `frontend/src/api/hooks.ts`
- **事件**：`step.start` / `step.finish` / `supervisor.decision` / `qa.outcome` / `run.finish`
- **验收**：断线自动重连；trace append-only 兜底重放；p95 刷新延迟 < 1s

---

## P2（扩展性 / 自进化）

### [x] EXT-001 行业包扩展 schema 注册机制

- **设计**：docs/3 §10.1 `industry_packs/<pack>/extension_schema.py` + `researcher_tools/` 加载契约
- **现状**：已通过通用字符串契约 + 校验器（`schemas/contracts.py`）落地可扩展边界，`focus_dimension / section_id / template_id / source_type` 不再受代码闭集限制
- **入口**：`backend/app/schemas/contracts.py` + `backend/app/schemas/supervisor.py` + `backend/app/service/industry_pack/models.py`
- **结论**：本周期“通用契约已达成”；`extension_schema.py` 的 Python 插槽作为路线图保留，待出现强类型字段注入的真实需求再做
- **验收**：无 pack 任意竞品可跑通至 QA approved，且维度/章节为运行时生成

### [x] ORCH-003 Skill Curator 异步化

- **设计**：docs/2.5 §3.6 + §6.1 异步，run 完成后启动，不参与主图并行
- **现状**：已从主图移除 `skill_curator` 节点，`qa.approved -> END`；`/api/runs` 与 `/api/runs/{id}/resume` 在主图完成后 `create_task` 启动 `run_skill_curator_for_run`，并挂入 `app.state.background_tasks`
- **入口**：`backend/app/agents/graph.py` + `backend/app/service/skill_curator/tasks.py` + `backend/app/router/run_rt.py` + `backend/app/app_main.py`
- **验收**：Curator 异步失败写 `skill_candidates.error` 且不阻断主 run 完成；shutdown 时后台任务可取消

### [x] FRT-001 Conclusion → Evidence 一键溯源

- **设计**：docs/0 §4 评分维度 1 要求“每条分析结论可定位到原始数据源，支持一键跳转或溯源查看”
- **现状**：后端 `GET /api/runs/{run_id}/report` 已返回 `evidence_id_to_brief`；新增 `/runs/:runId/evidence` 独立 Evidence Console，支持 `competitor_id/source_type/evidence_id` 过滤和高亮
- **入口**：`frontend/src/pages/RunViewPage.tsx` + `frontend/src/pages/RunTracePage.tsx` + `frontend/src/pages/RunEvidencePage.tsx` + `frontend/src/components/EvidenceDrawer.tsx`
- **验收**：report citation / competitor 卡片 / supervisor decision / drawer 四个入口均可跳转到 Evidence Console 并定位 evidence

### [x] METRIC-001 业务闭环指标面板

- **设计**：docs/0 §4 评分维度 3 要求“准确率、覆盖率、人工修正率”等可运营指标
- **现状**：新增 `GET /api/runs/{run_id}/metrics`，统一输出 coverage/QA/token/latency/manual-review-proxy 等指标；RunView 新增指标卡片
- **入口**：`backend/app/router/run_rt.py` + `backend/app/service/metrics/engine.py` + `frontend/src/components/MetricsPanel.tsx` + `frontend/src/pages/RunViewPage.tsx`
- **验收**：至少输出 coverage_rate / qa_rejection_rate / manual_review_rate，且口径在 endpoint docstring 与前端提示中可追溯

### [x] EXT-002 行业包扩展 source_type 注册

- **设计**：docs/3 §2.6 Evidence.source_type 可扩展；docs/2.6 channel 映射决策树
- **现状**：`Evidence.source_type` / `Collector.SourceType` 已改为通用字符串契约，保留 `KNOWN_SOURCE_TYPES` 仅作启发式提示，不作校验闸门
- **入口**：`backend/app/schemas/business.py` + `backend/app/service/collector/base.py` + `backend/app/agents/tools/extract_structured.py`
- **结论**：本周期“通用契约已达成”；pack 级 Python 注册机制降级为可选增强
- **验收**：未知 source_type 可被透传并通过 QA/存储链路，不再静默降级为固定白名单

---

## P3（工程治理 / 优化）

### [x] SEC-001 提交前参赛资源泄漏拦截（scanner-first）

- **设计**：赛题方额外通知 API Key / EP 多次泄漏将触发强制退赛；这是参赛资源与仓库治理红线，和 `docs/0` 第 82 行的“采集数据隐私与安全”不是同一类问题
- **现状**：已落地 `scripts/scan_secrets.py`，并接入 `.githooks/pre-commit`、`.github/workflows/secret-scan.yml`、`.cursor/.codex/.claude` hook 的 commit/push 拦截；`docs/0-problem-background.md` 中误入仓库的明文样式 EP 已替换为占位符
- **入口**：`scripts/scan_secrets.py` + `.githooks/pre-commit` + `.github/workflows/secret-scan.yml` + `hooks/safety_guard.py`
- **验收**：`python scripts/scan_secrets.py --staged/--all-tracked` 可通过；模拟 Key/EP 字符串会阻断 commit 或 CI
- **备注**：`gitleaks` 作为可选增强，不阻塞当前版本

### [ ] SEC-003 gitleaks 规则集接管（可选增强）

- **设计**：在现有 scanner-first 防线基础上，可增加第三方规则库与误报基线管理
- **现状**：当前已具备本地与 CI 双层扫描，满足当前赛题风险控制
- **备注**：边际收益低于通用化主线，本周期不做
- **入口**：`.gitleaks.toml` + `.pre-commit-config.yaml`
- **触发**：需要跨项目统一规则、统一审计报表、或团队已接受额外误报处理成本时
- **验收**：不显著增加误报的前提下，替换或并行现有扫描链路

### [ ] API-002 LLM 成本护栏

- **设计**：docs/2 §3.8 slot 级独立配置 + asyncio.Semaphore 限流
- **现状**：`llm_calls` 表已记 token/latency；无 slot 级 budget 与超限动作
- **备注**：边际收益低于通用化主线，本周期不做
- **入口**：`backend/app/service/llm/budget.py` + `service/llm/client.py`（call 前检查） + `core/config.py`（slot 预算字段）
- **验收**：每个 model_slot 有 token 预算；超限触发降级 prompt 或 skip

### [x] ORCH-004 Resume B2 reset_to 阶段重放

- **设计**：docs/2.5 §8 + docs/2 §10.1 节点中断恢复
- **现状**：已支持 `POST /api/runs/{id}/reset`（`reset_to in {writer, analyst}`）。执行时会清理目标阶段及后续 trace（steps/reports/conclusions），通过 checkpoint `aupdate_state(as_node="supervisor")` 重写阶段入口，再 `ainvoke(None)` 重放；重放完成后继续发 `run.finish` 并异步触发 curator
- **入口**：`backend/app/router/run_rt.py`（reset endpoint + checkpoint state override） + `frontend/src/api/hooks.ts` / `frontend/src/pages/RunViewPage.tsx`（阶段重放 UI） + `backend/app/tests/test_smoke.py`（writer/analyst replay 覆盖）
- **验收**：`reset_to=writer` 与 `reset_to=analyst` 可重放并回到 completed；`running` run 会返回 409 `RUN_NOT_RESETTABLE`
- **备注**：researcher 级 reset_to（涉及 `researched_competitors` 累加 reducer 与 fan-out）留在后续独立 plan

### [x] ORCH-005 Golden eval 集

- **设计**：docs/2.5 §8 失败模式可量化回归
- **现状**：已落地 `backend/app/tests/golden/`（10 条 case + runner + assertions）与 `backend/app/scripts/run_golden.py` 报告导出，支持固定口径回归
- **入口**：`backend/app/tests/golden/cases/*.yaml` + `backend/app/tests/golden/runner.py` + `backend/app/tests/golden/assertions.py` + `backend/app/scripts/run_golden.py`
- **验收**：可批量复跑 10 条核心场景并生成报告（`docs/private/golden_report_<ts>.md`）

### [x] CUR-001 Skill Curator 三类候选 generator 拆分

- **设计**：docs/2.5 §3.6 `extract_rejection_patterns` / `evaluate_prompt_effectiveness` / `rank_source_routing` / `generate_candidate` 四工具
- **现状**：已拆分 `qa_rule` / `prompt_template` / `source_routing` 三个 generator，engine 改为 dispatcher 并发汇总；trace 可区分 `skill_curator.<type>.start/finish`
- **入口**：`backend/app/service/skill_curator/generators/` + `backend/app/service/skill_curator/prompts.py` + `backend/app/service/skill_curator/engine.py`
- **验收**：任一 generator 失败不阻断其余类型候选产出；可在日志中定位候选来源

### [x] ORCH-006b promoted qa_rule YAML DSL 解释器

- **设计**：docs/2.5 §6.4 + docs/3 §10.1（`qa_rules_promoted.yaml`）
- **现状**：已新增 `service/qa/promoted_rules.py`，支持最小 DSL 算子并接入 `service/qa/engine.py`；promoted 规则可触发 blocking reject，且 payload 透传 `promoted_qa_blocked_rule_ids`
- **入口**：`backend/app/service/qa/promoted_rules.py` + `backend/app/service/qa/engine.py` + `backend/app/agents/nodes/qa.py`
- **验收**：构造 promoted 规则可稳定触发 `reject_to=writer`；`required_fields` 与 blocked rule id 可追溯

### [ ] MSG-001 AgentMessage 编排落地

- **设计**：docs/3 §4 AgentMessage + payload_type 枚举
- **现状**：`schemas/agent_message.py` Pydantic 模型已定义；编排走 `AgentState` dict
- **入口**：各节点输出包装为 AgentMessage，落 `step.payload`；评审决定是否物理表化（增加 `models/agent_message.py`）
- **决策点**：物理表 vs 仅逻辑契约
- **备注**：边际收益低于通用化主线，本周期不做

---

## 评审亮点（Highlights，非阻塞）

演示前如果有时间选 1-2 个：

| ID | 方向 | 入口 |
|---|---|---|
| HLT-002 | Battlecard 卡片网格视图，一屏多竞品 | `frontend/src/pages/RunViewPage.tsx` |
| HLT-003 | Prospect Voice 用户声音 / 情感分布视图 | `frontend/src/pages/RunVoicePage.tsx`（新） |
| HLT-004 | Compare 跨竞品矩阵 | `frontend/src/pages/RunComparePage.tsx`（新） |

---

## 已完成（Done）

- [x] OBS-001 关键路径结构化日志（three-layer：contextvars + llm.call.* + decision span；按 run_id 可回放）
- [x] ORCH-001 Researcher 真实采集渠道（`search_web` / `fetch_url` / `parse_page` / `extract_structured` / `lookup_offline_snapshot` + `fixtures_lookup`，dispatcher 接入 `ChannelRegistry`）
- [x] ING-001 `desensitize_text` 边界函数（邮箱 / 手机号 / 身份证 / @mention / 头像 URL / Bearer token，失败抛 `DesensitizeError`）
- [x] SEC-002 Prompt injection 关键词清洗（10 类模式命中写入 evidence metadata）
- [x] SEC-001 提交前参赛资源泄漏拦截（API Key / EP scanner-first：`scan_secrets.py` + `.githooks/pre-commit` + `secret-scan` CI + agent hooks）
- [x] SCH-001 Conclusion 持久化表（`conclusions` + `conclusion_evidence` 多对多落库；Analyst 双写，Writer 表优先 + JSON fallback）
- [x] ORCH-006 approved 候选写回 industry_packs（`qa_rule` 写回 `skills/qa_rules_promoted.yaml` + pack loader 读取 + QA trace 透传 `promoted_qa_rule_ids`；`prompt_template/source_routing` 先落盘）
- [x] FRT-001 Conclusion → Evidence 一键溯源（Evidence Console + 多入口跳转/高亮）
- [x] METRIC-001 业务闭环指标面板（`GET /api/runs/{run_id}/metrics` + RunView MetricsPanel）
- [x] HLT-001 DAG Run View（`@xyflow/react` + `@dagrejs/dagre`，`/runs/:runId/trace` 默认 DAG Tab，支持节点详情抽屉与 Evidence 跳转）
- [x] COMP-001 `docs/compliance-statement.md`（数据来源、抓取范围、robots/QPS/UA、脱敏与提示注入边界）
- [x] Supervisor 主循环 + tool calling 委派（ConductResearch / Analyze / Write / Finalize）
- [x] Researcher ReAct subgraph + compress_context 节点
- [x] Analyst LLM 跨竞品分析
- [x] Writer LLM 报告生成（content_json + content_markdown）
- [x] QA Reviewer fast path（规则 DSL） + slow path（LLM 语义）
- [x] QA 多目标 rejection（reject_to ∈ {supervisor, researcher, analyst, writer}）
- [x] Skill Curator 同步版 + 三类候选生成
- [x] Skill Candidate 审批 API（list / approve / reject）+ 前端 Skill Staging Console
- [x] LangGraph Send fan-out 动态 K 并行
- [x] LangGraph checkpoint-postgres + resume B1（thread 级）
- [x] LLM Provider 多模型路由（豆包 / OpenAI / Qwen）+ fallback prompt
- [x] industry pack YAML 注册（competitors / report_template / qa_rules / qa_semantic_prompt）
- [x] PG 数据模型：runs / steps / llm_calls / supervisor_decisions / evidence / reports / artifacts / skill_candidates
- [x] 业务实体 Pydantic schema（Competitor / Feature / Pricing / Persona / UserFeedback / Evidence / Conclusion / Fragment / Aggregate）
- [x] Supervisor 委派工具 schema（ConductResearch / Analyze / Write / Finalize / SupervisorDecision）
- [x] Rejection / Approval schema + RetryPolicy
- [x] SkillCandidate schema + 三类 payload
- [x] AgentMessage schema 定义（编排未使用，见 MSG-001）
- [x] FastAPI 路由：runs / packs / skill-candidates / health
- [x] 前端 Run List / NewRun / RunView / RunTrace / SkillStaging 页
- [x] main 分支保护（PR + approval + force push 禁止 + 删除禁止）
- [x] Docker compose dev 编排（postgres + backend）
