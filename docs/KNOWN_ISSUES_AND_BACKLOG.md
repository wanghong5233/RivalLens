# Known Issues & Backlog

最后更新: 2026-05-24

## Active Issues 索引

| ID | type | 问题 | 优先级 | 状态 | 当前阶段下一步 |
|---|---|---|---|---|---|
| ORCH-001 (M1) | improvement | Collector framework 缺失，队友无法并行接入真实采集 | P0 | planned | 明确协议与 registry 最小骨架后开领 |
| API-001 (M2) | improvement | 前端主干已打通，但 M2 业务页与 UI 精修仍待拆分认领 | P0 | planned | 按 M2.1-M2.5 领取独立 PR |
| ING-001 (M3) | improvement | 脱敏策略仅布尔标记，缺字段级规则和审计证据 | P1 | investigating | 先补违规样本与失败分布 |
| ORCH-002 (M4) | improvement | 无 SSE 进度流，长 run 只能轮询 | P1 | blocked-by:M1 | 主干先用 polling，等待 SSE 事件 schema 定稿 |
| ORCH-003 (M5) | improvement | Skill Curator 未落地，反思结果无法沉淀为可复用能力 | P2 | triaging | 先定义 candidate 生命周期与审批边界 |
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

## API-001 (M2) Frontend run console

- type: improvement
- status: planned
- priority: P0
- owner: _unassigned_

### Current Behavior

联调主干已上线（`/`、`/runs/new`、`/runs/:run_id`、`/runs/:run_id/trace` + Evidence Drawer），可完成端到端联调。

### Limitation

仍缺业务页与视觉系统，评审与演示体验不完整。

### Trigger Condition

主干稳定后，需要并行交付剩余 M2 页面与 UI 精修。

### Options Considered

1. 先做 run 列表 + 详情 + trace + report 四页最小闭环。
2. 一次性做完整交互（周期长，风险高）。

### M2 拆分任务

#### M2.1 单竞品 Battlecard 详情页

- owner: _unassigned_
- entry files:
  - `frontend/src/pages/RunCompetitorPage.tsx`（新）
  - `frontend/src/app/router.tsx`
  - `frontend/src/components/EvidenceDrawer.tsx`（复用）
- interface contract:
  - 路径：`/runs/:run_id/competitors/:competitor_id`
  - 消费：`GET /api/runs/{id}/report` + `GET /api/runs/{id}/evidence?competitor_id=...`
- acceptance:
  - 详情页展示该竞品的 section 内容
  - citation 点击可打开 Evidence Drawer

#### M2.2 Prospect Voice 页面

- owner: _unassigned_
- entry files:
  - `frontend/src/pages/RunVoicePage.tsx`（新）
  - `frontend/src/app/router.tsx`
- interface contract:
  - 路径：`/runs/:run_id/voice`
  - 第一版先消费 `report.content_json` 中 user_feedback 相关内容
- acceptance:
  - 支持按竞品筛选
  - 至少展示主题分组 + 引用明细

#### M2.3 Compare 对比矩阵页面

- owner: _unassigned_
- entry files:
  - `frontend/src/pages/RunComparePage.tsx`（新）
  - `frontend/src/app/router.tsx`
- interface contract:
  - 路径：`/runs/:run_id/compare`
  - 消费 `report.content_json`，按 section/competitor 透视
- acceptance:
  - 至少支持 4 个竞品横向对比
  - 支持 feature/pricing 维度切换

#### M2.4 Skill Staging 页面

- owner: _unassigned_
- entry files:
  - `frontend/src/pages/SkillStagingPage.tsx`（新）
  - `frontend/src/app/router.tsx`
- interface contract:
  - 路径：`/skills/staging`
  - 后端暂未提供完整 API，先以 mock 数据打通页面交互
- acceptance:
  - 可展示候选列表 + 通过/拒绝按钮
  - 预留后端 API 对接位

#### M2.5 UI 视觉系统精修

- owner: _unassigned_
- entry files:
  - `frontend/src/index.css`
  - `frontend/src/components/ui/*`
  - `frontend/src/components/StatusBadge.tsx`
- interface contract:
  - 统一深灰 + indigo 主题
  - 状态色具备文本/图标双重语义（可达性）
- acceptance:
  - 页面在 1366 宽度下视觉一致
  - loading/error/empty 状态样式统一

### Suggested Effort

~2.5 人日（可并行拆成 5 个 PR）

### DoD

- M2.1-M2.5 各自有验收截图或录屏
- 每个子任务都可独立回归

### Next Step

由前端同学按 M2.1->M2.5 顺序领取并并行提交。

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

`skill_candidates` 表已存在，但无异步反思流程和审批入口。

### Limitation

经验无法结构化沉淀，系统缺少自我演化闭环。

### Trigger Condition

主干稳定并开始积累重复失败模式。

### DoD

- candidate 产生、审批、落库链路定义完成

### Next Step

先定义 candidate 生命周期与 reject/revive 语义。

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
