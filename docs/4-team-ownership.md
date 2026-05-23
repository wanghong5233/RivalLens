# RivalLens 团队分工与协作机制

> 本文回答：3 人团队如何在 13 天窗口内交付一个**多 Agent 紧耦合**的系统、分支怎么管、提交记录怎么留、AI Coding 工具痕迹如何沉淀。
>
> 内部能力评估、答辩内部话术等不公开内容见 `docs/private/`。

## 1. 团队组成与角色

| 角色代号 | 主要职责 | 技术覆盖 |
|---|---|---|
| **L（队长 / Tech Lead）** | 系统架构、Agent 编排核心、端到端 MVP 打通、PR review、答辩主讲 | 全栈 + AI Coding 工作流（Cursor / TRAE） |
| **B（Backend Engineer）** | Researcher 工具层、数据脱敏管线、DB 迁移、FastAPI 路由、集成测试、部署脚本 | Python / FastAPI / SQLAlchemy / async |
| **C（Config & Demo Engineer）** | 演示数据集准备、行业包 YAML、文档完善、录屏剧本、答辩材料整理；P2 起视情况承接前端静态页 | YAML / Markdown / 配置；React（在 AI Coding 辅助下） |

**第一性原理**：本项目是**单一模块紧耦合**的 multi-agent 系统，传统"按 Agent 分人"会导致接口反复返工。改为按**耦合度 × 技术门槛**二维切：

```text
          高门槛              ↑
                              │
        L 独占                │
   Supervisor / LangGraph     │
   QA DSL / Skill Curator     │
        紧耦合核心            │
                              │
   ───────────────────────────┼───────────────────────────
                              │
        C 主场                │   B 主场
   演示数据 / 行业包 YAML     │   Researcher 工具 / DB
   文档 / 录屏 / 测试         │   脱敏 / API 层 / 部署
        松耦合外围            │   紧耦合外围
                              │
          低门槛              ↓
```

**保护规则**：
- C **不直接修改** `backend/agents/` 下的核心代码。
- B 的代码**必须**经 L review 后才能合入 `main`（保护 Agent 协议与 Schema invariant）。
- L 不直接修改 `industry_packs/<pack>/` 下的 YAML（除非 C 不在场紧急修复），保证 C 的工作领地清晰可见。

## 2. 工作切分（4 阶段）

ddl 锚点：录屏粗剪 `2026-06-05`。本表按从启动日起的相对天数估算（AI Coding 工作流下，传统估算应压缩约 50%）。

| 阶段 | 时长 | L | B | C |
|---|---|---|---|---|
| **P0 对齐** | 0.5 天 | 讲解架构 / Schema / Cursor rules / TRAE 工作流；本仓库 `.cursor/` `.agents/skills/` 已就位 | 跑通 hello world；熟悉 LangGraph subgraph + Send 文档 | 跑通仓库；理解 industry_packs/ 结构 |
| **P1 MVP 冲刺** | 3-4 天 | Supervisor + Researcher×N + Analyst + Writer + QA 最简版；PG schema + Alembic 迁移；端到端跑通 1 个竞品 | Researcher 工具层（`fetch_url` / `parse_page` / `extract_structured` / `search_web` / `lookup_offline_snapshot`）；脱敏管线；evidence 入库 | AI Coding 行业包：`competitors.yaml` + `report_template.yaml` + `qa_rules.yaml` + `qa_semantic_prompt.txt`；演示数据集（4 竞品各 ≥15 条 evidence 手工准备 + 脱敏） |
| **P2 联调 + 前端** | 3-4 天 | 联调闭环 + QA reject 路径打通 + Skill Curator 异步任务 | FastAPI 路由层 + WebSocket 状态推送 + 集成测试 + Docker compose | 视技术储备承接前端 Battlecard 静态页（在 AI Coding 辅助下做 mock 数据展示），否则负责测试用例编写 + 文档美化 |
| **P3 录屏 + 答辩** | 1-2 天 | 录屏主线 + 答辩 PPT 主稿 | bug 修复 + 部署脚本 + 本地一键启动验证 | 录屏次拍剪辑 + 答辩 PPT 美化 + 提交材料整理（数据来源清单 / 许可证 / 脱敏记录） |

**关键交接物**（每阶段结束必须存在）：

| 阶段 | 交接物 | 验证方式 |
|---|---|---|
| P0 | 三人都能 `make dev` 启动本地服务 | 截图 + 互相确认 |
| P1 | 端到端单竞品 run 可完成；演示数据集就位；YAML 行业包就位 | `pytest backend/tests/integration/test_e2e_single_competitor.py` 通过 |
| P2 | 4 竞品完整 run + Battlecard 报告页可视化 + QA reject 闭环触发 | 录屏前端 + 后端各一段 30s 演示 |
| P3 | 录屏粗剪 + 答辩 PPT + 提交材料 | 团队三人完整过一遍录屏 |

## 3. 分支模型（GitHub Flow + 人名首字母）

**第一性原理**：3 人 13 天，分支管理只需要解决 3 件事：

1. **隔离不同人的并行工作**（避免相互踩脚）
2. **保护 `main` 始终可演示**
3. **每个 PR 可追溯到具体作者**

为此**只需要**：一个 `main` 长期分支 + 每人开自己的短命 feature 分支。**不需要** `dev` 集成分支、不需要按 feat/fix/chore 分类前缀——这些是大团队工程，3 人小团队是过度设计。

```text
main             ──●──●──●──●──●──●──   始终可演示，PR 一步合入
                    ↑  ↑  ↑  ↑  ↑  ↑
wh/sup-loop      ──●──┘  │  │  │  │
xx/db-migration       ──●┘  │  │  │
yy/ai-coding-pack          ──●  │  │
xx/fetch-tool                   ●──┘  │
yy/cursor-data                        ●
```

### 3.1 分支命名约定

**格式**：`<作者首字母>/<短描述>`

- **作者首字母**：本仓库内三人各自姓名拼音首字母（例 `wh` / `xx` / `yy`），P0 对齐时确定并写入此处。
- **短描述**：3-5 个英文词，连字符分隔，**只描述做什么**——type 信息在 commit message 里，不在分支名里。

| 示例 | 谁开 | 内容 |
|---|---|---|
| `wh/supervisor-loop` | L | Supervisor 主循环 |
| `wh/qa-reviewer` | L | QA Reviewer Agent |
| `xx/fetch-url-tool` | B | Researcher 的 `fetch_url` 工具 |
| `xx/db-migration-init` | B | 初始 Alembic 迁移 |
| `yy/ai-coding-pack` | C | AI Coding 行业包 YAML |
| `yy/cursor-evidence-seed` | C | Cursor 竞品演示数据 |

**为什么不把 `feat/` / `fix/` / `chore/` 当分支前缀**：这些是 **commit type**（见 §5），用于描述"这次提交的性质"。分支前缀的作用完全不同——是标识"**谁在做什么**"，让 `git branch -a` 一眼能看出归属。两个概念混用会丢失作者信息。

**短命原则**：单个 feature 分支寿命 **≤2 天**，第一个工作日就该有 PR 合入 `main`。超过 2 天没合的分支强制砍掉重开（避免长寿命分支导致冲突地狱）。

### 3.2 `main` 分支保护

GitHub 仓库设置里给 `main` 加一条 Branch Protection Rule 即可：

- ✅ Require pull request before merging（必须经 PR）
- ✅ Require approval from §4.2 指定的 reviewer
- ❌ 不开启 "禁止 force push" 等大团队选项——3 人信任成本足够低

### 3.3 你现在马上开始后端编码，该开哪个分支？

```bash
git checkout main
git pull
git checkout -b wh/agent-skeleton    # L 的第一个 feature 分支
# ... 写代码、commit ...
git push -u origin wh/agent-skeleton
# 在 GitHub 开 PR → main
```

分支名替换为你自己的首字母 + 当前做的具体事。Agent 骨架做完合入 `main` 后，下一个功能（如 Supervisor 决策循环）就开 `wh/supervisor-loop`，依此类推。**任何情况下都不要直接在 `main` 上 commit。**

## 4. PR 规则（轻量但有锚点）

### 4.1 PR 必备字段

PR 模板（建议放 `.github/pull_request_template.md`）：

```markdown
## 改动摘要
（1-2 句，what + why）

## 涉及范围
- [ ] backend/agents/
- [ ] backend/api/
- [ ] backend/db/
- [ ] frontend/
- [ ] industry_packs/
- [ ] data/demo/
- [ ] docs/
- [ ] tests/

## Schema / 协议变更（如有）
（涉及 docs/3 中任何字段或 AgentMessage 协议时必须勾选并描述）
- [ ] 是
- [ ] 否

## AI Coding 工具使用
（哪个步骤用了 Cursor / TRAE，简短说明，可贴 prompt 片段）

## 验证
- [ ] 本地 `pytest backend/tests/` 通过
- [ ] 涉及 schema 变更时已更新 docs/3
- [ ] 涉及 Agent 协议变更时已更新 docs/2.5
```

### 4.2 review 责任

| PR 类型 | 必须 review 人 |
|---|---|
| 改 `backend/agents/` / `backend/core/` / `backend/db/migrations/` | L 必须 |
| 改 `docs/2` / `docs/2.5` / `docs/3` | L 必须 |
| 改 `industry_packs/` / `data/demo/` | L 一眼扫，不阻塞 |
| 改 `frontend/` | L 必须 |
| 改 `docs/` 其它 / `chore/` | 自合（self-merge）允许 |

**不强制队员之间相互 review**——避免"为什么不这样写"无意义循环；review 集中在 L，保护核心 invariant。

## 5. Commit 规范

采用 [Conventional Commits](https://www.conventionalcommits.org/)：

```text
<type>(<scope>): <short subject in lowercase>

<optional body explaining why, not what>

<optional footer, e.g. Refs #12 / [trae] / [cursor]>
```

### 5.1 type 取值

| type | 用途 |
|---|---|
| `feat` | 新功能 |
| `fix` | bug 修复 |
| `docs` | 文档 |
| `config` | 行业包 / YAML / 环境配置 |
| `data` | 演示数据 / seed |
| `refactor` | 重构（无功能变化） |
| `test` | 测试 |
| `chore` | 构建 / CI / 依赖 / 杂项 |

### 5.2 scope 取值

`supervisor` / `researcher` / `analyst` / `writer` / `qa` / `curator` / `api` / `db` / `frontend` / `ai_coding`（行业包名） / `2`（文档编号） / `2.5` / `3` / etc.

### 5.3 示例

```text
feat(supervisor): add ConductResearch tool with dynamic K fan-out
fix(researcher): handle pricing page 403 with single-shot retry
docs(2.5): clarify compress_context fallback semantics
config(ai_coding): add windsurf competitor profile
data(cursor): seed 18 evidence from G2 reviews 2026-Q1
chore(ci): add ruff to pre-commit
```

### 5.4 禁止

- ❌ "update" "fix bug" "wip" 等无信息量的 subject
- ❌ 一个 commit 跨多个 scope（拆开提交）
- ❌ 直接在 `main` commit（必须走 feature branch + PR）

## 6. AI Coding 协作机制与痕迹保留

评分项明确要求"TRAE 等 AI 编程工具的使用痕迹清晰，体现深度协作"（占总分 10%）。本节是该评分项的硬证据来源。

### 6.1 工具配置已沉淀在仓库

| 资产 | 路径 | 用途 |
|---|---|---|
| Cursor Rules | `.cursor/rules/*.mdc` | 工程纪律、Git 安全、env 安全 |
| Cursor Hooks | `.cursor/hooks/*` | 提交前安全门禁 |
| Agent Skills | `.agents/skills/*/SKILL.md` | 复用程序（agent-debugging、testing、git-change-control 等） |
| Agent 文件 | `AGENTS.md` / `CLAUDE.md` | 跨工具共享的工程约束 |

这些文件**进 git**，不在 `.gitignore`。评委 clone 即可看到。

### 6.2 一次性配置

#### Cursor 用户

Cursor Settings > Agent > Attribution **开启**（默认即开启）。生效后 Cursor Agent 创建的 commit 与 PR 自动附加 trailer `Made with Cursor`。

参考：<https://cursor.com/help/integrations/git>

#### TRAE 用户

```bash
git config commit.template .gitmessage
```

仓库根 `.gitmessage` 内容（已入仓）：

```text


Co-Authored-By: TRAE <noreply@bytedance.com>
```

生效后每次 `git commit` 自动附加 `Co-Authored-By` trailer；GitHub PR 页面自动渲染为 co-author 头像。

### 6.3 评委可验证的证据位置

| 证据 | 位置 | 验证 |
|---|---|---|
| 工具配置入仓 | `.cursor/` / `.agents/` / `AGENTS.md` / `.gitmessage` | `git ls-files` |
| Cursor Agent 提交 | commit trailer `Made with Cursor` | `git log --grep "Made with Cursor"` |
| TRAE 用户提交 | commit trailer `Co-Authored-By: TRAE` | GitHub PR co-author 头像；或 `git log --format='%(trailers)'` |
| Cloud Agent 分支与 PR | GitHub `agent/*` 分支 + Cloud Agent 撰写的 PR description | GitHub Branches / Pull Requests 页 |
| 本地 session 历史 | `~/.cursor/projects/<slug>/agent-transcripts/*.jsonl`、Cursor/TRAE 各自 `state.vscdb` | 答辩 Q&A 引用（不入仓） |

## 7. 同步机制（轻量但有节奏）

| 形式 | 频率 | 时长 | 内容 |
|---|---|---|---|
| 早会（异步）| 每个工作日早上 | 5 分钟 | 微信 / 群里文字汇报：昨天做完什么 / 今天做什么 / 阻塞点 |
| 联调同步 | P1 末期、P2 末期 | 30 分钟 | 视频会议：跑通端到端 + 集中解决跨人接口问题 |
| 答辩彩排 | P3 | 60 分钟 × 2 次 | 视频会议：完整过录屏 + 模拟 Q&A |

**决策机制**：
- Schema / 协议 / 架构层级决策 → L 拍板
- 工具选型（如某个 Python 库的选择） → 提议人选定，L 一眼扫不阻塞
- 工时安排 / 任务交换 → 当事人自行协商
