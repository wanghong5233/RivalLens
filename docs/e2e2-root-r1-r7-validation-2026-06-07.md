# E2E2 R1-R7 验收记录（2026-06-07）

## Subject

验证 `.cursor/plans/e2e2_根治_r1-r7_46bfb129.plan.md` 的修复结果。测试对象是 TRAE 对标 Cursor、GitHub Copilot、Windsurf、通义灵码、Baidu Comate、Doubao AI Coding Assistant 的 deep report 链路。

## Test Plan

| 项 | 内容 |
|---|---|
| 环境 | `rivallens_api` dev container，Qwen 路由已启用 |
| 请求入口 | `POST /api/runs/intake` → `POST /plan/confirm` |
| 验收 run | `run_ea385bf8fc76` |
| 中间失败 run | `run_fc7a9cab6852` |
| 回归测试 | R1-R7 targeted pytest |

## Result

最终 run `run_ea385bf8fc76` 状态为 `completed`。核心指标：

| 指标 | 值 |
|---|---:|
| wall clock | 600s |
| evidence_count_total | 73 |
| competitor coverage | 1.0 |
| dimension_coverage_rate | 1.0 |
| report_section_coverage_rate | 1.0 |
| report_char_count | 9497 |
| report_section_count | 5 + top-level `executive_summary` |
| qa_total_steps / rejected | 2 / 1 |
| llm_provider_error_count | 0 |
| llm_retry_total | 0 |

模型路由实际落点：

| slot | provider / model | calls |
|---|---|---:|
| research | `qwen / qwen3.7-plus` | 38 |
| summarization | `qwen / qwen3.7-max` | 1 |
| writer | `qwen / qwen3.7-max` | 2 |
| qa | `qwen / qwen3.7-plus` | 3 |
| compression | `qwen / qwen-flash` | 3 |

## Fixed Evidence

| 问题 | 现象 | 验收结果 |
|---|---|---|
| R1 writer 重写塌缩 | QA 打回后章节收窄 | writer 两轮均保留同一 `target_sections`；最终 `report_section_coverage_rate=1.0` |
| R2 维度命名割裂 | `strategic_*`、`china_vs_global_*` 变体拉低覆盖 | 补 canonical alias 后，现有 run 动态 metrics 回到 `dimension_coverage_rate=1.0` |
| R3 数字 factuality | 无据数字被 warning 放行 | 第一轮 QA 拒绝 `$20/month`、`$1.30 per million tokens`；writer 删除/改写后第二轮 approved，`qa_unsupported_numeric_claims=[]` |
| R6 来源质量漏判 | 图片/导航目录类低质来源进入 evidence | targeted tests 覆盖 `image_markdown`、`navigation_directory` |
| R7 来源权威性 | 官方来源无法识别 | 最终 evidence：`official=10`、`third_party=63`，并写入 `source_authority` / `competitor_source_match` |

最终报告未再出现 `uncovered_section:executive_summary`。该噪声来自 writer schema 只按 `sections[]` 判断目标覆盖，已改为把顶层 `executive_summary` 计入覆盖。

## Report Quality

报告可读性达到演示标准：有 executive summary、五个业务章节、风险提示、逐段 evidence 引用。内容能回答采购/工程管理视角的问题：定位差异、价格差异、企业能力、中外市场差异、采用建议。

仍未达到“商业上线可直接信任”的标准，原因是来源质量结构偏弱：

| 来源类型 | 数量 |
|---|---:|
| article | 63 |
| official_site | 6 |
| pricing_page | 4 |

官方/定价来源合计 10/73。系统已能标注权威性，但 researcher 仍会大量使用第三方文章支撑竞品判断。pricing、enterprise capability 这类高风险维度后续应提高官方来源优先级或在证据不足时输出 `unknown` / 定性结论。

## Residual Issues

### R8 Intake complete-but-ask

| 字段 | 内容 |
|---|---|
| type | Bug |
| status | resolved (2026-06-07) |
| priority | P1 |
| Symptom | `run_ea385bf8fc76` 首轮 intake payload 同时出现 `draft_complete=true` 与 `action=ask`，并停在 `intake_wait`。 |
| Evidence | `clarify_field_targets=["user_role"]`，但请求体已给 `user_role="pm"`；手动回复 “Use PM as the user_role” 后 planner 继续。 |
| Impact | 端到端自动化验收需要人工补一轮；真实用户会看到多余澄清。 |
| Root Cause | `intake_generate_node` 决策块（`intake.py`）里 `action=ask` 分支优先级高于 `next_draft.is_complete`，与注释 invariant 矛盾，导致已完整 draft 仍被 LLM 的 ask 覆盖。 |
| Fix | draft `is_complete` 且 ask 的 `field_targets` 全部已满足时丢弃冗余 ask（新增 `_clarify_target_satisfied`/`_unsatisfied_clarify_targets`）；真正未填字段的 ask 仍保留。 |
| DoD | 当 `RunIntakeDraft.is_complete()` 为真且用户已显式传入字段时，不因 LLM `action=ask` 暂停。✅ `test_intake_prompt.py` 回归覆盖。 |

### R9 strategic_recommendations evidence 为空

| 字段 | 内容 |
|---|---|
| type | Improvement |
| status | resolved (2026-06-07, 方案 A) |
| priority | P2 |
| Current | 最终 `dimension_coverage_rate=1.0`，但 `evidence_count_by_dimension["strategic_recommendations"]=0`。 |
| Limitation | 报告战略建议章节复用了其他维度证据；这在产品建议里可接受，但指标会掩盖“战略维度没有专门采证”的事实。 |
| Trigger Condition | deep report 的 plan_tree 含 `strategic_recommendations`，但 researcher span 没有该维度 evidence。 |
| Root Cause | strategic 被当独立采证维度，但它是 analyst 综合产出的衍生维度；coverage 指标按下游 section 算，造成假阳性 1.0。 |
| Fix | `contracts.py` 定义 `DERIVED_DIMENSIONS` + `research_focus_dimensions`；planner 的 research/discover 任务剥离衍生维（analyze/write 保留）；metrics 新增诚实的 `evidence_dimension_coverage_rate`（只看 research 维有无 evidence），curator gate 改用它。 |
| DoD | research 任务不再追逐 strategic；`evidence_dimension_coverage_rate` 揭示真实采证覆盖（假阳性场景下为 0/3）。✅ `test_contracts.py`/`test_run_metrics.py`/`test_skill_curator_tasks.py` 回归覆盖。 |

### R10 官方来源占比不足

| 字段 | 内容 |
|---|---|
| type | Improvement |
| status | resolved (2026-06-07, 三层治理) |
| priority | P2 |
| Current | `official/pricing=10`，`article=63`。 |
| Limitation | 报告可演示，但商业采购场景里第三方文章占比过高。 |
| Trigger Condition | `source_authority=third_party` 占比 >70%，且章节包含 pricing / enterprise / compliance 判断。 |
| Fix | 三层治理：(1) 检索 — researcher 对 pricing/enterprise/security/compliance 维度用 `site:官方域名` 定向 query + `_pick_url_for_dimension` 官方 host 优先 + prompt 引导；(2) 择优 — `select_layered_evidence_briefs` 同组优先 official，brief 透出 `source_authority`/`source_type`；(3) 门控 — QA 新增 `rule_buyer_critical_sections_need_official_source`（warning，缺官方来源时进 failed_rule_ids 供语义 QA 降级）。 |
| DoD | 高风险维度优先官方来源；缺官方证据时 QA 以 warning 降级而非硬放行。✅ `test_researcher_subgraph.py`/`test_prompt_evidence_selection.py`/`test_qa_rules.py` 回归覆盖。 |

## Verification

```text
docker compose -f backend/docker-compose.dev.yml exec -T rivallens_api pytest \
  tests/test_supervisor_batch.py \
  tests/test_agent_outputs.py \
  tests/test_run_metrics.py \
  tests/test_qa_rules.py \
  tests/test_writer_llm.py \
  tests/test_source_quality.py \
  tests/test_collector_channels.py \
  tests/test_researcher_evidence.py -q

95 passed in 10.39s
```

## Verdict

R1-R7 主问题已修复，E2E2 链路达到赛方演示标准：编排完整、Qwen 分档生效、无 provider error、QA 能打回并收敛、报告可读且证据可追踪。

R8/R9/R10 后续项已于 2026-06-07 全部根治（代码 + 单测）：
- R8：intake 已完整不再因冗余 ask 暂停。
- R9：strategic 作为衍生维度从 research 剥离；新增诚实的 `evidence_dimension_coverage_rate` 消除 coverage 假阳性，curator gate 改用它。
- R10：来源权威性从“只标注”升级为“检索官方优先 + 证据择优官方优先 + QA 官方来源 warning 门控”的三层弱约束。

综合回归：`tests/test_intake_prompt.py test_contracts.py test_run_metrics.py test_skill_curator_tasks.py test_plan_reconcile.py test_agent_outputs.py test_prompt_evidence_selection.py test_qa_rules.py test_qa_numeric_claims.py test_researcher_subgraph.py test_researcher_evidence.py test_collector_channels.py test_writer_llm.py` → 118 passed。

残余取舍：R10 的 QA 官方门控为 warning 级（不硬打回），因为部分竞品确无公开官方页；硬约束会造成误伤与重写循环。若后续要求强约束，可将该 rule 升为 blocking 并配合"缺官方→stance=unknown"的 writer 降级。
