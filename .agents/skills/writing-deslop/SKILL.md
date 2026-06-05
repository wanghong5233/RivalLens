---
name: writing-deslop
description: Shared anti-slop writing core for any doc/prose (去AI味 canon). Use when writing or editing README/架构/ADR/技术文章/playbook/坑点/issue or any Markdown, or when text has AI味/AI痕迹/啰嗦/口水话/辩解/低信息密度/模板句/口号标题/形容词自夸/过程辩证记录. Pairs with a format skill (writing-readme / writing-architecture-docs / writing-tech-article / writing-problem-records); this one owns tone, the format skill owns structure.
---

# Writing De-slop Core

## 一句话准则

**每一行要么承载读者必须带走的事实/判断/动作，要么删。解释、辩解、铺垫、对称节奏都是噪音。** 本 skill 管「去 AI 味」通用规则；具体文档的章节/字段结构由对应 format skill 负责。

## 硬性禁止（命中即删/即改）

| 反模式 | 判断特征 | 归宿 |
|---|---|---|
| AI 模板句 | `这不是 X，而是 Y` / `值得注意的是` / `总而言之` / `更重要的是` / `此外` / `赋能` / `打造` | 删，或改成事实连接 |
| 自夸形容词 | `强大 / 优雅 / 业界领先 / 创新 / 稳定 / 高效` 无证据 | 改成指标/阈值，或删 |
| 过程时态 / 辩证 | `我们曾经…后来…这次决定` / `考虑了 A 又 B 最后 C` | 改现在时；过程移 git log / `private/` |
| 对话/汇报语气 | `这里我思考 / 可见 / 显然 / 说白了 / 其实 / 就` | 直接删 |
| 教程口吻 | `首先 / 接下来 / 然后 / 最后` | 改成条目或表格 |
| 口号标题 | `深度解析 / 终极指南 / 核心理念 / 一文搞懂 / 为什么这是对的` | 改成对象、判断或触发条件 |
| 散文堆叠 | 连续 3 段超 5 行 | 改表格 / mermaid / 签名代码块 |
| 模糊量化 | `很慢 / 经常失败 / 大量` | 量化：`p95 12.4s` / `30%/周` |
| 安抚套话 | `不用担心 / 通常来说 / 一般建议 / 尽量` | 改成信号、后果、动作 |

完整禁词 / 禁短语 / 禁开头清单：`references/banned-phrases.md`（按需读）。

## 通用形态规则

- 表格 > 列表 > 段落；段落 ≤ 3 行，超过就拆表/图。
- 现在时陈述事实：❌`我们决定采用 X` → ✅`采用 X`。
- 中文正文 + 英文代码/标识符；不在同段中英混写解释。
- 无 emoji、无感叹号；标题写工程名词，不写营销口号。
- 交叉引用用 `§X.Y` 或锚链接，不写「上文提到」。
- 每 300 字至少一个具体例子 / 阈值 / 文件名 / 命令 / 反例。

## 通用自检（任何文档提交前先过这关，再过 format skill 的专属自检）

- [ ] 逐行问：删掉这行，读者会漏什么事实？漏不掉 → 删。
- [ ] 这段是「现在的结论/规则」还是「过程/对话/辩解」？后者 → 删或移 `private/`。
- [ ] 能用表格/图/签名代替的散文，替了吗？
- [ ] 出现 AI 模板句、口号标题、自夸形容词了吗？命中 → 改成可验证事实。
- [ ] 数字有出处或标明是实践阈值吗？
- [ ] 标题像工程索引还是 AI 摘要？像摘要 → 改成读者会搜索的名词。

## 与 format skill 的分工

| 这个 skill 负责 | format skill 负责 |
|---|---|
| 语气、禁句、形态、通用自检 | 章节顺序、字段契约、专属结构 |

写任何文档时，本 skill 与对应 format skill 并行生效：先用本 skill 去味，再用 format skill 套结构。
