# Known Issues & Backlog

最后更新: 2026-05-24

3 人敏捷迭代用的轻量 backlog。条目只保留真的会做的事；每条 3-6 行：**问题 + 影响 + 入口 + 下一步**。
凑数项、文档占位、未来再说的想法不进表，必要时挪到底部"想到再说"。

## 真问题

| ID | 问题 | 优先级 | 入口 |
|---|---|---|---|
| OBS-001 | 关键路径几乎没有结构化日志,bug 只能查 PG 表 + traceback | P0 | `utils/logger.py` + 各 Agent 节点 |
| ORCH-001 | Researcher 工具集只有 `pack_lookup`,无法接真实采集渠道 | P0 | `service/collector/` + `agents/tools/` |
| ING-001 | `desensitize_text` 函数不存在,evidence 边界只有布尔标记 | P1 | `service/desensitize/` |
| SCH-001 | Conclusion / Feature / Pricing 等只有 Pydantic,无持久化表,跨 run 查询不便 | P1 | `models/conclusion.py` + Alembic 迁移 |
| ORCH-002 | 前端用 2 秒轮询拿 run 进度,长任务体验差 | P2 | `router/run_rt.py` + `frontend/src/api/hooks.ts` |

---

### OBS-001 关键路径结构化日志

**问题**:`structlog` + `request_id` contextvar 已经配好,但全工程只有 `app_main.py` 三处埋点(启动/停止/未捕获异常)。Agent 节点、LLM Client、QA、Skill Curator、路由全部零日志。

**影响**:LLM fallback 命中、Writer fallback、QA semantic 跳过、Supervisor max_iter 兜底这些**不抛异常的降级路径**完全不可观测。按 `run_id` 串日志的能力价值无法兑现。

**入口**:`backend/app/utils/logger.py`(加 `bind_run(run_id)` helper) + `agents/nodes/*.py` + `service/llm/client.py` + `service/qa/engine.py` + `router/run_rt.py`,各文件独立认领。

**埋点最小集**:Supervisor decision、Researcher tool_call、LLM call + retry + fallback、QA outcome、Skill Curator 候选数、Pack 加载、Run API 入口。
所有 event 都用 `log.info("event.name", key=value, ...)` 结构化形式,**不打 prompt 原文 / Key / 完整 evidence quote**。

**下一步**:logger.py 加 helper → 节点按文件分发。

---

### ORCH-001 Collector framework

**问题**:Researcher subgraph 当前唯一工具 `pack_lookup`,证据源固定为本地行业包快照。

**影响**:无法接真实数据,信息单一。`docs/2.5-agent-architecture.md` §3.2 要求的 `fetch_url` / `search_web` / `parse_page` / `extract_structured` / `lookup_offline_snapshot` 都没有。

**入口**:`backend/app/service/collector/`(channel 注册中心) + `backend/app/agents/tools/<channel>.py`(每 channel 一个文件,互不冲突) + 在 `agents/subgraphs/researcher.py` 注入 channel。

**约束**:channel 输出必须经 `desensitize_text`(见 ING-001)再落 evidence;单站点 QPS ≤ 1。

**下一步**:先定 `CollectorChannel` 协议草案 + 一个 stub channel,队友再认领 search/fetch 扩展。

---

### ING-001 desensitize_text 边界函数

**问题**:`Evidence.desensitized: bool` 字段存在,但 `desensitize_text(text)` 函数完全没实装,Researcher 落 evidence 时也没调用。`docs/2-architecture-decision.md` §6.3 的强制脱敏边界目前是空契约。

**影响**:一旦 ORCH-001 接真实渠道,PII 会绕过脱敏直接落库。

**入口**:`backend/app/service/desensitize/`(新目录:`engine.py` + `patterns.py`) + `agents/subgraphs/researcher.py` 边界调用 + `tests/test_desensitize.py`。

**最小集**:邮箱 / 手机号 / 身份证 / 用户名 @mention / 头像 URL。失败抛 `DesensitizeError`,不静默。

**下一步**:写规则集 + 对抗样本测试,Researcher 落 evidence 前强制调用。和 ORCH-001 同期上线。

---

### SCH-001 业务实体持久化

**问题**:`schemas/business.py` 定义了 Feature/Pricing/Persona/UserFeedback/Conclusion,但 ORM 层没有对应表,数据只以 JSON 嵌在 `report.content_json` / `step.payload` 里。

**影响**:Evidence ↔ Conclusion 多对多双向溯源只能解析 markdown;跨 run 复用 conclusion 做 QA 校验或 Curator 反思,都得反序列化 JSONB。

**入口**:`backend/app/models/conclusion.py`(其它实体先不动) + 一个新的 Alembic 迁移(时间戳自动避免冲突) + `agents/nodes/analyst.py` 双写 + `agents/nodes/writer.py` 改读结构化数据。

**先做小**:第一版**只表化 Conclusion**,其它实体保留 JSON 内嵌;真有跨 run 查询需求再扩。

**下一步**:写迁移 + Conclusion model + Analyst 双写。

---

### ORCH-002 SSE 进度推送

**问题**:前端 `useRunDetail` / `useRunTrace` 每 2 秒轮询,长 run 体验差。

**影响**:5-15 分钟 run 期间持续重复请求,前端无法及时反映状态。`docs/2-architecture-decision.md` §4 定的方案是 PG `LISTEN/NOTIFY` + SSE。

**入口**:`backend/app/router/run_rt.py`(SSE endpoint) + `backend/app/service/event_bus/` + `frontend/src/api/hooks.ts`(改 EventSource)。

**何时做**:M1 ORCH-001 接真实采集后 run 时长变长再做,目前轮询够用。

---

## 想到再说 (不主动安排)

| ID | 一句话 |
|---|---|
| CUR-001 | Skill Curator 三类候选目前一个 prompt 生成,可以按 generator 拆分,看候选质量是否提升 |
| ORCH-003 | Skill Curator 现在是主图同步节点,后续可拆为异步任务 |
| ORCH-004 | `/resume` 只有 thread 级 (B1),不支持 reset_to 阶段重放 |
| EXT-001 | 行业包扩展 schema 注册机制 (`extension_schema.py`) 接第二个 pack 时再做 |
| SEC-001 | `gitleaks` pre-commit hook 防 Key 误提交,有空配 |
| SEC-002 | 公开评论的 prompt injection 关键词清洗,ORCH-001 接公开评论数据前补 |
| API-002 | LLM 成本护栏 (slot 级 budget),压测后波动大时再做 |
| ORCH-005 | Golden eval 集,迭代频率上来再立 |

---

## 评审亮点候选 (Highlights for v2)

非主干阻塞,演示前如果有时间可以选 1-2 个做:

| ID | 方向 | 入口 |
|---|---|---|
| HLT-001 | DAG Run View (`@xyflow/react`) Agent 拓扑可视化 | `frontend/src/pages/RunTracePage.tsx` |
| HLT-002 | Battlecard 卡片网格视图,一屏多竞品 | `frontend/src/pages/RunViewPage.tsx` |
| HLT-003 | Prospect Voice 用户声音 / 情感分布主题视图 | `frontend/src/pages/RunVoicePage.tsx`(新) |
| HLT-004 | Compare 跨竞品矩阵 | `frontend/src/pages/RunComparePage.tsx`(新) |
| HLT-005 | Skill Curator 真异步化 + approved 写回 `industry_packs/` | `agents/nodes/skill_curator.py` + `router/skill_rt.py` |

---

## 怎么用这份 backlog

- 每条入口都列了独立文件 / 目录,认领前在群里说一声避免撞车。
- "想到再说"里的条目**不要主动开 PR**,有时间再说。
- 真要开始做的条目把"问题"那段贴到 PR 描述里就够了,不需要把所有字段抄进 PR。
- 新增条目按上面格式 3-6 行写完,字段越少越好。
