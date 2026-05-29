# 实现切片 12：Skill Curator 闭环与审核 API

## 1. 目标与边界

本切片目标：

- 把 Skill Curator 接入主图闭环，确保 run 完成后可沉淀 `skill_candidates`；
- 提供候选查询与审核 API，前端可直接联调；
- 保持失败不阻塞主 run：Curator 失败只写 `error`，不让 run 卡死。

本切片不做：

- Curator 真异步化 worker（仍为同步节点）；
- `approved` 候选自动写回 `backend/skills/*/SKILL.md` 落盘生效；
- 评审亮点 UI（Battlecard 卡片网格 / Voice / Compare / DAG Run View）。

## 2. 编排改动（QA -> Curator -> END）

### 2.1 LangGraph 路由调整

- `qa` 节点输出 `qa_outcome=approved` 时，进入 `skill_curator`；
- `qa_outcome in {rejected, force_degraded}` 时，仍回 `supervisor`；
- `skill_curator` 完成后直接 `END`。

这保证了：

- QA 通过的 run 一定进入反思沉淀；
- QA 打回路径不受影响，仍由 Supervisor 决策重试或降级收敛。

### 2.2 Curator 节点行为

`backend/app/agents/nodes/skill_curator.py` 做三件事：

1. 读取 run 上下文（QA 反馈、Supervisor 决策尾部、evidence source 分布）；
2. 调用 LLM 生成候选（`qa_rule` / `prompt_template` / `source_routing`）；
3. 写入 `skill_candidates(status=staging)`，并记录 `steps + llm_calls`。

失败策略：

- LLM 请求失败或 schema 不合法时，写一条带 `error` 的候选行；
- 该失败不会把主 run 置为失败，run 仍可 `completed`。

## 3. 审核 API 契约

新增 `backend/app/router/skill_rt.py` 并挂载到 `app_main`：

- `GET /api/skill-candidates?status=&applies_to=&tag=&limit=&offset=`
  - 返回分页候选列表；
- `POST /api/skill-candidates/{candidate_id}/approve`
  - 仅允许 `staging -> approved`；
  - 写 `reviewed_by/reviewed_at`；
- `POST /api/skill-candidates/{candidate_id}/reject`
  - 仅允许 `staging -> rejected`；
  - 写 `reviewed_by/reviewed_at`。

约束：

- 非 staging 状态再次审核返回 `409 SKILL_CANDIDATE_NOT_REVIEWABLE`；
- 不存在候选返回 `404 SKILL_CANDIDATE_NOT_FOUND`。

## 4. 前端联调入口补齐

### 4.1 Skill 审核页

- 新增页面：`frontend/src/pages/SkillStagingPage.tsx`
- 路由：`/skills/staging`
- 能力：
  - 按 `status/applies_to/tag` 过滤；
  - 展示候选详情、支撑 run 链接、payload；
  - 执行 approve/reject。

### 4.2 顶栏入口与待审计数

- `frontend/src/app/layout/AppShell.tsx` 增加“Skill 审核台”入口；
- 通过 `status=staging` 查询显示待审数量 badge。

### 4.3 resume 入口接通

- `frontend/src/pages/HomePage.tsx` 在 `running` run 行增加“恢复运行”按钮；
- 接通已有 `useResumeRun`，完成 9/9 后端 API 前端入口覆盖。

## 5. 数据流（本切片）

```mermaid
flowchart LR
    Supervisor[supervisor] --> Writer[writer]
    Writer --> QA[qa]
    QA -->|approved| Curator[skill_curator]
    QA -->|rejected_or_force_degraded| Supervisor
    Curator --> CandidateTable[(skill_candidates)]
    Curator --> EndNode[END]

    SkillPage[/skills/staging] --> ListAPI["GET /api/skill-candidates"]
    SkillPage --> ApproveAPI["POST /api/skill-candidates/{id}/approve"]
    SkillPage --> RejectAPI["POST /api/skill-candidates/{id}/reject"]
    ListAPI --> CandidateTable
    ApproveAPI --> CandidateTable
    RejectAPI --> CandidateTable
```

## 6. 与架构文档对齐

本切片对应 `docs/2-architecture-decision.md` 的落地关系：

- §2 系统总图：Skill Curator 与 Skill Candidate Review API 已落地；
- §7.2 生命周期：`staging -> approved/rejected` 单向迁移已在 API 层约束；
- §10.1 可靠性：Curator 失败不阻塞主 run，错误写入 `skill_candidates.error`。

仍待后续版本完成：

- Curator 真异步化（减少主流程 wall-clock）；
- `approved` 候选写回 `backend/skills` 生效池并输出可审计 diff。
