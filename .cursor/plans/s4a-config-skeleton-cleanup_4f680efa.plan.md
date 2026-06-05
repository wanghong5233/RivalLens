---
name: s4a-config-skeleton-cleanup
overview: S4 批A 二级 plan(对应一级总纲 todo S4a)。低风险纯重构:把跨文件重复/业务上限类魔法数收敛进 core/defaults.py 单一事实源,清理 demo 阶段 skeleton 残留。除一处 user_query 默认值的受控契约收紧外行为不变,为批B(LLM-first)与批C(契约对齐)打好 config 底座与绿基线。
todos:
  - id: s4a-magic-numbers
    content: "刀 S4A-1 魔法数收敛进 core/defaults.py(值不变,纯去重复):新增 MAX_SUPERVISOR_ITERATIONS=10 / MAX_REACT_TURNS=6(联动 schema ConductResearch.max_iterations + supervisor fallback 三联) / MAX_ADDITIONAL_PLAN_TASKS=5 / MAX_FOCUS_DIMENSIONS=5 / MAX_QA_RERESEARCH_ITERATIONS=3 / discovery 容量(MAX_DISCOVERY_SEARCH_QUERIES=5、DISCOVERY_SEARCH_MAX_RESULTS_CAP=10、DISCOVERY_SNIPPETS_TO_EXTRACT=20、DEFAULT_DISCOVER_MAX_RESULTS=8) / PLAN_TASK_TITLE_MAX_LEN=60、PLAN_TASK_DESCRIPTION_MAX_LEN=500。压缩族/预览截断/纯局部启发式 YAGNI 保留。Verify: 逐常量核对值不变 + docker targeted(test_supervisor_batch/test_plan_reconcile/discovery)/full。"
    status: completed
  - id: s4a-skeleton
    content: "刀 S4A-2 skeleton 残留清理:run_rt.py:107 user_query 默认 'skeleton' → 必填 Field(min_length=1)(先 grep 依赖再改);supervisor.py:766 缺省 user_query 与 API 对齐;supervisor.py:283 Finalize notes 去 walking-skeleton 措辞。QA fast-path/Phase2/legacy_stub/测试命名 不动。Verify: run 创建缺 query 应 422 + docker full。"
    status: completed
isProject: false
---

# S4 批A:魔法数收敛 + skeleton 清理(低风险)

对应一级总纲 todo `S4a`。S4 已按风险拆为 S4a/S4b/S4c 三批,本 plan 只做 S4a;批B(LLM-first:S4-4+S4-3+S4-6)、批C(契约对齐:S4-2+S4-1)后续单开二级 plan。只做行为不变的重构与清理,建立 config 单一事实源和绿基线。

## 进入基线

S3 后 docker `pytest tests` = 236 passed / 1 failed(唯一失败 = S5-1 flaky,正交)。本批每刀与收尾须保持非 S5-1 用例全绿,且业务行为(常量值)不变。

## 刀 S4A-1 [重构] 魔法数收敛进 core/defaults.py

把跨文件重复 / 业务上限类常量收敛到 [core/defaults.py](backend/app/core/defaults.py),取值与原字面量完全一致(纯去重复,行为不变)。

### Files
- [backend/app/core/defaults.py](backend/app/core/defaults.py)(新增常量)
- [backend/app/agents/nodes/supervisor.py](backend/app/agents/nodes/supervisor.py)、[backend/app/agents/subgraphs/researcher.py](backend/app/agents/subgraphs/researcher.py)、[backend/app/agents/nodes/planner.py](backend/app/agents/nodes/planner.py)、[backend/app/agents/nodes/discovery.py](backend/app/agents/nodes/discovery.py)、[backend/app/schemas/supervisor.py](backend/app/schemas/supervisor.py)、[backend/app/schemas/agent_outputs_pipeline.py](backend/app/schemas/agent_outputs_pipeline.py)(改为引用常量)

### Changes(新增常量,值=现状)
- `MAX_SUPERVISOR_ITERATIONS = 10` —— 替换 [supervisor.py](backend/app/agents/nodes/supervisor.py):44/809
- `MAX_REACT_TURNS = 6` —— 替换 [researcher.py](backend/app/agents/subgraphs/researcher.py):35,并联动 [schemas/supervisor.py](backend/app/schemas/supervisor.py):30 `ConductResearch.max_iterations` 与 [supervisor.py](backend/app/agents/nodes/supervisor.py):192/225 fallback(三联重复合一)
- `MAX_ADDITIONAL_PLAN_TASKS = 5` —— 替换 [planner.py](backend/app/agents/nodes/planner.py):45 `_MAX_ADDITIONAL_TASKS`
- `MAX_FOCUS_DIMENSIONS = 5` —— 替换 [supervisor.py](backend/app/agents/nodes/supervisor.py):109 `derived[:5]`(与 prompt "3-5 dimensions" 一致)
- `MAX_QA_RERESEARCH_ITERATIONS = 3` —— 替换 [supervisor.py](backend/app/agents/nodes/supervisor.py):419
- discovery 容量:`MAX_DISCOVERY_SEARCH_QUERIES = 5`([discovery.py](backend/app/agents/nodes/discovery.py):147 / [schemas/supervisor.py](backend/app/schemas/supervisor.py):21)、`DISCOVERY_SEARCH_MAX_RESULTS_CAP = 10`([discovery.py](backend/app/agents/nodes/discovery.py):156/164)、`DISCOVERY_SNIPPETS_TO_EXTRACT = 20`([discovery.py](backend/app/agents/nodes/discovery.py):211)、`DEFAULT_DISCOVER_MAX_RESULTS = 8`(统一 [supervisor.py](backend/app/agents/nodes/supervisor.py):166 / [schemas/supervisor.py](backend/app/schemas/supervisor.py):23 / [discovery.py](backend/app/agents/nodes/discovery.py):126)
- plan 字段长:`PLAN_TASK_TITLE_MAX_LEN = 60`、`PLAN_TASK_DESCRIPTION_MAX_LEN = 500` —— 替换 [planner.py](backend/app/agents/nodes/planner.py):86/164/254/255、[agent_outputs_pipeline.py](backend/app/schemas/agent_outputs_pipeline.py):197

### 明确不抽(YAGNI,保留模块内)
- researcher 压缩族:`COMPRESS_AFTER_TURNS`/`COMPRESS_AFTER_CHARS`/`OBSERVATIONS_FULL_RETAIN`(运行时 token 预算,非业务上限)
- 各类 preview/error 截断:200/220/300/500 等(可观测性截断)
- 纯局部启发式:`qa_reasons[:3]`、`len(pending)>=2`、`snippets[:3]`、`len(messages)>=8`、`briefs[-6:]`、`len(competitors)>=3` 补 positioning 等

### Verify
- 逐常量核对收敛后取值与原字面量一致(grep 旧字面量应清零)
- docker targeted:`test_supervisor_batch`、`test_plan_reconcile`、discovery 相关用例
- docker full,保持 236 passed / 1 failed(S5-1) parity 不变

### Done-when
目标常量均来自 [core/defaults.py](backend/app/core/defaults.py) 单一定义,无散落重复;全量 parity 与行为不变。

## 刀 S4A-2 [清理] skeleton 残留

仅清理 3 处真 demo 残留,其余注释 / 迁移标识 / 测试命名不动。

### Files
- [backend/app/router/run_rt.py](backend/app/router/run_rt.py)、[backend/app/agents/nodes/supervisor.py](backend/app/agents/nodes/supervisor.py)

### Changes
- [run_rt.py](backend/app/router/run_rt.py):107 `RunCreateRequest.user_query` 默认 `"skeleton"` → 收紧为必填 `Field(min_length=1)`(本批唯一行为变更点,受控契约收紧)
- [supervisor.py](backend/app/agents/nodes/supervisor.py):766 `supervisor_node` 缺省 `user_query="skeleton"` → 与 API 对齐(空串或显式常量,不再产出具名 skeleton run)
- [supervisor.py](backend/app/agents/nodes/supervisor.py):283 Finalize `notes="All planned skeleton phases are completed."` → `"All planned phases completed."`

### 不动(非 stub)
QA fast-path `not implemented in fast-path slice`([supervisor.py](backend/app/agents/nodes/supervisor.py):461-462,属 S5)、Phase 2 路线图注释、`legacy_stub` provider 标识、[models/run.py](backend/app/models/run.py):45-47 过时注释(可顺手更正注释文字)、[app_main.py](backend/app/app_main.py):119 OpenAPI walking-skeleton 文案(可选)。

### 风险点
`user_query` 改必填可能影响依赖默认值的调用方 / 测试;须先 grep 依赖(含 test fixtures)再改,并在 Verify 覆盖 run 创建校验路径。

### Verify
- run 创建缺 `user_query` 应返回 422(参数校验)
- docker full,parity 不变

### Done-when
无 `"skeleton"` 默认值产出真实 run;Finalize 文案清理完成;测试绿。

## 收尾(方法论流程,非 build 刀)

S4 拆三批与三路调研结论已在一级 [系统纠偏总纲](.cursor/plans/系统纠偏总纲_7d21aa68.plan.md) 的 `S4a/S4b/S4c` 完成。本 plan 两刀 build 并验证无误后,按闭环回写一级总纲:把 `S4a` 标 completed、记录提交号与 docker 数;批A 执行中若发现新结构性问题,同步迭代总纲(活文档)。

## 明确不做(YAGNI)

不在本批动任何 LLM 决策路径(supervisor 维度推导、intake 双轨、prompt 域偏置归批B);不动 contract 处置统一与 writer 章节对齐(归批C);不引入新依赖。
