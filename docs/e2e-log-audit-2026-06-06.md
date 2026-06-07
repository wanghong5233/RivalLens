# 端到端链路审查记录：run_e279844fd270

## 结论

本次真实 run 能完整走到 `completed`，具备多 Agent 编排、HITL plan pause、并发调研、跨竞品矩阵、Writer 产出、QA 打回重写、最终报告审批、trace 查询等关键能力。按赛题“必须展示 multi-agent 协作和可追溯链路”的最低线，系统已经可演示。

但它还不是“可直接交付业务使用”的成熟状态。主要风险集中在四处：证据质量门槛弱、引用不能证明量化结论、Analyst 结构化结论过薄、Curator 学习门槛误判导致成功 run 不沉淀。最终报告可作为内部草稿，不适合作为无人工复核的老板级选型方案。

## 样本

| 项 | 值 |
|---|---|
| run_id | `run_e279844fd270` |
| 用户问题 | 工业自动化设备销售，30 人销售团队，线下拜访 + 邮件跟单，3-6 个月成交周期，要求下周产出 AI 提效方案 |
| 状态 | `completed` |
| 起止时间 | 2026-06-06 12:34:28 UTC → 12:55:22 UTC |
| 总耗时 | 约 20 分 54 秒 |
| 最终报告 | `report_0f2e4957cc36` |
| 报告长度 | 3574 chars |
| 报告章节 | 5 |
| Evidence | 243 条，10 个竞品，9 个原始维度，179 个去重 URL |
| Trace | 24 steps，6 supervisor decisions，73 LLM calls |

## Agent 链路

| Agent | 结果 | 观察 |
|---|---|---|
| Intake | completed | 一轮完成，正确识别用户角色、场景、无明确竞品名单、需要自动发现。 |
| Planner | completed + pause | 生成 3 个任务并进入人工确认，HITL 链路正常。 |
| Supervisor | completed | 6 次决策，包含发现竞品、批量调研、分析、写作、QA 退回后的重写。 |
| Discovery | completed | 发现 10 个竞品；日志里出现 `cap=8` 但后续仍研究 10 个竞品，观测口径不一致。 |
| Researcher | completed | 10 个 researcher step，243 条 evidence；并发调研能力成立。 |
| Analyst | completed | fallback prompt 成功，但只落 1 条 conclusion；结构化洞察明显不足。 |
| Writer | completed | 写了两版报告；第一版被 QA 打回，第二版通过。 |
| QA | completed | 规则快检 + LLM 语义审查均触发；一次阻塞退回 writer，第二次批准。 |
| Skill Curator | skipped | run completed 但因 `dimension_coverage_rate=0.0` 跳过学习，说明学习门槛/指标口径仍错位。 |

## LLM 调用

| Agent | Slot | Calls | Retry | Fallback | Avg latency | Max latency | Tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| Intake | research | 1 | 0 | 0 | 26.1s | 26.1s | 1787 / 1516 |
| Planner | research | 1 | 0 | 0 | 17.1s | 17.1s | 644 / 1125 |
| Supervisor | research | 5 + guardrail 1 | 0 | 0 | 12.9s | 19.3s | 5942 / 4083 |
| Researcher | research | 50 | 0 | 0 | 7.9s | 17.0s | 63479 / 19790 |
| Researcher | compression | 10 | 0 | 0 | 17.4s | 21.6s | 18358 / 10609 |
| Analyst | summarization | 1 persisted | 2 | 1 | 50.1s | 50.1s | 4063 / 4583 |
| Writer | writer | 2 | 0 | 0 | 84.3s | 119.9s | 14992 / 7152 |
| QA | qa | 2 | 0 | 0 | 25.0s | 26.4s | 14080 / 3239 |

### 异常

| 严重度 | 现象 | 证据 |
|---|---|---|
| P1 | Analyst 大模型调用连续 3 次接近 read timeout 后连接失败，再走 fallback。 | 日志显示 summarization attempt latency 187s/189s/191s，随后 `llm.call.fallback`。 |
| P1 | provider 错误日志暴露真实部署 endpoint id。 | `llm.provider.error` / `fallback_reason` 中出现 `model=ep-...`。这违反 endpoint id 不落日志的安全约束。 |
| P2 | 单次 run 耗时近 21 分钟，其中 analyst retry 放大约 9 分钟。 | run 起止时间 + retry latency。 |
| P2 | 分档路由尚未产生真实质量分层。 | 本次所有真实 LLM 调用仍是同一个豆包 lite 模型；tier catalog 为空时仍回落单 EP。 |

## 证据质量

| 指标 | 值 | 判断 |
|---|---:|---|
| evidence 总数 | 243 | 数量充足。 |
| 竞品覆盖 | 10 | 覆盖足够，但 discovery cap 日志与实际研究数量不一致。 |
| 维度覆盖 | 9 原始维度 | 采集维度丰富，但 analyst 只转成 5 个比较维度。 |
| 缺 URL | 0 | 溯源字段完整。 |
| 短 quote | 0 | quote 基本非空。 |
| 脱敏 | 243/243 | 合规基础线满足。 |
| LinkedIn 源 | 6 | 有登录墙噪声。 |
| 登录页噪声 | 1 | 需要采集质量过滤。 |
| Blog 源 | 131 | 来源偏营销内容，权威性不足。 |

抽样问题：

| 问题 | 示例 |
|---|---|
| 搜索主题和竞品归属漂移 | `Inventive AI` 的 query 抽到 Outreach、Highspot 等泛 B2B 销售工具内容。 |
| 登录墙/无效页面入库 | LinkedIn quote 出现 `Welcome back`、`Continue with Google`。 |
| 表格残片入库 | 部分 quote 是 `---`、空表格、加载组件等低语义文本。 |
| 营销博客占比高 | 大量来源为厂商博客或第三方营销内容，价格、ROI、效率数字可信度不足。 |

## 分析与比较

| 项 | 结果 |
|---|---|
| conclusions | 1 条 |
| conclusion-evidence links | 3 |
| comparison cells | 50 |
| judged cells | 39 |
| ungrounded judged cells | 0 |
| comparison dimensions | 5 |

比较矩阵的 grounding 合同已明显改善：非 `unknown` 的比较 cell 均有 evidence id。问题在于 Analyst 层产出的“总结性结论”过少，只有 1 条，且 competitor_ids 与 claim 表述不完全一致。`analyst.dimension_drops` 记录 `out_of_focus=218`，说明 evidence → analysis dimension 的映射损耗很大。

## 报告质量

最终报告结构：

| Section | Evidence refs | Chars |
|---|---:|---:|
| `scene_matching_degree` | 6 | 526 |
| `efficiency_promotion_potential` | 6 | 429 |
| `implementation_cost` | 5 | 429 |
| `team_adaptation_ease` | 5 | 476 |
| `differentiation` | 4 | 500 |

优点：

| 能力 | 证据 |
|---|---|
| 能贴合用户场景 | 报告围绕 30 人 B2B 工业自动化销售、线下拜访、邮件跟单、3-6 个月周期展开。 |
| 能给出可读建议 | 章节覆盖场景匹配、提效潜力、成本、适配难度、差异化选型。 |
| 能引用 evidence id | 最终报告 5 节均有 evidence refs，总计 26 个引用。 |
| QA 闭环真实触发 | 第一版因语义 QA blocking 被退回 writer，第二版通过。 |

不达标点：

| 严重度 | 问题 | 证据 |
|---|---|---|
| P1 | 量化结论未被引用直接支持。 | 报告写“人均每周节省 1.5 小时”“整体行政性工时下降 28%”“成交周期缩短 12%”，抽查 evidence 只支持“自动化/减少切换/CRM 数据录入”等方向，未直接给出这些数字。 |
| P1 | 价格结论混合公开价、二手评论、定制报价推断。 | Reply.io、Outreach 可找到价格线索；Highspot/Seismic 为定制报价，报告给出 2.7 万-3.2 万美元区间但证据不足。 |
| P2 | 报告短而密，适合草稿，不适合“老板级方案”。 | 3574 chars、5 节，每节约 400-500 字；缺少实施路线表、风险矩阵、推荐优先级表、预算假设表。 |
| P2 | QA 通过不等于 factuality 通过。 | QA 语义审查只确认“引用存在、章节覆盖、无明显编造”，没有校验 claim-evidence entailment。 |

## 字节赛题要求对齐

| 要求 | 当前状态 | 判断 |
|---|---|---|
| 多 Agent 角色清晰 | Intake / Planner / Supervisor / Discovery / Researcher / Analyst / Writer / QA / Curator 均有 trace。 | 达标 |
| DAG / LangGraph 编排可追溯 | 24 steps、6 supervisor decisions、73 LLM calls；trace API 可查询。 | 达标 |
| 结构化消息 / Schema | LLM harness、Pydantic、steps payload、reports JSONB 均工作。 | 达标 |
| 反馈闭环真实触发 | QA blocking → supervisor → writer redo → QA approve。 | 达标 |
| 每条分析结论可溯源 | 报告有 evidence refs，comparison cells 有 grounding；但 conclusions 只有 1 条，且量化 claim 未做 entailment。 | 部分达标 |
| 业务价值 | 能从开放问题自动发现竞品并生成草稿。 | 部分达标 |
| 可运营指标 / 自进化 | Curator 因 dimension coverage 误判跳过，未从成功 run 学习。 | 未达标 |
| 合规脱敏 | evidence 243/243 desensitized。 | 达标 |
| 系统成熟度 | provider retry/fallback、QA redo、trace 均有效；模型分档未真正启用，source quality gate 弱。 | 部分达标 |

## 问题清单

| ID | Priority | Type | Symptom | Evidence | Impact | Next Step |
|---|---|---|---|---|---|---|
| E2E-001 | P1 | Bug | Provider 错误日志泄漏 endpoint id。 | `llm.provider.error` / fallback reason 含 `model=ep-...`。 | 违反 secret/endpoint 日志边界。 | 对 provider error、fallback_reason、llm_calls.error 做 model id redaction。 |
| E2E-002 | P1 | Bug | Curator 在 completed run 后跳过学习。 | `reason=dimension_coverage_rate_below_threshold`, `dimension_coverage_rate=0.0`，但 report_section_coverage=1.0、comparison dimensions=5。 | 成功样本不能进入技能沉淀，S6 闭环失效。 | 修正 curator dimension coverage 口径，至少读 comparison cells / report sections / analyst dimensions 之一。 |
| E2E-003 | P1 | Quality | 报告量化数字缺少直接证据支撑。 | 抽查引用只支持方向，不支持 28%、12%、1.5h 等精确数字。 | 业务报告可信度不足。 | 增加 claim-evidence entailment QA；数字 claim 必须引用含同数字或可计算字段的 evidence，否则降级为区间/定性。 |
| E2E-004 | P0 | Quality | Analyst 结论过薄，Battlecard 与全局 ComparePage 几乎无内容。 | `conclusions=1`、`conclusion_links=3`，但 comparison cells=50；`BattlecardGrid` 与 `/app/compare` 依赖 `/conclusions`。 | 报告正文丰富，但结构化产品视图稀疏；RunView 的 comparison matrix 因使用 `/comparisons` 不受该问题影响。 | Analyst 每个 focus dimension 至少输出 1 条 conclusion；把 comparison summary 结构化成 conclusions；复验 Battlecard 与全局 ComparePage。 |
| E2E-005 | P0 | Reliability | Analyst summarization retry 放大耗时。 | 3 次约 187-191s 失败后 fallback，run 总耗时增加约 9 分钟。 | 21 分钟端到端耗时中 analyst 长 retry 占比过高，演示和真实使用都会卡住。 | 为 long-slot 加 retry budget / circuit breaker；同一 connection error 连续发生时直接 fallback 或切备用模型。 |
| E2E-006 | P2 | Data Quality | Source noise 入库。 | LinkedIn 登录页、加载组件、表格残片、营销博客占比高。 | 报告引用看似完整但有效性不稳。 | Collector/extract 增加 source quality gate：登录墙、加载组件、低语义 quote、非目标竞品页面降权或过滤。 |
| E2E-007 | P2 | Observability | Discovery cap 日志与实际研究数量不一致。 | 日志 `cap=8 dropped Highspot/Outreach`，但 evidence 与 researcher steps 覆盖 10 个竞品。 | Trace 解释不一致，影响答辩复盘。 | 对 reconcile 后的实际 competitor set 写统一事件，避免多个口径并存。 |
| E2E-008 | P0 | Maturity | 模型分档尚未产生真实质量差异。 | 所有 slot 仍走同一豆包 lite 模型；`DOUBAO_MODEL_STRONG` 为空，Analyst 没有真实 strong 路由。 | Writer/Analyst 质量和延迟都被 lite 模型上限拖住，E2E-004/E2E-005 会反复出现。 | 配置 strong/balanced/fast 真实模型；用同一 run replay 对比报告质量与延迟。 |
| E2E-009 | P1 | Quality | Writer 把内部 ID 泄进报告正文。 | 最终报告 `ev_` 命中 52 次、`[ev_]` 命中 0 次、`Evidence:` 行 5 行、`insight_` 命中 4 次；前端 linkify 只识别 `[ev_xxx]`。 | 报告展示裸 evidence/insight id，降低专业度，也破坏 citation 交互。 | Writer prompt/schema/serializer 统一 citation 格式；禁止裸 `ev_xxx` / `insight_x`；脚注由前端渲染层负责。 |
| E2E-010 | P1 | Validation | QA 章节完整性判定可能不稳定。 | 第一次 QA 写“5 out of 9 mandatory target sections”并打回；两版 report 均为 5 sections；第二次 `rule_qa_semantic_audit` passed。 | QA 可能把 LLM 自生成规格当硬门槛，或二次审查放宽，导致 pass gate 不可解释。 | 固定同一 report payload 重跑 QA 3 次；显式定义 required sections 来源；禁止 QA 自行发明章节数量。 |

## 是否可以作为最终演示

| 场景 | 判断 |
|---|---|
| 技术演示 | 可以。该 run 展示了 agentic planning、自动发现、批量调研、分析、写作、QA 打回、trace、报告与 evidence。 |
| 赛题答辩 | 可以，但需要主动说明“当前报告是 AI 草稿，系统已经暴露并记录 quality gates，下一步加强 factuality gate”。 |
| 真实业务使用 | 不建议直接上线。需要先修 E2E-004 / E2E-005 / E2E-008 / E2E-009，再处理 E2E-001 / E2E-002 / E2E-003 / E2E-010。 |
| 老板级决策报告 | 不达标。可作为初稿和调研入口，不能作为无人工复核的采购建议。 |

## 外部验收交叉验证

外部 LLM 对同一 run 的验收结论已复核。结论大体一致，但部分表述需要收窄。

| 外部结论 | 复核结果 | 证据 | 处置 |
|---|---|---|---|
| Analyst 阶段约 11 分钟卡死，演示级致命。 | 成立，按 P0 处理。 | summarization 连续 3 次 provider connection error，每次约 187-192s；fallback 后才落 analyst step。 | 合并到 E2E-005，优先级从 P2 升为 P0。 |
| `DOUBAO_MODEL_STRONG` 为空，Analyst 实际仍用 lite。 | 成立。 | 本 run 所有真实 LLM 调用 model 均为同一个豆包 lite；tier routing 架构就绪但 catalog 未配置真实 strong。 | 合并到 E2E-008，优先级从 P2 升为 P0。 |
| conclusions 只有 1 条，Battlecard 几乎空。 | 成立。 | `conclusions=1`、`conclusion_evidence=3`；`BattlecardGrid` 只用 `/conclusions`。 | 合并到 E2E-004，优先级从 P1 升为 P0。 |
| ComparePage 也依赖 conclusions，演示时会空。 | 部分成立。 | `/app/compare` 依赖 `/conclusions`；但 RunView 内的 `ComparisonMatrix` 使用 `/comparisons`，本 run 有 50 cells，不会空。 | 文档按“Battlecard 与全局 ComparePage 受影响，RunView comparison 不受影响”记录。 |
| Writer 把裸 `ev_xxx` / `insight_1` 泄进报告正文。 | 成立。 | 最终报告 `ev_` 命中 52 次，`[ev_]` 命中 0 次，`Evidence:` 行 5 行，`insight_` 命中 4 次；前端 linkify regex 只识别 `[ev_xxx]`。 | 新增 E2E-009。 |
| QA 可能伪通过：第一次说 9 个必需章节，第二次仍 5 个章节却通过。 | 待确认，风险成立。 | 两版报告都是 5 sections；第一次 semantic finding 写“5 out of 9 mandatory target sections”，第二次 `rule_qa_semantic_audit` passed。无法仅凭单 run 判断是 QA 放宽还是第一次 QA 过度约束。 | 新增 E2E-010，要求复验稳定性。 |
| 可观测性是强项。 | 成立。 | step、decision、llm_calls、structured logs 均能串起 run_id/node；异常和 fallback 可回放。 | 保留为赛题达标项。 |

环境备注：

| 项 | 状态 | 判断 |
|---|---|---|
| `.cursor/hooks/safety_guard.py` Windows 中文路径问题 | 已由外部核查临时修复：stdin 改为 UTF-8 bytes decode；`beforeShellExecution.failClosed=false`。 | 与本 run 质量无关，属于本地开发拦路障。是否保留/提交需要单独评审；L1 fail-open 可接受的前提是 L2 git hook 和 L3 服务端扫描保持有效。 |

## 下一轮建议

优先拆 7 个 Layer-2 plan：

| Plan | 目标 | 验收 |
|---|---|---|
| `e2e_s7_analyst_stability_and_model_route` | 治理 analyst 超时、同参数无效重试、strong 模型未生效。 | 本 run replay：analyst 不发生 3 次长 retry；conclusions ≥ focus dimensions；summarization 使用 strong 或显式 fallback policy。 |
| `e2e_s8_secret_safe_observability` | 去除日志/DB error 中真实 endpoint id。 | grep 日志和 `llm_calls.error/fallback_reason` 不出现 `ep-...`。 |
| `e2e_s9_curator_metric_alignment` | 修正 curator coverage 口径，让高质量 completed run 可进入候选生成。 | 本 run replay 后 curator 不因 dimension coverage=0 跳过。 |
| `e2e_s10_claim_evidence_entailment` | 对数字 claim 与强判断增加 evidence entailment gate。 | 含 unsupported 数字的报告被 QA 打回或降级。 |
| `e2e_s11_source_quality_gate` | 过滤登录墙、加载组件、低语义 quote、竞品错配来源。 | LinkedIn login/noise source 不进入 final evidence；抽样 quote 可读且指向目标竞品。 |
| `e2e_s12_report_rendering_hygiene` | Writer 输出中禁止裸 `ev_xxx` / `insight_x` 和脚注噪声，统一可点击 citation。 | final markdown 中 `ev_` 只以 `[ev_xxx]` 或前端可识别 AST 形式出现；无 `Insights: insight_1` 裸文本。 |
| `e2e_s13_qa_consistency_replay` | 验证 QA 章节完整性判定是否稳定。 | 同一 report payload 重跑 QA 3 次，required section 判断一致；若“9 必需章节”来自 prompt 误读，修 prompt/contract。 |
