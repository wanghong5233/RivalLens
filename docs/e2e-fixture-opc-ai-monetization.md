# E2E 测试剧本 — AI 时代 OPC 变现（歧义缩写）

文档定位：联调 / 回归时**直接复制粘贴**的 Intake 对话脚本。对标本轮 P0/P1 修复（OPC 消歧、维度统一、Schema 三件套 QA），以及 DAQ 语言腿纠偏后的复测。

基线 run：`run_69eb754e7db1`（2026-06-08，中文 query，`market_scope` 为空）。

---

## 0. 前置

- 后端 `make up`，`.env` 配好 `LLM_PROVIDER` + key。
- **建议清空历史**（避免旧 run 干扰对比）：

```bash
curl -s -X POST http://localhost:8000/api/runs/clear \
  -H "Content-Type: application/json" \
  -d '{"status":"all","include_running":false}'
```

- 入口：`/app/runs/new` 聊天框；或 `POST /api/runs/intake?mode=chat`。

---

## 1. 人设

创业者 / 独立开发者，想在 AI 时代找**可落地、能赚钱**的方向。知道「OPC」可能指一人公司，但**不清楚赛道里有哪些玩家、怎么变现**；也没有自备竞品名单。

---

## 2. 首句（轮 0，直接复制）

```text
在ai时代，有哪些可以落地的能赚钱的好的OPC项目？
```

---

## 3. 对话脚本（修复后期望）

> 「Agent 提问」是**语义期望**，真实 LLM 措辞会变；只要 `field_targets` / 消歧门槛命中即通过。  
> 「用户回话」按顺序复制；也可点对应 chip，再补一句 `text`。

### 3.1 标准路径（推荐）

| 轮 | 角色 | 复制粘贴内容 | 预期落库 |
|---|---|---|---|
| 0 | **User** | 见 §2 首句 | `user_query` 写入 |
| 1 | Agent | 您当前角色更接近？`field_targets` 含 `user_role` | — |
| 1 | **User** | `我是创业者，想找 AI 时代能落地变现的方向` | `user_role=founder` |
| 2 | Agent | **OPC 消歧（硬门槛，必须出现）**：「这里的 OPC 可能有多种含义。您指的是一人公司/个人可落地变现项目，还是工业通信协议 OPC UA，或其他含义？」`field_targets=["domain_hint","analysis_intent"]` | — |
| 2 | **User** | `我指一人公司/个人可落地变现项目` | 或选 chip `一人公司 / One Person Company` |
| 3 | Agent | 是否让 Agent 帮您发现竞品？ | — |
| 3 | **User** | `让 Agent 帮我发现` | `competitors_discovery_mode=true`，`competitors_explicit=[]` |
| 4 | Agent | `action="complete"`，进入 Plan 页 | `is_complete=true` |

**轮 2 用户回话（单独复制块）：**

```text
我指一人公司/个人可落地变现项目
```

**轮 1 / 3 备用回话：**

```text
我是创业者，想找 AI 时代能落地变现的方向
```

```text
让 Agent 帮我发现
```

### 3.2 可选：补市场范围（测显式 `market_scope`）

若 Agent 追问「主要关注哪个市场？」（`field_targets` 含 `market_scope`），可复制：

```text
主要关注中国国内市场，但也参考海外一人公司变现案例
```

预期：`market_scope` 写入中文市场描述；检索仍保持**跨语言广度**（zh+en 双路），报告语言仍为中文。

### 3.3 可选：工业协议对照（负例）

若故意选「工业通信协议」验证消歧分支：

```text
我指的是工业通信协议 OPC UA，不是一人公司
```

预期：`domain_hint` 含 `open platform communications`；discovery 候选偏向西门子 / 三菱 / B&R 等工业厂商——**与 §2 首句的变现意图不一致**，仅用于验证消歧分支，不作主验收路径。

---

## 4. 基线 run 快照（修复前，`run_69eb754e7db1`）

| 项 | 值 |
|---|---|
| `user_query` | 在ai时代，有哪些可以落地的能赚钱的好的OPC项目？ |
| `status` | `completed`（约 8 分钟） |
| `market_scope` | `null`（用户未指定地域 → 应走全球广度 + 中文报告） |
| `domain_hint`（错误） | `OPC (Open Platform Communications)` — intake **未消歧即猜成工业协议** |
| `analysis_intent` | 寻找AI时代可落地且盈利的OPC项目机会 |
| `focus_dimensions` | `[]` → 下游自造 27 个自由维度，`dimension_coverage_rate=0` |
| discovery 竞品（发散） | ChatGPT、MidJourney、Stable Diffusion、文心一言、讯飞星火、通义千问、Nomad List、Koe |
| evidence | 84 条；host 混合 openai.com / midjourney.com / nomadlist.com / cloud.baidu.com 等 |
| 报告标题 | `# AI时代高盈利OPC项目机会与落地路径分析`（正文按一人公司写，与 `domain_hint` 矛盾） |
| `run_knowledge` 三件套 | `features=0, pricings=0, personas=0`；coverage 全 `insufficient_data` |
| QA | 真闭环（writer → qa 打回 → supervisor → writer 重写 → qa 通过） |

**已解决（DAQ 纠偏，本 run 可验证）：** 中文报告、中英混合 evidence、无 locale 误报。

**未解决（触发 P0/P1，需按 §3 复测）：** OPC 三义矛盾、空 `focus_dimensions`、三件套全空仍放行。

---

## 5. 验收清单（修复后复测）

### 5.1 Intake

- [ ] 轮 2 **必须**出现 OPC 消歧问句（§3.1）；未消歧不得 `complete`。
- [ ] `intake_draft.domain_hint` **不含** `Open Platform Communications`（除非走 §3.3 负例）。
- [ ] 标准路径下 `domain_hint` 含 `one person company` 或等价变现语境。
- [ ] `analysis_intent` 含「一人公司」或 `One Person Company` 语义。
- [ ] `focus_dimensions` **非空**，且为 canonical token（如 `monetization_model`、`pricing_strategy`、`target_persona` 等，见 `schemas/contracts.py`）。

### 5.2 Discovery / Research

- [ ] `supervisor_decisions` 首条 `chosen_tool=DiscoverCompetitors`。
- [ ] `DiscoverCompetitors` 的 `domain_context` 使用消歧后的 `domain_hint`，**不是**裸 `user_query`。
- [ ] 竞品列表**同赛道**（一人公司变现 / indie SaaS / AI agent 工具链等），**不应**以 ChatGPT+Nomad List 为主轴拼凑。
- [ ] evidence ≥ 12 时，来源语言可中英混合；`market_scope` 为空时不应触发 locale 误报。

### 5.3 结构化产物 / QA

- [ ] `comparison_cells` 的 `dimension` 落在 plan 的 `focus_dimensions` 命名空间内（非 27 个自由字符串）。
- [ ] `dimension_coverage_rate > 0`（或 curator 不再因 coverage=0 跳过学习）。
- [ ] evidence ≥ 12 且竞品已 research 时，`run_knowledge.features/pricings/personas` **至少一类非空**；否则 QA 应 blocking 打回 analyst（非 `insufficient_data` 全放行）。
- [ ] 最终报告为**中文**；外文证据在正文中翻译呈现，溯源保留原文。

### 5.4 快速 SQL（替换 `{run_id}`）

```sql
-- Intake 落库
SELECT user_query,
       intake_draft->>'domain_hint' AS domain_hint,
       intake_draft->>'analysis_intent' AS analysis_intent,
       intake_draft->>'focus_dimensions' AS focus_dims,
       intake_draft->>'market_scope' AS market_scope
FROM runs WHERE run_id = '{run_id}';

-- 竞品与维度
SELECT DISTINCT competitor_id FROM comparison_cells WHERE run_id = '{run_id}' ORDER BY 1;
SELECT COUNT(DISTINCT dimension) AS dim_count FROM comparison_cells WHERE run_id = '{run_id}';

-- Schema 三件套
SELECT jsonb_array_length(features) AS f,
       jsonb_array_length(pricings) AS p,
       jsonb_array_length(personas) AS pe
FROM run_knowledge WHERE run_id = '{run_id}';

-- 报告语言抽样
SELECT LEFT(content_markdown, 200) FROM reports
WHERE run_id = '{run_id}' ORDER BY created_at DESC LIMIT 1;
```

---

## 6. 文档联动

| 主题 | 文档 |
|---|---|
| 测试案例库总索引 | `docs/7-test-cases.md`（TC-I9） |
| DAQ / 语言腿审计 | `docs/e2e-audit-2026-06-08-data-acquisition.md` |
| 赛方评分维度 | `docs/0-problem-background.md` |
| Intake 子系统 | `docs/2.7-agent-native-intake-and-live-run.md` |
