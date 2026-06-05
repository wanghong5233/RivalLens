---
name: s4c contract alignment
overview: S4c 契约对齐(S4 最后一批,改动面最大):统一全链路 dimension/section_id 越界与缺失处置为 normalize-or-skip + dropped 审计(policy B:真实 evidence 保留置空、不强配,衍生 insight 越界 skip),并将 writer 维度→章节对齐改为直配 section_id(去 round-robin/收敛别名表/修 NameError)。二级 plan 内分两刀,S4C-2 依赖 S4C-1。
todos:
  - id: s4c-1-contract-unify
    content: "S4C-1 contract 处置统一 [已完成]:contracts.py 新增 normalize_dimension_or_none(raw, allowed)->(norm|None, reason|None);替换 researcher subgraph/nodes、analyst、AnalystOutput.parse_llm_content 的私自 fallback;evidence 越界置 None 保留、insight 越界 skip;dropped 审计写 Step.payload + 日志。提交 efbf962。Verify: contracts/agent_outputs/researcher evidence/subgraph/dispatcher targeted = 28 passed;writer/conclusion/event 相邻回归 = 17 passed。"
    status: completed
  - id: s4c-2-writer-align
    content: "S4C-2 writer 维度→章节对齐(依赖 S4C-1)[已完成]:去 _select_insights/_select_evidence 的 round-robin→无匹配返回[];去 _SECTION_DIMENSION_ALIASES 改直配 section_id==dimension;修 DEFAULT_FALLBACK_SECTIONS NameError 路径;无匹配 section→空章+uncovered_section risk。提交 0025c74。Verify: writer/agent_outputs targeted = 24 passed;docker full pytest tests = 254 passed。"
    status: completed
  - id: s4c-wrapup
    content: 收尾 [已完成]:docker full 254 passed;一级总纲 S4c→completed、§4.8 记录处置统一公式与 dropped 审计口径;下一块进入 S5。
    status: completed
isProject: false
---

# S4c 契约对齐(normalize-or-skip + writer 维度→章节对齐)

## 背景与现状(已复核,行号为当前)

同类契约值(`dimension`/`section_id`)的越界与缺失在各节点被**不同对待**(6 条不一致),且 writer fallback 靠启发式硬塞:

- 缺失 `dimension` 三轨:子图 draft / analyst / writer brief 用 `"unknown"`,researcher 持久化用 `"feature"`。
- 越界 `dimension`(归一后 ∉ focus)分裂:子图/tool_exec 不校验、researcher 持久化 remap→`focus_dimensions[0]`、analyst evidence skip、LLM insight skip(且按**原串**比较不 slugify)——**均无 dropped 审计**。
- slugify 应用不一致:`parse_llm_content` 用原串 ∈ allowed([agent_outputs.py](backend/app/schemas/agent_outputs.py):114-124),`AnalystInsight` validator 才 slugify → `"User Feedback"` 被静默 drop。
- writer 维度→章节靠别名表 `_SECTION_DIMENSION_ALIASES`([writer.py](backend/app/agents/nodes/writer.py):46-52) + round-robin `% len`(81-82/103-106)静默填。
- **真实 bug**:[writer.py](backend/app/agents/nodes/writer.py):358 引用 `DEFAULT_FALLBACK_SECTIONS[0]`,全库无定义无导入 → fallback report 路径(所有 target section 都无内容时)NameError,未被测试覆盖。

**已定策略(policy B)**:真实抓取的 evidence 的 dimension 归一(slugify)后仍缺失或 ∉ focus 时 → **保留 evidence、dimension 置空(未归类)+ 记 dropped 审计**;下游 writer/analyst **不 round-robin、不 remap**。衍生的 insight(按维度组织,非真实数据)越界 → **skip + 审计**。`AnalystInsight.dimension` 保持 required `str`;evidence dimension 存于 metadata JSON,None 化无需 DDL 迁移。

## S4C-1:contract 处置统一(normalize-or-skip + dropped 审计)

新增公共归一函数(扩展契约层 [contracts.py](backend/app/schemas/contracts.py)),作为唯一事实源:

```python
def normalize_dimension_or_none(raw: object, *, allowed: list[str]) -> tuple[str | None, str | None]:
    # 返回 (normalized | None, drop_reason | None)
    # 缺失/非 str → (None, "missing"); slugify 失败 → (None, "invalid")
    # 归一 ∉ allowed → (None, "out_of_focus"); 归一 ∈ allowed → (value, None)
```

替换各节点私自 fallback,统一走该函数:

- 子图 [researcher.py](backend/app/agents/subgraphs/researcher.py):571-615 evidence draft:dimension 用 helper,缺失/越界 → `None`(去 `"unknown"`)。
- nodes/[researcher.py](backend/app/agents/nodes/researcher.py):112-200 持久化:**去 `"feature"` / `focus_dimensions[0]` remap 与 `continue` 丢弃**,改 helper → `None` + 累计 dropped 计数/原因。
- nodes/[analyst.py](backend/app/agents/nodes/analyst.py):57-60 evidence brief:evidence 走 helper(`None` 保留,去 `"unknown"`+skip 二分);insight 维度(required `str`)越界统一 **skip + 审计**。
- [agent_outputs.py](backend/app/schemas/agent_outputs.py):114-124 `parse_llm_content`:原串 ∈ allowed → 改 **slugify 后** membership(修不一致,`"User Feedback"` 不再误丢);[agent_outputs_pipeline.py](backend/app/schemas/agent_outputs_pipeline.py):389-435 action_args 走同一语义。

dropped 审计落点:沿用 S2 observability,写 `Step.payload`(dropped_dimensions 计数 + 原因分布)+ 结构化日志。

Verify:新单测覆盖 missing/invalid/out_of_focus → `(None, reason)` 三分支;真实 evidence 不丢、越界 insight 被 skip 且计数;`parse_llm_content` 接受 `"User Feedback"`;docker targeted(researcher/analyst/pipeline)+ full。原子提交。

## S4C-2:writer 维度→章节对齐(依赖 S4C-1)

- 去 [writer.py](backend/app/agents/nodes/writer.py):66-106 `_select_insights_for_section`/`_select_evidence_ids_for_section` 的 round-robin(81-82/103-106)→ 无匹配返回 `[]`。
- 收敛/去 `_SECTION_DIMENSION_ALIASES`(46-52):S4C-1 后 dimension 已归一到 focus token、section_id 同源 `focus_dimensions`,改为直接 `dimension == section_id` 匹配,删除 demo 期别名补丁。
- 修 NameError:358 `DEFAULT_FALLBACK_SECTIONS[0]` → 合法常量(导入 `DEFAULT_FOCUS_DIMENSIONS` 或用 section_id 自身),title 与 section_id 一致。
- 无匹配 section → 空内容(不硬塞)+ `uncovered_section:{section_id}` risk_callout,与 schema 层 [agent_outputs.py](backend/app/schemas/agent_outputs.py):320-329 既有 `uncovered_section` 语义对齐。

Verify:fallback writer 对无匹配 section 给 uncovered risk 而非乱填;原 NameError 路径有单测;docker targeted(writer)+ full,保持 244 passed / 2 failed(S5-1)parity。原子提交。

## 收尾(方法论)

S4C-1、S4C-2 各原子提交;docker full 绿(除 S5-1 已记录的 flaky);二级 plan 无错后**回写一级总纲**:`S4c`→completed、`S4`(naive→成熟)整体完成,§4 记录处置统一公式与 dropped 审计口径。S4 收口后下一块进入 **S5(QA/agent 成熟度,S5-1 skill_store 后台 count=0 根因)**。

## 执行收尾

S4C-1/S4C-2 已落地。提交:`efbf962`/`0025c74`。验证:S4C-1 targeted `test_contracts.py test_agent_outputs.py test_researcher_evidence.py test_researcher_subgraph.py test_researcher_dispatcher.py` = **28 passed**;相邻回归 `test_writer_llm.py test_conclusions_persistence.py test_phase3_events.py` = **17 passed**;S4C-2 targeted `test_writer_llm.py test_agent_outputs.py` = **24 passed**;docker 全量 `pytest tests` = **254 passed**。两刀 staged secret scan 均通过。

## 不做(YAGNI / 越界)

- 不引入 report template 文件驱动 section(当前 section 由 supervisor `_derive_write_sections` 从 focus 派生,够用)。
- 不重构 QA 增加 dimension 契约规则(不一致点 #6,留 S5 评估)。
- 不动 S5-1 flaky 测试根因(S5 范围)。
