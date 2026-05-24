# RivalLens Git 协作规范

本文只描述 git 工作流：分支、commit、PR、main 保护、AI Coding 痕迹。
团队角色、项目排期、同步机制不在此文档范围。

## 1. 分支模型

- 长期分支只有 `main`，始终可演示，不能直接 commit/push
- 短命 feature 分支寿命 ≤ 2 天，超时砍掉重开避免冲突地狱
- 一个 feature 一条分支，不在同一分支堆多个任务

### 1.1 分支命名

格式：`<作者首字母>/<短描述>`

- 作者首字母：本仓库内三人各自姓名拼音首字母（`wh` / `xx` / `yy`，P0 对齐时确定）
- 短描述：3-5 个英文词，连字符分隔，只描述做什么

示例：

| 分支 | 谁开 | 内容 |
|---|---|---|
| `wh/supervisor-loop` | L | Supervisor 主循环 |
| `xx/fetch-url-tool` | B | Researcher 的 `fetch_url` 工具 |
| `yy/ai-coding-pack` | C | AI Coding 行业包 YAML |

不要把 `feat/` `fix/` `chore/` 当分支前缀——这是 commit type（见 §3），不是分支前缀。分支前缀作用是标识"谁在做什么"，让 `git branch -a` 能看出归属。

## 2. main 分支保护

仓库已转 public（GitHub Free 个人 private repo 不支持 branch protection），在 `Settings → Branches → Classic branch protection rule` 上启用：

- ✅ Require a pull request before merging
- ✅ Required approvals: 1（L 审核）
- ✅ Dismiss stale pull request approvals when new commits are pushed
- ✅ Require conversation resolution before merging
- ✅ Do not allow force pushes
- ✅ Do not allow deletions

L 拥有 admin，B / C 给 Write 权限。Write 推不到 `main`，只能 push feature 分支并开 PR。

## 3. Commit 规范

采用 [Conventional Commits](https://www.conventionalcommits.org/)：

```text
<type>(<scope>): <short subject in lowercase>

<optional body explaining why, not what>

<optional footer, e.g. Refs #12 / [trae] / [cursor]>
```

### 3.1 type

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

### 3.2 scope

`supervisor` / `researcher` / `analyst` / `writer` / `qa` / `curator` / `api` / `db` / `frontend` / `ai_coding`（行业包名） / `2`（文档编号） / `2.5` / `3` 等。

### 3.3 示例

```text
feat(supervisor): add ConductResearch tool with dynamic K fan-out
fix(researcher): handle pricing page 403 with single-shot retry
docs(2.5): clarify compress_context fallback semantics
config(ai_coding): add windsurf competitor profile
chore(ci): add ruff to pre-commit
```

### 3.4 禁止

- `update` / `fix bug` / `wip` 等无信息量 subject
- 一个 commit 跨多个 scope（拆开提交）
- 直接在 `main` 上 commit

## 4. PR 流程

### 4.1 标准步骤

```bash
git checkout main
git pull origin main
git checkout -b <首字母>/<短描述>
# ... 写代码 + commit ...
git push -u origin <分支>
# 去 GitHub 网页开 PR → main
```

### 4.2 PR 描述模板

```markdown
## 改动摘要
（1-2 句，what + why）

## 涉及范围
- [ ] backend/agents/
- [ ] backend/api/
- [ ] backend/db/
- [ ] frontend/
- [ ] industry_packs/
- [ ] docs/
- [ ] tests/

## Schema / 协议变更
（涉及 docs/3 字段或 AgentMessage 协议时勾选并描述）
- [ ] 是
- [ ] 否

## 验证
- [ ] 本地 `pytest backend/app/tests/` 通过
- [ ] 涉及 schema 变更已更新 docs/3
- [ ] 涉及 Agent 协议变更已更新 docs/2.5
```

### 4.3 review 责任

| PR 涉及范围 | 必须 review 人 |
|---|---|
| `backend/agents/` / `backend/app/service/` / Alembic 迁移 | L 必须 |
| `docs/2` / `docs/2.5` / `docs/3` | L 必须 |
| `frontend/` | L 必须 |
| `industry_packs/` YAML / `data/demo/` | L 一眼扫，不阻塞 |
| 其它 `docs/` / `chore/` | self-merge 允许 |

不强制队员之间相互 review；review 集中在 L 保护核心 invariant。

### 4.4 合入方式

PR 通过后用 **Squash and merge** 把 feature 分支压成一个 commit 合入 `main`，feature 分支合入后删除。

## 5. AI Coding 痕迹资产

评分项要求"AI 编程工具痕迹清晰可验证"（占总分 10%）。已沉淀在仓库的资产：

| 资产 | 路径 | 用途 |
|---|---|---|
| Cursor Rules | `.cursor/rules/*.mdc` | 工程纪律、Git 安全、env 安全 |
| Cursor Hooks | `.cursor/hooks/*` | 提交前安全门禁 |
| Agent Skills | `.agents/skills/*/SKILL.md` | 复用 Skill |
| Agent 文件 | `AGENTS.md` / `CLAUDE.md` | 跨工具共享约束 |

一次性配置：

- **Cursor**：Settings → Agent → Attribution 默认开启，Cursor Agent 创建的 commit 自动附 `Made with Cursor`
- **TRAE**：`git config commit.template .gitmessage`（仓库根 `.gitmessage` 已入仓，含 `Co-Authored-By: TRAE`）

验证：

```bash
git log --grep "Made with Cursor"
git log --format='%(trailers)'
```

## 6. 第一次上手

```bash
git clone https://github.com/wanghong5233/RivalLens.git
cd RivalLens
git checkout -b <首字母>/<你的第一个任务>
```

任务从 `docs/KNOWN_ISSUES_AND_BACKLOG.md` 按优先级认领，认领前在群里说一声避免撞车。
