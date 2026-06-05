---
name: writing-tech-article
description: Write or refactor dense personal-portfolio tech writing — blog/Feishu 干货 and cross-project engineering playbook (跨项目工程直觉, publish 飞书/blog NOT GitHub). Use when editing `docs/private/tech-articles/*.md` or `docs/private/engineering-playbook/*.md`, or user asks 写技术博客/复习笔记/面试沉淀/干货/高密度/沉淀工程经验/playbook/第一性原理/跨项目复用/去AI味/用图表达. Do NOT use for README (writing-readme), problem records (writing-problem-records), or ADR (writing-architecture-docs). Tone: writing-deslop.
---

# Writing Tech Articles

## 一句话准则

**技术文章不是聊天记录，也不是资料堆砌。它应该把读者必须记住的判断、模型、边界和行动压缩到最小心智负担。** 去 AI 味通用规则见 `writing-deslop`；本 skill 管技术文章 / playbook 的结构与密度。

## 写作目标

| 目标 | 判断标准 |
|---|---|
| 高密度 | 每段都回答一个工程判断，不铺垫、不复述常识 |
| 第一性原理 | 先解释为什么这个问题存在，再给规则 |
| 可记忆 | 关键结论能被一句话、表格或图记住 |
| 可复用 | 读者看完能迁移到下一个项目 |
| 可面试 | 能提炼成 3-5 个可讲的工程观点 |

## 标准结构

1. **一句话结论**：文章先给判断，不卖关子。
2. **问题模型**：用图/表描述概念关系或成本结构。
3. **核心规则**：3-7 条，不超过读者工作记忆。
4. **反例 vs 正例**：展示错误形态和改法。
5. **落地清单**：读者下一次做事时照着检查。
6. **出处**：只放支撑关键判断的链接，不堆 bibliography。

## 信息压缩规则

| 内容 | 处理 |
|---|---|
| 背景故事 | 压成 1-2 句，除非影响判断 |
| 长段解释 | 改成表格 / 决策树 / 公式 |
| 重复例子 | 留最能代表差异的 1 个 |
| 名词定义 | 只定义会影响决策的词 |
| 业界链接 | 链接后必须说明它支撑哪条判断 |
| 口号 | 没有操作含义就删 |

## 图优先

优先使用这些文本图：

```text
decision tree:  什么情况下选 A / B / C
cost model:      L1 常驻税 → L2 触发税 → L3 按需读
pipeline:        input → route → tool/retrieval → model → state → UI
2x2 matrix:      重要/紧急、稳定/变化、常驻/按需
```

如果一段话能变成表格或流程图，就不要保留成长段文字。

## 文章专属反模式（通用 AI 味禁令见 writing-deslop）

| 反模式 | 改法 |
|---|---|
| 「先介绍背景」写 500 字 | 第一段直接给结论 |
| 把调研链接排成清单 | 每个链接绑定一条判断 |
| 同一观点 3 种说法重复 | 留最硬的一句 |
| 为显完整塞边缘内容 | 放进「非目标」或删 |
| 空喊「第一性原理」 | 补成本模型 / 约束表 / 可证伪条件，补不出就删 |

## 跨项目 Playbook 变体

当目标是「跨项目复用的工程直觉」（发飞书/blog，不进 GitHub）时，在上述规则上额外收紧：

- **抽象化判别**：把项目业务名词（产品名 / env 前缀 / 厂商品牌如 `pgvector`、`DashScope`）换成抽象概念（向量索引 / 协作服务 / 业务参数），文章仍成立 → 合格；立刻散架 → 这属于项目坑点，改投 `writing-problem-records`。
- **主轴 > 副轴**：主轴 Agent/LLM（provider 熔断 / prompt 是契约 / 工具调用后一致性 / 评估闭环 / 上下文预算）必须多于副轴通用后端（配置治理 / 失败要响亮 / 可观测即合同）。
- **必备形态**：现状陈述 → 反模式 vs 正例表（≥5 行）→ 第一性原理维度表（`维度/分析/结论`，维度名用抽象语义：调用面 / 异质性 / 可逆性 / 故障域 / 可观测 / 责任归属）→ 触发信号（4-7 条可验证）→ 自检。
- **单向引用**：项目坑点可引 playbook；playbook 不引项目坑点（破坏可移植性）。
- **开源就绪**：无真实 IP / hostname / API key / 内部域名、无未公开仓库链接；换个行业的工程师读仍有指导价值。

完整规则与反例：`references/playbook-variant.md`、`references/playbook-examples.md`。

## 自检

- [ ] 第一屏能看到核心结论吗？
- [ ] 是否有至少 1 个图 / 表 / 决策树承载核心模型？
- [ ] 每个小节是否都能被一句话标题概括？
- [ ] 是否删掉了“懂的人不用看，不懂的人看了也不会做”的段落？
- [ ] 关键数字是否有出处或标明是实践阈值？
- [ ] 是否有 AI 味标题（"深度解析 / 终极指南 / 核心理念 / 一文搞懂"）？→ 改成具体问题
- [ ] 是否每 300 字至少有一个具体例子、阈值、文件名、命令或反例？
- [ ] 读者能否带走 3 条可复述观点？
- [ ] Playbook 变体：把业务名词改抽象后文章仍成立？主轴 ≥ 副轴？无内部敏感信息？

## 链路

- 去 AI 味通用核：`writing-deslop`
- Playbook 完整规则与反例：`references/playbook-variant.md`、`references/playbook-design-rationale.md`、`references/playbook-examples.md`
- 项目坑点 / backlog：`writing-problem-records`
- 项目架构 / 长期决策：`writing-architecture-docs`
- 项目对外名片：`writing-readme`

