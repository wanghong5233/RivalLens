# RivalLens Rules and Hooks

Index of the agent guardrails configured in this repository.

## Agent Rules

- `AGENTS.md` — root engineering rules for the RivalLens monorepo.

## Cursor

- `.cursor/rules/engineering.mdc` — always-on RivalLens repository model, Git safety, env safety.
- `.cursor/rules/env-secrets.mdc` — scoped rules for env/config files.
- `.cursor/rules/core-principles.mdc` — cross-project engineering invariants (from `agent-engineering-kit`).
- `.cursor/rules/cursor-package-boundaries.mdc` — how `.cursor/` rules/skills/commands/hooks divide responsibility.
- `.cursor/rules/configuration-management.mdc` — config centralization, typed validation, no magic numbers.
- `.cursor/rules/agent-runtime-contracts.mdc` — LLM / RAG / tool / async durability and failure contracts.
- `.cursor/commands/review.md`, `.cursor/commands/retro.md` — manual review and retrospective workflows.
- `.cursor/hooks.json` — project-level hook configuration.
- `.cursor/hooks/safety_guard.py` — blocks `git add .` patterns and reads of real env files.
- `.cursor/hooks/block-dangerous-shell.py` — blocks force-push / hard reset / branch -D / commit --amend / rm -rf / Remove-Item -Recurse -Force and similar (10 patterns, cross-platform, `failClosed: true`).
- `scripts/scan_secrets.py` — scans staged/tracked files for API key / token / `ep-...` leakage patterns.
- `.githooks/pre-commit` — local git pre-commit secret scan gate.
- `.github/workflows/secret-scan.yml` — server-side secret scan gate on push/PR.

## Codex

- `.codex/hooks.json` — project-level hook configuration.
- `.codex/hooks/safety_guard.py` — blocks broad/destructive commands and real env-file edits.
- `.codex/rules/git-safety.rules` — execpolicy rules for dangerous Git commands (Codex Rules are experimental; hook is the real enforcer).

## Claude Code

- `.claude/settings.json` — Claude Code hook configuration.
- `.claude/hooks/safety_guard.py` — blocks real env-file edits and broad/destructive commands.
- `.claude/prompts/security-rules.md` — generic security guidance.

## Trae

- `.trae/project_rules.md` — Trae project rules (primary path).
- `.trae/rules/project_rules.md` — compatibility copy for the nested-rules path.

## Skill Pointers

`.codex/skills`, `.cursor/skills`, `.claude/skills`, and `.trae/skills` are pointer files; the actual skills live in `.agents/skills/`.

## Maintenance Rule

Hooks and rules in this repository are workspace guardrails inspired by reusable engineering practice. Keep their descriptions free of brand names from other workspaces.
