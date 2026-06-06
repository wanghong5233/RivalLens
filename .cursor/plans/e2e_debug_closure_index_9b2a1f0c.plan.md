---
name: E2E Debug 收尾总纲
overview: 独立于 S0-S5 系统重构总纲的端到端 debug 收尾一级 plan。编号使用 E2E-S* 前缀,避免与其他总纲的 S1/S2 混淆。阶段编号按依赖/执行拓扑序,不按问题发现顺序。一级 todo 只对应已切好的二级 plan;问题证据留在正文,二级 plan 进入阶段前再详细调研代码并展开 Files / Changes / Verify / Done-when。
todos:
  - id: E2E-S1
    content: "E2E-S1 可观测卫生(enabler,先行)[已完成]:logger 压制 readability/urllib3 噪声(固定 WARNING)、supervisor happy-path dimension_source 扩 llm_tool_output 消除仪表盲区。二级 plan `e2e_s1_observability_hygiene_7d78fe36.plan.md`,docker 定向 14 passed + 容器真实进程 DEBUG 噪声压制验证。"
    status: completed
  - id: E2E-S2
    content: "E2E-S2 状态/API 合同[已完成]:state 层统一 spread_without_accumulators,修 supervisor/intake/planner 回吐 operator.add 字段导致的 competitors 膨胀;全局 JSON 响应声明 charset=utf-8。二级 plan `e2e_s2_state_api_contract_7458107a.plan.md`,docker 定向 30 passed;真实 run `run_3af895f2ad79` 验证 competitors 2/2 且 trace content-type UTF-8。"
    status: completed
  - id: E2E-S3
    content: "E2E-S3 证据采集与质量[已完成]:fetch_url 改 Tavily Extract advanced+质量门(删 parse_page channel/action);dimension 沿 tool_exec/observation args 继承并约束 focus 枚举;EvidenceRecord 单路径去重(正文 hash key)+ analyst/writer 按竞品×维度分层选证;S3-4 补 researcher coverage guard、动态 turn 预算下限、focus 名 <=32 约束、dimension coverage metrics。二级 plan `e2e_s3_evidence_quality_29d03999.plan.md`,S3 总定向回归 78 passed;真实 run `run_4c34a4133121` 复验正文有效、每竞品 3 个维度、dimension drops 0、dimension_coverage_rate=0.75、focus 名无截断、报告引用 21 个唯一 evidence id。"
    status: completed
  - id: E2E-S4
    content: "E2E-S4 报告与 QA 质量门[已完成]:deep report_depth 接入 writer/QA/direct run;确定性 deep blocking 结构门(总长/section 覆盖/每段长度/每段引用);QA semantic judge 维度化 rubric + 全文/分层 evidence;promoted DSL 支持 section_id_in、parse_error blocking、内置 rule 迁移;metrics 暴露 report_char_count/report_section_count/report_depth/report_section_coverage_rate。二级 plan `e2e_s4_report_qa_gates_5e63b2de.plan.md`,docker 定向 83 passed;真实 run `run_9ac27e44aea8` 先拒 2 次再通过,最终 deep 报告 6439 字/4 段/section coverage 1.0/parse_error=0。"
    status: completed
  - id: E2E-S5
    content: "E2E-S5 LLM 稳定性成熟化[已完成]:provider 错误分类+异常元数据、Retry-After/full-jitter 成熟重试、fallback retry、per-provider TPM token bucket、retry_count 持久化、provider_error/retry metrics、配置/env 成熟化。二级 plan `e2e_s5_llm_稳定性成熟化_e9f8be1f.plan.md`,docker 定向 42 passed;真实 run `run_287bcb0d6f80` completed,17 LLM calls/44465 tokens/llm_provider_error_count=0/llm_retry_total=0。"
    status: completed
  - id: E2E-S6
    content: "E2E-S6 自进化 curator[已完成]:Gate-1 只从成功 run 学(run status + metrics 阈值,低质量/degraded skip,发 curator.skipped);Gate-2 入库前确定性校验 qa_rule DSL,坏 rule approve 返回 422 且不落盘。二级 plan `e2e_s6_curator_样本质量门槛_272ed3ff.plan.md`,docker 定向 25 passed;真实路径复用 `run_287bcb0d6f80` 手动触发 curator,候选 delta=3。"
    status: completed
isProject: false
---

# E2E Debug 收尾总纲

最后更新: 2026-06-06

## 0. 定位

这是新一轮“端到端 debug 收尾”的一级 plan,不是 `系统纠偏总纲` 的 S6。编号规则:

| 层级 | 编号 | 示例 | 含义 |
|---|---|---|---|
| 计划族 | `E2E` | `E2E Debug 收尾总纲` | 与 S0-S5 系统重构、后续其他总纲隔离 |
| 一级阶段 | `E2E-S1` | `E2E-S1 可观测卫生` | 一个 todo = 一个二级 plan,**按依赖拓扑序编号** |
| 问题条目 | `E2E-S1-1` | `E2E-S1-1 日志降噪` | 一级阶段内的问题地图 |
| 二级 slice | `E2E-S1-A` | 二级 plan 内定义 | 进入阶段后调研代码再切 |

阶段编号 = 依赖/执行顺序,不是问题发现顺序。Layer-1 只保留问题地图、依赖阶段、证据锚点。不要在本文件写文件级改法、Verify、build slice。进入某阶段时再创建二级 plan,并按 `Files / Changes / Verify / Done-when` 展开。

## 1. 证据锚点

| 项 | 值 |
|---|---|
| run_id | `run_c039c44cb009` |
| request_id | `req_934141ed236240faa3a562dd7de4c991` |
| 时间窗口 | 2026-06-05 18:18:39Z - 18:24:01Z |
| 请求 | TRAE 对标 Cursor / GitHub Copilot / Windsurf / 通义灵码 / 文心 Comate / 豆包 AI 编程助手, deep 报告 |
| 终态 | `completed` |
| 总耗时 | 296s |
| LLM | 21 calls, 56567 tokens, p50 latency 15445ms |
| Evidence | 95 条 / 41 唯一 URL, dimension 94 null + 1 product_positioning, article 93 / public_review 2 |
| Report | DB markdown 仅 2086 字符 / 5 段(每段 170-260 字), deep 档 |
| QA | 1 次, rejected=0, promoted enforced=1 / parse_error=1, 中文定价标题未命中 |
| DB | 同窗口无 PostgreSQL ERROR/WARNING |
| 复测·抽取 | readability 抓页脚/导航;实测 Tavily Extract advanced 同 URL: 通义灵码 54→1789 字、Comate 标题→25435 字真实正文 |
| 复测·火山搜索 | `/responses` + `tools:[{"type":"web_search"}]` 现 DOUBAO key 可调通, 需 `tool_choice:"required"` 强制; lite 模型自造查询跑偏, 返回带 `url_citation`(title/url/site_name/publish_time) |
| 复测·日志噪声 | 单 run readability/urllib3 数百行 DOM 调试输出(`Removing unlikely candidate`/`Branch...link density`/`Top 5`)直冲 stdout |
| 复验·S3 | run `run_7e6cfe43a741` 暴露 S3-4:正文/去重/missing 已达标,但维度全塌缩 `core_coding_features` 且 focus 名截断;补第四刀后 run `run_4c34a4133121` 通过核心阈值:63 evidence、每竞品 3 个维度、dimension drops 0、`dimension_coverage_rate=0.75`、focus 名无 32 截断、报告引用 21 个唯一 evidence id |

## 2. 一级阶段(按依赖拓扑序)

| 阶段 | 二级 plan | 范围 | 包含问题 | 依赖/进入条件 |
|---|---|---|---|---|
| E2E-S1 | `e2e_s1_observability_hygiene_*.plan.md` | 日志卫生、仪表盲区 | E2E-S1-1, E2E-S1-2 | 无依赖,enabler 先行:净化 stdout + 修仪表是后续调试绿色基线 |
| E2E-S2 | `e2e_s2_state_api_contract_*.plan.md` | 状态污染、API 编码合同 | E2E-S2-1, E2E-S2-2 | 无硬依赖;competitors 膨胀污染下游 prompt,状态正确性在质量主线前修 |
| E2E-S3 | `e2e_s3_evidence_quality_*.plan.md` | 抽取质量、维度、去重利用率、维度覆盖深度 | E2E-S3-1, E2E-S3-2, E2E-S3-3, E2E-S3-4 | 报告质量硬依赖根;内部有序 抽取→维度→去重→维度覆盖深度(S3-4 补刀) |
| E2E-S4 | `e2e_s4_report_qa_gates_*.plan.md` | Report depth、QA gates、promoted rules | E2E-S4-1, E2E-S4-2 | 依赖 E2E-S3 证据质量结论 |
| E2E-S5 | `e2e_s5_llm_稳定性成熟化_e9f8be1f.plan.md` | provider retry/限流、配置参数成熟度 | E2E-S5-1, E2E-S5-2 | 已完成;稳定复跑验证 S3/S4 |
| E2E-S6 | `e2e_s6_curator_样本质量门槛_272ed3ff.plan.md` | Skill curator 候选门槛 | E2E-S6-1 | 已完成;最后一层防止坏样本继续扩散 |

> 编号原则:阶段号 = 依赖拓扑序,不是发现顺序。硬依赖链 `抽取(S3-1) → 维度(S3-2)/去重(S3-3) → 报告/QA(S4) → curator(S6)`;enabler(日志降噪 S1)最先,curator(S6)最后。独立项(状态/API S2、provider/config S5)按"是否污染下游 / 是否影响复跑验证"插入链中。前一版把后发现的日志/配置排成尾号 S5 是反模式(发现顺序≠依赖顺序),本版已纠正。

## 3. 问题地图

| ID | type | 问题 | priority | status | 当前阶段动作 |
|---|---|---|---|---|---|
| E2E-S1-1 | Bug | readability/urllib3 日志噪声未压制 | P2 | fixed | 已落地:urllib3 入 HTTP 清单 + readability 固定 WARNING;容器 DEBUG 实测压制 |
| E2E-S1-2 | Bug | supervisor `dimension_source` happy-path 恒 null | P3 | fixed | 已落地:FocusDimensionSource 扩 `llm_tool_output`,维度型决策赋值,非维度型 None(文档化) |
| E2E-S2-1 | Bug | `run.competitors` 重复膨胀(48=6×8) | P1 | investigating | 在 E2E-S2 二级 plan 中定位 reducer 写入点 |
| E2E-S2-2 | Bug | API JSON 未显式 UTF-8 | P3 | planned | 在 E2E-S2 二级 plan 中补 header/客户端回归 |
| E2E-S3-1 | Bug | fetch_url 抽取页脚/导航垃圾 | P1 | fixed | 已验(run_7e6cfe43a741):Tavily Extract advanced + 正文质量门, 真实 deep run 正文为含具体数字的真实产品/定价正文, 无页脚 |
| E2E-S3-2 | Bug | Evidence 维度几乎全丢(94/95 null) | P1 | fixed | missing 已修;S3-4 后真实 run `run_4c34a4133121` 每竞品覆盖 3 个维度且 drops=0 |
| E2E-S3-3 | Bug | Evidence URL 大量重复且利用率低 | P1 | fixed | 已验(run_7e6cfe43a741):单路径去重 + 正文 hash key + 分层选证, URL 15/15 去重、报告引用 15/15 全覆盖(原 86 unused 归零) |
| E2E-S3-4 | Bug | 维度多样性塌缩 + supervisor focus 名 32 截断 + 无 dimension coverage 指标 | P2 | fixed | 已落地:coverage guard + 动态 turn 预算下限 + focus 名 <=32 prompt 约束 + metrics dimension coverage;真实 run `run_4c34a4133121` 验收通过。S4 review 暴露 follow-up(fetch_url/extract_structured)dimension 回退 pending[0]=下一维度的错标,supervisor 层(agent_outputs_pipeline fallback_to_pending=False)+ researcher 层(_effective_action_dimension follow-up 优先 _recent_search_dimension)均已补修,定向 58 passed |
| E2E-S4-1 | Improvement | deep 报告质量门缺失 | P1 | fixed | 已落地:report_depth 接入 direct run/writer/QA,deep 结构门 blocking + semantic judge 维度化;真实 run `run_9ac27e44aea8` 先拒 2 次再生成 6439 字 deep 报告通过 |
| E2E-S4-2 | Bug | promoted QA rule DSL 与触发条件失效 | P1 | fixed | 已落地:section_id_in 中文友好触发、parse_error blocking 可观测、内置 QA rule 迁移为支持算子;定向 promoted/golden/smoke 覆盖 |
| E2E-S5-1 | Bug | 429 TPM retry 语义不一致 + 无 TPM 退避 | P2 | fixed | 已落地:provider 分类元数据 + Retry-After/full-jitter retry + per-provider TPM token bucket;定向 42 passed,真实 run `run_287bcb0d6f80` 无 429/retry |
| E2E-S5-2 | Improvement | 配置/参数成熟度不足 | P2 | fixed | 已落地:LLM retry/backoff/TPM/provider/base-url config 与 `.env.example`;retry_count/provider_error metrics 暴露 |
| E2E-S6-1 | Improvement | skill curator 低质量样本扩散 | P2 | fixed | 已落地:源头 run 质量门槛 + promote 前 qa_rule DSL 确定性校验;定向 25 passed,真实达标 run 仍生成候选 |

## 4. E2E-S1 可观测卫生(enabler)

### E2E-S1-1 readability/urllib3 日志噪声未压制

type: Bug  
status: fixed  
priority: P2

> 已落地(`e2e_s1_observability_hygiene_7d78fe36.plan.md`):`_HTTP_CLIENT_LOGGER_NAMES` 加 `urllib3`、新增 `_NOISY_THIRD_PARTY_LOGGER_NAMES=("readability",)` 固定 WARNING;容器真实进程 LOG_LEVEL=DEBUG 实测两者 debug 被压制、structlog info 仍可见。

#### Symptom

单次 run 内 readability-lxml 与 urllib3 把数百行 DOM 解析调试输出直冲 stdout,淹没 structlog JSON 事件,debug 时几乎无法阅读。

#### Evidence

```text
readability: "Removing unlikely candidate ..." / "Branch ... link density ..." / "Top 5 : ..." / "ruthless removal did not work"
urllib3: "Starting new HTTPS connection (1): api.tavily.com:443" / 'POST /search HTTP/1.1" 200'
utils/logger.py: _HTTP_CLIENT_LOGGER_NAMES = (openai, httpx, httpcore, httpcore.http11, httpcore.connection)  # 缺 readability / urllib3
dev LOG_LEVEL=DEBUG → basicConfig 放行二者 debug
```

#### Root Cause

已确证:第三方 logger 压制清单不全。S2 可观测合同只覆盖 LLM/HTTP 客户端,漏了工具层 readability 与 Tavily 走的 urllib3;dev DEBUG 下二者经 root logger 全量输出。

#### DoD

- `_HTTP_CLIENT_LOGGER_NAMES` 补 `readability`、`urllib3`(及 requests),设为 WARNING。
- 一次 deep run 的 stdout 只剩 structlog JSON + 必要 access log,无 DOM 解析行。

#### Next Step

进入 E2E-S1 二级 plan 时随 S1-2 一起处理(同属 logger/observability)。

### E2E-S1-2 supervisor `dimension_source` 仪表全 null

type: Bug  
status: fixed  
priority: P3

#### Symptom

本轮所有 `supervisor.decision` 的 `dimension_source: null`,S4b 引入的维度来源观测在真实 run 未被填充,无法判断维度推断链(plan task > intake > hints > default)是否生效。

#### Root Cause

已确证:`decision_dimension_source` 初值 None,只在 QA 驱动 redo 与 LLM 解析失败走 `_fallback_decision` 两条路径赋值;正常 happy path(`harness_result.value is not None` → `_decision_from_tool_output`)维度直接来自 LLM `tool_args`,不走 fallback 链,故恒 None。`FocusDimensionSource` 旧枚举只表达 fallback 来源,无法描述 LLM 直选。

#### Fix

`FocusDimensionSource` 扩 `llm_tool_output`;happy-path 对维度型工具(`_DIMENSIONAL_SUPERVISOR_TOOLS`)赋 `llm_tool_output`,与 QA 分支共用同一工具集合;非维度型(DiscoverCompetitors/Finalize/max-iter forced)保持 None 为预期并文档化。字段名不变,对 SSE/前端纯 additive。

#### DoD(达成)

- 维度型 decision 的 `dimension_source` 稳定可读(`upstream_task|intake|hints|default|llm_tool_output`);非维度型为 null 且有文档解释。单测 `test_supervisor_batch.py` 覆盖 happy-path 非空 + discovery 为 None。

## 5. E2E-S2 状态/API 合同

### E2E-S2-1 `run.competitors` 重复膨胀

type: Bug  
status: investigating  
priority: P1

#### Symptom

用户显式给出 6 个竞品,最终 `/api/runs/{id}/trace` 的 `run.competitors` 变成 48 条,每个竞品重复 8 次。

#### Repro

1. 打开 `GET /api/runs/run_c039c44cb009/trace`。
2. 读取 `run.competitors`。
3. 统计长度和去重长度。

#### Evidence

```text
competitors_len=48
competitors_unique=['Cursor','GitHub Copilot','Windsurf','通义灵码','文心 Comate','豆包 AI 编程助手']
backend/app/agents/state.py: competitors: Annotated[list[str], operator.add]
```

#### Impact

UI 展示污染;supervisor / analyst / writer prompt 中 competitors 列表变长(污染下游质量,故排在质量主线前修);后续 pending competitor 判断可能被重复状态干扰。

#### Hypotheses

- H1: 某个 graph node 返回完整 `state.competitors`,被 `operator.add` 当 delta 追加。
- H2: checkpointer resume 后的 state snapshot 被再次作为 node output 合并。
- H3: final persistence 把 reducer 后的重复状态原样写回 `runs.competitors`。

#### Open Questions

- planner_generate / planner_wait 之外是否还有 node 返回完整 state?
- `Send("researcher", {...})` 并行返回时是否把 reducer state 合并多次?

#### Root Cause

未收敛。

#### DoD

- 同一 run 结束后 `len(run.competitors)==len(unique(run.competitors))`。
- 计划确认、reset、resume、follow-up 后均不重复。
- 新增 regression 覆盖 `operator.add` 字段只返回 delta。

#### Next Step

补证据:进入 E2E-S2 二级 plan 后定位第一个重复写入节点。

### E2E-S2-2 API JSON 未显式 UTF-8

type: Bug  
status: planned  
priority: P3

#### Symptom

PowerShell `Invoke-RestMethod` 读取 `/api/runs/{id}/trace` 和 `/report` 时中文出现 mojibake。Python 按 UTF-8 decode 同一响应正常。

#### Evidence

```text
PowerShell title=å­èè·³å¨TRAE...
curl header: content-type: application/json
Python utf-8 decode: title=字节跳动TRAE AIGC编程助手竞品对标与战略投入方向高层汇报报告
```

#### Root Cause

响应 header 未显式声明 charset;客户端推断不一致。

#### DoD

- `/report`、`/trace`、`/evidence` 响应 header 明示 UTF-8 或客户端回归稳定。
- Windows PowerShell 与 Python 两条路径中文一致。

#### Next Step

进入 E2E-S2 二级 plan 时一起处理。

## 6. E2E-S3 证据采集与质量

> 内部依赖序:抽取(S3-1)是上游 → 维度(S3-2)、去重(S3-3)在干净正文之上才有意义。

### E2E-S3-1 fetch_url 抽取页脚/导航垃圾

type: Bug  
status: root-caused  
priority: P1

#### Symptom

researcher 第二跳 `fetch_url` 频繁 `success:true` 却抽到无效正文:通义灵码=`© 2009- Copyright by Alibaba Cloud`、Windsurf=`MCP Server\nSearch channels...`(插件导航)、文心=仅标题。垃圾正文回流到 analyst/writer,是报告质量塌方的上游。

#### Evidence

```text
parse_page.py 用 readability-lxml(Document(html).summary)自研抽取
fetch_url 通义灵码 snippet="© 2009- Copyright by Alibaba Cloud All rights reserved"
fetch_url Windsurf snippet="MCP Server Search channels and messages..."
readability 日志: "ruthless removal did not work" / "Returning raw html"
search_web.py:49-50 仅用 search_depth="basic" + include_raw_content=False(只取短 snippet)
复测 Tavily Extract advanced: 通义灵码 54→1789 字真实产品正文; Comate 标题→25435 字
```

#### Root Cause

已确证:抽取链路用错工具。Tavily 只取最浅 snippet,真正正文交给自研 readability,而 readability 在 JS/SPA 与中文站点退化为页脚/导航/原始 HTML。Tavily search 本身质量正常,瓶颈在自研抽取这一跳。

#### Decision(实测支撑)

- 首选:删自研 readability 抽取,改用 **Tavily Extract API**(`extract_depth="advanced"` + `query`/`chunks_per_source`),实测剥离样板、返回干净正文,现有 key 即用、零额外配置。
- 备选(独立调研,不阻塞本修复):**火山方舟联网搜索** `/responses` + `tools:[{"type":"web_search"}]`,现有 DOUBAO key 可调通且返回 `url_citation`(带 publish_time,溯源更强),但需 `tool_choice:"required"` 强制、lite 模型自造查询会跑偏,需配更强模型并自控查询;新旧并存验 parity 后再决定是否替换 search_web。

#### DoD

- fetch/extract 返回正文通过最小有效性校验(长度/正文占比/非纯导航),不达标显式标记而非 `success:true`。
- 同 run target competitor 的 evidence 正文不再以页脚/导航为主。
- 抽取工具切换有 parity 对照(旧 readability 兜底到新抽取稳定再撤)。

#### Next Step

进入 E2E-S3 二级 plan 时,先落 Tavily Extract 替换并加正文有效性校验;火山搜索另立调研 slice。

### E2E-S3-2 Evidence 维度几乎全丢

type: Bug  
status: root-caused  
priority: P1

#### Symptom

Researcher 收集 95 条 evidence,analyst 阶段 94 条因 `dimension=missing` 被统计为 dropped。分析无法按用户要求的产品定位、定价、企业版能力、中外市场差异建立证据矩阵。

#### Evidence

```text
researcher Cursor dropped_dimensions={"count":12,"reasons":{"missing":7,"out_of_focus":5}}
researcher GitHub Copilot dropped_dimensions={"count":20,"reasons":{"missing":15,"out_of_focus":5}}
analyst dropped_dimensions={"count":94,"reasons":{"missing":94}}
metadata_dimension_counts={"missing":94,"product_positioning":1}
```

#### Impact

报告只能做泛化总结,不能稳定回答按维度的横向对标。当前 `coverage_rate=1.0` 掩盖维度覆盖失败。

#### Hypotheses

- H1: researcher tool observation snippets 没有继承 tool args 的 normalized dimension。
- H2: LLM 输出 `product_positioning_pricing_stra` 这类越界维度,归一化后被 drop。
- H3: analyst allowed dimensions 和 researcher focus dimensions 命名不一致。

#### Root Cause

已确证(本轮日志):两条并存。
1. `missing` 主因 — fetch_url 第二跳产出的 evidence 没有继承 search_web 时的 dimension,绝大多数 evidence 落 `dimension=null` → researcher/analyst 统计为 `missing`(analyst 94/95)。
2. `out_of_focus` 次因 — researcher 工具未把 dimension 约束成 focus 枚举 `(feature/pricing/user_feedback)`,LLM 自由生成复合词 `product_positioning_pricing_strategy`,slugify+截断成 32 字符 `product_positioning_pricing_stra`,归一后 ∉ focus → drop。

修复方向:① researcher 工具 schema/prompt 把 dimension 限定为 focus 枚举(或显式 `other`);② evidence 沿调用链继承当前 dimension,fetch_url 不丢上游维度。

#### DoD

- 每个 target competitor 至少覆盖 3 个 focus dimensions。
- `analyst.dimension_drops.count / evidence_count_total < 0.2`。
- metrics 增加 dimension coverage,不能只报 competitor coverage。

#### Next Step

补证据:进入 E2E-S3 二级 plan 后调研 researcher observation -> EvidenceRecord.span 的 dimension 传递链。

### E2E-S3-3 Evidence 重复与利用率低

type: Bug  
status: investigating  
priority: P1

#### Symptom

本次 run 有 95 条 evidence,但报告只引用 9 个唯一 evidence id;URL 重复组 41 个,重复行 54 条。

#### Evidence

```text
used_refs_count=18 unique=9
unused_evidence=86
duplicate_url_groups=41 duplicate_rows=54
top duplicate: https://www.digitalapplied.com/blog/cursor-ai-2b-revenue-enterprise-coding-market-leader x4
top duplicate: https://comate.baidu.com/zh x4
```

#### Impact

token 被重复 evidence 消耗;writer 只看到 `evidence_briefs[-24:]`;QA 只看尾部 evidence,大量检索成本没有转化为报告质量。

#### Hypotheses

- H1: dedupe 只在单个 researcher step 内生效,不跨 step / URL / title 去重。
- H2: dedupe key 使用 `quote[:80] + url`,同 URL 不同 snippet 会重复入库。
- H3: writer 使用尾部截断而非按 section/dimension/competitor 选证据。

#### Root Cause

未收敛。

#### DoD

- 同 run 内 `(competitor_id, source_url)` 重复行有明确合并或解释。
- report unique evidence refs / evidence_count_total 达到阈值,或 metrics 标记低利用。
- writer evidence brief 选择按 target_sections 覆盖,不再简单取最后 N 条。

#### Next Step

补证据:进入 E2E-S3 二级 plan 后为 evidence build 增加统计测试。

## 7. E2E-S4 报告与 QA 质量门

### E2E-S4-1 deep 报告质量门缺失

type: Improvement  
status: investigating  
priority: P1

#### Current

请求 `report_depth=deep`,最终报告 5 个 section,每段正文约 170-260 中文字符。QA semantic 通过,但没有检查报告深度、维度覆盖、引用支撑强度、竞品矩阵完整性。

#### Limitation

QA 当前主要证明结构存在和引用 id 存在,不证明引用支撑结论。QA semantic prompt 只含 `report_markdown[:600]` 和 `evidence_briefs[-20:]`,无法审完整报告。

#### Trigger Condition

deep 报告、面向高层决策、用户显式要求多竞品多维度对标时触发。

#### DoD

- deep 报告低于长度/覆盖/证据支撑阈值时 QA rejection 或 degraded。
- `/metrics` 暴露 report_depth_quality 字段。
- golden case 固化本次样例,避免短报告再次通过。

#### Next Step

补证据:进入 E2E-S4 二级 plan 后定义最小质量 rubric,把本次 report 作为 failing baseline。

### E2E-S4-2 promoted QA rule DSL 与触发条件失效

type: Bug  
status: planned  
priority: P1

#### Symptom

本次 run 加载 2 条 promoted QA rule,但 1 条 parse error,另 1 条未命中中文定价标题。QA 仍 approved。

#### Evidence

```text
qa.fast_path promoted_qa_rule_ids=["evidence_must_cite_source","pricing_must_have_tier"]
qa.fast_path promoted_qa_enforced_count=1 promoted_qa_parse_error_count=1
evidence-must-cite-source uses require.section_has_evidence_refs=true
parser supports evidence_refs_count_gte / section_content_min_chars / has_evidence_with
pricing rule when.section_title_contains=["Pricing"]
report title="定价模式基准对标"
```

#### Root Cause

现有 promoted skill DSL 与当前 parser schema 不一致;定价规则触发条件依赖英文标题。

#### DoD

- 两个内置 promoted QA skills parse_error=0。
- 定价规则能命中中文 section 或 section_id。
- 增加 regression:中文定价 section 无具体 tier 时不能静默 approved。

#### Next Step

进入 E2E-S4 二级 plan 时处理。

## 8. E2E-S5 provider 稳定性与配置成熟度

### E2E-S5-1 LLM 429 retryable 语义不一致

type: Bug  
status: root-caused  
priority: P2

#### Symptom

Analyst 调用遭遇 Doubao TPM 429。provider 日志标 `retryable=false`,client 仍执行 `llm.call.retry` 两次,最终第三次成功。终态 summary 没暴露 provider pressure。

#### Evidence

```text
llm.provider.error http_status=429 retryable=false
llm.call.retry attempt=1 max_attempts=3
llm.call.retry attempt=2 max_attempts=3
```

#### Impact

高并发 batch 研究后 analyst 大 prompt 更容易撞 TPM。终态 completed 掩盖模型限流风险,真实用户可能遇到长等待或失败。

#### Root Cause

已确证:三处叠加。
1. 所有 model_slot(research/summarization/writer/qa)都路由到同一 doubao endpoint `[REDACTED_ENDPOINT]`,6 路并行 research + analyst(5601 token)瞬时撞该 endpoint TPM。
2. `LLM_GLOBAL_CONCURRENCY=4`(Semaphore,client.py:158)只限并发数,不限每分钟 token,大 prompt 并发照样超 TPM。
3. retry backoff `0.2*(2**attempt)`(client.py:269,亚秒级)远小于 TPM 的分钟级窗口;且 retry 不读 provider 标的 `retryable=false`,标志与行为不一致。

#### DoD

- retryable 字段与实际 retry 行为一致。
- run summary 暴露 provider_error_count / retry_count。
- batch 并发触发 429 时有可配置限流或降并发策略。

#### Next Step

补证据:进入 E2E-S5 二级 plan 后读取 LLM client retry policy,确认 429 分类与执行分叉。

### E2E-S5-2 配置/参数成熟度不足

type: Improvement  
status: investigating  
priority: P2

#### Current

多处运行参数仍是 demo 期默认值,真实 deep run 暴露其不成熟。集中视图(各项归属其 owning 阶段执行):

| 参数 | 现值 | 本轮观察 | 方向 | owner |
|---|---|---|---|---|
| 报告长度/覆盖门 | 无 | deep 2086 字 / 每段 170-260 字也 approved | 加最小长度+维度覆盖门 | E2E-S4-1 |
| `MAX_REACT_TURNS` | 6 | 每竞品实际只 2 turn(search+fetch),研究浅 | 评估强制多轮取证或按维度补检 | E2E-S3 |
| `LLM_TIMEOUT_SECONDS` | 30 | analyst 5601 token 首次 32s 撞边界 | 大 prompt slot 调高或拆 prompt | E2E-S5-1 |
| 并行 researcher / TPM | 并发 4(不限 TPM) | 6 路 + analyst 撞 429 | 加 TPM 预算/降并发/分 endpoint | E2E-S5-1 |
| retry backoff | `0.2*2^n`(亚秒) | 对分钟级 TPM 无效 | 429 专用退避(分钟级+jitter) | E2E-S5-1 |

#### DoD

- 每项参数有明确阈值与依据,不再沿用 demo 默认。
- 报告长度门、429 退避在对应阶段落地并有回归。

#### Next Step

进入 E2E-S5 二级 plan 时,把跨阶段无主的参数(如 react turns)定阈;其余在 owner 阶段执行,本表只做总览与防遗漏。

## 9. E2E-S6 自进化 curator

### E2E-S6-1 skill curator 低质量样本扩散

type: Improvement  
status: investigating  
priority: P2

#### Current

本次 run QA rejection=0,但 skill curator 生成 4 个 staging candidates,其中 2 个 qa_rule、1 个 prompt_template、1 个 source_routing。候选总量已到 1872。

#### Limitation

Curator 只看 `qa_rejection_count`、supervisor decisions、source counts、evidence count。它不知道本次 run 存在 dimension drops、重复 evidence、短报告、promoted parse error。

#### DoD

- 本次 run 类型的质量缺陷不会生成 high confidence prompt_template / qa_rule。
- `api.skill.list` staging 总量增长受控,有去重 key。
- Curator candidate payload 能解释质量告警。

#### Next Step

补证据:进入 E2E-S6 二级 plan 后查询最近 staging candidates,统计同 run/同 payload 重复和 high confidence 比例。

## 10. 不做

- 不把本文件合并进 S0-S5 系统纠偏总纲。
- 不从本文件直接 build 代码;进入各阶段时先调研代码并创建二级 plan。
- 不把本次报告内容当成事实正确性背书;外部事实需另跑 source verification。
- 不在本文件写文件级改法 / Verify / build slice;上文出现的 client.py:158/269、logger.py 等行号仅为根因证据锚点,具体改法下沉二级 plan。
