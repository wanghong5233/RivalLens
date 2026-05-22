# RivalLens Rules and Hooks

Index of the agent guardrails configured in this repository.

## Agent Rules

- `AGENTS.md` — root engineering rules for the RivalLens monorepo.

## Cursor

- `.cursor/rules/engineering.mdc` — always-on rules for repository model, Git safety, env safety, engineering discipline.
- `.cursor/rules/env-secrets.mdc` — scoped rules for env/config files.
- `.cursor/hooks.json` — project-level hook configuration.
- `.cursor/hooks/safety_guard.py` — blocks broad/destructive shell commands and reads of real env files.

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
