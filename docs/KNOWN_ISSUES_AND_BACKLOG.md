# RivalLens 实现 TODO

最后更新: 2026-05-27

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

### [ ] SCH-001 Conclusion 持久化表

- **设计**：docs/3 §2.7 Conclusion + §9 Evidence ↔ Conclusion 多对多双向溯源
- **现状**：`schemas/business.py` 已定义 Conclusion / Feature / Pricing / Persona / UserFeedback 全套 Pydantic；ORM 层无对应表，数据只以 JSON 嵌在 `report.content_json` / `step.payload`
- **入口**：`backend/app/models/conclusion.py` + `backend/app/alembic/versions/<timestamp>_add_conclusions.py` + `agents/nodes/analyst.py`（双写） + `agents/nodes/writer.py`（改读结构化）
- **范围**：第一版**只**表化 Conclusion，其他实体保留 JSON 内嵌；真有跨 run 查询需求再扩
- **验收**：SQL 直接 join evidence 还原多对多；smoke 验证 Conclusion 表 row count ≥ 1

### [ ] ORCH-002 SSE 进度推送

- **设计**：docs/2 §4 PG `LISTEN/NOTIFY` + SSE / EventSource 自动重连
- **现状**：前端 `useRunDetail` / `useRunTrace` 每 2 秒轮询 `/api/runs/{id}` 与 `/api/runs/{id}/trace`
- **入口**：`backend/app/router/run_rt.py`（SSE endpoint） + `backend/app/service/event_bus/`（PG LISTEN/NOTIFY 封装） + `frontend/src/api/hooks.ts`（改 EventSource）
- **事件**：`step.start` / `step.finish` / `supervisor.decision` / `qa.outcome` / `run.finish`
- **验收**：断线自动重连；trace append-only 兜底重放；p95 刷新延迟 < 1s

---

## P2（扩展性 / 自进化）

### [ ] EXT-001 行业包扩展 schema 注册机制

- **设计**：docs/3 §10.1 `industry_packs/<pack>/extension_schema.py` + `researcher_tools/` 加载契约
- **现状**：`industry_packs/ai_coding_tools/` 只有 YAML；Pack Python 扩展注入机制不存在
- **入口**：`backend/app/service/industry_pack/extensions.py` + `backend/app/service/industry_pack/registry.py`（加 `load_extension_schema(pack_id)`） + `industry_packs/ai_coding_tools/extension_schema.py`
- **触发**：接第二个行业包，或 AI Coding pack 需要 `AICodingExtension` 字段
- **验收**：AICodingExtension 注册可挂到 Researcher fragment 上；未注册 pack 不影响其他 pack 加载

### [ ] ORCH-003 Skill Curator 异步化

- **设计**：docs/2.5 §3.6 + §6.1 异步，run 完成后启动，不参与主图并行
- **现状**：Curator 是主图同步节点（`agents/graph.py` 中 QA approved → skill_curator → END）；run wall-clock 受 Curator 影响
- **入口**：`backend/app/agents/graph.py`（qa-approved 后异步触发改造） + `agents/nodes/skill_curator.py`
- **验收**：Curator 拆为异步任务，失败不影响主 run 完成时间

### [ ] ORCH-006 approved 候选写回 industry_packs

- **设计**：docs/2.5 §6.1 闭环 / docs/2 §7.2 `skill_candidates ──[approved by reviewer]──> industry_packs/<pack>/skills/`
- **现状**：审批 API 有，approved 状态切换可用；写回 YAML 文件未做
- **入口**：`backend/app/router/skill_rt.py`（approve handler 触发写回） + `industry_packs/<pack>/skills/`
- **验收**：approved 候选生成对应 YAML 文件；Git diff 可审计变更

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

### [ ] EXT-002 行业包扩展 source_type 注册

- **设计**：docs/3 §2.6 Evidence.source_type 可扩展；docs/2.6 channel 映射决策树
- **现状**：当前实现固定 7 类 source_type，尚未提供 pack 级扩展注册入口
- **入口**：`backend/app/service/collector/registry.py` + `backend/app/service/industry_pack/extensions.py`（新增） + `industry_packs/<pack>/extension_schema.py`
- **触发**：第二行业包需要新增来源类型（例如 `github_release` / `app_store_review`）
- **验收**：新 pack 可注册新增 source_type 且不影响现有 7 类映射与查询

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
- **入口**：`.gitleaks.toml` + `.pre-commit-config.yaml`
- **触发**：需要跨项目统一规则、统一审计报表、或团队已接受额外误报处理成本时
- **验收**：不显著增加误报的前提下，替换或并行现有扫描链路

### [ ] API-002 LLM 成本护栏

- **设计**：docs/2 §3.8 slot 级独立配置 + asyncio.Semaphore 限流
- **现状**：`llm_calls` 表已记 token/latency；无 slot 级 budget 与超限动作
- **入口**：`backend/app/service/llm/budget.py` + `service/llm/client.py`（call 前检查） + `core/config.py`（slot 预算字段）
- **验收**：每个 model_slot 有 token 预算；超限触发降级 prompt 或 skip

### [ ] ORCH-004 Resume B2 reset_to 阶段重放

- **设计**：docs/2.5 §8 + docs/2 §10.1 节点中断恢复
- **现状**：`POST /api/runs/{id}/resume` 仅 thread 级（B1），不支持 reset_to 阶段重放
- **入口**：`backend/app/router/run_rt.py` + `agents/graph.py`（配合 checkpoint reset_to） + 可选 `backend/app/service/checkpoint/`
- **验收**：可指定 `reset_to=writer` 等阶段，清理后续 steps 重新跑

### [ ] ORCH-005 Golden eval 集

- **设计**：docs/2.5 §8 失败模式可量化回归
- **现状**：回归仅靠 smoke + 人工观察
- **入口**：`backend/app/tests/golden/cases/*.yaml` + `runner.py` + `assertions.py` + `scripts/run_golden.sh`
- **验收**：10 条核心场景，可复跑脚本 + 通过阈值

### [ ] CUR-001 Skill Curator 三类候选 generator 拆分

- **设计**：docs/2.5 §3.6 `extract_rejection_patterns` / `evaluate_prompt_effectiveness` / `rank_source_routing` / `generate_candidate` 四工具
- **现状**：`service/skill_curator/engine.py` 单一 prompt 同时产出三类候选
- **入口**：`backend/app/service/skill_curator/generators/`（每候选类型一文件） + `service/skill_curator/engine.py`（改 dispatcher）
- **验收**：三个 generator 互不耦合；trace 可看到每类候选来自哪个 generator

### [ ] MSG-001 AgentMessage 编排落地

- **设计**：docs/3 §4 AgentMessage + payload_type 枚举
- **现状**：`schemas/agent_message.py` Pydantic 模型已定义；编排走 `AgentState` dict
- **入口**：各节点输出包装为 AgentMessage，落 `step.payload`；评审决定是否物理表化（增加 `models/agent_message.py`）
- **决策点**：物理表 vs 仅逻辑契约

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
