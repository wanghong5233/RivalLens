---
name: pr
description: Pull request and branch workflow. Use when the user asks to create a PR, submit changes, prepare a branch, summarize commits, or follow team PR conventions.
---

# PR Workflow

## Branch Strategy

- Inspect the target repo's branch convention before opening a PR; check `AGENTS.md` or existing branches.
- Identify the development target vs the release branch (they often differ).
- Do not PR directly to a protected/release branch unless the task is explicitly release/hotfix.

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
- Use the target repo's commit style; infer it from recent `git log` or `AGENTS.md`.
- PR body should explain what changed, why, how it was tested, and remaining risks.
- Match the repo's existing PR language convention.

## Duplicate PRs

- Check whether the current branch already has an open PR before creating another.
- If a PR exists, report it instead of creating a duplicate.

## Safety

- Never include secrets, `.env` real values, local-only config, or unrelated generated output.
- Mention skipped tests or unavailable services clearly.
