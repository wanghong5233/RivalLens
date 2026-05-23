# 实现切片 08：Analyst LLM + QA 语义混合 + Fallback Prompt

## 目标

本切片补齐 `docs/2-architecture-decision.md` 中质量闭环相关的三项缺口：

- `§3.1`：Analyst 从 deterministic stub 升级为 LLM-driven 跨竞品分析；
- `§2/§3.1`：QA 从纯规则快路径升级为“规则 DSL + LLM 语义混合”；
- `§10.2`：LLM 主 prompt 持续失败后触发 fallback prompt，降低单次模型抖动导致的 run 失败概率。

## Analyst 真化

- 节点：`backend/app/agents/nodes/analyst.py`
- 调用：`get_llm_client().complete_json(model_slot="summarization", ...)`
- 产物：
  - `steps.agent_name="analyst"` 记录 `analysis_mode`（`llm`/`fallback`）；
  - `llm_calls` 新增 analyst 对应调用轨迹；
  - `artifacts.kind="analysis_result"` 保持不变。

### 关键约束

- Analyst 输出必须是结构化 JSON；
- `insights[*].evidence_ids` 必须来自当前 run 的 evidence 集合；
- 若 LLM 出错或结构不合法，回落 deterministic fallback，不中断 run。

## QA 规则 + 语义混合

- 引擎：`backend/app/service/qa/engine.py`
- 节点：`backend/app/agents/nodes/qa.py`
- 流程：
  1. 先跑 `evaluate_fast_path_rules`；
  2. 再跑 `model_slot="qa"` 的语义审查；
  3. 聚合为统一 `Approval | Rejection`。

### 语义审查策略

- 语义审查成功且输出合法：追加 `rule_qa_semantic_audit` 参与统一裁决；
- 语义审查失败或结构非法：降级为 `degraded_rule_only`（规则结果优先），并在 step payload 保留降级元信息；
- QA 节点把语义审查对应调用写入 `llm_calls`，与 `qa` step 绑定。

## Fallback Prompt 机制

- 客户端：`backend/app/service/llm/client.py`
- 行为：
  - 主 prompt 在重试耗尽后（仅 `LLMRequestError`）触发一次 fallback prompt；
  - fallback 成功：`error=None`，并标记 `fallback_used=True`；
  - fallback 失败：返回 `primary + fallback` 合并错误；
  - fallback 元数据通过 `LLMResponse` 回传（`fallback_used`、`fallback_reason`）。

## 涉及节点

- `supervisor`：研究规划调用增加 fallback prompt；
- `researcher`（ReAct + compression）：研究决策与压缩调用增加 fallback prompt；
- `analyst`：主分析调用增加 fallback prompt；
- `qa semantic`：语义审查调用增加 fallback prompt。

## 验证口径

- 单测：`test_llm_client.py` 覆盖 fallback 成功/失败分支；
- smoke：新增 analyst/qa 的 `llm_calls` 断言与 QA 语义降级断言；
- 真实 run：可观测到 analyst 与 qa 的 LLM trace，且失败时流程不直接中断。
