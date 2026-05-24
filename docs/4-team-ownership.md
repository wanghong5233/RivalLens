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

## 4. PR 流程（gh CLI 命令为主）

3 人敏捷只有一条铁律：**B/C 不能自合自己的代码，必须 L 过一遍**。这条铁律不靠纪律，靠 protection 物理约束（§2 的 `Required approvals: 1` + B/C 是 Write 不是 admin → B/C 在技术上无法合自己 PR）。

下面三个场景覆盖所有 PR。

### 4.1 一次性配置

```powershell
gh auth login          # 选 github.com / HTTPS / 浏览器授权,只配一次
```

### 4.2 场景 A：作者开 PR（L / B / C 通用）

```powershell
git push -u origin <你的分支>
gh pr create           # 交互式问标题和 body,或加 --fill 把 commit message 当 PR 内容
```

PR 标题用 commit type 起头，例如：

```text
feat(researcher): add fetch_url tool with robots.txt check
docs(2): clarify desensitize boundary
```

PR body 简短即可：

```markdown
## 改动摘要
（1-2 句 what + why）

## 涉及范围
backend/agents/ , docs/2

## 验证
本地 pytest 通过 / 文档改动无需测试
```

不强制填模板。

### 4.3 场景 B：L 合 B/C 的 PR（AI 风险扫描 + approve + merge）

L 在合 B/C 的 PR 前**必须**用 AI 扫一遍 diff。这是这套流程的核心质量门。

```powershell
gh pr diff <PR编号>                              # 看 diff
gh pr checkout <PR编号>                          # 把分支拉到本地,让 Cursor agent 在 IDE 里扫
# ↑ 二选一,看变更量大小

gh pr review <PR编号> --approve --body "LGTM"   # AI 确认无风险后 L approve
gh pr merge <PR编号> --squash --delete-branch   # 合入 main + 自动删远端分支
```

AI 风险扫描清单（让 Cursor agent 对照检查）：

- 有没有 hardcode 的 API Key / 密码 / cookie / JWT
- 有没有破坏 `docs/3` Schema 不变量（字段删 / 类型改 / Literal 枚举改）
- 有没有改已合并的 Alembic 迁移历史（只能加新迁移版本）
- 有没有引入 GPL / AGPL 依赖
- 有没有 `except Exception` / 静默 fallback 返回 `[]` / 空 dict 隐藏失败
- 有没有删别人的代码或文档
- 有没有 git config / hook bypass / `--no-verify`

### 4.4 场景 C：L 合自己的 PR（admin bypass）

L 自己开的 PR 因为 GitHub 不允许 approve 自己，需要 admin 权限 bypass approval：

```powershell
gh pr merge <PR编号> --squash --delete-branch --admin
```

`--admin` 只 L 能用（B/C 没 admin 权限，对他们这条命令会报错）。**L 自审等于无审**，敏捷阶段接受这个折扣，换回 L 不被流程卡住。

### 4.5 收尾（三种场景通用）

```powershell
git checkout main
git pull origin main
git fetch --prune              # 同步远端已删的分支引用
git branch -D <已合的分支>     # squash 后本地视角是 unmerged,必须 -D 强删
```

### 4.6 合入方式

统一 **Squash and merge**：feature 分支上 N 个 commit 压成 1 个进 main，main 历史保持线性可读。`gh pr merge --squash` 已经是这个行为。

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
