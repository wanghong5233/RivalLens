# Init Checklist · 初始化 `.cursor/` 工程包

> 配套 `bootstrap-cursor-package`。建议作为 PR checklist 的一部分。

## 1. 通用层是否到位

| 工件 | 必装 | 检查点 |
|---|:---:|---|
| `rules/core-principles.mdc` | ✅ | always-on，≤30 行，只写禁止与必须 |
| `rules/cursor-package-boundaries.mdc` | ✅ | description 含 `.cursor/**/*` glob |
| `rules/configuration-management.mdc` | ✅ | 列出 magic-number 禁令、secrets 来源 |
| `rules/agent-runtime-contracts.mdc` | LLM/Agent 项目必装 | globs 收窄到真实代码路径 |
| `commands/review.md` | ✅ | 含 critical / important / style 三档 |
| `commands/retro.md` | ✅ | 输出五选一分类（rule/skill/command/hook/docs） |
| `hooks.json` | ✅ | 包含 `failClosed: true` |
| `hooks/block-dangerous-shell.py` | ✅ | Python stdlib，无外部依赖 |

## 2. Skills 是否合理

| 类型 | 推荐组合 |
|---|---|
| 后端服务（无 LLM） | writing-skill + writing-readme + writing-tech-article + writing-pitfall-archive + writing-issue-backlog |
| LLM / Agent 应用 | 上一行 + agent-debugging + llm-observability-and-evals + tool-and-mcp-design + llm-cost-optimizer |
| 纯文档 / 知识库 | writing-skill + writing-tech-article + writing-readme + writing-architecture-docs |
| MCP / 工具开发 | writing-skill + tool-and-mcp-design + agent-debugging + llm-observability-and-evals |

每加一个 skill 前自问：

- [ ] description 是否 <300 字符
- [ ] 触发词是否覆盖中英混说的真实表达
- [ ] 是否有 `Do NOT use for` 负向边界
- [ ] body 是否 <150 行
- [ ] 长篇内容是否下沉 `references/`

## 3. Hook 自检

```text
- [ ] hooks.json JSON 解析通过
- [ ] hook 脚本能 py_compile / 编译
- [ ] safe command（如 git status）输出 permission=allow
- [ ] dangerous command（如 git reset --hard）输出 permission=deny
- [ ] Cursor Hooks 面板无 invalid JSON / timeout 报错
```

如当前 Cursor 版本下 `beforeShellExecution` 的 deny / ask 不稳定，先用 `preToolUse + Shell` 替代。

## 4. 项目专属内容判断

| 内容 | 何时写 | 何时不写 |
|---|---|---|
| `<project>-architecture.mdc` | 已有 ≥3 个稳定目录 / 服务 | pre-MVP / 仅有想法 |
| 项目专属 review checklist | 已发生过契约漂移 / 前后端 schema 不一致事故 | 凭直觉认为"可能会有" |
| 项目专属 hook | 已出过实际危险命令事故 | 想象中的风险 |
| 项目专属 command（release-check / db-migration） | 已有真实流程被人执行过 ≥3 次 | 第一次执行，尚未稳定 |
| 项目专属 skill | 已重复出现过 ≥3 次同类工作 | 单次任务 |

## 5. 反向自检

| 反模式 | 信号 |
|---|---|
| 上下文污染 | always-on rules 总长度 > 100 行 |
| 项目泄漏 | rules / skills 引用了上一个项目的产品名、env 前缀 |
| 安全形同虚设 | hook 没有 `failClosed`，或在 fail-open 时静默放行 |
| 安全策略写成 command | 用户不触发就完全不执行 |
| skills 触发率低 | description <100 字符或缺触发词 |
| skills 数量爆炸 | 总 active 超过 15 |
| 占位内容 | rule 里出现"待补充 / TODO" |

## 6. 提交前

- [ ] 跑一遍 `/review`，确保新加的 hook、rule、commands 不会被自己 review 出问题
- [ ] 跑一遍 `/retro`，把本次 bootstrap 中观察到的不变量沉淀回 kit
- [ ] 在 `AGENTS.md` 或 README 里写一句"本项目使用基于 agent-engineering-kit 的 `.cursor/` 配置"
