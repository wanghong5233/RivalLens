---
name: FE 前端冲刺总纲
overview: RivalLens 前端冲刺一级 plan(活文档)。声明计划族 FE,阶段 S1-S5,每个阶段=一个 todo=指向一个二级 plan 去 build,二级验证无误回写本总纲,执行中发现新结构性问题迭代纠正本总纲。证据来自 docs/frontend-audit-2026-06-07.md(FE-001..020)+ 执行中实测 carryover facts,引用带 file:line。本总纲只列阶段、依赖、决策门与问题地图,不写文件级改法/Verify/build 单元。
todos:
  - id: FE-S1
    content: "FE-S1 可观测与指标接线(enabler,先行) → 二级 fe-s1_可观测指标接线_d7dcadb0。已完成:FE-001 Trace 类型补 llm_calls/timeline + LLM tab 渲染真实调用、FE-002 挂载 MetricsPanel 到 RunView、FE-005 来源权威占比/脱敏覆盖率展示 + 证据 authority 标注。含一小后端聚合字段 source_authority_distribution。验证:type-check + build 通过,后端 metrics/curator 目标测试通过。"
    status: completed
  - id: FE-S2
    content: "FE-S2 可观测诊断台(debug/admin) + QA 闭环 → 二级 fe-s2_验收台_qa闭环_c61bb78b。已完成:/app/runs/:runId/audit 诊断台(不挂主导航,报告页按钮进入),一屏聚合 Run 概览/Agent DAG/LLM 调用/QA 闭环/溯源证据/业务产物:FE-003 诊断台、FE-004 QA 打回→重做→改善可视化。定位为开发调试/比赛验证的内部视图,非终端用户特性(生产可隐藏,见 FE-S3/FE-021)。GATE-1 已决并落地:暴露 rejection_reason,prompt 仍只用 prompt_preview。验证:type-check + build + trace mapper pytest 通过。"
    status: completed
  - id: FE-S3
    content: "FE-S3 产品正确性打磨 → 二级 fe-s3_产品正确性_c26c902f。已完成:FE-007 running 按 phase 导航(列表响应补 phase,Dashboard/历史行进 plan/live,RunView 只软提示不强跳)、FE-011 Live 终态不自动 replace 跳报告、FE-013 Landing 删除 PDF/3分钟/42条/假竞品卡并改真实 completed run 预览、FE-017 清空全部历史移入危险操作 + type-to-confirm、FE-021 /audit 诊断台入口与路由受 VITE_SHOW_DEBUG_PANELS/DEV 开关控制。FE-012 已删除:不为演示造假。"
    status: completed
  - id: FE-S4
    content: "FE-S4 Schema 三件套后端产出 + QA 一致性闭环(核心 MVP,补字节 35% 点名 gap) → 二级 fe-s4_schema三件套后端_b9c4e1a7(已展开,5 把后端刀 A-E)。后端 Analyst 新增产出结构化功能树/定价/画像(对齐 docs/3-schema §2.2-2.6/§3.3 预定义 Schema)+ 持久化 + migration + /knowledge API + QA 校验字段完整/格式一致,不合格打回 analyst 重做 + 每轮落 failed_rule_count 快照。GATE-2(真做)/GATE-4(接 QA 校验,全套)已决,见 §2。"
    status: completed
  - id: FE-S5
    content: "FE-S5 三件套前端视图 + QA 闭环改善证据 + 收尾 → 二级 fe-s5_*(进入阶段后调研代码再创建)。三件套结构化视图(功能树/定价/画像)+ 证据一键溯源(RunView 新 Tab + 诊断台复用)、QA 闭环重做改善 delta 加强(修基线错位 + 展示失败规则数下降)、FE-010 分享页溯源就地化、FE-015 删死代码/修文档漂移。硬依赖 FE-S4 的 /knowledge 与 QA 快照。"
    status: completed
isProject: false
---

# RivalLens 前端冲刺总纲(活的一级 plan)

最后更新: 2026-06-07 · 截止: 6/10 提交

> 这是一级 plan,不是普通文档。闭环:每个阶段(todo)=一个任务 → 指定二级 plan 去 build → 二级验证无误回写本总纲 → 二级执行中发现新结构性问题则迭代纠正本总纲。证据来自前端静态审计 [docs/frontend-audit-2026-06-07.md](docs/frontend-audit-2026-06-07.md)(FE-001..020),引用带 file:line。方法论见 [03-incremental-refactor-layered-piv](docs/private/engineering-playbook/03-incremental-refactor-layered-piv.md)。

## 命名体系

按方法论新一轮声明新计划族,从 S1 重启,不续后端 `E2E`/`E2E2` 族。

- 计划族:`FE`。
- 阶段(一级 todo):`FE-S1` .. `FE-S5`,一个阶段 = 一个二级 plan,按依赖/演示影响推进。
- 问题条目:`FE-S<n>-<m>` + 性质标签(`[可观测]`/`[可信度]`/`[体验]`/`[正确性]`/`[诚实]`/`[合规]`/`[产品]`),只描述问题与证据,不直接 build。
- 二级刀:`FE-S<n>-A`/`-B`(二级 plan 内的原子提交单元),进入该阶段后调研代码再切。
- ↔ 审计映射:`FE-S<n>-<m>` 与审计文档 `FE-0xx` 一一对应,见 §3 问题地图。

## 0. 一句话结论(第一性原理:短期评分 gap 驱动核心 MVP,长期产品成熟度)

**双轴分线(2026-06-07 二次澄清,见 §7 顶部决策)**:短期(到 6/10)直接目标是字节评分,标准指向「工业级、深入落地、可控的 Agent 系统」——**以评分 gap 排优先级**,但兑现方式是把核心 MVP 做真(不造假 demo,延续纠偏红线);长期才是上线运营产品(面向未来 backlog)。

S1-S3 已把可观测、QA 闭环可视、可量化指标、证据溯源、诚实文案做扎实——**5 维评分大半已自然覆盖**。对照评分盘点后,**剩余唯一点名级硬 gap = Schema 三件套(功能树/定价/画像)后端零产出 + QA 是否真验「字段完整/格式一致」且重做有改善(非伪闭环)**——字节把这两点写在同一条 35% 里。这就是 S4(后端产出 + QA 校验)+ S5(前端视图 + 闭环证据)。

两层仍要分清:**面向终端用户的轻量信任信号**(证据溯源、来源权威徽章、QA 通过率)留在 `RunView`;**深度可观测**(prompt_preview/token/LLM 调用/QA 内部/decision)聚合到 `/audit` debug/admin 诊断台,生产默认隐藏(开关控制,见 FE-021)。主线:S1 接线 → S2 诊断台+QA 闭环 → S3 产品正确性 → S4 三件套后端+QA 一致性闭环 → S5 三件套前端+闭环证据+收尾。

## 1. 依赖拓扑(阶段编号=依赖序,非发现序)

```text
FE-S1 可观测接线 (enabler)
  ├─ FE-001 Trace 类型补 llm_calls/timeline ─┐
  ├─ FE-002 MetricsPanel 挂载              ─┼─→ FE-S2 可观测诊断台 (debug/admin)
  └─ FE-005 来源/脱敏展示                   ─┘     ├─ FE-003 /audit 聚合 (用 S1 的 LLM/metrics/source)
                                                  └─ FE-004 QA 闭环可视
FE-S3 产品正确性 (与 S1/S2 无硬依赖, 可并行)  [completed]
FE-S4 Schema 三件套后端 (核心 MVP; GATE-2/4 已决)
  ├─ Analyst 产出三件套 → 持久化/migration → /knowledge API
  └─ QA 一致性校验(打回 analyst 重做) + 改善 delta 快照
       └─→ FE-S5 三件套前端 (硬依赖 S4 的 /knowledge + QA 快照)
            ├─ 三件套视图 + 证据溯源
            ├─ QA 闭环改善证据加强
            └─ FE-010 分享溯源 / FE-015 治理收尾
```

硬依赖:FE-001 是 FE-003「LLM 调用」区块的前置;FE-002/FE-005 喂 FE-003 的「指标/溯源」区块。故 **S1 必须先于 S2**。S3 与 S1/S2 无硬依赖,独立推进。**S5 硬依赖 S4**:前端三件套视图消费 S4 的 `/knowledge` API,QA 闭环改善证据消费 S4 的 `failed_rule_count` 快照——S4 未落地前 S5 无真实数据可接。

## 2. 决策门(RC 未定 / 需外部输入,build 前必须先过)

| 门 | 归属 | 问题 | 触发动作(playbook:RC 空只许补证据/召集决策) |
|---|---|---|---|
| GATE-1 | FE-S2 | prompt 全文不暴露;`rejection_reason` 后端存库且已随 `/trace` 暴露 | 已决并落地:只暴露 QA `rejection_reason`,prompt 继续使用 `prompt_preview`,不暴露全文 prompt_text |
| GATE-2 | FE-S4(FE-006) | 后端是否产出 persona/功能树/定价 的结构化 schema? | **已决(2026-06-07 调研落地)**:后端零产出三件套——`business.py:20-134` 仅契约,`app/` 无 producer,Analyst 只产 conclusions/comparison。决议=**真做**:Analyst 新增结构化产出 + 持久化 + /knowledge API,不降级为按维度分组 |
| GATE-3 | FE-S4(FE-008) | 专家表单是统一进 intake/plan/live,还是保留"快速直跑"定位 | **已决:撤销**。双 intake(对话式 Agent 澄清新手需求 / 专家表单高效直跑)是刻意产品设计,非缺陷——不动 `NewRunPage`,FE-008 转 dropped |
| GATE-4 | FE-S4 | 三件套是否接 QA 一致性校验(字段完整/格式一致 + 非伪闭环) | **已决:全套**。QA 强制 docs §3.3 最小合格标准,不合格打回 analyst 重做,前端展示改善 delta。触发数据:docs §7 selector DSL(`pricings[*]`)是文档示例**未实现**,真实 QA(`engine.py:439-639`)只校验报告章节+evidence(451-459) |

## 3. 问题地图(↔ 审计 FE-0xx)

| 阶段 | 问题条目 | 审计 ID | 性质 | 证据(file:line) |
|---|---|---|---|---|
| FE-S1 | S1-1 Trace 类型漂移,拿不到真实 LLM 调用 | FE-001 | 可观测 | `types.ts:183-187` `RunTraceResponse` 只声明 run/steps/supervisor_decisions,缺 `llm_calls`/`timeline`;`RunTracePage.tsx:28-38` 只抽 5 个 payload key |
| FE-S1 | S1-2 MetricsPanel 未挂载,可量化指标不可见 | FE-002 | 可观测/可量化 | `RunViewPage.tsx:174-186` 仅 4 个内联 KPI;`MetricsPanel.tsx` 全仓库无 import;`types.ts:206-235` metrics 类型完整 |
| FE-S1 | S1-3 来源权威占比/脱敏覆盖率不可见 | FE-005 | 可信度/合规 | metrics `source_type_distribution`/`desensitization_coverage` 已返回前端无展示;`evidence.metadata.source_authority` 未在证据 UI 标注 |
| FE-S2 | S2-1 可观测诊断台缺失(debug/admin),内部可观测散落多页 | FE-003 | 可观测 | 维度证据分散在 /live、/trace、/evidence、报告 tab、Skill 台 |
| FE-S2 | S2-2 QA 打回→重做→改善 闭环不可视 | FE-004 | 可信度 | `RunViewPage.tsx:299-311` 只列最近 5 条 supervisor reasoning,不突出 QA 闭环 |
| FE-S3 | S3-1 running 状态不按 phase 导航,用户看空报告 | FE-007 | 体验/正确性 | `DashboardPage.tsx:248-250` running 进 RunView 而非 Live;RunView 不按 phase 导向 plan/live |
| FE-S3 | S3-2 Live 终态强制踹走用户,无法回看编排 | FE-011 | 体验/可信度 | `LiveRunPage.tsx:326-334` 终态 2.5s `navigate(replace)` 自动跳报告且回退不了 |
| FE-S3 | S3-3 营销文案承诺未兑现功能(诚实问题) | FE-013 | 诚实/合规 | `LandingPage.tsx:30` "3 分钟"、`:55` "42 条结论"、`:58-76` 假数据、`:108` PDF(实际仅 MD);`PricingPage.tsx:6-28` 硬编码 |
| FE-S3 | S3-4 清空全部历史在主工具栏,易误删 | FE-017 | 产品/安全 | `DashboardPage.tsx:322-329` 主工具栏 + 仅 `window.confirm` |
| FE-S3 | S3-5 /audit 诊断台入口对用户无条件可见 | FE-021 | 产品 | `RunViewPage.tsx:215` 入口按钮 + `router.tsx:57-63` 路由始终可达;应受 `VITE_` 开关控制,生产默认隐藏 |
| ~~FE-S3~~ | ~~S3-x 无 demo fallback 只读演示入口~~ | ~~FE-012~~ | dropped | 为演示造兜底=反产品;稳健由 FE-011+历史列表自然达成,删除不留 backlog |
| FE-S4 | S4-1 后端零产出三件套结构化 Schema(功能树/定价/画像) | FE-006(后端) | Schema/35% | `business.py:20-134` 仅契约,`app/` 无 producer;Analyst 只产 conclusions/comparison |
| FE-S4 | S4-2 QA 不校验三件套一致性(字段完整/格式一致);§7 selector DSL 未实现 | FE-006/FE-004 衍生 | 可信度/35% | `engine.py:439-639` 只校验报告章节+evidence(451-459);docs §7 `pricings[*]` 仅文档示例 |
| FE-S4 | S4-3 QA 打回→重做缺「改善」硬数据 | FE-004 衍生 | 可信度/35% | `failed_rule_count` 未落 step.payload(engine.py:383);仅 writer 重写有可信前后计数 |
| FE-S5 | S5-1 三件套无结构化前端视图 | FE-006(前端) | Schema/35% | 依赖 S4 `/knowledge`;现仅 battlecard+comparison 矩阵 |
| FE-S5 | S5-2 QA 闭环改善 delta 基线错位/未展示 | FE-004 衍生 | 可信度 | `qaClosure.ts:196-200` analyst/researcher 基线取到 writer;失败规则数前后未对比 |
| FE-S5 | S5-3 分享页溯源跳出工作区 | FE-010 | 产品/合规 | `SharedReportPage.tsx:41-49` 引用跳 `/app/.../evidence`,公开访客断裂 |
| FE-S5 | S5-4 死代码/文档漂移 | FE-015 | 代码质量/10% | `HomePage.tsx` 未挂路由;backlog METRIC-001 漂移 |
| ~~FE-S4~~ | ~~双 intake 路径不一致~~ | ~~FE-008~~ | dropped | 双 intake(新手 Agent 澄清 / 专家直跑)是刻意产品设计,非缺陷(GATE-3) |
| backlog | Compare 语义/占位页/Watchlist/intake 字段/follow-up 入口/Skill 台 | FE-009/014/016/018/019/020 | 面向未来 | 长期上线产品化,赛后做,不阻塞 6/10 |

## 4. 阶段路线

### FE-S1 可观测与指标接线 [enabler,先行]

二级 plan:`fe-s1_可观测指标接线_d7dcadb0.plan.md`。

- 范围:FE-001 / FE-002 / FE-005。把 `/trace` 的 `llm_calls`+`timeline`、`/metrics` 全字段、evidence `source_authority` 接到前端;并补一小刀后端聚合字段 `source_authority_distribution`。
- 进入条件:无依赖(后端数据均已返回)。建议作为第一刀。
- 出口验收:type-check + build 通过;真实 completed run 上 LLM tab 见 provider/model/token/latency/retry、指标区见维度覆盖/脱敏/官方占比、证据条目见 official/第三方标注。
- 调研锚点:`frontend/src/api/types.ts`、`RunTracePage.tsx`、`RunViewPage.tsx`、`MetricsPanel.tsx`、`EvidenceDrawer.tsx`(进入阶段后详读再切刀)。

### FE-S2 可观测诊断台(debug/admin) + QA 闭环 [可信度/可观测核心]

二级 plan:`fe-s2_验收台_qa闭环_c61bb78b.plan.md`。

- 范围:FE-003 / FE-004。新增 `RunAuditPage`(路由 `runs/:runId/audit`),6 区块聚合;QA 闭环可视化(打回原因→重做 Agent→前后差异)。定位:开发调试/比赛验证的内部诊断视图,**非终端用户特性**;深度可观测(prompt_preview/token/decision)与干净用户视图分离。UI 文案用中性词(分析详情/诊断),不用"验收/答辩"。
- 进入条件:**硬依赖 FE-S1**(LLM 类型/metrics/source);**GATE-1 已过**(暴露 `rejection_reason`,不暴露 prompt 全文)。
- 出口验收:type-check + build 通过;真实 run 上 `/audit` 一屏让开发/admin 看清一次 run 的完整内部执行;至少展示一次 QA 闭环及重做前后差异(无打回时显式"规则全部通过")。
- 复用:`MetricsPanel`/`RunTraceDag`/`ComparisonMatrix`,不重做后端。

### FE-S3 产品正确性打磨 [真实缺陷,非演示]

二级 plan(待创建):`fe-s3_*.plan.md`。

- 范围:FE-007 / FE-011 / FE-013 / FE-017 / FE-021(FE-012 已删除,不为演示造假数据兜底)。
- 进入条件:与 S1/S2 无硬依赖,独立推进。
- 出口验收:type-check + build 通过;running run 按 phase 进对的页(不让用户看空报告);Live 终态保留页面让用户自己点进报告(不替用户做决定);营销文案不承诺未实现功能(删 PDF/3分钟/42条,预览用真实数据);清空全部历史防误删(移出主工具栏 + 强确认);`/audit` 诊断台入口受 `VITE_` 开关控制,生产默认隐藏。

### FE-S4 Schema 三件套后端产出 + QA 一致性闭环 [核心 MVP,35% 点名]

二级 plan(已展开):[fe-s4_schema三件套后端_b9c4e1a7.plan.md](.cursor/plans/fe-s4_schema三件套后端_b9c4e1a7.plan.md)(5 把后端刀 A-E,带 file:line carryover facts)。

- 范围:S4-1/S4-2/S4-3。Analyst 新增产出结构化功能树/定价/画像(对齐 docs §2.2-2.6 预定义 Schema)→ 持久化(新表)+ migration → `/knowledge` API;QA 强制 docs §3.3 最小合格标准,不合格打回 analyst 重做;QA 每轮落 `failed_rule_count` 快照供改善度量。
- 进入条件:GATE-2(真做)+ GATE-4(接 QA 校验,全套)已决。
- 出口验收(阶段级):容器内 pytest 目标测试 + `alembic upgrade head`;真实 run 产出符合 Schema 的三件套并落库、`/knowledge` 可读;不完整三件套能触发 QA 打回重做(超 `MAX_QA_REJECTIONS` 走 force_degraded)。
- 调研锚点(carryover facts,进入阶段详读再切刀):产出/持久化沿用 `analyst.py:260-321` + `persist_conclusions_for_step` 模式;Schema 契约 `business.py:20-134`;迁移 head `0018` 于 `backend/app/alembic/versions/`;QA `engine.py:439-639`(只读 report/evidence 451-459)、`MAX_QA_REJECTIONS=3`(engine.py:33);现有 `backend/skills/qa_rule/` 2 个规则文件;预定义合格标准 docs §3.3。
- 风险:Analyst 稳定产出三件套(LLM)为最高风险——降级空列表 + coverage 标 insufficient_data,不阻断主链;QA 打回多轮由 force_degraded 兜底。

### FE-S5 三件套前端视图 + QA 闭环改善证据 + 收尾 [核心 MVP + 治理]

二级 plan(待创建,进入阶段后调研代码再切 slice):`fe-s5_*.plan.md`。

- 范围:S5-1/S5-2/S5-3/S5-4。三件套结构化视图(功能树/定价/画像)+ 证据一键溯源(RunView 新 Tab + 诊断台复用);QA 闭环改善 delta 加强(修基线错位 + 展示失败规则数下降);FE-010 分享页溯源就地化;FE-015 删死代码/修文档漂移。
- 进入条件:**硬依赖 FE-S4** 的 `/knowledge` API 与 QA `failed_rule_count` 快照字段。
- 出口验收(阶段级):type-check + build;真实 completed run 上三件套视图数据来自真实 API、证据可溯源;有 QA 打回的 run 能看到重做前后改善。
- 调研锚点(carryover facts):证据抽屉复用 RunView `EvidenceDrawer` 模式;`qaClosure.ts:196-200` 基线错位、`QaClosureSection.tsx`;`SharedReportPage.tsx:41-49`;`HomePage.tsx` 死代码。

## 5. 验收基线(前端,与后端 pytest 不同)

前端无 test runner(见 AGENTS.md)。每刀的 parity 锚:

1. `npm run type-check` 通过(契约/类型 parity)。
2. 宽改动追加 `npm run build` 通过。
3. **对任一真实 completed run 目检**(视觉/交互 parity):截图前后对照,确认数据来自真实 API 而非占位。锚点是真实历史 run,不为目检专设 demo run。
4. 一刀一原子提交,可独立回滚;连失败 3 次 → revert 重拆刀。
5. 旧路径(如现有 RunView KPI)保留到新视图 parity 稳定再撤。

## 6. 附录:赛题 5 维 ↔ 阶段覆盖映射

> 双轴(§0):短期 S4/S5 直接用评分 gap 排优先级;S1-S3 以产品成熟度驱动,已自然覆盖大半维度。本表是 5 维 ↔ 阶段的覆盖映射。

| 维度(权重) | 已覆盖(S1-S3) | 剩余 gap → 阶段 |
|---|---|---|
| 多 Agent 可信度 (35%) | QA 闭环可视(S2-2)、证据溯源、结构化消息 | Schema 三件套产出+视图 → FE-S4(S4-1)/FE-S5(S5-1);QA 一致性校验+非伪闭环 → FE-S4(S4-2/3)/FE-S5(S5-2) |
| 技术深度/可观测 (25%) | Prompt_preview/Token/决策/LLM 调用 UI、指标(S1/S2) | 已基本覆盖;持久化新表/迁移属工程完整度 → FE-S4 |
| 业务价值/体验 (20%) | 可量化指标、导航/终态(S1/S3) | 三件套提升结构化一致性 → FE-S4/S5 |
| 代码质量/文档 (10%) | 类型对齐、设计 token | 死代码/backlog 漂移 → FE-S5(S5-4) |
| 合规/材料 (10%) | 脱敏/官方占比可见、诚实文案(S1/S3) | 分享溯源就地化 → FE-S5(S5-3) |

## 7. 活文档增补(执行中发现,新→旧)

### 2026-06-07 · FE-S5 completed

- 落地刀:FE-S5-A/B/C/D/E 全部完成。前端新增 `/knowledge` 类型与 `useRunKnowledge`,RunView 新增「竞品知识」Tab,RunAudit「业务产物」复用同一三件套视图;功能树/定价模型/用户画像均使用 FE-S4 的真实 `GET /api/runs/{run_id}/knowledge` 响应,不从报告正文猜结构。
- 溯源闭环:新增 `KnowledgePanel`,每个 feature/pricing/persona 使用自身 `evidence_ids` 打开现有 `EvidenceDrawer`;分享页引用从跳回 `/app/runs/:id/evidence` 改为就地打开抽屉,公开分享阅读不再断裂到工作区。
- QA 改善证据:修正 `qaClosure.ts` 中 analyst/researcher 重做基线误用 writer `target_step_id` 的问题;QA 打回轮次新增 `失败规则数 before -> after` 展示,直接消费 FE-S4 落下的 `failed_rule_count` 快照。
- 治理收尾:删除未挂路由的 `frontend/src/pages/HomePage.tsx`;`docs/KNOWN_ISSUES_AND_BACKLOG.md` 中 METRIC-001 更新为真实已挂载 `MetricsPanel` 的状态。
- 验证:`frontend npm run type-check` passed;`frontend npm run build` passed。每刀均跑过对应 type-check/build;S5-D 额外确认 `/api/runs/{run_id}/report` 与 `/api/runs/{run_id}/evidence` 同为 run router 读接口。

### 2026-06-07 · FE-S4 completed

- 落地刀:FE-S4-A/B/C/D/E 全部完成。AnalystOutput 新增 `schema_version/features/pricings/personas/coverage`,解析时过滤越界 evidence/competitor、服务端重铸 `feat_/price_/persona_` id;fallback 产空三件套并按 competitor 标 `insufficient_data`。
- 持久化/API:新增 `run_knowledge` 单表 JSONB + migration `0019_add_run_knowledge` + `service.knowledge.persist_knowledge_for_step/load_knowledge_for_run`;Analyst 以 `begin_nested()` 错误隔离写入三件套计数。新增 `GET /api/runs/{run_id}/knowledge`,响应 `{run_id,schema_version,features,pricings,personas,coverage}`,无知识返回空结构,缺 run 返回 404。
- QA 闭环:新增确定性 `rule_knowledge_schema_conformance`,按 run.competitors 校验 docs §3.3 最小标准;结构残缺/无证据/未诚实声明不足时 blocking 打回 `analyst`,诚实 `partial/insufficient_data/missing` 不误伤。QA step payload approval/rejection 均带 `failed_rule_count` 和 `failed_rule_ids`,供 FE-S5 展示轮次改善 delta。
- 验证:`alembic upgrade head` passed;`alembic downgrade -1` passed;再 `upgrade head` passed。容器内 `pytest tests/test_agent_outputs.py tests/test_knowledge_persistence.py tests/test_qa_knowledge_conformance.py tests/test_qa_payload_snapshot.py tests/test_knowledge_api.py tests/test_qa_rules.py tests/test_smoke.py tests/test_intake_api.py tests/test_plan_api.py -q` passed(87 passed)。
- 给 FE-S5 的 carryover:`/knowledge` 是三件套唯一前端数据源;证据溯源字段统一用各 item 的 `evidence_ids`;QA 改善度量用 trace 中 QA step payload 的 `failed_rule_count`/`failed_rule_ids`;S5 不需要猜 Analyst payload 内部结构。

### 2026-06-07 · Critical Decision:短期轴翻转 + S4/S5 重构(supersede §0 旧表述)

- **触发(用户指令)**:短期(到 6/10)直接目标是字节比赛拿名次;字节标准倾向「工业级、深入落地、可控的 Agent 系统」,要求详细设计优化方案。supersede 旧 §0「赛题维度只是产品做好后的副产物,不是设计轴」——短期改为**用评分 gap 排优先级**,但兑现方式仍是真核心 MVP(延续纠偏红线:不造假 demo)。
- **gap 盘点(调研实测)**:S1-S3 已覆盖可观测/QA 闭环可视/指标/溯源/诚实文案,5 维大半自然达标。剩余唯一**点名级**硬 gap 集中在 35% 同一条:① Schema 三件套(功能树/定价/画像)后端零产出;② QA 是否真验「字段完整/格式一致」且重做有改善(非伪闭环)。
- **决策门收敛**:GATE-2 已决=真做后端(零产出实测,见 §2);GATE-3 已决=撤销(双 intake 刻意设计,FE-008 dropped);GATE-4 新增已决=三件套接 QA 一致性校验(全套)。
- **结构重构**:原 FE-S4「产品语义收尾(选做/赛后)」拆为 **FE-S4 后端**(三件套产出+持久化+migration+/knowledge API+QA 校验)+ **FE-S5 前端**(三件套视图+QA 闭环改善证据+FE-010/FE-015 收尾);S5 硬依赖 S4。FE-009/014/016/018/019/020 降为面向未来 backlog。
- **carryover facts(供 Layer-2,免重新调研)**:后端无 producer(`business.py:20-134` 仅契约);Analyst 持久化模式 `analyst.py:260-321`;迁移 head `0018`;QA `engine.py:439-639` 只读 report/evidence(451-459),docs §7 `selector: pricings[*]` 文档示例未实现,`MAX_QA_REJECTIONS=3`(engine.py:33),现有 qa_rule skills 2 个;预定义合格标准 docs §3.3;前端 `qaClosure.ts:196-200` 基线错位、`failed_rule_count`(engine.py:383)未落 payload。
- **方法论守纪**:本次只更新 Layer-1 总纲(轴/阶段/决策门/问题地图/carryover facts);FE-S4/S5 的 slice(Files/Changes/Verify)等进入各阶段调研代码后再在 Layer-2 展开,不在本文件下沉。

### 2026-06-07 · FE-S3 completed

- 落地刀:FE-S3-A/B/C/D/E 全部完成。Dashboard 和历史行的 running run 现在按 `phase` 进入 plan/live,RunView 仅给进行中软提示;Live 终态不再自动 `replace` 跳报告;Landing 删除 PDF/3分钟/42条/假竞品卡,预览改真实 completed run 数据,空库只显示中性占位;清空全部历史移入危险操作并要求输入确认词;`/audit` 诊断台入口和直链受 `VITE_SHOW_DEBUG_PANELS`/`DEV` 开关控制。
- 结构性修正:二级 plan 预设“列表项已含 phase”与真实代码不符。为避免前端靠 status 猜阶段,后端 `/api/runs` 列表响应补只读派生字段 `phase`,与详情页 `_derive_run_phase` 保持同源。
- 验证:`frontend npm run type-check` passed;`frontend npm run build` passed;容器内 `pytest tests/test_intake_api.py tests/test_plan_api.py -q` passed(11 passed)。
- 产品结论:FE-S3 不做 demo fallback,而是修真实导航、终态控制、诚实文案、危险操作和内部诊断隐藏。

### 2026-06-07 · 方向纠偏(活文档反馈闭环生效)

- 触发:S2 build 后复盘,发现总纲第一性原理设反了——把"给评委答辩验收"当成设计驱动力,泄漏出一串"答辩/验收/demo"措辞,其中 `RunAuditPage.tsx:94` H1"答辩验收台"已印到真实产品 UI。
- 纠正:驱动力改回"成熟可上线产品";赛题 5 维降级为 §6 自检附录(覆盖度核对,不反向排优先级)。
- `/audit` 重定位(两次纠偏收敛):它不是"给评委的验收台",也不是"给用户的分析透明度特性",而是 **debug/admin 诊断视图**——深度可观测(prompt_preview/token/decision/QA 内部)给开发调试和比赛验证,终端用户看不见;现在临时暴露,生产默认隐藏(开关控制,新增 FE-021)。面向用户的轻量信任信号(证据溯源/来源徽章/QA 通过率)留在 `RunView`。代码全保留,只改定位与文案。
- 删除:FE-012(demo fallback 只读演示入口)整条移除,不留 backlog——为演示造假数据兜底是反产品;演示稳健由 FE-011(终态不踹走用户)+ 已有历史列表/最新报告自然达成。
- 新增:FE-021 给 `/audit` 入口加 `VITE_` 开关,生产默认隐藏(归 FE-S3)。
- 落地:重写总纲 §0/§1/§3/§4/§5/§6;同步重写 FE-S2 二级 plan 与审计文档 FE-003/004/011/012/013/017 + 新增 FE-021;清理 `RunAuditPage`/`RunViewPage` 泄漏到 UI 的"答辩验收台/验收视图"文案为中性诊断术语。
- 结论:S1/S2 代码无需返工(溯源/可观测/QA 质控都是真产品价值);跑偏的只是计划叙事与少量 UI 文案。

### 2026-06-07 · FE-S1 completed

- 落地刀:FE-S1-A/B/C/D 全部完成。Trace 类型已补 `llm_calls`/`timeline`;Trace 页 LLM tab 渲染真实调用表;RunView 挂载完整 MetricsPanel;后端 `/metrics` 新增 `source_authority_distribution`;证据抽屉/证据库展示来源权威与脱敏徽章,证据库支持 `source_authority` 筛选。
- 验证:`frontend npm run type-check` passed;`frontend npm run build` passed;容器内 `pytest tests/test_run_metrics.py tests/test_skill_curator_tasks.py -q` passed(10 passed)。
- 结构性修正:FE-S1 不是纯前端刀。为让官方来源占比可量化,补了一个后端只读聚合字段 `source_authority_distribution`;不改变 Agent 主链路和持久化 schema。
- 后续依赖:FE-S2 可以直接消费 S1 的真实 `llm_calls`、完整 metrics、source authority/脱敏信息来做 `/audit` 验收台。

### 2026-06-07 · FE-S2 completed

- 落地刀:FE-S2-A/B/C/D 全部完成。`StepTraceResponse` 已暴露 `rejection_reason`;LLM 调用表抽为 `LlmCallsTable`;新增 `buildQaClosure` 与 `QaClosureSection`;新增 `/app/runs/:runId/audit` 分析透明度视图并从 RunView toolbar 进入。
- 验证:`frontend npm run type-check` passed;`frontend npm run build` passed;容器内 `pytest tests/test_smoke.py::test_step_trace_response_exposes_rejection_reason -q` passed。
- GATE-1 决议已落地:只暴露 QA `rejection_reason`;prompt 全文不暴露,继续使用 `prompt_preview`。这满足用户对结论的可观测/透明度需求,同时避免把完整 prompt/上下文扩大到前端。
- 后续依赖:FE-S3 与本阶段无依赖;FE-S4 若做 Schema/Compare 语义,可复用透明度视图的业务产物区。
- 注:本条目里"验收台"等措辞已在 2026-06-07 纠偏中重定位为"分析透明度视图",见 §7 顶部纠偏条目。

## 8. 明确不做(YAGNI)

- 不为演示/答辩造任何假数据、只读兜底入口或评委专用页(FE-012 已删)。一切以真实产品形态自然演示。
- 不一个执行 plan 解决 FE-001~020;按阶段切二级 plan,fresh context 一刀一刀做。
- 不在本文件写文件级改法 / Verify / build slice;上文行号仅为根因锚点 / carryover facts。
- 不统一双 intake(GATE-3:对话式 Agent 澄清 / 专家直跑是刻意设计);不暴露 prompt 全文(GATE-1 不变,仍 `prompt_preview`)。
- S4 持久化用 MVP 单表 JSONB,不做规范化多表;不改 researcher `extract_structured`(三件套在 Analyst 从 evidence 合成)。
- FE-009/014/016/018/019/020 为上线后产品化,赛后 backlog,不阻塞 6/10。
