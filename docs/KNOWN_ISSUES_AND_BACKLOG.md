# RivalLens 实现 TODO

最后更新: 2026-05-24

对照 `docs/2-architecture-decision.md` / `docs/2.5-agent-architecture.md` / `docs/3-schema-and-protocol.md`，列出尚未实现的功能点。按 P0-P3 排序，完成打勾。新增条目按已有格式：设计引用 + 现状 + 入口 + 验收。

---

## P0（阻塞主干 / 致命缺失）

### [ ] OBS-001 关键路径结构化日志

- **设计**：docs/2 §3.10 `structlog` 结构化日志写文件 + Observable-by-default 原则
- **现状**：`backend/app/utils/logger.py` 已配 `structlog` JSON + `request_id` contextvar；全工程仅 `app_main.py` 三处埋点（启动/停止/未捕获异常）。6 个 Agent 节点、LLM Client、QA Engine、Pack Registry、Skill Curator、Run/Skill 路由全部零日志
- **入口**：`backend/app/utils/logger.py`（加 `bind_run(run_id, step_id)` helper） + `agents/nodes/*.py` + `agents/subgraphs/researcher.py` + `service/llm/client.py` + `service/qa/engine.py` + `service/industry_pack/registry.py` + `router/run_rt.py` + `router/skill_rt.py`
- **埋点最小集**：Supervisor decision / Researcher tool_call+compress / LLM call+retry+fallback / QA outcome（含 reject_to） / Skill Curator candidate count / Pack load / Run API 入口
- **约束**：不打 prompt 原文 / API Key / 完整 evidence quote；只打长度、哈希、截断前 N 字
- **验收**：按 `run_id` 在容器日志 `rg "run_xxx"` 可还原一次 run 的决策路径

### [ ] ORCH-001 Researcher 真实采集渠道

- **设计**：docs/2.5 §3.2 Researcher 工具集 `fetch_url` / `search_web` / `parse_page` / `extract_structured` / `lookup_offline_snapshot`
- **现状**：`agents/tools/` 只有 `pack_lookup`，证据源固定为本地行业包快照
- **入口**：`backend/app/service/collector/`（channel 注册中心） + `backend/app/agents/tools/<channel>.py`（每 channel 一个文件） + `agents/subgraphs/researcher.py`（注入 channel）
- **约束**：单站点 QPS ≤ 1（docs/2 §11.1）；`urllib.robotparser` 检 robots.txt；User-Agent `RivalLens-Researcher/0.1`；输出强制经 ING-001 脱敏
- **验收**：至少 1 个 stub channel 被 Researcher 调用；channel 失败不阻塞主 run；trace 可区分 `source_type`

### [ ] ING-001 `desensitize_text` 边界函数

- **设计**：docs/2 §6.3-§6.4 强制脱敏边界 `raw → desensitize_text → evidence.sanitized_text`
- **现状**：`schemas/business.py` 中 `Evidence.desensitized:bool` 字段存在；`desensitize_text(text)` 函数不存在；Researcher 落 evidence 时无强制调用
- **入口**：`backend/app/service/desensitize/`（新目录：`engine.py` + `patterns.py`） + `agents/subgraphs/researcher.py`（边界调用） + `backend/app/tests/test_desensitize.py`
- **覆盖**：邮箱 / 手机号 / 中国身份证 / `@mention` 用户名 / 头像 URL
- **约束**：失败抛 `DesensitizeError`，不静默；与 ORCH-001 同期上线
- **验收**：≥15 条对抗样本单测 pass；`Evidence.desensitized` 由函数结果决定而不是写死 True

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

### [ ] SEC-002 Prompt injection 关键词清洗

- **设计**：docs/2 §11.3 公开评论先过脱敏，再过越狱关键词清洗
- **现状**：清洗层完全不存在；Researcher 抓取的文本经脱敏后直接进 LLM context
- **入口**：`backend/app/service/prompt_safety/`（新目录：`sanitizer.py` + `patterns.py`） + `agents/subgraphs/researcher.py`（desensitize 之后调用） + `backend/app/tests/test_prompt_safety.py`
- **触发**：ORCH-001 接公开评论数据前必须上线
- **验收**：≥10 类越狱模式样本检测命中；命中模式在 evidence trace 上有明确标记

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

---

## P3（工程治理 / 优化）

### [ ] SEC-001 gitleaks pre-commit hook

- **设计**：docs/2 §11.2 建议接入 `gitleaks` pre-commit hook 阻止 Key 误提交
- **现状**：`.gitignore` 已排除 `.env`；无任何静态扫描
- **入口**：`.gitleaks.toml` + `.pre-commit-config.yaml` + `scripts/install_hooks.sh`
- **验收**：本地 commit 含模拟 Key 字符串被拒绝

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

### [ ] COMP-001 compliance-statement.md

- **设计**：docs/2 §11.1 `docs/compliance-statement.md`（待建）
- **入口**：`docs/compliance-statement.md`
- **内容**：每个 channel 数据来源 / 抓取约束 / robots 策略 / User-Agent；引用 ING-001 + SEC-002 规则集
- **触发**：ORCH-001 + ING-001 + SEC-002 落地后整理实际约束

---

## 评审亮点（Highlights，非阻塞）

演示前如果有时间选 1-2 个：

| ID | 方向 | 入口 |
|---|---|---|
| HLT-001 | DAG Run View（`@xyflow/react`） Agent 拓扑可视化 | `frontend/src/pages/RunTracePage.tsx` |
| HLT-002 | Battlecard 卡片网格视图，一屏多竞品 | `frontend/src/pages/RunViewPage.tsx` |
| HLT-003 | Prospect Voice 用户声音 / 情感分布视图 | `frontend/src/pages/RunVoicePage.tsx`（新） |
| HLT-004 | Compare 跨竞品矩阵 | `frontend/src/pages/RunComparePage.tsx`（新） |

---

## 已完成（Done）

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
