---
name: writing-architecture-docs
description: Write or refactor architecture/design/ADR docs (current-state + first-principles form). Use when editing `docs/*设计*`/`*架构*`/`*ADR*`/`*RFC*`, or user asks write/修改 architecture/设计/ADR docs, or complains doc is 啰嗦/口水/AI味/AI痕迹/对话记录/辩证过程. Do NOT use for README (writing-readme) or problem records (writing-problem-records). Pairs with writing-deslop.
---

# Writing Architecture Docs

## 一句话准则

**架构文档只回答两个问题：`当前实现是什么` 与 `为什么是这个形态`。其他都属污染。** 去 AI 味通用规则见 `writing-deslop`；本 skill 管架构文档结构。

## 架构专属禁止（通用 AI 味禁令见 writing-deslop）

| 反模式 | 判断特征 | 归宿 |
|---|---|---|
| 结论先行 / TL;DR / 摘要 | 用 `**xxx**` 开头总结全文 | 删，每节都是结论无需元结构 |
| 辩证过程 / 四轮反应 / 讨论记录 | "第一反应→反驳→第二反应"序列 | `agent-transcripts/` |
| 外部证据 / 产品对比 / 调研表 | 列举 ChatGPT / Claude / Letta 等做法 | 删，至多一句泛指 |
| 已删除/不再维护工件清单 | 列出被移除的文件、env、字段 | git log / CHANGELOG |
| 运维现象 | "启动失败 / wheel 冲突 / ABI 问题 / Windows-WSL 下 xxx" | issue tracker / `writing-problem-records` |

## 必要章节

每节缺哪一块不强求，**出现即必须是这种形态**（完整示例见 `references/examples.md`）：

### 1. 现状陈述（一句 + 一图）

现在时陈述"当前实现是什么"，配 mermaid 或分层职责表。

### 2. 分层职责表

三列 `层 / 负责 / 不负责`，一层一行，无解释段落。

### 3. 第一性原理分析（为什么是这个形态）

维度表，不用散文。维度名从以下挑选：

- 数据规模（量化：行数、QPS、体积）
- 能力归属（哪个角色负责这件事）
- 写入/读取成本（延迟、token、依赖体积）
- 故障域（失败面、传染性）
- 可逆性（未来换方案的迁移成本）

三列 `维度 / 分析 / 结论`，无散文。

### 4. 接口契约（签名 + 不变式）

接口签名用 `text` 块；不变式编号列出。**失败时必须失败，不返回伪成功**。

### 5. 可逆性 / 重评触发条件（如适用）

"当前选 A，未来可能换 B"类决策必须给**量化门槛**：

**触发判断以运行时指标为准，不在无数据时提前决策。**

## 架构专属微观规范（通用形态规则见 writing-deslop）

- 标题写对象或契约，不写口号：✅`运行时状态机`，❌`为什么这是正确架构`
- `第一性原理` 必须落成维度表；否则改名为 `设计约束`
- 章节引用用 `§X.Y` 或 `[附录 B](#...)`，不写"上文提到过"

## 架构专属自检（先过 writing-deslop 通用自检）

- [ ] 描述的是"当前架构"还是"过程/对话/运维"？后者→删
- [ ] "为什么"是否走了第一性原理维度表？口水论证→改表
- [ ] 出现架构专属禁止章节了吗？命中→删

## 链路

- 去 AI 味通用核：`writing-deslop`
- 工程约束基线：`.cursor/rules/core-principles.mdc`
- 配置治理基线：`.cursor/rules/configuration-management.mdc`
- 项目架构 rule（如已建立）：`.cursor/rules/<project>-architecture.mdc`
- README 撰写：`writing-readme`
- 坑点 / backlog：`writing-problem-records`
- 跨项目工程经验：`writing-tech-article`
