---
name: git-change-control
description: Git workflow and dirty-worktree control. Use before staging, committing, branching, rebasing, creating PRs, inspecting git status, or protecting unrelated changes.
---

# Git Change Control

## Dirty Worktree Rules

- Always inspect `git status --short` in the target repository before editing and before committing.
- Treat pre-existing dirty files as user work unless proven otherwise.
- Do not revert, overwrite, format, move, stage, or commit unrelated changes.
- If an unrelated dirty file is in the same area, read enough to avoid conflicts and edit around it.

## Staging

- Prefer explicit paths: `git add path/to/file`.
- Avoid `git add .` in multi-repo or dirty worktrees.
- Review `git diff --cached` before committing.
- Do not stage local env files, generated caches, build output, or unrelated examples.

## Commit Hygiene

- Commit one coherent change at a time.
- Keep walking skeleton commits separate from later business integration commits.
- Use the target repository's commit style; infer it from recent `git log` or the repo's `AGENTS.md`.

## Branches and PRs

- Confirm branch strategy from the target repo before opening PRs; check `AGENTS.md` or existing branches for the development-vs-release target.
- Do not PR directly to a protected/release branch unless explicitly asked.
- PR descriptions should state what changed, why, how it was tested, and any skipped verification.

## Safe Git Commands

Use non-destructive inspection first:

```bash
git status --short
git diff -- path/to/file
git diff --cached
git log --oneline -5
git branch --show-current
```

Do not use destructive commands like `git reset --hard`, `git checkout --`, or broad clean operations unless the user explicitly requests them and the target is clear.

## Final Check

- `git status --short` shows only intended changes or known unrelated dirty files.
- The commit, if created, contains only files belonging to the requested task.
- The summary explicitly mentions unrelated dirty files that were preserved.
