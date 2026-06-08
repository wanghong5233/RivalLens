# E2E 审计 — 上游数据采集质量与语言/地域漂移

审计对象：`run_959c9dc1d6d7`（2026-06-07，一次开放性中文/国内市场请求）
关注面：上游数据采集（广度、语言、地域、渠道），对照 `docs/0-problem-background.md` 评分维度 1（35%，输出可信度/溯源）与维度 3（20%，业务价值/覆盖度）。

## 1. 结论

用户用中文提问、`market_scope` 已正确捕获为「中国国内市场」，但全程跑成英文：70 条 evidence 全部来自国外厂商站点，最终报告标题是 `# AI-Enabled OPC Projects: Monetization Opportunities...`。

根因不是单点 bug，是一条**意图→检索→证据→报告**的语言/地域漂移链，叠加「多渠道」名不副实（实际只有 Tavily 一个英文偏置的 search provider）。结构化产物（schema 三件套、溯源、QA）本身在跑，但**上游喂进来的就是错地域、错语言的料**，下游再规整也是规整一份「面向海外市场的英文竞品报告」，不符合用户需求，未达商业可用。

## 2. 复现与证据（已冻结）

请求事实（`runs` 表）：

```text
run_id          = run_959c9dc1d6d7   status = completed
user_query      = 我想知道有哪些AI时代，有哪些好的OPC项目？我需要能够变现
analysis_intent = 寻找高变现潜力的AI+OPC项目机会      （中文，正确）
market_scope    = 中国国内市场                          （正确捕获）
competitors_explicit = []                               （discovery 模式）
```

证据来源（`evidence` 表，共 70 条，零中文源）：

```text
source_type:  article 48 | official_site 20 | public_review 2
host TOP:     br-automation.com(9) prosysopc.com(5) siemens.com(4)
              mitsubishielectric.com(×5 区域域名) advantech.com beckhoff.com
              aveva.com opcfoundation.org ...
              —— 全部为奥/德/日/美工业自动化厂商，无 .cn，无国内厂商
quote 样本:   "The platform also offers a secure and flexible architecture..."
              "Outcome-based pricing (per successful outcome)..."   —— 全英文
```

报告语言（`reports.content_markdown`）：

```text
# AI-Enabled OPC Projects: Monetization Opportunities and Competitive Landscape
## Executive Summary
The convergence of AI and OPC UA is creating distinct monetization pathways...
```

附带事实：模糊词「OPC」被 discovery 直接锁定为工业协议 OPC UA（OPC Foundation 生态），无消歧、无「国内 / 变现」语境候选。

## 3. 根因链（按故障域分层）

| 层 | 实际行为 | 证据位置 |
|---|---|---|
| Intake | `market_scope=中国国内市场` 正确写入 draft | `runs.intake_draft` |
| Planner→Researcher | `market_scope` **没有进入** researcher 子状态 | `agents/subgraphs/researcher.py` `ResearcherSubState`（只有 `research_topic`/`domain_hint`，无 market_scope/locale 字段） |
| 检索 query | `{domain_hint} {competitor_id} {dimension} {research_topic}`，无地域/语言限定 | `researcher.py:413-414` |
| 检索 provider | Tavily `client.search(...)` **未传 `country`/语言任何参数**，默认全球英文偏置；且系统只有 Tavily 一个 search 渠道 | `agents/tools/search_web.py:41-56`；`service/collector/registry.py:46-54` |
| Analyst/Writer | 运行时只拿到 `user_query`，**拿不到** `analysis_intent`/`market_scope`；且 `ANALYST_SYSTEM_PROMPT`/`WRITER_SYSTEM_PROMPT` **无输出语言约束** | `prompts.py:367,489`（system prompt）；`prompts.py:982,1083`（user prompt builder 入参） |
| 输出 | 上下文里全是英文 evidence，模型自然产英文报告 | `reports.content_markdown` |

关键判断：报告英文**不是 writer 单独的 bug**，是「英文证据占满上下文 + 无显式语言指令」共同结果。只改 writer 语言指令能让报告变中文，但证据仍是海外英文源——治标不治本。**根因在上游检索的地域/语言缺失。**

## 4. 多渠道接入：设计 vs 现实

`docs/2.6-collector-channels.md` 画了 6 通道（search_web/fetch_url/parse_page/extract_structured/load_skill/read_skill_file），读起来像「多渠道」。现实：

- **search（外部信息入口）只有 Tavily 一家**；`fetch_url` 也走 Tavily extract。真正决定数据广度的检索层是单点。
- 设计图里的 `parse_page` 通道**未在 registry 注册**（`registry.py` 只注册 5 个，无 parse_page）。
- `source_routing` 机制存在（`applies_to=source_routing` 的 skill 加载链路），但 `backend/skills/` 下**实际一个 source_routing 规则都没有**（只有 2 个 qa_rule + 1 个 prompt_template），更没有「中文/国内优先」的路由规则。
- 无任何中文原生检索渠道（百度/必应中国/微信公众号/知乎/36氪/厂商中文站等），赛方资源里的火山 `web_search`（`scripts/probe_search_providers.py` 已探活）也未接入主链路。

结论：「多渠道」目前是渠道**抽象**到位、渠道**实例**单一。要提质，得在这一层补真正的多 provider + 地域/语言路由。

## 5. 问题清单（按优先级，对齐评分维度）

状态机：`triaging`(未定义清) / `investigating`(根因未定) / `planned`(根因已定待实现)。

### [planned] DATA-001 market_scope/语言未下达到检索层（P0，维度1+3）

- **Current**：Intake 正确捕获 `market_scope`、`analysis_intent`（语言），但 planner→researcher 不透传，`ResearcherSubState` 无对应字段。
- **Limitation**：用户声明「国内市场」对实际检索零影响；地域/语言意图在第一跳就丢失。
- **Evidence**：`market_scope=中国国内市场` 却 70/70 海外源（§2）。
- **Root Cause**：`ResearcherSubState`(`researcher.py:122-143`) 无 `market_scope`/`response_language`；query 构造(`researcher.py:413`)与 Tavily 调用(`search_web.py:41`)均无地域/语言入参。
- **DoD**：`market_scope` + 推导出的 `response_language` 贯通 planner→researcher→search；中文/国内请求的检索 query 与 provider 参数体现地域；新增一条断言（中文+国内 run 的中文源占比 > 阈值）进 golden。
- **Next Step**：定字段流转契约（intake draft → AgentState → ResearcherSubState → search args）。

### [planned] DATA-002 检索 provider 单点且无地域参数（P0，维度1+3）

- **Current**：仅 Tavily 一个 search 渠道，`client.search` 不传 `country`/语言。
- **Limitation**：全球英文偏置；无 provider 兜底，Tavily 抖动即采集失败。
- **Evidence**：`search_web.py:44-56`；`registry.py:46-54`。
- **Root Cause**：渠道抽象到位但只注册了 Tavily；`_tavily_search` 未利用 Tavily 的 `country` 等地域能力。
- **DoD**：(1) Tavily 调用按 `market_scope` 传地域参数；(2) 至少接入 1 个中文原生检索 provider（候选：赛方火山 `web_search`，已探活；或必应中国），形成 provider 路由 + 失败兜底；(3) `docs/2.6` 同步为「多 provider + 地域路由」真实形态。
- **Next Step**：评审 provider 选型（火山 web_search vs 必应）与合规边界（robots/ToS）。

### [planned] LANG-001 Analyst/Writer 无输出语言约束、且看不到 intent（P0，维度1+3）

- **Current**：`ANALYST_SYSTEM_PROMPT`/`WRITER_SYSTEM_PROMPT` 无语言规则；二者 user prompt 只含 `user_query`，无 `analysis_intent`/`market_scope`。
- **Limitation**：报告语言跟随证据语言；用户中文意图在产出端不可见。
- **Evidence**：`prompts.py:367/489`（无 language rule）；`prompts.py:982-999/1083-1107`（builder 入参）；报告英文（§2）。
- **Root Cause**：仅 intake/planner 有语言规则，分析/撰写端缺规则且缺 intent 上下文。
- **DoD**：analyst/writer system prompt 增「输出语言 = response_language（默认随 analysis_intent/user_query）」；user prompt 注入 `analysis_intent`/`market_scope`；中文请求产中文报告（含 schema 字段文案）。
- **Next Step**：与 DATA-001 的 `response_language` 字段一起落，避免重复推导。

### [investigating] DATA-003 模糊实体无消歧、discovery 无地域候选（P1，维度3）

- **Current**：discovery 把「OPC」直接当 OPC UA 工业协议，候选全为海外厂商。
- **Limitation**：开放性/模糊请求易跑偏到与用户语境无关的领域；无「你是指 A 还是 B」澄清，也无国内候选优先。
- **Evidence**：competitors 全为西门子/三菱/B&R/Beckhoff 等（§2）。
- **Open Questions**：消歧应放 intake（追问）还是 discovery（多义并列候选 + 证据投票）？国内候选优先权重多大不伤召回？
- **Root Cause**：未定（先补证据：跑 3-5 个模糊中文 query 看 discovery 候选分布）。
- **Next Step**：补证据，不先改默认行为。

### [fixed] DATA-004 source authority 指标缺语言/地域覆盖（P2，维度3）

> 跨语言广度纠偏（2026-06-08）：初版护栏把「中文用户」当「中国市场」,会对中文问全球话题的请求误判「中文源不足」。对照成熟方案(CrossRAG / Deep Research「home turf」/ Felo 跨语言检索)纠偏——语言只决定输出,不决定市场;检索追求跨语言广度,best info wins。已落码并 407 tests passed,详见总纲「修正决策」。

- **Current**：`locale_match_rate` 退为「显式 market_scope 锁定地域的覆盖度」(无显式地域则 =1.0,不惩罚全球源);`rule_locale_mismatch` 仅在 market_scope 显式锁定地域且一手源 < 覆盖底线(0.20)才 warning;`locale_distribution` 保留语言/地域分布观测。配套:`target_country_from_scope` 移除 response_language 触发、S2 改双路并行召回、analyst/writer 增外文证据翻译规则。
- **Limitation**：地域错配仍不升级为 blocking；这是刻意选择，避免误杀跨境/全球化场景。
- **Evidence**：run completed 且无任何语言/地域告警。
- **DoD**：metrics 增 `locale_match_rate`（命中目标地域/语言的源占比）；低于阈值时 QA 出 warning；`warning_rule_ids` 写入 QA payload；golden 覆盖中文国内 case。
- **Next Step**：真实中文 run 复测，若 `locale_match_rate` 仍低，优先回到 S2/S3 检索与重排补采，不改 QA 阈值。

## 6. 暂缓 / 不做

- 重型无头浏览器抓取：与 §138「轻解析」原则冲突，本周期不引入。
- 多义实体的完整知识图谱消歧：超出赛题范围，DATA-003 先用「澄清 + 候选投票」轻量解。
- 问卷/访谈专用渠道：已在 backlog `SURVEY-001`，维持暂缓。

---

补充：DATA-001 / DATA-002 / LANG-001 共享同一条 `response_language` + `market_scope` 贯通改造，建议合并为一个 plan 实施（上游检索地域化 + 产出语言化），DATA-003/004 作为后续质量护栏。
