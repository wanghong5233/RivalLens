---
name: writing-problem-records
description: Write or refactor problem records across the lifecycle — active Known-Issues/Backlog (unresolved, evidence-before-solution) and Pitfall Archive (converged recurring-failure invariants). Use when editing `docs/KNOWN_ISSUES_AND_BACKLOG*.md` / `*PITFALL*` / `*MANUAL*` / `*RUNBOOK*` / `*坑*`, or user asks 记录 bug/补 issue/整理待办/沉淀踩坑/故障复盘/不再犯同样错误, or an entry has 拍脑袋解法/补丁式方案/启发式/先入为主. Do NOT use for single postmortems (git/private) or cross-project playbook. Pairs with writing-deslop.
---

# Writing Problem Records

去 AI 味通用规则见 `writing-deslop`。本 skill 只管「问题类文档」的两种模式与结构契约。

## 一句话准则

**Backlog 模式**：只追踪未解决问题，让「问题本身」先讲清楚——Root Cause 未定前的「方案」都是噪音。
**Pitfall 模式**：只为让同一类故障不再发生第二次；不服务这个目的的内容都删。

## 选模式（先判断写哪种）

| 文档 | 范围 | 时态 | 位置 |
|---|---|---|---|
| **Known Issues & Backlog** | 活跃、未解决 | 现在时：还在发生 | `docs/KNOWN_ISSUES_AND_BACKLOG.md` |
| **Pitfall Archive** | 已收敛、需防复发的不变量 | 现在时：现在的规则是 | `docs/*MANUAL*.md` |
| Postmortem | 单次事件复盘 | 过去式 | git commit / `private/` |
| Engineering Playbook | 跨项目工程直觉 | 中性 | `writing-tech-article`（跨项目变体） |
| ADR / RFC | 长期决策 | 现在时 | `writing-architecture-docs` |

判别口诀：「还没解决」→ Backlog；「已解决防复发」→ Pitfall；「跨项目复用」→ tech-article；「定长期约束」→ architecture。

## 模式专属禁止（通用 AI 味禁令见 writing-deslop）

| 模式 | 反模式 | 归宿 |
|---|---|---|
| Backlog | 先写解法再补问题（`下一步` 早于/长于 Evidence） | 按字段顺序重写 |
| Backlog | 启发式补丁（`默认走 X / 自动 Y` 未评审） | 改 Open Question 或拆 ADR |
| Backlog | 同根因拆多 ID | 合并到首个 ID |
| Backlog | 不可复现 Bug 进活跃列表 | 标 `triaging`，30 天补不齐关闭 |
| Pitfall | 命令序列 >5 行 | 抽 `<repo>/scripts/`，正文留链接 |
| Pitfall | 单次事件完整记录 / 决策辩证 | git log / `private/` |
| Pitfall | 通用 SRE 知识（Docker 分层原理） | 删 |
| Pitfall | 口号式不变量（`保证系统稳定`） | 改成可违反、可检测、可追责的约束 |

## Backlog 模式结构

状态机（仅 4 合法值，禁用 `todo/done/wip/wontfix`）：

| 状态 | 含义 | 离开条件 |
|---|---|---|
| `triaging` | 问题未定义清楚 | Symptom/Repro/Evidence 齐 → `investigating` |
| `investigating` | 已定义，根因未定 | Root Cause 写明 → `planned` |
| `planned` | 根因已定，待实现 | 实现合并 → 移出文件 |
| `blocked` | 等外部输入 | 阻塞解除 → 回原阶段 |

每条先声明 `type`，按字段顺序写（字段顺序即写作顺序）：

- **Bug**：`Symptom → Repro → Evidence → Scope → Impact → Hypotheses → Open Questions → Root Cause → DoD → Next Step`
- **Improvement**：`Current → Limitation → Trigger Condition → Options → DoD → Next Step`
- **Validation**：`Subject → Test Plan → Pass Criteria → Environment → Result`

**关键硬约束**：`Root Cause` 为空时，`Next Step` 只允许「补证据 / 召集决策」，禁止任何「改 X / 默认 Y」。

完整字段定义、状态流转、ID/优先级规则：`references/backlog-schema.md`。

## Pitfall 模式结构

七节骨架（出现即必须是该形态）：

| 节 | 内容 |
|---|---|
| §1 硬性约束 | 不变量清单，每条 `**编号+约束** — 量化范围 + 违反后果`，不解释 why |
| §2 路径/命名约定 | 环境路径、容器命名、卷挂载事实表 |
| §3 业务关键 env | 变量名 + 典型值 + 漂移后果（不写完整 .env） |
| §4 坑点档案（核心） | 五段式 `Symptom / Evidence / Root Cause / Solution / Invariant`，命名 `§4.N [日期] 一句话`，时间倒序 |
| §5 关键工具脚本 | 脚本 / 触发条件 / 产物（不写实现） |
| §6 信号判别表 | 症状 → 坑点编号 |
| §7 演进规则 | 第 2 次复现新增 §4；违反 ≥3 次升 §1；跨 ≥2 项目上抽到 playbook |

**编号一旦发布永不变**（外部 `grep §4.3` 可能依赖），新增只往后追加。完整结构与演进/引用规则：`references/pitfall-schema.md`。

## 自检（先过 writing-deslop 通用自检，再过本表）

- [ ] 选对模式？（未解决→Backlog；防复发→Pitfall）
- [ ] Backlog：每条声明 `type/status/priority`；状态在 4 合法值内；RC 空时 Next Step 只写「补证据/决策」；≥1 条可原样执行的 Repro；单条 <60 行。
- [ ] Pitfall：命令序列 >5 行已抽脚本；每个 Invariant 可被一次 grep/监控/review 检查违反；编号无历史冲突。
- [ ] 引用日志/payload 原文作 Evidence（留关键 3 行，非 30 行全文）。
- [ ] 无已关闭/已上线残留；无真实 IP/hostname/API key/内部域名。

## 链路

- 去 AI 味通用核：`writing-deslop`
- 字段/结构细节：`references/backlog-schema.md`、`references/pitfall-schema.md`、`references/backlog-checklist.md`
- 设计依据与反例：`references/backlog-design-rationale.md`、`references/backlog-examples.md`、`references/pitfall-design-rationale.md`、`references/pitfall-examples.md`
- 跨项目沉淀（上抽象层）：`writing-tech-article`
- 项目架构/长期决策：`writing-architecture-docs`
