# RivalLens Known Issues & Backlog

最后更新：2026-05-29

本清单只保留仍有决策价值的条目。  
已经被 Agent-Native 4 轴重构彻底替代的历史方案，统一归档到实现文档，不再作为待办推进。

---

## P0（阻塞项）

当前无 P0 未完成项。

---

## P1（近期必须收敛）

### [ ] SKILL-001 Progressive Disclosure 观测指标

- **问题**：已接入 `load_skill` / `read_skill_file`，但缺少“何时触发、触发后是否改善质量”的持续观测口径。
- **目标**：建立最小可运营指标，避免技能库演进盲飞。
- **建议指标**：
  - `load_skill_call_rate`（每 run 调用率）
  - `load_skill_after_reject_rate`（被 QA 打回后触发率）
  - `qa_rejection_rate_delta_with_skill`（触发技能前后拒绝率差）
- **入口**：`backend/app/tests/golden/runner.py` + `backend/app/router/run_rt.py`（metrics 扩展）+ 前端 metrics 展示。
- **验收**：指标可在 run 级查询与 golden 报告对比中看到。

### [ ] API-002 LLM 成本护栏

- **问题**：当前只有 token 记录，没有 slot 预算/超限策略。
- **目标**：避免多 run 并发时成本失控。
- **入口**：`service/llm/client.py` + `core/config.py` + metrics 聚合。
- **验收**：支持按 slot 配置预算并触发降级动作。

---

## P2（质量与可维护性）

### [ ] MSG-001 AgentMessage 编排落地

- **问题**：`AgentMessage` schema 已定义，但主编排仍以 `AgentState` dict 传递。
- **目标**：提升跨节点协议可追踪性与可演化性。
- **入口**：`schemas/agent_message.py` + 相关 nodes payload 规范化。
- **验收**：关键节点间传递信息可被统一 schema 校验。

### [ ] SEC-003 gitleaks 规则集接管（可选）

- **现状**：scanner-first 防线已足够覆盖当前风险。
- **目标**：如后续进入团队协作阶段，再引入更强规则库与误报基线。

---

## 已完成（关键里程碑）

### [x] EXT-001 通用扩展 schema（已通过 Skill Library 实现）

- **结果**：核心协议改为通用字符串契约 + 运行时技能注入，不再依赖静态目录扩展。
- **证据**：`docs/2-architecture-decision.md`、`docs/3-schema-and-protocol.md`、`backend/app/service/skill_store/*`

### [x] EXT-002 source_type 扩展（已通过通道协议实现）

- **结果**：`source_type` 走通用字符串透传，通道能力通过 registry 注册扩展。
- **证据**：`docs/2.6-collector-channels.md`、`backend/app/service/collector/*`

### [x] ORCH-005 Golden Eval 集（12/12）

- **结果**：覆盖 baseline / reject / force_degraded / promoted rules / generic competitors / progressive disclosure。
- **证据**：`backend/app/tests/golden/cases/*.yaml` + `backend/app/scripts/run_golden.py`

### [x] ORCH-004 阶段重放（resume/reset）

- **结果**：支持 `resume` 与 `reset_to={analyst,writer}`，并与 checkpoint 对齐。
- **证据**：`backend/app/router/run_rt.py` + `backend/app/tests/test_smoke.py`

### [x] CUR-001 Skill Curator 三类候选生成

- **结果**：`qa_rule` / `prompt_template` / `source_routing` 并发生成并入 staging 审核流。
- **证据**：`backend/app/service/skill_curator/generators/*`

---

## 历史归档说明

以下历史方向已完成重构或降级为归档，不再作为 backlog：

- 静态打包扩展模型（见 `docs/impl/04-industry-pack-and-researcher.md`）
- 旧版离线快照耦合采集路径（已被通用通道 + hint 机制替代）
