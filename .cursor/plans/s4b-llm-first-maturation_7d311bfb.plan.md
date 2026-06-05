---
name: s4b-llm-first-maturation
overview: S4 批B(LLM-first 成熟化,对应一级总纲 todo S4b):让 supervisor 在 fallback/QA 路径复用上游已定的 focus_dimensions(单一事实源)而非子串重猜,并消除 intake/prompt 的单一赛道 few-shot 域偏置(多领域平衡 + fallback 中立化)。语义判断交 LLM、确定性仅做护栏与归一。
todos:
  - id: s4b-supervisor-dimensions
    content: "刀 S4B-1 supervisor 维度复用上游单一事实源(S4-4)[已完成]:维度来源改优先级链 — 当前 plan task.focus_dimensions > intake_draft.focus_dimensions > DIMENSION_HINTS 子串推导(仅无上游维度兜底) > DEFAULT_FOCUS_DIMENSIONS;fallback/QA 路径统一走该链不再子串重猜;记录 dimension_source 可观测。提交 775a644。Verify: docker targeted test_supervisor_batch.py = 7 passed。"
    status: completed
  - id: s4b-debias-prompt
    content: "刀 S4B-2 intake/prompt 去域偏置(S4-3+S4-6)[已完成]:INTAKE few-shot(domain_hint/suggested_answer/summary_title)从单一 AI 编程改跨赛道多领域平衡(AI 编程+供应链/ERP+通用 SaaS/CRM,小 k≈3);summary_title 去 TRAE/Copilot 具体产品范本改通用/占位;intake.py fallback suggested_answer 去 AI 编程写死改中立模板。不引动态检索(YAGNI)。提交 8610c90。Verify: docker targeted test_intake_prompt.py + test_intake_api.py = 11 passed;docker full pytest tests = 244 passed / 2 failed(仅 S5-1 已知 promoted QA 后台 enforcement)。"
    status: completed
isProject: false
---

# S4 批B:LLM-first 成熟化(维度复用 + 去域偏置)

对应一级总纲 todo `S4b`。两把刀:S4B-1(supervisor 维度复用上游)、S4B-2(intake/prompt 去域偏置,合并 S4-3+S4-6)。这是行为变更批,须前批(S4a)绿基线稳定。

## 进入基线

S4a 后 docker `pytest tests` = 237 passed / 2 failed(均为 S5-1 flaky,正交)。本批每刀须保持非 S5-1 用例全绿。

## 刀 S4B-1 [成熟度] supervisor 维度复用上游单一事实源(S4-4)

### 现状问题
[supervisor.py](backend/app/agents/nodes/supervisor.py):96-109 `_derive_focus_dimensions` 在 fallback/QA 路径用 `DIMENSION_HINTS` 子串匹配**重新猜**维度,却未消费 intake/planner 上游已确定的 `focus_dimensions`(planner 已把维度写到每个 plan task)。子串误匹配 + 与用户真实意图脱节。

### Files
- [backend/app/agents/nodes/supervisor.py](backend/app/agents/nodes/supervisor.py)

### Changes
- 维度来源改为优先级链(单一事实源贯穿):当前 plan task 的 `focus_dimensions` > `intake_draft.focus_dimensions` > `DIMENSION_HINTS` 子串推导(仅完全无上游维度时兜底) > `DEFAULT_FOCUS_DIMENSIONS`。
- `_fallback_decision`/QA 路径(149-244、377-418、781-897)取维度处统一走该优先级链,不再直接调 `_derive_focus_dimensions` 重猜。
- `DIMENSION_HINTS` 保留但降为最末兜底;`MAX_FOCUS_DIMENSIONS` 截断不变。
- 可观测:记录维度来源(`dimension_source: upstream_task|intake|hints|default`),复用 S2 日志风格。

### Verify
- 单测:intake/plan 已有维度时,fallback/QA 路径复用上游维度而非子串猜;完全无维度时才落 hints/default。
- docker targeted `test_supervisor_batch` + full,parity 保持。

### Done-when
fallback/QA 维度来自上游已定值;DIMENSION_HINTS 仅在无上游维度时生效;维度来源可观测。

## 刀 S4B-2 [成熟度] intake/prompt 去域偏置(S4-3 + S4-6)

### 现状问题
[prompts.py](backend/app/service/llm/prompts.py):114/134-135/150-154 的 INTAKE few-shot 示例清一色 AI 编程(TRAE/Copilot),[intake.py](backend/app/agents/nodes/intake.py):258 fallback `suggested_answer` 写死 AI 编程句。非该赛道用户被注入单一领域先验。S4-3 intake 双轨职责分层本身合理,其 naive 主要即此 fallback 域偏置,故并入本刀。

### 依据(few-shot bias 业界做法)
示例同质化是域偏置根因,解法是多样化 + 覆盖输入空间,但保持小 k(3-5);动态检索需 example store 属 YAGNI。故采用 B(多领域平衡静态示例)+ 局部 A(强领域锚定处中立化)。

### Files
- [backend/app/service/llm/prompts.py](backend/app/service/llm/prompts.py)(`INTAKE_SYSTEM_PROMPT`)
- [backend/app/agents/nodes/intake.py](backend/app/agents/nodes/intake.py)(`_fallback_clarify`)

### Changes
- INTAKE few-shot 多领域平衡:`domain_hint` 信号、`suggested_answer`、`summary_title` 范例从单一 AI 编程改为跨赛道(AI编程 + 供应链/制造 + 通用 SaaS/ERP)各一,保持每字段约 3 个、小 k。
- `summary_title` 去具体产品名范本(TRAE/Copilot → 通用描述或占位 `[产品A] vs [产品B]`),避免诱导特定竞品框架。
- [intake.py](backend/app/agents/nodes/intake.py):258 `_fallback_clarify` 的 `suggested_answer` 去 AI 编程写死,改行业中立模板(或从已有 `domain_hint`/`user_query` 片段轻量填充,不引 embedding/检索)。
- 不动:LLM 主解析与 wait 关键词 floor 的分层结构(已合理);不引入动态示例检索(YAGNI)。

### Verify
- 回归式断言:供应链/ERP 类 query 的 intake 输出(domain_hint/analysis_intent/summary_title)不再被引向 AI 编程语义。
- docker full,parity 保持。

### Done-when
INTAKE few-shot 跨赛道均衡、无单一领域 majority bias;fallback 不写死 AI 编程;产品名范本去具体化。

## 收尾(方法论流程,非 build 刀)

两刀 build 验证无误后,回写一级 [系统纠偏总纲](.cursor/plans/系统纠偏总纲_7d21aa68.plan.md):`S4b` 标 completed、记录提交号与 docker 数;执行中发现新结构性问题同步迭代总纲。

## 执行收尾

S4B-1/S4B-2 已落地。提交:`775a644`/`8610c90`。验证:S4B-1 targeted `test_supervisor_batch.py` = **7 passed**;S4B-2 targeted `test_intake_prompt.py tests/test_intake_api.py` = **11 passed**;docker 全量 `pytest tests` = **244 passed / 2 failed**。2 例失败仍为 S5-1 promoted QA 后台 enforcement(`test_promoted_qa_rule_blocks_report_with_enforced_yaml` + `test_promoted_qa_rule_blocks_then_writer_redo_passes`),日志继续显示测试 tmp skills 目录 `skill_count=0`、`promoted_qa_enforced_count=0`,非 S4b 回归。两刀 staged secret scan 均通过。

## 明确不做(YAGNI)

不做动态 few-shot 检索/example store;不改 intake LLM 主解析与 wait floor 的分层架构;不动 contract 处置统一与 writer 章节对齐(归批C S4c);不引入新依赖。
