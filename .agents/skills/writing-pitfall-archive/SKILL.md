---
name: writing-pitfall-archive
description: Write or refactor a pitfall archive (recurring failures → invariants; Google SRE blameless multi-incident form). Use when editing `*DEPLOYMENT*`/`*MANUAL*`/`*RUNBOOK*`/`*PITFALL*`/`*坑*`/`*手册*` under `docs/`, or user asks 沉淀部署经验/踩坑/故障复盘/去AI味/不再犯同样错误. Do NOT use for single postmortems.
---

# Writing Pitfall Archive

## 一句话准则

**档案只为一件事：让同一类故障不再发生第二次。任何不服务于这个目的的内容都是噪音。**

## 与 Runbook / Postmortem 的边界

| 文档 | 范围 | 时态 | 位置 |
|---|---|---|---|
| Postmortem | 单一事件 | 过去式 | git commit / `private/` |
| Runbook | 高频流程 | 命令式 | `<repo>/scripts/` 即是 |
| **Pitfall Archive** | 多次故障沉淀 | **现在时：规则是什么** | **`docs/*MANUAL*.md`** |

**关键差异**：Postmortem 是事件级临时产物；Pitfall Archive 是"项目级不变量库"，永远活的、持续演进。详见 `references/design-rationale.md`。

## 硬性禁止（命中即删）

| 反模式 | 判断特征 | 归宿 |
|---|---|---|
| 命令序列 / 一步步操作 | 连续 `cd / docker compose / ssh` 等 5 行以上代码块 | shell 脚本 (`<repo>/scripts/`) |
| 教程口吻 | "首先 / 接下来 / 然后 / 最后" | 改为坑点条目 |
| 架构图 / 整体图 | mermaid 整体 graph | 架构文档（`writing-architecture-docs`） |
| 单次事件的完整记录 | "2026-05-09 14:32 我登录服务器看到 ..." | git log / `private/` |
| 决策辩证过程 | "考虑了 A 方案，又考虑 B，最后选 C" | git commit / `private/` |
| 安抚性语言 | "不用担心 / 这是正常的 / 后续会解决" | 删 |
| 重复表达 | 同一不变量在 4 节复述 | 用 `§X.Y` 引用 |
| 复制粘贴报错堆栈 | 完整 traceback 30 行 | 留关键 3 行作 Evidence |
| 通用 SRE 知识 | "Docker 镜像分层原理 / Linux OOM 机制" | 删 |
| AI 安慰话 | "通常来说 / 一般建议 / 值得注意的是" | 改成信号、后果、动作 |
| 口号式不变量 | "保证系统稳定" | 改成可违反、可检测、可追责的约束 |

## 必要章节结构

每节缺哪一块不强求，**出现即必须是这种形态**：

### §1 硬性约束（Hard Constraints）

不变量清单，每条 1-2 句、含**违反后果**：

> **1.2 资源紧张时不能并发** — 不能"旧容器 + build"同跑；不能并行 build 多服务；**重型构建链（如含 LaTeX / GPU / 大模型权重）永远不能在受限节点上完整 build**

格式：`**编号 + 一句话约束** — 量化范围 + 违反后果`。**不解释 why**（why 进 §4 坑点条目）。

### §2 路径与命名约定

环境路径、容器命名、域名、卷挂载的事实表：

| 项 | 值（示例） | 备注 |
|---|---|---|
| 代码 checkout | `/opt/apps/<project>` | 部署主机统一前缀 |
| 容器命名 | `<project>_<service>` | `api` / `worker` / `db` |

### §3 业务关键 env（多环境必须对齐）

变量名 + 典型值 + **漂移后果**。**不写完整 .env 内容**（那是 `.env.<env>.example` 的职责）。

### §4 坑点档案（核心）

每条用**五段式**：Symptom / Evidence / Root Cause / Solution / Invariant。

条目命名：`§4.N [日期] 坑点一句话总结`，按时间倒序排列。

完整反例 → 正例对照见 `references/examples.md`。

### §5 关键工具脚本

| 脚本 | 触发条件 | 产物 |
|---|---|---|
| `<repo>/scripts/<name>.sh` | 触发条件描述 | 产物路径或副作用 |

不写脚本内部实现，只写"什么时候用 / 产生什么"。

### §6 信号判别表

症状 → 坑点条目编号的快速查表：

| 症状 | 查 |
|---|---|
| CPU 95%+、SSH banner timeout | `§4.<N>` |
| 本地能跑、生产/远端不能跑 | `§4.<N>` |

### §7 演进规则

| 触发 | 行为 |
|---|---|
| 同一现象出现第 2 次 | 新增 §4.N 条目 |
| 同一类约束被违反 ≥ 3 次 | 升级到 §1 |
| **同类问题在 ≥ 2 个项目里都出现** | **上抽象到 engineering-playbook**，pitfall 条目 Invariant 段引用 playbook §NN |
| 不变量被新架构推翻 | 标 `~~strikethrough~~` 保留 1 版本，下次清理 |
| 工具脚本失效 | §5 删条 + 脚本归档 `private/archived/` |
| 季度回顾 | 检查 §4 中 6 个月未触发的条目，归档 `docs/archived/` |

**两层引用方向**（严格单向）：

| 方向 | 是否允许 | 理由 |
|---|---|---|
| pitfall → playbook | 是 | "上抽象到 playbook §08" 提醒未来复用 |
| playbook → 本仓库 pitfall | **否** | 破坏 playbook 跨项目可移植性 |
| playbook ↔ playbook | 是 | 内部反向链接形成网状结构 |

## 写作微观规范

- 现在时陈述：❌"曾经出现过 X" → ✅"在 X 条件下会出现 Y"
- 量化优先：❌"CPU 很高" → ✅"CPU 95%+ 持续 30s"
- 证据原始化：日志/容器状态/监控数值原文引用
- 内部交叉引用用 `§X.Y`，不用"上文 / 前面"
- 中文正文 + 英文代码 / 日志 / 路径
- 编号一旦发布**永不变**（外部 `grep §4.3` 可能依赖），新增只往后追加
- 句子以事实开头，不以评价开头：✅"CPU 95%+ 持续 30s"，❌"这是一个严重问题"
- 禁止"总结一下 / 经验告诉我们"，直接写 Invariant

## 自检（提交前必过）

- [ ] 这一段是"现在的规则"还是"过去的故事"？后者 → 删 / 移 `private/`
- [ ] 能用表格 / 五段式代替吗？能就替
- [ ] 命令序列超过 5 行？→ 抽脚本，正文留链接
- [ ] 出现"首先 / 接下来 / 然后"教程口吻？→ 改写
- [ ] §1 / §4 / §6 互相引用闭环？（信号查到坑点，坑点上溯约束）
- [ ] 编号无与历史版本冲突？（git blame 验证）
- [ ] 含敏感信息（真实 IP / hostname / API key / 内部域名）？→ 删
- [ ] 每个 Invariant 是否能被一次 grep、监控或 review 检查发现违反？不能→重写
- [ ] 是否有 AI 式安全套话（"通常 / 建议 / 尽量"）？→ 改成硬约束或触发条件

## 链路

- 设计依据与业界对照：`references/design-rationale.md`
- 反例 → 正例完整对照：`references/examples.md`
- 跨项目工程经验（上抽象层）：`writing-engineering-playbook`
- 项目对外名片：`writing-readme`
- 项目架构文档：`writing-architecture-docs`
