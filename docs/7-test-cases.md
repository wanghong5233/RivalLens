# RivalLens 测试案例库

文档定位：联调和录制 demo 时直接复用的"准备好的输入"。每个 case 列出 query、competitors、target_roles、可选 domain_hint/reference_urls，以及预期路径与观察点。

竞品种子来自 `backend/demo_fixtures/competitors_seed.yaml`，共 6 类 12 个，可被自动补全。允许输入种子外的任意竞品名（系统按通用字符串契约处理）。

测试矩阵：领域 × 问题类型 × Agent 路径 × 任务管理操作。

---

## 1. 领域基线（每类 1 个 happy path）

| 编号 | 领域 | query | competitors | target_roles | domain_hint | 预期路径 |
|---|---|---|---|---|---|---|
| TC-A1 | AI 编程工具 | 比较 Cursor 与 Windsurf 在产品定位、定价、用户口碑上的差异 | Cursor, Windsurf | pm, founder | ai_coding_assistant | research → analyze → write → qa.approved |
| TC-A2 | 知识管理 | Notion 与 Obsidian 在团队协作场景下的功能边界 | Notion, Obsidian | pm | knowledge_management | research → analyze → write → qa.approved |
| TC-A3 | 项目管理 | ClickUp 与 Asana 在中小团队中的核心功能对比 | ClickUp, Asana | pm, founder | project_management | research → analyze → write → qa.approved |
| TC-A4 | CRM | HubSpot CRM 与 Salesforce 在中小企业获客阶段的差异 | HubSpot CRM, Salesforce | founder | crm | research → analyze → write → qa.approved |
| TC-A5 | Issue 跟踪 | Linear 与 Jira 在工程团队 sprint 流程中的对比 | Linear, Jira | pm | issue_tracking | research → analyze → write → qa.approved |

---

## 2. 问题类型变体（同一组竞品，问题维度不同）

固定竞品 `Cursor, Windsurf`，验证 Skill Library 的 `applies_to=qa_rule / source_routing` 是否真的会按问题语义路由。

| 编号 | query | 期望章节 | 验证点 |
|---|---|---|---|
| TC-B1 | Cursor 与 Windsurf 的核心功能差异是什么 | 功能对比 | conclusions 至少 1 条 section=`features` |
| TC-B2 | Cursor 与 Windsurf 的定价策略和免费额度有何差异 | 定价 | source_type 命中 `pricing_page` |
| TC-B3 | 开发者社区如何评价 Cursor 与 Windsurf | 用户口碑 | source_type 命中 `public_review` 且 prompt-safety 不报红 |
| TC-B4 | Cursor 与 Windsurf 的 SWOT 分析 | SWOT | conclusions 覆盖 strength/weakness/opportunity/threat 四类 |
| TC-B5 | Cursor 在 enterprise 场景下相对 Windsurf 的差异化 | 综合 | confidence 分布合理（high/medium 都有） |

---

## 3. Agent 路径覆盖（异常路径与降级）

观察 SSE 事件流和 `/runs/:runId/trace`、`/runs/:runId/metrics`，确认对应字段被打中。

| 编号 | 触发方式 | query 示例 | 验证点 |
|---|---|---|---|
| TC-C1 QA reject | 故意把 query 模糊化 | "竞品分析" 单词 | `qa.outcome` 出现 `rejected` 且 `reject_to` 非空，主图回到对应 Agent 重做 |
| TC-C2 在线降级 | 设置 `TAVILY_API_KEY` 为空 | TC-A1 同 query | research 走离线 fallback，evidence `source_type=local_note` 增多，run 状态可为 `completed` 或 `degraded` |
| TC-C3 reset → analyst | 先跑通 TC-A1，再 reset_to=analyst | 同 TC-A1 | `/api/runs/{id}/reset` 后 conclusion + report 被清，重跑产生新一批 |
| TC-C4 reset → writer | 先跑通 TC-A1，再 reset_to=writer | 同 TC-A1 | conclusion 保留，仅 report 重生 |
| TC-C5 resume | 主动 kill 一个 running run（API restart）后调 resume | 任意 | 状态恢复并完成或显式失败，不会出现"卡死" |

---

## 4. 边界与稳健性

| 编号 | 输入 | 验证点 |
|---|---|---|
| TC-D1 单竞品 | competitors=`[Cursor]` | 主图能跑通；conclusions 仅含一个 competitor_id |
| TC-D2 三竞品 | competitors=`[Cursor, Windsurf, GitHub Copilot]` | Battlecard 网格按竞品分组渲染三列 |
| TC-D3 未知领域 | query 用电商工具 + 自由竞品名 `Shopify, WooCommerce` | 不在种子表也能完成；Skill Curator 异步落 `skill_candidates` |
| TC-D4 长 query | query ≥ 300 字符 | 不报 422，prompt 不被截到致命位 |
| TC-D5 reference_urls 重复 | 提交 3 个其中 2 个相同 | 后端去重生效，evidence 不出现重复源 |
| TC-D6 空 competitors 触发发现 | competitors=`[]`, query="AI Coding 工具赛道有哪些产品" | 触发 DiscoverCompetitors → 发现 3+ 竞品 → 正常完成 research/analyze/write |
| TC-D7 prompt 注入 | query 内嵌 `ignore previous instructions...` | `evidence.span.prompt_safety.hit_patterns` 命中，sanitized_text 不外泄 |

---

## 5. 任务管理 CRUD（新加的功能）

跑完 TC-A1~A5 后再做这一组。

| 编号 | 操作 | 验证点 |
|---|---|---|
| TC-E1 单删 | 在 `/app` 历史任务里点 `⋯ → 删除` | run 消失；`/api/runs` 不再返回；evidence/conclusion/report 也被级联清掉 |
| TC-E2 重命名 | 行内编辑 user_query | 列表实时刷新；下次 `/api/runs/{id}` 返回新 query |
| TC-E3 批量删 | 复选 3 条不同状态的 run | `deleted_count=3`、`not_found=[]`；列表刷新 |
| TC-E4 批量删含失败 ID | 拼一个不存在的 run_id 提交 `/api/runs/batch-delete` | `not_found` 列出该 ID，已存在的仍被删 |
| TC-E5 取消 running | PATCH `{status: "cancelled"}` 给一个 running run | run.status 转 `cancelled`，finished_at 写入 |

---

## 6. 横向能力

| 编号 | 场景 | 验证点 |
|---|---|---|
| TC-F1 SSE 实时刷新 | 开 `/app/runs/:runId` 看新建任务 | KPI/进度卡片在 step.start/finish 时秒级更新 |
| TC-F2 SSE 重连 | 任务运行中 kill 后端 5s 再起 | 前端自动重连，trace append-only 不丢事件 |
| TC-F3 Watchlist | 在 NewRun 勾选"加入追踪列表" | 提交后 `/api/watchlist` 出现新条目 |
| TC-F4 分享链接 | 完成 run 后点工具条复制链接 | `/share/:runId` 公开可见，无登录 |
| TC-F5 导出 Markdown | 工具条点导出 | 下载文件名含 run_id，内容是 report.content_markdown |
| TC-F6 对比矩阵 | `/app/compare` 选 TC-A1 + TC-A3 两个 run | 表格渲染：行=section、列=competitor，confidence 着色生效 |
| TC-F7 证据溯源 | 报告里点击任意 `[evidence:xxx]` 链接 | 跳到 `/app/runs/:runId/evidence?evidence_id=xxx` 并高亮 |
| TC-F8 DAG 视图 | `/app/runs/:runId/trace` | dagre 排版正常，节点点击展开抽屉 |
| TC-F9 Skill 候选审核 | 跑完 TC-D3 后访问 `/app/settings/skill-admin` | 至少 1 条 pending 候选；批准后 `backend/skills/<applies_to>/<id>/SKILL.md` 落地 |

---

## 7. 赛道扫描（Agent Discovery）

验证"用户不提供竞品名，Agent 自动发现"的 Agent Native 能力。

| 编号 | query | competitors | target_roles | domain_hint | 预期路径 |
|---|---|---|---|---|---|
| TC-G1 纯赛道输入 | AI Coding 工具赛道有哪些产品，各自定位和差异是什么 | （空） | pm, founder | ai_coding_assistant | discovery → research(N) → analyze → write → qa |
| TC-G2 模糊意图 | 我想做一个企业知识管理工具，帮我看看市场上有哪些竞品 | （空） | founder | knowledge_management | discovery → research(N) → analyze → write → qa |
| TC-G3 部分已知 | 除了 Cursor 还有谁在做 AI 编程助手，帮我全面对比 | Cursor | pm | ai_coding_assistant | research(Cursor) + discovery → research(discovered) → analyze → write → qa |
| TC-G4 宽赛道 | 2024 年最值得关注的项目管理 SaaS 工具有哪些 | （空） | pm, founder | project_management | discovery → research(5-8) → analyze → write → qa |
| TC-G5 非种子领域 | 国内主流的 AI 绘画工具对比分析 | （空） | pm | — | discovery → research(N) → analyze → write → qa |

验证点：
- `supervisor_decisions` 表第一条 `chosen_tool=DiscoverCompetitors`
- `steps` 表出现 `agent_name=discovery`
- `runs.competitors` 字段在 run 完成后包含 Agent 发现的竞品名
- 报告 Battlecard 按发现的竞品分组渲染
- 证据控制台可追溯 discovery 阶段的搜索来源

---

## 8. 录制 Demo 推荐脚本

控制总时长 ≤ 3 分钟。建议序列：

1. 落地页 30s：`/` 滑过英雄区与 Battlecard 预览，强调"3 分钟可分享报告"
2. 新建分析 40s：`/app/runs/new` 走 TC-A1，提交后展示 SSE 实时进度
3. 报告作品化 50s：完成后展示 Battlecard、悬浮 chip 调出证据抽屉、切到完整报告再回 Battlecard
4. 跨能力 30s：复制分享链接、再用对比矩阵选两个 run 演示 TC-F6
5. 任务管理 20s：演示 TC-E2 重命名 + TC-E1 单删（用 throwaway run）

录制前清空数据库（`docs/KNOWN_ISSUES_AND_BACKLOG.md` 里有数据库重置注意事项），保留 3-4 条 completed 作为"作品墙"打底。

---

## 9. 文档联动

- 功能清单：`docs/1.1-product-features.md`
- 协议字段：`docs/3-schema-and-protocol.md`
- Agent 路径：`docs/2.5-agent-architecture.md`
- 合规边界：`docs/6-compliance-statement.md`
- 待办 / 已知问题：`docs/KNOWN_ISSUES_AND_BACKLOG.md`
