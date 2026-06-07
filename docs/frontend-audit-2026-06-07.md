# 前端审计与迭代清单

最后更新: 2026-06-07 · 范围: `frontend/src/**` 静态审计 · 截止: 6/10 提交
验证: `npm run type-check` 通过;未做浏览器交互录屏,本文件只记静态审计结论。
来源: 两份并行静态审计(本文 FE-xxx 与 codex `frontend-static-audit`)交叉验证后合并,代码论断均带 `file:line`。

目标(2026-06-07 纠偏:产品成熟度是驱动力,赛题维度是自检副产物):
1. **产品成熟度(驱动力)** — 从 naive 逻辑升级到可上线、可留存、可付费的深度研究平台:逻辑直观、真实可用、信任信号清晰。
2. **赛题维度(自检)** — 把产品做好后,核对 `docs/0-problem-background.md` §4 的 5 个评分维度是否被自然覆盖;不用赛题权重反向排优先级。

后端 Agent 编排、证据、指标、结论、对比、Trace 接口已较完整(见 `docs/KNOWN_ISSUES_AND_BACKLOG.md`);本轮缺口集中在**前端没把后端能力接给用户**:页面分散、信任信号不集中、部分后端字段前端类型未声明。

---

## 1. 结论速览

| ID | 类型 | 缺口一句话 | 评分维度 | 优先级 | 成本 |
|---|---|---|---|---|---|
| FE-001 | Bug | 前端 `RunTraceResponse` 类型缺 `llm_calls`/`timeline`,Trace 页拿不到真实 LLM 调用 | 维度2 (25%) | P0 | 低 |
| FE-002 | 回归 Bug | `MetricsPanel` 已实现但未挂载,RunView 只剩 4 个简化 KPI | 维度2+3 | P0 | 低 |
| FE-003 | Improvement | 无分析透明度视图:DAG/QA/LLM/证据/指标分散多页,用户无一屏看懂结论怎么来的 | 维度1+2 | P0 | 中 |
| FE-004 | Improvement | QA 打回→重做→改善 闭环不可视化(无法证明非伪闭环) | 维度1 (35%) | P0 | 中 |
| FE-005 | Improvement | 来源权威占比 / 脱敏覆盖率不可见(R10/合规亮点埋没) | 维度1+5 | P1 | 低 |
| FE-006 | Improvement | Schema 三件套(功能树/定价模型/用户画像)无专门视图,`content_json` 未用 | 维度1 (35%) | P1 | 中 |
| FE-007 | Bug | running 状态不按 phase 导航(不进 plan/live) | 维度3 | P1 | 低 |
| FE-008 | Bug | 专家表单走 legacy `/api/runs`,绕过 plan/live | 维度1+3 | P1 | 中 |
| FE-009 | Improvement | Compare 页语义错位:跨历史 run 拼 conclusions,非本次竞品矩阵 | 维度3 | P1 | 中 |
| FE-010 | Bug | 分享页引用跳转进 `/app` 工作区,公开访客溯源断裂 | 维度1/产品 | P1 | 低 |
| FE-011 | Improvement | Live 终态 2.5s 强制踹走用户(replace 还回退不了),无法回看编排;历史 run 无 Live 回放 | 维度2/体验 | P1 | 低 |
| ~~FE-012~~ | dropped | ~~无 demo fallback 只读演示入口~~ → 删除:为演示造兜底=反产品;稳健由 FE-011+历史列表自然达成 | — | — | — |
| FE-013 | Improvement | 营销页承诺未兑现功能 + 假数据(3 分钟 / 42 条结论 / PDF 导出实际仅 MD) | 维度3/诚实 | P2 | 低 |
| FE-014 | Improvement | Templates / Settings 账户为占位页 | 产品 | P2 | 中 |
| FE-015 | 治理 | 死代码 `HomePage.tsx`、孤儿 `MetricsPanel`、backlog METRIC-001 标记失真 | 维度4 | P2 | 低 |
| FE-016 | Improvement | Watchlist 仅 CRUD,无刷新/告警闭环 | 产品 | P2 | 中 |
| FE-017 | Improvement | "清空全部历史"在主工具栏,仅 `window.confirm`,用户易误删数据 | 产品/安全 | P2 | 低 |
| FE-018 | Improvement | intake 澄清仅身份/意图/竞品三项,deep 模式缺预算/地区/输出格式 | 产品 | P2 | 中 |
| FE-019 | Improvement | follow-up 仅 Live 页可达,报告完成后无追问/重做入口 | 产品 | P2 | 低 |
| FE-020 | Improvement | Skill 审核台是工程页,价值表达脱节 | 产品 | P2 | 低 |

P0 四项(FE-001/002/003/004)收敛到「可观测 + 闭环可信度」主线——把"结论可信、可溯源"这件产品核心做扎实;赛题最高权重的 35%+25% 维度随之自然覆盖。

---

## 2. 赛题维度自检 → 前端落地映射(覆盖度核对,非驱动主线)

| 维度(权重) | 已可见 | 缺口 | 关联 |
|---|---|---|---|
| 多 Agent 协作与可信度 (35%) | DAG 可视化(`RunTracePage`+`@xyflow`)、结构化 conclusions/comparison、证据一键溯源(`EvidenceDrawer`+`evidence://`) | **反馈闭环不可视**(QA reject→redo→改善)、**Schema 三件套**无专门视图、内部可观测分散(归 debug 诊断台) | FE-003/004/006 |
| 技术深度与工程完整 (25%) | 端到端可演示、SSE 实时流、DAG trace | **Prompt/输入/输出/Token 无 UI**(类型漂移 FE-001)、重试/降级指标不可见(MetricsPanel 未挂载) | FE-001/002/003 |
| 业务价值与产品体验 (20%) | 报告查看、溯源跳转、决策回放(静态)、plan 确认/follow-up/reset | **可量化指标埋没**、专家路径与 running 导航断裂、Compare 语义错位 | FE-002/007/008/009 |
| 代码质量与文档 (10%) | 设计 token 化、shadcn 组件库、模块清晰 | 死代码、前端类型与后端 response 漂移、backlog 与实现漂移 | FE-001/015 |
| 合规、材料 (10%) | 脱敏后端 100% 覆盖、endpoint 不落日志 | **脱敏覆盖率/官方来源占比前端不可见**、分享页溯源断裂、营销文案承诺未兑现 | FE-005/010/013 |

后端已暴露但前端未消费的关键能力:`GET /api/runs/{id}/trace`(含 `llm_calls`/`timeline`,前端类型未声明)、`GET /api/runs/{id}/metrics`(完整指标)、SSE `qa.outcome`/`evidence.collected`。后端有存但 API 未暴露(FE-003 耦合项):`llm_calls.prompt_text`/`response_raw`、`steps.rejection_reason`。

---

## 3. P0 — 赛题直接失分,优先补

### FE-001 Trace 类型漂移:前端拿不到真实 LLM 调用
- type: Bug · status: planned · priority: P0
- **Symptom**: `RunTracePage` 的 LLM tab 只从 `steps.payload` 抽 `analysis_mode` 等 5 个 highlight key(`RunTracePage.tsx:28-38`),展示不出 provider/model/token/latency/retry/prompt_preview。
- **Root Cause**: 后端 `RunTraceResponse` 已返回 `llm_calls` 与 `timeline`,但前端 `types.ts` 的 `RunTraceResponse` 只声明 `run/steps/supervisor_decisions`(`types.ts:183-187`),类型层直接丢弃了这两个数组。
- **Impact**: 维度2 要求"每个 Agent 的 Prompt、Token、决策过程均有 Trace 可查"。当前前端无法展示真实 LLM 调用,答辩只能靠后端日志或数据库。
- **入口**: `frontend/src/api/types.ts`(补 `LLMCallTraceResponse`/`TraceTimelineItemResponse` + 加进 `RunTraceResponse`) + `frontend/src/pages/RunTracePage.tsx`(LLM tab 渲染真实 `llm_calls`)。
- **DoD**: LLM tab 展示真实调用表:agent/slot/provider/model/tokens/latency/retry/fallback/error/prompt_preview;`npm run type-check` 通过。
- **Next Step**: 先补类型,再渲染表格;这是 FE-003 的前置。

### FE-002 MetricsPanel 孤儿:可量化指标不可见
- type: 回归 Bug · status: planned · priority: P0
- **Current**: `RunViewPage` KPI 区是 4 个内联 `KpiCard`,仅 `coverage_rate / qa_rejection_rate / evidence_count_total / 耗时`(`RunViewPage.tsx:174-186`)。`MetricsPanel` 已实现完整指标但全仓库无 import(`components/MetricsPanel.tsx`)。`RunMetricsResponse` 类型字段完整(`types.ts:206-235`),纯属未渲染。
- **Limitation**: 端点已返回但被丢弃的字段:`evidence_dimension_coverage_rate`(R9 诚实覆盖)、`source_type_distribution`(R10 官方占比)、`desensitization_coverage`(合规)、`llm_token_total / llm_latency_p50_ms / llm_retry_total / llm_provider_error_count`(可观测)、`dimension_coverage_rate`、`manual_review_rate`。`METRIC-001` 在 backlog 标 `[x]` 但实际未挂载,文档与实现漂移(见 FE-015)。
- **对应维度**: 维度2(可观测 token/重试)+ 维度3(可量化提升)。
- **入口**: `frontend/src/pages/RunViewPage.tsx`(挂载) + `frontend/src/components/MetricsPanel.tsx`(补 R9/R10 字段)。
- **DoD**: RunView 完成态展示覆盖率/维度覆盖率/QA 通过率/脱敏覆盖率/官方来源占比/Token/延迟/重试;字段口径在组件提示可追溯。
- **Next Step**: 挂载到 RunView 报告区,与 FE-005 一并补来源/脱敏展示。

### FE-003 可观测诊断台缺失(debug/admin,临时暴露可隐藏)
- type: Improvement · status: planned · priority: P0
- **定位(重要)**: `/audit` 是 **debug / admin 诊断视图,不是终端用户特性**。深度可观测(prompt_preview/token/LLM 调用/QA 内部/decision)给开发调试和比赛验证用,**终端付费用户看不见、也不需要看**。现在临时从报告页暴露入口,生产环境应默认隐藏(用一个 `VITE_` 开关随时关,见 FE-021)。
- **Current**: 深度可观测散落在 `/live`、`/trace`、`/evidence`、报告 tab、Skill 审核台,开发自查/比赛验证"一次 run 怎么跑的"需多次跳转。
- **Limitation**: 调试与比赛验证需一屏看清多 Agent 编排、QA 闭环、LLM 调用、溯源。这些是内部诊断信息,必须与干净用户视图分离——`RunView` 给用户(结论+轻量信任信号),`/audit` 给开发/admin。
- **方案**: 新增 `/app/runs/:runId/audit` 诊断台,从报告页按钮进入(措辞用"分析详情/诊断"等中性词,不用"验收/答辩"),不挂主导航,入口受开关控制可隐藏。页面区块:

| 区块 | 展示内容 | 数据来源 |
|---|---|---|
| Run 概览 | 状态/耗时/竞品数/证据数/报告字数 | `/runs/:id`、`/metrics` |
| 多 Agent DAG | Agent 节点、Supervisor 决策、状态色 | `/trace.steps`、`/trace.supervisor_decisions` |
| LLM 调用 | provider/model/slot/token/latency/retry/fallback/error/prompt_preview | `/trace.llm_calls`(依赖 FE-001) |
| QA 闭环 | QA 次数/打回原因/触发重写/最终通过 | `/trace`、`/metrics`(依赖 FE-004) |
| 溯源证据 | source_type 分布、官方占比、证据链接 | `/metrics`、`/evidence` |
| 业务产物 | Battlecard、comparison cells、报告入口 | `/conclusions`、`/comparisons`、`/report` |

- **入口**: 新增 `frontend/src/pages/RunAuditPage.tsx` + 路由 `runs/:runId/audit`;复用 `MetricsPanel`/`RunTraceDag`/`ComparisonMatrix`,不重做后端(prompt 全文/rejection_reason 如需更细再扩 `/trace`,注意脱敏、不落 Key)。
- **DoD**: 一屏覆盖 6 区块,开发/admin 可一页看清一次 run 的完整内部执行;入口可被开关隐藏(FE-021)。
- **Next Step**: FE-001/002/004 落地后聚合到本页;入口加开关(FE-021)。

### FE-004 QA 反馈闭环不可视化
- type: Improvement · status: planned · priority: P0
- **Current**: QA 打回→重做在后端真实发生,SSE 有 `qa.outcome`(含 `reject_to`/`failed_rule_count`)。`RunView` 决策回放只列最近 5 条 supervisor reasoning(`RunViewPage.tsx:299-311`),不突出"第 N 轮打回 X、重做后 Y 改善"。
- **Limitation**: 维度1 明确考察"质检 Agent 打回且重做后输出有改善(非伪闭环)",当前无法直观证明。
- **对应维度**: 维度1 (35%) 核心。
- **入口**: `frontend/src/components/dag/RunTraceDag.tsx`(QA reject 回环高亮) + 诊断台 QA 区(打回原因 → 重做 Agent → 前后差异:章节数/证据数/失败规则数)。数据先用 `trace.steps` 的 QA payload + `supervisor_decisions.triggered_by/outcome` 聚合,无打回时显示"规则全部通过"。
- **DoD**: 一屏可见至少一次完整 QA 闭环及重做前后差异。
- **Next Step**: 从现有 trace 字段聚合,需更精确字段再补后端。

### FE-021 /audit 诊断台入口未受开关控制(易隐藏)
- type: Improvement · status: planned · priority: P1
- **定位**: `/audit` 是 debug/admin 视图(见 FE-003),现在入口对所有用户可见。生产上线应默认隐藏,只在开发/比赛时打开。
- **Current**: `RunViewPage.tsx:215` 入口按钮无条件渲染;`router.tsx:57-63` `/audit` 路由始终可达。
- **方案**: 加一个 `VITE_SHOW_DEBUG_PANELS`(沿用 `client.ts` 的 `import.meta.env` 模式)开关;flag 关时隐藏 RunView 入口按钮(必要时路由也降级 NotFound)。默认值:开发/比赛 = 开,生产 = 关。翻一个开关即可隐藏。
- **DoD**: flag 关闭时终端用户在产品里看不到任何 `/audit` 入口;flag 打开时开发/比赛可正常进入。
- **Next Step**: 归入 FE-S3(产品正确性:不向用户暴露内部诊断)。

---

## 4. P1 — 体验断裂 / 一致性 / 答辩观感

### FE-005 来源权威 / 脱敏不可见
- type: Improvement · status: planned · priority: P1
- **Current**: `metrics.source_type_distribution` 与 `desensitization_coverage=1.0` 后端已返回,前端无展示;`evidence.metadata.source_authority`(official/third_party)未在证据 UI 标注。
- **对应维度**: 维度1(可信度)+ 维度5(合规)。R10 官方来源治理与 100% 脱敏是硬亮点,答辩无体现。
- **入口**: `frontend/src/components/MetricsPanel.tsx`(来源分布 + 脱敏徽章) + `frontend/src/components/EvidenceDrawer.tsx` / `RunEvidencePage.tsx`(每条证据标 official/第三方/定价/文档 + 脱敏标 + 维度)。
- **DoD**: 指标区显官方占比与脱敏覆盖率;证据条目标权威性;筛选支持"官方/第三方"。
- **Next Step**: 随 FE-002 一并接入。

### FE-006 Schema 结构化展示不全
- type: Improvement · status: investigating · priority: P1
- **Current**: 报告以 markdown 渲染(`content_json` 未用,`RunReportResponse.content_json` 已返回);结构化展示为 battlecard(conclusions)+ comparison matrix(dimension×competitor stance)。
- **Limitation**: 赛题 Schema 明确"功能树、定价模型、用户画像"三件套。当前无三者的专门结构化视图,`content_json` 价值未释放。
- **对应维度**: 维度1 (35%) "输出严格符合预定义 Schema,字段完整、格式一致"。
- **Open Question**: 后端 conclusions/comparison 是否已覆盖 persona/功能树/定价 维度?需确认 schema 实际产出范围再定视图(RC 未定前不动手)。
- **入口**: `frontend/src/pages/RunViewPage.tsx`(消费 `content_json`) + 新增结构化视图组件。
- **Next Step**: 先确认后端 schema 产出,再决定视图。

### FE-007 running 状态导航断裂
- type: Bug · status: planned · priority: P1
- **Current**: Dashboard"继续处理"running run 进 RunView 而非 Live(`DashboardPage.tsx:248-250`);RunView 在 running 时停留显示"报告生成中",不按 `phase` 导向 `/plan`(待确认)或 `/live`(执行中)。
- **对应维度**: 维度3。用户在错误页空等,实时编排亮点被绕过。
- **入口**: `frontend/src/pages/app/DashboardPage.tsx` + `frontend/src/pages/RunViewPage.tsx`(按 `detail.phase` 路由)。
- **DoD**: phase=planning→`/plan`;executing→`/live`;done→RunView。
- **Next Step**: 加 phase 守卫跳转。

### FE-008 双 intake 路径不一致
- type: Bug · status: planned · priority: P1
- **Current**: 对话路径(`NewRunChatPage`)走 intake→plan→live→report;专家表单(`NewRunPage`)直接 `POST /api/runs`,跳 RunView,跳过 plan 确认与 live 观测(`NewRunPage.tsx:252-290`)。
- **对应维度**: 维度1+3。专家用户看不到 plan 编辑与实时编排,削弱"DAG 流转可视化"与"人工介入"演示。
- **入口**: `frontend/src/pages/NewRunPage.tsx`(改接 `/api/runs/intake` 预填 draft)或文档明确"专家=快速直跑"定位。
- **DoD**: 专家路径进入统一 plan/live 流,或 UI 明示"跳过确认"语义。
- **Next Step**: 决策——统一到 intake 流 vs 保留快速直跑(需用户拍板范围)。

### FE-009 Compare 页语义错位
- type: Improvement · status: planned · priority: P1
- **Current**: `/app/compare` 选 2-4 个历史 run,用 conclusions 拼 section×competitor 表(`ComparePage` 直接 `GET /conclusions`),无 stance/evidence/source quality。
- **Limitation**: 用户预期先看"某次 run 内的竞品维度矩阵";当前更像跨项目知识归档,与 `/comparisons`(dimension×competitor cells)定位混淆。
- **对应维度**: 维度3。
- **入口**: `frontend/src/pages/app/ComparePage.tsx`。
- **DoD**: "本次竞品矩阵"用 `/comparisons` 作主入口;跨 run 对比改名"历史报告对照"。
- **Next Step**: 明确两类对比的命名与入口。

### FE-010 分享页溯源跳出工作区
- type: Bug · status: planned · priority: P1
- **Symptom**: `SharedReportPage` 引用点击跳 `/app/runs/:runId/evidence?...`(`SharedReportPage.tsx:44-50`),公开访客被带进工作区,溯源体验断裂。
- **Scope**: 内部答辩可接受;上线产品会破坏公开分享。
- **入口**: 分享页内置 `EvidenceDrawer` 或公开 evidence 子路由,引用不依赖 `/app`。
- **DoD**: 分享页内点引用就地展开证据,不跳工作区。

### FE-011 Live 终态强制踹走用户
- type: Improvement · status: planned · priority: P1
- **Current**: `LiveRunPage.tsx:326-334` 终态后 2.5s `navigate(replace)` 自动跳报告且 replace 导致回退不了;历史 run 无等价"回放 Live 过程"页。
- **Limitation**: 用户(以及录屏/演示时)还没看清工具调用、证据流、Plan Tree 就被系统带走,是"替用户做决定"的体验问题。
- **对应维度**: 维度2/体验。
- **入口**: `frontend/src/pages/LiveRunPage.tsx`。
- **DoD**: 终态显示"已完成,查看报告"按钮(429-435 已存在),不强制跳转,由用户自己点。

### ~~FE-012 无 demo fallback 演示入口~~ — DROPPED(2026-06-07 纠偏)
- status: **dropped**
- **删除理由**: 为演示造只读兜底入口本质是"为演示写代码",与"成熟可上线产品"的驱动力冲突。演示稳健由 FE-011(终态不踹走用户)+ 已有历史列表/最新报告自然达成:自然打开一份真实 completed run 就是最好的演示。不留 backlog。

---

## 5. P2 — 产品成熟度 / 治理

| ID | 类型 | 现状(file:line) | 建议 | 维度 |
|---|---|---|---|---|
| FE-013 | Improvement | `LandingPage.tsx:30` "3 分钟产出"(真实 deep ~4-5 分钟);`:55` "42 条结论"硬编码;`:58-76` Competitor A/B/C 假数据;`:108` 承诺 PDF 实际仅 MD;`PricingPage.tsx:6-28` `PLANS` 硬编码 | 产品诚实:文案改"数分钟"、预览用真实 completed run、删未兑现的 PDF 承诺(或补 PDF);定价页明确"即将上线"标注 | 维度3/诚实 |
| FE-014 | Improvement | `TemplatesPage.tsx:14`、`SettingsPage.tsx:23` "即将上线";后端无 `/templates`/`/settings` | 答辩前隐藏入口,或 Templates 落 3 个可直接发起的前端策展模板(复用 `EXAMPLE_PROMPTS`) | 产品 |
| FE-015 | 治理 | `HomePage.tsx` 未挂路由(与 Dashboard 重叠);`MetricsPanel` 孤儿(见 FE-002);backlog `METRIC-001` 标 `[x]` 失真 | 删 `HomePage.tsx`;修正 `docs/KNOWN_ISSUES_AND_BACKLOG.md` METRIC-001 状态 | 维度4 |
| FE-016 | Improvement | `WatchPage` 仅 watchlist CRUD;`next_refresh_at` 字段未展示,无刷新/告警/关联报告 | 长期项;短期改"已追踪竞品 + 最近报告入口",答辩以"可扩展"口径说明 | 产品 |
| FE-017 | Improvement | `DashboardPage.tsx:322-329` "清空全部历史"在历史区主工具栏,仅 `window.confirm` 单次确认 | 移到设置/危险区,改强确认(type-to-confirm),降低用户误删数据风险 | 产品/安全 |
| FE-018 | Improvement | 对话 intake 只补身份/意图/竞品三项(`RunIntakeDraft` 另有 report_depth/focus_dimensions) | deep 模式追加预算/地区/输出格式/时间范围澄清;专家模式保留 | 产品 |
| FE-019 | Improvement | follow-up 仅 `LiveRunPage` 可达;报告完成后无追问/重做入口 | 报告页加"继续追问/重做分析/只重写报告"(复用 `/follow-up`、`/reset`) | 产品 |
| FE-020 | Improvement | `SkillStagingPage` 是工程审核页,价值表达脱节 | 改"质量规则学习台":候选规则 + 来源 run + 审核后生效的 QA/Prompt/Source routing | 产品 |

---

## 6. 产品成熟度方向(长期)

赛题之外、面向上线运营,不阻塞 6/10 提交:

| 方向 | 现状 | 目标 |
|---|---|---|
| 引导与空状态 | 新用户进 Dashboard 多为空列表 | 首跑引导、示例 run、空状态 CTA |
| 报告可消费性 | 仅 MD 导出 | PDF/分享页增强、章节锚点目录、可折叠 |
| 人工介入 | follow-up/plan/reset 已有但入口分散 | 报告内联编辑、结论标注采信/存疑、统一介入入口(关联 FE-019) |
| 信任与定价 | 定价页 mock | 用量计费模型、配额可视、付费墙设计 |
| 多 run 资产化 | Compare 跨 run 结论矩阵 | 竞品库沉淀、趋势追踪(接 Watchlist FE-016) |
| 性能与稳定 | SSE+10s poll fallback | 断线恢复体验、大报告虚拟滚动 |

---

## 7. 建议执行顺序(按产品成熟度收益)

| 序 | 目标 | 范围 | 自检维度 |
|---:|---|---|---|
| 1 | 补真实 Trace/LLM 可观测(诊断台基础) | FE-001(`types.ts`+`RunTracePage`) | 维度2 |
| 2 | 点亮可量化指标 + 来源/脱敏 | FE-002 + FE-005(`MetricsPanel`+`RunView`) | 维度2/3/5 |
| 3 | 建可观测诊断台聚合一屏(debug/admin) | FE-003 + FE-004(新 `RunAuditPage`) | 维度1/2 |
| 4 | 产品正确性:导航/终态/诚实/防误删 | FE-007 + FE-011 + FE-013 + FE-017 | 维度3/体验 |
| 5 | 诊断台入口可隐藏(不向用户暴露内部) | FE-021 | 产品 |
| 6 | 余量补 | FE-006/008/009/010/014-020 | 产品 |

驱动力是产品成熟度;FE-001~004 把"结论可信+内部可诊断"做扎实,赛题最高权重维度随之自然覆盖。FE-001 是 FE-003 的前置,应最先做。
