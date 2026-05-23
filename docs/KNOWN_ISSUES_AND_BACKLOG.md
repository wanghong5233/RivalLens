# Known Issues & Backlog

最后更新: 2026-05-24

## Active Issues 索引

| ID | type | 问题 | 优先级 | 状态 | 当前阶段下一步 |
|---|---|---|---|---|---|
| ORCH-001 (M1) | improvement | Collector framework 缺失，队友无法并行接入真实采集 | P0 | planned | 明确协议与 registry 最小骨架后开领 |
| ING-001 (M3) | improvement | 脱敏策略仅布尔标记，缺字段级规则和审计证据 | P1 | investigating | 先补违规样本与失败分布 |
| ORCH-002 (M4) | improvement | 无 SSE 进度流，长 run 只能轮询 | P1 | blocked-by:M1 | 主干先用 polling，等待 SSE 事件 schema 定稿 |
| ORCH-003 (M5) | improvement | Skill Curator 已落地同步版，但缺异步化与 approved 写回 pack | P2 | triaging | 明确异步触发点与写回冲突策略 |
| ORCH-004 (M6) | improvement | 仅支持 resume B1，缺 reset_to 阶段重放 | P2 | triaging | 明确 checkpoint 与业务 trace 一致性策略 |
| API-002 (M7) | improvement | 缺 token/cost 护栏，运行成本不可控 | P2 | triaging | 先补 slot 级成本基线与告警阈值 |
| ORCH-005 (M8) | improvement | 缺 golden eval 集，回归质量难量化 | P2 | triaging | 先定义评测样本结构与通过阈值 |

## ORCH-001 (M1) Collector framework

- type: improvement
- status: planned
- priority: P0
- owner: _unassigned_

### Current Behavior

Researcher 当前仅支持 `pack_lookup`，证据源固定为本地行业包快照。

### Limitation

无法让信息采集团队并行接入真实渠道（search/fetch/特定站点解析），阻塞后续质量提升。

### Trigger Condition

联调主干已稳定，需并行推进真实采集能力。

### Options Considered

1. 直接在 researcher 节点硬编码渠道（实现快，但扩展差）。
2. 先定义 `CollectorChannel` 协议 + registry（可并行、可替换）。

### Entry Files

- `backend/app/agents/tools/`
- `backend/app/agents/subgraphs/researcher.py`
- `backend/app/service/collector/`（新目录）

### Interface Contract

- `CollectorChannel.collect(query, context) -> list[EvidenceDraft]`
- registry 按 `channel_id` 路由并统一错误语义

### Acceptance Criteria

- 至少 1 个 stub channel 可被 researcher 调用
- channel 失败不会破坏主 run（可降级）
- trace 中可区分 `source_type`

### Suggested Effort

~1.5 人日

### DoD

- 单测覆盖 registry 路由与错误分支
- smoke 至少一条 evidence 来源于 channel stub

### Next Step

输出 collector 协议草案并由队友认领实现。

## Highlights for v2（评审亮点候选，非主干阻塞）

| ID | 方向 | 触发条件 | 入口文件 |
|---|---|---|---|
| HLT-001 | DAG Run View（`@xyflow/react`） | 需要把 Agent 拓扑直观展示给评审 | `frontend/src/pages/RunTracePage.tsx` |
| HLT-002 | Battlecard 卡片网格视图 | 需要一屏展示多竞品结论卡片 | `frontend/src/pages/RunViewPage.tsx` |
| HLT-003 | Prospect Voice 主题视图 | 需要突出真实用户声音与情感分布 | `frontend/src/pages/RunVoicePage.tsx`（新） |
| HLT-004 | Compare 跨竞品矩阵 | 需要横向比较 feature/pricing 差异 | `frontend/src/pages/RunComparePage.tsx`（新） |
| HLT-005 | Skill Curator 真异步化 | 主流程耗时受 Curator 影响或需要脱耦 | `backend/app/agents/nodes/skill_curator.py` |
| HLT-006 | approved 候选写回 `industry_packs` | 需要完成 skill 生效闭环并可审计 diff | `backend/app/router/skill_rt.py`、`industry_packs/*/skills/` |
| HLT-007 | Battlecard freshness + importance 视觉系统 | 演示阶段需要更强业务可读性 | `frontend/src/components/StatusBadge.tsx`、`frontend/src/pages/RunViewPage.tsx` |

## ING-001 (M3) Desensitization pipeline

- type: improvement
- status: investigating
- priority: P1
- owner: _unassigned_

### Current Behavior

证据仅保留 `desensitized: bool`，缺少字段级脱敏策略和审计上下文。

### Limitation

当证据渠道扩展后，布尔值不足以支撑隐私合规和故障追踪。

### Trigger Condition

Collector 接入真实数据后必须升级。

### Options Considered

1. 继续沿用布尔值（短期简单）。
2. 引入规则化脱敏函数与脱敏痕迹字段（长期可审计）。

### DoD

- 定义最小字段级规则集
- 可复现一次脱敏前后对比

### Next Step

补三类高风险样本，明确规则边界后再进入 planned。

## ORCH-002 (M4) SSE run progress

- type: improvement
- status: blocked-by:M1
- priority: P1
- owner: _unassigned_

### Current Behavior

前端当前使用 polling（`useRunDetail/useRunTrace` 每 2 秒刷新），主干联调可用。

### Limitation

长任务体验差，且轮询对后端有重复请求开销。

### Trigger Condition

M2 页面稳定后，轮询负载或用户等待明显上升。

### DoD

- 明确 p95 刷新延迟目标
- 明确 SSE 事件最小 schema

### Next Step

先收集轮询频率、请求量和用户等待时间基线，再设计 SSE 事件 schema。

## ORCH-003 (M5) Skill Curator async reflection

- type: improvement
- status: triaging
- priority: P2
- owner: _unassigned_

### Current Behavior

Skill Curator 已在主流程中同步执行，且已提供 `GET/POST /api/skill-candidates*` 审批 API 与前端审核页。

### Limitation

当前仍是同步节点，且 `approved` 候选尚未自动写回 `industry_packs/<pack>/skills/` 生效池。

### Trigger Condition

主流程 wall-clock 受反思阶段影响，或出现需要自动生效 skill 的明确需求。

### DoD

- Curator 从主图拆为异步任务，失败不影响主 run 完成时间
- `approved` 候选可写回 `industry_packs` 并保留可审计变更记录

### Next Step

先定义异步触发点、写回冲突策略和 reviewer 兜底机制。

## ORCH-004 (M6) Resume B2 reset_to replay

- type: improvement
- status: triaging
- priority: P2
- owner: _unassigned_

### Current Behavior

已支持 `/resume`（B1），仅 thread 级恢复，不支持阶段重放。

### Limitation

无法对特定阶段进行精确重试（如只重跑 writer）。

### Trigger Condition

出现明确的阶段性重放需求且 B1 不足。

### DoD

- checkpoint 与业务 trace 的一致性方案达成评审

### Next Step

梳理 `update_state` 与历史 steps 清理策略的冲突点。

## API-002 (M7) LLM cost guardrails

- type: improvement
- status: triaging
- priority: P2
- owner: _unassigned_

### Current Behavior

现有 trace 有 token 字段，但缺预算上限与自动降级策略。

### Limitation

成本不可预测，难支撑持续迭代与多 run 对比。

### Trigger Condition

多 run 压测下 token 波动超过可接受阈值。

### DoD

- 每个 model_slot 有成本预算与超限动作

### Next Step

先给出 slot 级 token/latency 成本基线。

## ORCH-005 (M8) Golden eval set

- type: improvement
- status: triaging
- priority: P2
- owner: _unassigned_

### Current Behavior

回归主要靠 smoke 与人工观察，无标准化黄金集。

### Limitation

质量回归无法快速定位，版本对比缺客观基准。

### Trigger Condition

迭代频率提升后需要自动化质量门禁。

### DoD

- 定义最小黄金样本集（query+expected assertions）
- 具备可复跑脚本和通过阈值

### Next Step

先确定 10 条核心场景与统一断言口径。
