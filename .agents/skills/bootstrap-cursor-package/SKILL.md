---
name: bootstrap-cursor-package
description: Bootstrap or audit a project `.cursor/` engineering package. Use when starting a new repo, asks to 初始化 .cursor / 套用工程经验包 / 复制 cursor 模板, or auditing existing `.cursor/` for missing rules/skills/hooks or project-name leakage. Do NOT use to write a single rule, hook, command, or skill in isolation.
---

# Bootstrap Cursor Package

## 一句话准则

**新项目的 `.cursor` 不是从空白开始，而是从"通用工程经验包"开始；项目专属内容只能在 MVP 架构落地之后再写，否则会污染 Agent 上下文并形成不存在的边界。**

## 决策门槛

执行前先确认：

| 项目阶段 | 装什么 | 不装什么 |
|---|---|---|
| 仓库刚建立、无代码 | 通用 rules + 通用 skills + 通用 hooks + 通用 commands | 任何项目专属架构 / 业务边界 |
| 已有 MVP 但架构未稳 | 通用层 + 极简 architecture rule（只写已存在的目录） | 还没决定的子服务 / 子模块 |
| 架构稳定、上线后 | 通用层 + 完整 architecture rule + 项目专属 commands / hooks | 仍处于"想做"阶段的设想 |

不知道处于哪一阶段时，按"刚建立"处理。

## 标准 `.cursor/` 骨架

```text
.cursor/
├── rules/
│   ├── core-principles.mdc           # always-on, ≤30 行
│   ├── cursor-package-boundaries.mdc # 防止 .cursor 膨胀
│   ├── configuration-management.mdc  # 配置集中治理、禁止魔法参数
│   ├── agent-runtime-contracts.mdc   # LLM/RAG/tool/async 契约（仅 LLM/Agent 项目）
│   └── <project>-architecture.mdc    # 仅在架构稳定后新增
├── skills/
│   ├── writing-skill/                # 元能力，必装
│   ├── writing-tech-article/         # 高密度技术沉淀
│   ├── writing-readme/               # README 治理
│   ├── agent-debugging/              # 仅 Agent 项目
│   ├── llm-observability-and-evals/  # 仅 Agent 项目
│   ├── tool-and-mcp-design/          # 仅 Agent / MCP 项目
│   └── llm-cost-optimizer/           # 仅 LLM 项目
├── commands/
│   ├── review.md                     # 必装
│   └── retro.md                      # 必装
├── hooks.json
└── hooks/
    └── block-dangerous-shell.py      # 必装
```

## 初始化流程

1. **复制通用层**：把 kit 的 `template/.cursor/`（或个人维护的通用包）整体拷入新仓库 `.cursor/`。
2. **裁剪 skills**：按项目类型保留 4-8 个。后端项目不要装 LLM/Agent skills；纯 Agent demo 不要装 deployment 类 skills。
3. **校验 hook**：参考 `references/init-checklist.md` 跑一遍 hook 自检；不过则在合并前修。
4. **不要新增 architecture rule**。直到出现实际目录、模块或服务，再写 `<project>-architecture.mdc`。
5. **不要复制上一个项目的业务名词**：Agent 看到 `scholarmind` / `chartflow` 等具体词会按字面理解。
6. **生成或更新 `AGENTS.md`** 指向 `.cursor/`，并声明项目当前阶段（pre-MVP / MVP / stable）。

## 项目专属内容的迁入时机

什么时候才允许在 `.cursor/rules/` 写项目内容：

| 信号 | 该写什么 |
|---|---|
| 已有 ≥3 个稳定后端目录 / 微服务 | `<project>-architecture.mdc`（目录职责 + 不变量） |
| 已对接 ≥1 个 LLM provider | runtime contract 里写 provider 列表与 fallback 策略 |
| 已发生 ≥1 次"前后端契约漂移" | review command 增加项目专属 schema 检查 |
| 已发生 ≥1 次"魔法参数引发线上事故" | configuration-management 增加项目专属字段表 |
| 已发生 ≥1 次危险 shell 误操作 | 在 hook 中增加项目专属命令模式 |

无信号则不写。空规则比错规则危害更大，因为它们污染上下文却不带来约束。

## 可复用工程红线（必须保留，不分项目）

通用层不可裁剪的硬规则：

- 配置集中治理，禁止魔法参数（`configuration-management`）
- fail fast、不要 silent fallback、不要 ghost layer（`core-principles`）
- 安全的 git / shell 拦截 hook，`failClosed: true`
- LLM / tool 输出消费方必须 schema 校验
- async job 必须有状态机、retry、audit 字段
- secrets 不入代码 / 测试 / 日志 / 文档

## 自检（合并前）

- [ ] `.cursor/rules/` 没有上一个项目的产品名、env 前缀、子服务名
- [ ] `always-on` rule ≤ 3 个、每个 ≤ 50 行
- [ ] `skills/` 数量 5-15，每个 description ≤ 300 字符且含触发词与负向边界
- [ ] `hooks.json` 有 `failClosed: true`，安全 hook 在新机器上能用 stdlib 跑通
- [ ] `commands/` ≤ 7，且每个 command 有固定输出格式
- [ ] 不存在尚未实现的 architecture rule
- [ ] `AGENTS.md` / 顶层 README 指向 `.cursor/` 当前阶段

## 链接

- 完整初始化清单：`references/init-checklist.md`
- skill 写作准则：`writing-skill`
- rule / hook / command 边界：`.cursor/rules/cursor-package-boundaries.mdc`
- 配置治理：`.cursor/rules/configuration-management.mdc`
- runtime 契约：`.cursor/rules/agent-runtime-contracts.mdc`
