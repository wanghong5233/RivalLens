

## 真实 gap(二次核实后)

| # | gap | 证据(亲自读过) | 二次核实结论 | 值得做 |
|---|---|---|---|---|
| A | researcher 单竞品空证据炸掉整个 run | `nodes/researcher.py:292-293` 抛 `RuntimeError` → `run_rt.py:1066-1072` `except Exception` → `_mark_run_failed_and_emit` → `status="failed"` | **成立**。researcher 是 fan-out 子图节点,一个竞品无证据,整轮多竞品分析全 failed;其余 agent 全走 degraded。哲学不一致、健壮性缺陷 | 是(P0) |
| B | prompt_template / source_routing promote 后"假生效" | catalog 只注入 `name/description/applies_to/tags`(`prompts.py:38-54`),**不含 template_body**;`priority_delta`/`target_agent` 全库无运行时消费方(只在 schema/写入端/测试);只有 qa_rule 被 QA 真正加载(`qa/engine.py:227-243`) | **成立**。三类候选里 qa_rule 真生效、source_routing 半生效(researcher 可 `load_skill` 读 instructions)、**prompt_template body 完全无人读**。人工 approve 了不起作用的东西 | 是(P0) |
| C | AgentState 混入不可序列化的 session_factory | `state.py:44` 声明 `async_sessionmaker` 字段;生产 `initial_state` 不注入,节点 fallback `get_session_factory()`(`nodes/researcher.py:28-32`) | **成立但是纯卫生**。当前靠不注入规避,字段仍在;一旦启用 checkpoint 持久化会炸,且误导。低成本清理 | 顺手(P1) |
| D | Analyst insight 无结构化跨竞品对比 | `AnalystInsight` 仅 `dimension/finding/evidence_ids/confidence`(`schemas/agent_outputs.py`),无 per-竞品结构化对比字段 | **成立,已修复**。新增 analyst `comparisons` contract,按维度输出 competitor cell,落库到 `comparison_cells`,API 与前端矩阵可稳定消费。 | 已做(P2) |
| E | fan-out 跨竞品 URL 去重缺失 | 每 researcher 只拿单 topic(`graph.py:30-57`),去重仅子图内(`researcher.py:244-251`) | **成立但证伪投入产出**。真实库 682 runs / 3803 distinct fetches 中,跨竞品重复 fetch 55 次(1.4%),仅 29 个共享 URL,主要是 firstpagesage、martal 等行业基准/榜单页。共享跨节点 URL 缓存 + 并发协调不值得。 | 不做(P2) |

## 修复状态

| # | 状态 | 落点 |
|---|---|---|
| A | 已修复 | researcher 零证据不再抛出 RuntimeError;step/event 标记 degraded;竞品仍写入 researched_competitors;supervisor finalize 看到 researcher_degraded_competitors 时 run 收口 degraded。 |
| B | 已修复 | curator 生成入口只产 qa_rule;prompt_template/source_routing generator 和 promote 能力保留,但不再自动产出假生效候选;prompt catalog 收窄到运行时实际消费集合。 |
| C | 已修复 | AgentState 移除 session_factory 字段;节点统一直接取 get_session_factory();测试注入改为 patch 节点级 get_session_factory。 |
| D | 已修复 | `AnalystOutput.comparisons` + `comparison_cells` + `GET /api/runs/{id}/comparisons` + 前端 `ComparisonMatrix`;writer/QA 链路不动。 |
| E | 已决策/不做 | 真实数据重复率仅 1.4%,共享去重层收益过低;保留 researcher 子图内去重即可。 |

