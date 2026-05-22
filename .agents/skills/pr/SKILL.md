---
name: pr
description: Pull request and branch workflow. Use when the user asks to create a PR, submit changes, prepare a branch, summarize commits, or follow team PR conventions.
---

# PR Workflow

## Branch Strategy

For RavenWeb/LobeHub-style work:

- `canary` is the development target.
- `main` is the release branch.
- Do not PR directly to `main` unless the task is explicitly release/hotfix.

For other repositories, inspect local branch conventions before assuming this strategy.

## Before PR

Run from the target repository:

```bash
git branch --show-current
git status --short
git log --oneline --decorate -5
git diff --stat
```

- Do not include unrelated dirty changes.
- Prefer explicit staging paths.
- Review `git diff --cached` before committing.

## Commit and PR Content

- Keep commits coherent and scoped.
- Use the target repo's commit style; RavenWeb commonly uses gitmoji-style messages.
- PR body should explain what changed, why, how it was tested, and remaining risks.
- Use English for RavenWeb PR content unless the team asks otherwise.

## Duplicate PRs

- Check whether the current branch already has an open PR before creating another.
- If a PR exists, report it instead of creating a duplicate.

## Safety

- Never include secrets, `.env` real values, local-only config, or unrelated generated output.
- Mention skipped tests or unavailable services clearly.
