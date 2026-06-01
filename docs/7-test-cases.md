# RivalLens 测试案例库

文档定位：联调、回归、录制 demo 时**直接复制粘贴的可执行剧本**。每个 case 给出真实首句、Agent 预期 clarify 对话、用户回话、PlanTree 形状、执行期关键事件、可选 follow-up、验收点——不是字段拼凑，而是端到端可复演的脚本。

**测试观念（与 `docs/2.7-agent-native-intake-and-live-run.md` 同步）**：

系统价值不在于"竞品分析"本身（任何 LLM 都能列对比表），而在于：

1. **用户根本不知道自己要什么** → Intake Agent 多轮 clarify 把模糊愿望逼成结构化 `RunIntakeDraft`
2. **用户不知道有哪些竞品** → Planner / Supervisor 通过 `DiscoverCompetitors` 自动发现赛道
3. **用户半路改主意** → 运行中 `POST /follow-up` 注入新指令，Supervisor 下一轮消费
4. **用户对默认计划不满** → Plan 确认页勾掉 / 追加 user-pinned task，强制 Agent 改路径
5. **全过程透明** → Live 页 SSE 实时呈现 supervisor decision / tool call / evidence

测试矩阵按"用户输入清晰度 × HITL 干预 × 异常路径"分层。

---

## 0. 通用约定

- 所有"首句"可直接粘进 `/app/runs/new` chat 输入框。
- 「Agent 提问」一行是**期望的语义**，真实 LLM 文案会变；只要 `field_targets` 与 `suggested_options` 命中即视为通过。
- "用户回话"按 `IntakeUserReply` 提交：`text` + 可选 `selected_options`。
- 测试前置：后端 `make up`、`.env` 配好 `LLM_PROVIDER` + key、`DEMO_FIXTURES_DIR` 指向 `backend/demo_fixtures`。
- 真实 LLM 与 fake LLM 都应能跑通；fake LLM 路径见 `backend/app/tests/conftest.py::_build_intake_response / _build_planner_response`。

---

## 1. Intake 多轮澄清：模糊→结构化（核心价值案例）

### TC-I1 圈外人：有具体业务背景但不知道工具市场

**人设**：B2B 工业自动化设备销售运营负责人，30 人销售团队，最近高层一直在喊「用 AI 提效」，但他本人没碰过 AI 工具市场，被要求下周给一个采购方向。**关键画像**：他完全清楚自己的业务和痛点，但完全不知道 AI 销售工具有哪些细分赛道（外联 / CRM 智能化 / 会议纪要 / 客户洞察 / sales enablement / 报价生成…）。

**首句（user_query）**：

```text
我们是做工业自动化设备销售的，30 人销售团队，主要走线下拜访 + 邮件跟单，平均成交周期 3-6 个月。最近老板一直说要用 AI 提效，让我下周拿个方案出来，但我对 AI 工具完全不了解，市面上现在都有哪些适合 B2B 销售场景的？我们该看哪一类？
```

> 这才是真实的「圈外人」首句：有行业（工业自动化）、有团队规模（30 人）、有销售模式（线下+邮件）、有成交周期、有明确诉求（提效），**唯一不知道的是 AI 工具市场结构**。

**预期对话**（2-3 轮 clarify 后 complete）：

| 轮 | 角色 | 内容 | 关键字段 |
|---|---|---|---|
| 1 | Agent | 您当前的角色更接近？ `field_targets=["user_role"]` `suggested_options=["sales","pm","founder","investor"]` | 选 `sales`（虽是销售运营，最贴近的角色） |
| 1 | User | `selected_options=["sales"]`，可附 text："销售运营负责人，向销售 VP 汇报" | `user_role=sales` |
| 2 | Agent | B2B 长周期销售场景下，AI 工具可以从这几条路径切入。您想先聚焦哪一两个？`field_targets=["analysis_intent","focus_dimensions"]` `suggested_options=["邮件外联 / 跟单自动化","CRM 智能化（线索打分 + 客户洞察）","会议纪要 + Action Item","销售知识库 / Sales Enablement","让我看全景再决定"]` | `selected_options=["邮件外联 / 跟单自动化","CRM 智能化（线索打分 + 客户洞察）"]` + text："长周期跟单最痛，邮件追单和客户动态识别都想看" | Agent 推断 `analysis_intent="B2B 长周期销售：邮件跟单自动化 + CRM 智能化客户洞察"`，`focus_dimensions=["email_outreach","lead_scoring","customer_insight","pricing","onboarding_cost"]` |
| 3 | Agent | 您手上已有候选清单，还是让 Agent 帮您发现？`suggested_options=["我已有名单","让 Agent 帮我发现"]` | `selected_options=["让 Agent 帮我发现"]` | `competitors_discovery_mode=true` |
| 4 | Agent | `action="complete"`，emit `intake.complete` | `is_complete=true` |

**预期 PlanTree**（4 阶段，~6 任务）：

```text
[discover]  发现适合 B2B 长周期销售的 AI 工具（max_results=8，domain_context 含 "B2B sales / long cycle / industrial"）
[research]  Supervisor 在 discovery 完成后按 user_role=sales 视角对每个候选派发（K=3~5）
[analyze]   邮件外联能力 + 线索打分 + 客户洞察 + 与现有 CRM 集成成本 + 定价
[write]     销售运营视角采购建议（含 30 人团队规模下的 ROI 测算）
```

**验收点**：

- `runs.intake_draft.is_complete=true`，`competitors_discovery_mode=true`，`competitors_explicit=[]`
- `intake_draft.analysis_intent` 同时含「邮件」/「跟单」/「CRM」/「客户洞察」中至少两个关键词
- `plan_tree.tasks[0].stage="discover"`，`tool_args.domain_context` 含 `B2B` 或 `sales` 或 `industrial`
- `supervisor_decisions` 首条 `chosen_tool="DiscoverCompetitors"`
- Live 页右下证据流出现 ≥ 3 个不同 `competitor_id`（候选可能含 Salesloft / Outreach / Apollo / Gong / Clari 等）
- 最终 report 章节同时覆盖「邮件外联」与「CRM 智能化」两条线

### TC-I2 创业者做自家产品的赛道对标：部分已知 + 需要补全

**人设**：3 人小团队联合创始人，正在做一款 AI 简历 + 求职助手 MVP，目标用户是国内应届生与 1-3 年工作经验的年轻人。下个月要见种子轮投资人，最关键的问题是：**赛道里到底有几家在做、我自己产品的差异化空间在哪、有没有被先发玩家抢光**。她听说过 Teal、Rezi 和 LinkedIn 的 AI 求职助手，但国内有哪些对手、海外还有谁在做并不清楚。

> 这是创业者使用 RivalLens 的典型场景：**用户在做自己的产品，竞品分析的目的是给投资人讲清楚"我处于赛道哪个位置"**，不是给自己团队买工具。

**首句**：

```text
我们三人团队在做一款「AI 简历优化 + 求职流程跟踪」工具，目标用户是国内应届生和 1-3 年工作经验的年轻人，目前 MVP 已上线小红书内测。下个月要见种子轮投资人，需要搞清楚：海外像 Teal、Rezi 这种 AI 简历优化，LinkedIn 在做 AI 求职助手，国内也有公众号在卷类似产品，整个赛道现在到底有哪些玩家、各自切什么人群和功能、我们这个「简历 + 跟踪」的组合点位是不是已经被覆盖了？
```

**预期对话**（2 轮 clarify 后 complete）：

| 轮 | Agent | User |
|---|---|---|
| 1 | role？ | `selected_options=["founder"]` |
| 2 | 您这次分析的核心问题是赛道格局扫描，还是聚焦给投资人讲清楚差异化定位？`suggested_options=["赛道格局扫描（谁在做什么）","差异化定位分析（我在哪个位置）","两者都要 - 先扫赛道再定位"]` `field_targets=["analysis_intent","competitors_explicit","competitors_discovery_mode"]` | `selected_options=["两者都要 - 先扫赛道再定位"]` + text："已知 Teal / Rezi / LinkedIn，国内的产品和其它海外玩家麻烦 Agent 帮我补" → Agent 应同时设 `competitors_explicit=["Teal","Rezi","LinkedIn"]` + `competitors_discovery_mode=true`（双开），并推断 `domain_hint="ai_resume_job_assistant"`、`analysis_intent="AI 简历 + 求职助手赛道格局与差异化定位（面向种子轮投资人）"`、`focus_dimensions=["target_user","core_feature_set","pricing","go_to_market_channel","funding_stage"]` |

**预期 PlanTree**：

```text
[discover]  AI 简历 / 求职助手赛道发现（max_results=8，domain_context 覆盖海外 + 中文市场）
[research]  Teal（目标用户 + 核心功能 + 定价 + GTM 渠道 + 融资阶段）
[research]  Rezi（同上五维）
[research]  LinkedIn AI 求职功能（同上）
[research]  每个发现的国内 / 海外候选 1 个 task（discovery 后由 supervisor 派发）
[analyze]   人群切片 × 功能矩阵 × GTM 渠道；找出「简历优化 + 求职流程跟踪」组合的空白象限
[write]     面向种子轮投资人的赛道地图 + 差异化定位 narrative
```

**验收点**：

- `intake_history` 长度 ≤ 2
- `intake_draft.competitors_explicit==["Teal","Rezi","LinkedIn"]` 且 `competitors_discovery_mode==true`（双开）
- `intake_draft.domain_hint` 含 `resume` / `job` / `求职` / `简历` 任一关键词
- Supervisor 首次决策为 `DiscoverCompetitors`，`domain_context` 同时含海外与中文线索（"resume" / "中国" / "招聘" 等）
- 候选发现结果中至少出现 1 个国内产品 + 1 个非首句已给的海外产品
- 最终 report 章节同时包含「人群切片」「功能矩阵」「差异化定位象限图所需的原始数据」

### TC-I3 真·模糊：用户开局只甩任务指令

**人设**：互联网公司中层 PM，被老板派去做"竞品分析"，但老板没说做什么 / 为什么 / 给谁看，他自己也没想清楚。

**首句**：

```text
老板让我做个竞品分析，下周二之前要
```

> 这才是真实的极端模糊场景：用户只甩了「任务 + deadline」，**完全没有领域、目标、对象**。系统必须靠主动追问把这堆零信息拉成结构化 draft。

**预期对话**（3 轮硬上限内 complete）：

| 轮 | Agent | User |
|---|---|---|
| 1 | role？ | `selected_options=["pm"]` |
| 2 | 这次竞品分析是想解决什么问题？是给老板汇报市场格局，还是为某个新功能做对标，或评估某个赛道值不值得进？`field_targets=["analysis_intent"]` `suggested_options=["市场格局扫描","新功能对标","新赛道评估","定价策略制定","其它（自由描述）"]` | `selected_options=["新功能对标"]` + text："我们做在线教育的，最近要加 AI 答疑功能，想看同行怎么做的" → Agent 推断 `analysis_intent="在线教育 AI 答疑功能对标"`、`domain_hint="online_education_ai_qa"` |
| 3 | Agent | 您手上已经有想对标的产品名单吗？`suggested_options=["我已有名单","让 Agent 帮我发现"]` | `selected_options=["让 Agent 帮我发现"]` |
| 4 | Agent | `action="complete"` | `is_complete=true` |

**验收点**：

- `intake_history` 长度 = 3（Agent 每轮只问一个 blocking 字段，**绝不一句话塞多个问题**）
- 任一轮 LLM 失败时走 `_fallback_clarify`（运行期可临时把 `LLM_PROVIDER` 改错验证）：第 1 轮强制问 role，第 2 轮问 analysis_intent，第 3 轮问 competitors path
- `intake_draft.is_complete==true` 后才允许 `intake.complete` 事件 emit

### TC-I4 用户连「老板让我做」都不愿意打：极端敷衍

**人设**：测试用户主动权——用户始终一字不发或只回"嗯"。

**首句**：

```text
帮帮我
```

**操作**：连续 3 轮 `IntakeUserReply.text` 全部为 `嗯` 或 `不知道`，不勾选任何 `selected_options`。

**预期**：

- 轮 1 / 2 / 3 走 `_fallback_clarify`（LLM 拿不到信号也会按顺序问 role → intent → competitors path）
- 第 3 轮系统强制 `action="complete"` 并填兜底默认值：`user_role=pm`、`analysis_intent="通用竞品扫描"`、`competitors_discovery_mode=true`（详见 `.cursor/plans/agent-native_intake_and_live_run_95a68da8.plan.md` Phase 1b §风险条目）
- PlanTree 仍能产出（fallback 路径），run 能跑到终态而非卡死

**验收点**：

- `intake_history` 长度 = 3
- 第 3 个 `IntakeExchange.action="complete"`
- `runs.status` 最终落到 `completed` 或 `degraded`（不允许 `running` 卡住）

---

## 2. Intake 半专业：部分已知 → 补全

### TC-I5 用户报出 1 个竞品，要求扩展

**人设**：互联网公司 PM，团队最近在评估给工程师配 Cursor 还是其它 AI 编程助手，需要把市面同类工具的定价和企业版差异摸清楚。

**首句**：

```text
我们工程团队 50 人，正在评估给大家配 AI 编程助手。除了 Cursor 还有哪些主流选择？想全面对比定价（个人版 / 团队版 / 企业版）和企业版能力（SSO / 私有部署 / 代码不出域 / 审计日志）
```

**预期对话**（仅 1 轮 clarify）：

| 轮 | Agent | User |
|---|---|---|
| 1 | role？ `suggested_options=["pm","founder","sales","investor"]` | `selected_options=["pm"]` |
| 2 | Agent 应识别：`analysis_intent="AI 编程助手定价与企业版能力对比"` 已隐含；`competitors_explicit=["Cursor"]` 已给；`focus_dimensions` 可从首句抽出（`pricing_tiers`, `sso`, `private_deployment`, `code_data_residency`, `audit_log`）；询问"是否让 Agent 补充其他主流 AI 编程助手？" `suggested_options=["补充其他竞品","只看 Cursor"]` | `selected_options=["补充其他竞品"]` → `competitors_discovery_mode=true` + 保留 `competitors_explicit=["Cursor"]` |

**预期 PlanTree**：

```text
[discover]   AI 编程助手赛道发现（max_results=6, domain_context 含 "enterprise"）
[research]   Cursor（pricing tiers + enterprise capabilities）
[research]   每个发现的竞品 1 个 task（候选可能含 GitHub Copilot / Windsurf / Cody / Tabnine / Continue 等）
[analyze]    定价分层 × 企业能力矩阵
[write]      面向 PM 的 50 人团队采购建议
```

**验收点**：

- `intake_draft.competitors_explicit == ["Cursor"]` 且 `competitors_discovery_mode==true`
- Supervisor 第一次 decision 为 `DiscoverCompetitors`，但 `state.competitors` 已含 Cursor → discover 跑完后 `ConductResearchBatch` 同时派发 Cursor + 新发现的竞品
- 终态 report 至少 3 列竞品；每个竞品有「企业版 SSO / 代码不出域」字段

### TC-I6 用户描述就是完整的需求规格

**人设**：高级 PM，已经把要分析的产品和维度都想清楚了，只想让 Agent 立刻动手。

**首句**：

```text
我是产品经理，下周要给 CEO 汇报，对比 Notion、Obsidian、Logseq 三个产品在「个人知识管理」场景下的差异，重点看付费转化路径和社区生态活跃度
```

**预期对话**：理论上 0 轮 clarify（三必填字段都齐了），Agent 应直接 `action="complete"`：

- `user_role=pm`
- `analysis_intent="Notion / Obsidian / Logseq 个人 KM 场景对比 - 付费转化 + 社区生态"`
- `competitors_explicit=["Notion","Obsidian","Logseq"]`
- 可选：`focus_dimensions=["pricing_conversion","community"]`

**验收点**：

- `intake_history` 长度 = 0
- `POST /api/runs/intake?mode=chat` 的 `first_clarify_request` 字段为 `null`（直接进 planning 阶段；但因为 Invariant D 要求 sync 等到首 interrupt，会停在 `planner_wait`——前端应直接跳 `/plan` 而非显示 chat 第二轮）

> 该 case 也是「Agent-native 直跳 Plan」的基线。

### TC-I7 内部产品团队对标自家产品所在赛道（TRAE vs 全球 AI 编程工具）

**人设**：字节 AIGC 创新孵化团队 PM，TRAE 已在集团内部上线一段时间，下个月要给集团高层做「TRAE 在全球 AI 编程赛道里的位置 + 下一步投入方向」专题汇报。**关键边界**：自家 TRAE 不放进 `competitors`（它是分析者的「我方」，不是对标对象），重点对标海外头部 + 国内同期玩家。

**首句**：

```text
我们是字节 AIGC 创新孵化团队，集团内部刚发布 TRAE 这款 AI 编程工具，下个月要给集团高层做「TRAE 在全球 AI 编程赛道里的位置」专题汇报。需要重点对标海外的 Cursor、GitHub Copilot、Windsurf，以及国内同期的通义灵码、文心 Comate、豆包 AI 编程助手。最终要回答三个问题:(1) 我们和这些产品在产品定位、定价、企业版能力上的差距和优势分别在哪;(2) 中国市场与海外市场的用户画像和获客路径有什么不同;(3) TRAE 下一步应该加大哪个方向的投入才能在国内 + 出海双战场建立差异化优势。
```

**预期对话**（仅 1 轮 clarify，因为首句信息密度极高）：

| 轮 | Agent | User |
|---|---|---|
| 1 | role？ | `selected_options=["pm"]` |
| 2 | Agent 应识别：`competitors_explicit=["Cursor","GitHub Copilot","Windsurf","通义灵码","文心 Comate","豆包 AI 编程助手"]` 已齐；`analysis_intent` 已隐含"赛道对标 + 中国 vs 出海 + 投入方向建议"；`focus_dimensions` 可从首句抽出（`positioning`, `pricing_tiers`, `enterprise_capabilities`, `user_persona`, `gtm_channel_cn_vs_global`, `pricing_localization`）；`domain_hint="ai_coding_assistant"`。唯一需要确认的是：是否让 Agent 补充其它候选（Cody / Tabnine / Continue / 阿里 AI 助手 / 等）？`suggested_options=["补齐其它海外 + 国内候选","只看我列出的 6 个"]` | `selected_options=["补齐其它海外 + 国内候选"]` → `competitors_discovery_mode=true`（与 explicit 双开）|

> **关键设计**：TRAE 是用户**自己的产品**，**不进 `competitors_explicit`**。RivalLens 的所有 research / analyze 都是"竞品视角"，Writer 在写 report 时会通过 `analysis_intent` 自然带入"我方 TRAE vs 这些竞品"的对照叙事。

**预期 PlanTree**（4 阶段，~9-10 任务）：

```text
[discover]  AI 编程工具赛道补全（max_results=4，domain_context 同时含 "AI coding assistant" 与 "China market"）
[research]  Cursor          （定位 + 定价分层 + 企业版 + 用户画像 + 中国可用性 + 获客路径）
[research]  GitHub Copilot  （同上六维）
[research]  Windsurf        （同上）
[research]  通义灵码        （同上 + 重点关注国内企业渗透与阿里云捆绑策略）
[research]  文心 Comate     （同上 + 重点关注百度内部应用 + 国央企渠道）
[research]  豆包 AI 编程助手 （同上 + 注意与 TRAE 同属字节，分析报告需点明协同 vs 重叠）
[research]  每个发现的候选 1 个 task（候选可能含 Cody / Tabnine / Continue / Cline 等）
[analyze]   三层对照矩阵：① 功能 × 定价矩阵；② 中国 vs 海外用户画像 + GTM 渠道；③ TRAE 在该矩阵中的位置 + 空白象限识别
[write]     给字节集团高层的「TRAE 战略对标 + 下一步投入方向建议」汇报（含 1 页管理层摘要 + 技术细节附录）
```

**验收点**：

- `intake_history` 长度 = 1
- `intake_draft.competitors_explicit` 长度 = 6 且**不含 TRAE**；`competitors_discovery_mode==true`（双开）
- `intake_draft.focus_dimensions` 至少含 `pricing_tiers` / `enterprise_capabilities` / `user_persona` / `gtm_channel_cn_vs_global` 四者
- Supervisor `DiscoverCompetitors.domain_context` 同时含 "AI coding" 与 "China" 或 "中国" 关键词
- Live 页右下证据流出现至少 6 个不同 `competitor_id`（首句 6 个）+ ≥ 2 个发现新增
- 最终 report 章节顺序为：管理层摘要 → 功能 × 定价矩阵 → 中国 vs 海外用户画像 → **TRAE 下一步投入方向建议**（核心可执行输出）→ 附录

### TC-I8 企业 IT 平台选型对标：隐私合规自动化平台（备用 case）

**人设**：大型互联网企业的隐私合规组 PM，集团跨境业务持续扩张（产品线覆盖海外多个市场），现有隐私合规工作流依赖人工台账 + 自研零散脚本，需要评估「自研一套统一的隐私合规自动化平台 vs 引入海外成熟产品」。

> 与 TC-I7 互为备选；TC-I7 偏「产品战略对标」，本 case 偏「企业级专业赛道 + buy vs build 决策」。两者覆盖不同观众气质。

**首句**：

```text
我们是集团信息系统部隐私合规组，跨境业务覆盖多个产品线，需要同时满足 GDPR、CCPA、PIPL、新加坡 PDPA、印度 DPDP 等多个司法管辖区合规要求。现在 DSAR 响应、Cookie 同意管理、数据流图维护、内部合规审计这些工作还是人工台账 + 零散自研脚本拼起来的。想对标海外主流的隐私合规自动化平台（听说有 OneTrust、TrustArc、Securiti 这些），看看它们在大型互联网企业、多司法管辖区、跨境数据流转场景下的能力到底覆盖了哪些环节，与我们自研方案相比的差距在哪，作为「自研 vs 采购」决策的输入。
```

**预期对话**（1-2 轮 clarify 后 complete）：

| 轮 | Agent | User |
|---|---|---|
| 1 | role？ | `selected_options=["pm"]` + text："企业内部 IT 平台 PM"（Agent 推断映射到 `pm`） |
| 2 | 您这次对标主要服务于"自研 vs 采购"决策本身，还是想先做能力 gap 分析再判断？`suggested_options=["先做能力 gap 分析","直接出自研 vs 采购建议","两者都要"]` `field_targets=["analysis_intent","focus_dimensions"]` | `selected_options=["两者都要"]` + text："先看能力 gap，再给 buy vs build 建议" → Agent 推断 `analysis_intent="隐私合规自动化平台能力 gap 分析 + buy vs build 决策"`、`domain_hint="enterprise_privacy_compliance_automation"`、`focus_dimensions=["cross_border_jurisdictions","dsar_automation","cookie_consent","data_mapping_lineage","third_party_risk","internal_audit_workflow","enterprise_idp_integration","large_org_scalability","pricing_model"]`、`competitors_explicit=["OneTrust","TrustArc","Securiti"]`、`competitors_discovery_mode=true`（请 Agent 补齐其它玩家如 BigID / Osano / Ketch / Transcend / DataGrail 等） |

**预期 PlanTree**（4 阶段，~8-9 任务）：

```text
[discover]  隐私合规自动化平台赛道发现（max_results=6，domain_context="enterprise privacy compliance automation cross-border GDPR PIPL"）
[research]  OneTrust（多管辖区覆盖 + DSAR + Cookie + 数据图谱 + IdP + 企业级扩展性 + 价格）
[research]  TrustArc（同上九维）
[research]  Securiti（同上）
[research]  每个发现的候选 1 个 task（候选可能含 BigID / Osano / Ketch / Transcend / DataGrail）
[analyze]   能力 gap 矩阵（行=能力维度，列=产品 vs 自研现状）；自研 vs 采购决策建议（含合规风险、人力成本、可定制性、出海业务弹性）
[write]     内部技术评审用对标报告（含管理层 1 页摘要 + 技术细节附录）
```

**验收点**：

- `intake_history` 长度 ≤ 2
- `intake_draft.competitors_explicit` 含 `OneTrust` / `TrustArc` / `Securiti` 三者；`competitors_discovery_mode==true`
- `intake_draft.focus_dimensions` 同时含 `cross_border_jurisdictions` 与 `dsar_automation` / `cookie_consent` / `data_mapping_lineage` 中至少 2 个
- Supervisor `DiscoverCompetitors.domain_context` 同时含 `privacy compliance` 与至少一个司法管辖区关键词（`GDPR` / `PIPL` / `CCPA` / `cross-border`）
- 至少 1 个 evidence `source_type` 命中 `vendor_official` 或 `analyst_report`（Gartner / Forrester 类报告链接）
- 最终 report 顶部包含「跨境管辖区覆盖矩阵」与「buy vs build 建议」两个明确章节

---

## 3. 专家模式：跳过 Intake

### TC-E1 专家用户直接填表单

**入口**：右上角切「专家表单」→ `/app/runs/new/expert`，走 legacy `POST /api/runs`。

**输入**：

| 字段 | 值 |
|---|---|
| `user_query` | `对比 Cursor 与 Windsurf 在产品定位、定价、用户口碑的差异` |
| `competitors` | `["Cursor","Windsurf"]` |
| `target_roles` | `["pm","founder"]` |
| `domain_hint` | `ai_coding_assistant` |
| `reference_urls` | （留空） |

**预期路径**：

- `POST /api/runs` 立返 `accepted`（≤ 100ms）
- graph 直进 `supervisor`（无 phase 字段，走 `_route_entry` 默认分支）
- 不出现 intake / planner 节点

**验收点**：

- `runs.intake_draft` 为 `NULL`、`plan_tree` 为 `NULL`
- 跳转目标 `/app/runs/{id}`（RunViewPage 自带 SSE），不是 `/plan` 也不是 `/live`
- Trace 第一条 step 为 `agent_name=supervisor`

---

## 4. Plan 干预：disable + user-pinned

### TC-P1 用户取消默认任务，追加自定义任务

**前置**：先按 TC-I6 完整跑完 intake，停在 `/app/runs/:runId/plan`。

**预期 PlanTree**（intake 完成后由 Planner 产出）：

```text
research  Notion 调研（pricing_conversion, community）
research  Obsidian 调研（pricing_conversion, community）
research  Logseq 调研（pricing_conversion, community）
analyze   跨产品对比
write     PM 汇报用 battlecard
```

**操作**：

1. 取消勾选 `research Logseq`（disable）
2. 点「+ 添加任务」追加：
   - stage = `research`
   - title = `Roam Research pricing`
   - competitor = `Roam Research`
   - description = `重点看个人版和团队版定价差异`
3. 提交 `POST /plan/confirm`：

```json
{
  "disabled_task_ids": ["<logseq research 的 ptask_xxx>"],
  "additional_tasks": [{
    "stage": "research",
    "title": "Roam Research pricing",
    "description": "重点看个人版和团队版定价差异",
    "competitor_id": "Roam Research",
    "focus_dimensions": [],
    "source": "user",
    "priority": "user_pinned",
    "enabled": true,
    "task_id": "client_xxx"
  }]
}
```

**验收点**：

- `plan_tree.tasks` 不含 Logseq research（被 disable）
- 新增 task `source="user"`，`priority="user_pinned"`，`task_id` 由后端重发为 `ptask_<uuid>`（不是 `client_xxx`）
- `Run.competitors` 中追加 `"Roam Research"`（来自 `competitors_diff`）
- `supervisor.decision.tool_args.topics` 中 Roam Research 排在 Notion / Obsidian 之前（user_pinned 优先）
- `plan_tree.version == 2`，`confirmed_at` 落 ISO 时戳

### TC-P2 用户在 PlanConfirm 注入非法 task

**操作**：把 stage 改成 `discover`（前端 NativeSelect 强制三选一应该禁，但用 curl 直接打 API）：

```bash
curl -X POST localhost:8010/api/runs/{run_id}/plan/confirm \
  -H "Content-Type: application/json" \
  -d '{"disabled_task_ids":[],"additional_tasks":[{"stage":"discover","title":"x","description":"","competitor_id":null,"focus_dimensions":[],"source":"user","priority":"user_pinned","enabled":true,"task_id":"c1"}]}'
```

**预期**：HTTP 返回 `accepted`（端点本身按 Invariant C 立返），但 background task 抛 `_normalize_user_tasks` 的 `ValueError("user-injected discover stage is not allowed")` → `Run.status="failed"` + `run.failed` 事件 emit。

**验收点**：

- `Run.status="failed"`，`Run.error_message` 含 "discover"
- LiveRunPage 收到 `run.failed` 显示具体错误

### TC-P3 stale plan：disable 不存在的 task_id

**操作**：提交 `disabled_task_ids=["ptask_does_not_exist"]`。

**预期**：bg task 抛 `RuntimeError("disabled_task_ids reference unknown tasks: ...")` → run 失败（不静默丢弃）。

---

## 5. 运行中 follow-up

### TC-F1 标准追加指令

**前置**：TC-I6 跑到 supervisor 已经在 executing（plan_tree.confirmed_at 非空，run.status="running"）。

**操作**：在 LiveRunPage 底部输入框输入：

```text
顺便看看这三个产品的中文社区活跃度怎么样，比如知乎、即刻、Bilibili 的相关讨论
```

提交 → `POST /api/runs/{run_id}/follow-up`。

**验收点**：

- 返回 `{follow_up_id: "fu_xxx", received_at: "..."}`
- `runs.follow_ups[0]` 为新条目，`consumed_at=null`
- LiveRunPage 顶部出现「等待处理 chip」
- 下一次 `supervisor.decision` payload 中 `consumed_follow_up_ids=["fu_xxx"]`
- chip 消失；`reasoning_summary` 提到「用户追加：中文社区活跃度」
- 至少多一次 research task（针对 zhihu/jike/bilibili 源）

### TC-F2 守卫 - graph paused

**操作**：在 chat intake 阶段（graph 停在 `intake_wait`）就提交 follow-up。

**预期**：HTTP 409 `FOLLOWUP_GRAPH_PAUSED`，前端 toast「Agent 正在等您回话，请先回答完澄清问题」。

### TC-F3 守卫 - 终态 run

**操作**：对一个 `status="completed"` 的 run 提交 follow-up。

**预期**：HTTP 409 `FOLLOWUP_RUN_NOT_RUNNING`。

### TC-F4 input 超长

**操作**：提交 `text` 长度 = 1500 的字符串。

**预期**：HTTP 422（Pydantic `max_length=1000`），前端 FollowUpComposer 应在本地拦下（textarea 红边 + 字数提示）。

### TC-F5 连发 3 条

**操作**：在同一次 supervisor turn 之间快速发送 3 条 follow-up。

**验收点**：

- 3 条都 append 进 `runs.follow_ups`，按 `received_at` 排序
- 下次 supervisor decision 一次性消费 3 条（`consumed_follow_up_ids` 长度=3）
- prompt 中 `pending_follow_ups` 段含 3 条按顺序

---

## 6. Discovery + Schema 演化

### TC-D1 非种子领域（跨行需求）

**首句**：

```text
我想了解一下国内做 AI 写真 / AI 摄影的产品，比如妙鸭那一类
```

**预期**：

- intake 完成（competitors_discovery_mode=true，domain_hint 类似 "ai_photo"）
- discovery 节点搜出 ≥ 3 个竞品（妙鸭、星绘、写真馆 AI 等）
- run 完成后异步触发 Skill Curator
- `skill_candidates` 表至少出现 1 条 staging 候选（可能是 `source_routing_candidate` 因为出现了新的 source_type 模式）

**验收点**：

- `/app/settings/skill-admin` 看到 staging 候选
- 候选 `rationale` 字段写明"为什么要新增这条 skill"

### TC-D2 跨语言（英文 query）

**首句**：

```text
Compare top open-source vector databases (Chroma / Qdrant / Weaviate) for a RAG application
```

**预期**：Planner 按英文产出 `tasks[].title / description`（PLANNER_SYSTEM_PROMPT 规则 7）。前端 PlanConfirmPage 应正确渲染英文标题（不被截断/乱码）。

---

## 7. 异常与降级

### TC-X1 在线采集全失败

**前置**：在 `.env` 设 `TAVILY_API_KEY=` 空、`HTTP_FETCH_DISABLED=true`（或拔网线）。

**预期**：

- Researcher 工具调用全部 fail（`tool.finish` 的 `success=false`）
- 降级走 `demo_fixtures` 或 `local_note` source
- run 完成态 = `degraded`，report 顶部带「数据为离线快照」横幅

### TC-X2 LLM provider 不可用

**前置**：把 LLM key 改成错的。

**预期**：

- intake 第一轮 LLM 失败 → 走 `_fallback_clarify`，弹出"请问您的角色是？" hardcoded 问题
- 用户能继续回话；但每轮都走 fallback；Planner 也走 `_fallback_tasks`
- run 能跑到终态（fallback 路径），report 质量降级但不崩

### TC-X3 graph 中断 resume

**操作**：

1. TC-I1 跑到 executing 中
2. `docker compose restart rivallens_api`
3. 等 30s 重连

**预期**：

- 重启 lifespan 把仍在 background 跑的 task 标 `failed` + emit `run.failed`
- 前端 LiveRunPage 收到 `run.failed` 显示「服务重启，请重新发起分析」
- 不会出现"卡死 running 几小时"

### TC-X4 用户长时间不回 intake

**操作**：跑到第一轮 clarify，浏览器关闭，30 分钟后回来。

**预期**（当前实现）：thread 仍存活，重新打开 `/app/runs/{id}` 应该能恢复对话（checkpoint 在 PG）。`docs/KNOWN_ISSUES_AND_BACKLOG.md` 已登记后续应加 30 分钟 timeout cleanup。

---

## 8. 横向能力（基线回归）

| 编号 | 场景 | 输入 | 验收 |
|---|---|---|---|
| TC-O1 | SSE 重连 | 跑 TC-I5 时 kill EventSource（DevTools Network → Close） | 自动重连，trace 不丢；右下证据流补齐缺失条目 |
| TC-O2 | 分享链接 | 完成 TC-I5 后点工具条「复制分享链接」 | `/share/:runId` 公开打开，无登录可读，但 `/app/*` 仍需要工作区入口 |
| TC-O3 | 导出 Markdown | 完成 TC-I5 后点导出 | 文件名含 `run_id`，内容 = `report.content_markdown` 字段原文 |
| TC-O4 | 对比矩阵 | 选 TC-I5 + TC-I6 两个 PM 工具评估 run | 行=section，列=competitor；confidence 着色生效 |
| TC-O5 | 证据溯源 | report 里点 `[evidence:ev_xxx_001]` chip | 跳到 `/app/runs/:runId/evidence?evidence_id=ev_xxx_001`，对应 evidence 高亮+滚动到视图内 |
| TC-O6 | DAG 视图 | `/app/runs/:runId/trace` | dagre LR 布局正常；点 supervisor 节点抽屉显示完整 `reasoning_summary` |

---

## 9. 任务管理 CRUD

| 编号 | 操作 | 验收 |
|---|---|---|
| TC-M1 单删 | `/app` 历史任务点 `⋯ → 删除` | run 消失，`GET /api/runs` 不再返回；evidence / conclusion / report 级联清理 |
| TC-M2 行内重命名 | 点 ⋯ → 重命名，输入新 `user_query` | 列表实时刷新；`/api/runs/{id}` 返回新 query |
| TC-M3 批量删 | 复选 3 条不同状态的 run | 响应 `deleted_count=3, not_found=[]` |
| TC-M4 Live Run 停止分析 | 在 LiveRunPage header 点「停止分析」→ 弹窗确认 | PATCH `{status:"cancelled",cancel_reason:"用户主动停止"}`；后端 cancel 对应 background asyncio task；emit `run.finish` 含 `status="cancelled"`、`error_type="UserCancelled"`、`error_message="用户主动停止"`；前端立刻显示「已停止」横幅 + StatusBadge 「已停止」；后台日志不再出现该 run 的 LLM 调用 |
| TC-M5 Intake 阶段放弃 | 在 NewRunChatPage 第二轮澄清时点 header「放弃此次分析」 | 不必等 intake 完成即可终止；run.status 转 `cancelled`；返回仪表盘后该 run 显示「已停止」 |
| TC-M6 服务重启清扫 | 故意 `docker restart rivallens_api_dev` 时同时有 1 条 running run | 启动日志含 `startup.orphan_runs.swept run_count=1`；该 run.status 自动变 `failed`，error_message="服务重启时此任务正在执行..."；前端再访问立刻看到失败横幅，不再无限「进行中」 |
| TC-M7 卡死提示 | running 状态超过 4 分钟无任何 SSE 事件 | LiveRunPage 顶部出现「分析似乎已停滞」警告横幅，文案显示 idle 时长，并附「标记为失败并退出」按钮 |

---

## 10. Demo 录制脚本（≤ 3 分钟）

### 路线 A — 产品战略对标场景：跑 TC-I7（TRAE 对标）

适合演示「内部产品团队对标自家产品所在赛道，输出投入方向建议」这条链路。

| 幕 | 时长 | 内容 |
|---|---|---|
| 幕 1：高密度首句 → 1 轮确认即跳 Plan | 40s | 粘 TC-I7 首句，演示 Agent 一眼识别 6 个竞品 + 6 维 focus + `domain_hint="ai_coding_assistant"`，只问"是否补充其它候选" → 用户选「补齐」→ intake.complete；右侧需求清单 4 个字段秒级全勾 |
| 幕 2：Plan 干预 | 30s | 跳 `/plan`，演示勾掉 `research 豆包 AI 编程助手`（"自家产品已有内部数据") + 「+ 添加任务」追加 user-pinned `research Cody`；提交后 Plan Tree 顶部 user-pinned 标记翻转 |
| 幕 3：Live 透明 | 60s | 跳 `/live`，左栏 Plan Tree 节点状态从 pending → running → done 翻转，右上工具面板出现 `search_web` / `fetch_url` / `tool.finish`，右下证据流卡片陆续 append Cursor 定价页 / Copilot Enterprise 文档 / 通义灵码官网；底部发一条 follow-up「重点对比中国市场企业版的国央企渠道策略」，chip 出现→消失，下一轮 supervisor decision 的 `consumed_follow_up_ids` 命中并显式输出"已重点检索 国央企 + 阿里云 / 百度智能云 渠道线索" |
| 幕 4：结果作品化 | 30s | 跳 `/app/runs/:id`，演示三大章节：① 功能 × 定价矩阵（Cursor / Copilot / 通义灵码…横向 + TRAE 自身列）；② 中国 vs 海外用户画像；③ **TRAE 下一步投入方向建议**（核心可执行输出）；点任一 evidence chip 弹抽屉看证据原文，复制分享链接 |

### 路线 B — 圈外人 + 多轮澄清场景：跑 TC-I1

适合演示「Agent 主动追问把模糊需求结构化」这条核心能力。

| 幕 | 时长 | 内容 |
|---|---|---|
| 幕 1：模糊需求 → 澄清 | 50s | 用 TC-I1 首句（B2B 工业销售提效），演示 Agent 主动追问 3 轮，右侧需求清单从 0/3 → 3/3 |
| 幕 2：Plan 干预 | 30s | 跳 `/plan`，演示勾掉 1 个 task + 「+ 添加任务」追加 user-pinned，鼠标 hover 显示 Pin 图标 |
| 幕 3：Live 透明 | 60s | 跳 `/live`，左栏 Plan Tree 状态翻转，右上工具调用面板出现 search_web / fetch_url，右下证据流卡片实时 append；演示底部发送一条 follow-up，chip 出现→消失 |
| 幕 4：结果作品化 | 30s | 跳 `/app/runs/:id`，演示 Battlecard、点 evidence chip 弹抽屉、复制分享链接打开 `/share/:id` |

### 路线 C — 企业级 buy vs build 场景：跑 TC-I8

如观众更关注「企业级合规 / 跨境多管辖区 / 自研 vs 采购」这条专业向链路，可改跑 TC-I8 替代路线 A。四幕节奏与路线 A 一致，区别在 follow-up 可改成「重点对比 PIPL 跨境数据传输的支持」，最终报告章节落在「跨境管辖区覆盖矩阵 + buy vs build 建议」。

录制前清空数据库或新建 namespace（参考 `docs/KNOWN_ISSUES_AND_BACKLOG.md` 的数据库重置注意事项）；保留 4 条 completed run 作为「作品墙」打底，建议覆盖 TC-I1（圈外人）/ TC-I2（创业者赛道对标）/ TC-I6（完整规格）/ TC-I7（产品战略对标），四类不同信息密度的入场对话。

---

## 11. 文档联动

| 主题 | 文档 |
|---|---|
| Intake / Planner / Live / Follow-up 子系统 | `docs/2.7-agent-native-intake-and-live-run.md` |
| Agent 角色与拓扑 | `docs/2.5-agent-architecture.md` |
| Schema（含 `RunIntakeDraft` / `PlanTree` / `FollowUpRequest` 字段） | `docs/3-schema-and-protocol.md` |
| 系统级工程边界 | `docs/2-architecture-decision.md` |
| 已落地功能盘点 | `docs/1.1-product-features.md` |
| 合规边界 | `docs/6-compliance-statement.md` |
| 已知问题 / 待办 | `docs/KNOWN_ISSUES_AND_BACKLOG.md` |
