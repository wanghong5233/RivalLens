# RivalLens Agent Guidelines

Engineering guardrails for the RivalLens repository — an AI-driven competitive intelligence agent system built for the ByteDance AI Full-Stack Challenge.

## Repository Model

Single-repository monorepo. Top-level packages:

- `backend/` — Python 3.11 + FastAPI + LangGraph agent core, PostgreSQL persistence.
- `frontend/` — React + Vite + TypeScript visualization console.
- `docs/` — source-of-truth specs (problem, demo, architecture, schema, ownership, prior art).
- `industry_packs/` — pluggable vertical-domain configurations.
- `configs/` — shared YAML/JSON configuration.
- `data/` — raw and processed competitive data (gitignored where appropriate).
- `scripts/` — utility scripts.

## Always-On Engineering Rules

- Read existing patterns before introducing new ones.
- Fail fast at boundaries; do not silently swallow exceptions or return empty defaults to hide failures.
- Prefer explicit file paths over broad operations. Never use `git add .` or `git add -A`.
- Never run destructive Git or filesystem commands without explicit approval (`git reset --hard`, `git clean -fd`, recursive forced deletes).
- Preserve unrelated dirty files when staging.
- Never commit real `.env` values, API keys, tokens, credentials, or cookies — only `.env.example` placeholders.
- Type hints on all Python function signatures; explicit types on TypeScript boundaries.
- Comments explain WHY, never WHAT. No narrative comments that restate code.
- No bare `except` / `except Exception` — catch specific exceptions.
- No wrapper classes that merely delegate (avoid Ghost Layers).
- YAGNI: no features beyond what is explicitly requested.

## Skills

Reusable procedures live under `.agents/skills/`. Each skill has a YAML `description` that controls when it auto-loads.

**Agent engineering (cross-project, from `agent-engineering-kit`):**

- `agent-debugging` — system-level debugging across UI / API / retrieval / tool / provider / async / persistence layers
- `llm-observability-and-evals` — trace contracts, decision logs, golden eval sets, pass gates
- `tool-and-mcp-design` — tool/MCP schema, permission model, error semantics, idempotency
- `llm-cost-optimizer` — per-feature cost logging, model routing, prompt cache, output control
- `bootstrap-cursor-package` — when starting a new agent project's `.cursor/`

**Writing & documentation:**

- `writing-architecture-docs` — current-state + first-principles, no narrative / no AI filler
- `writing-readme` — 10-second-scannable READMEs
- `writing-tech-article` — high-density technical writing
- `writing-pitfall-archive` — postmortem archive, prevent recurring failures
- `writing-issue-backlog` — evidence-first issue records
- `writing-engineering-playbook` — cross-project engineering intuition
- `writing-skill` — meta: how to write a good SKILL.md

**Project workflow:**

- `engineering-quality` — general code quality
- `env-secrets` — env / secret / token hygiene
- `git-change-control` — safe Git workflow
- `pr` — branch and PR conventions
- `review-checklist` — pre-merge review bias
- `testing` / `testing-debugging` — verification
- `debug` — debug logging

**Tech-stack (frontend, will trigger only on .ts/.tsx):**

- `typescript` / `react`

## Commands

Manual workflows under `.cursor/commands/`:

- `/review` — risk-focused code review
- `/retro` — session retrospective and learning capture

## Review Bias

Before finalizing changes:

- Is the change limited to what was requested? (YAGNI)
- Are env and secret changes safe?
- Are logs free of sensitive data?
- Is verification proportional to the risk?
- Are unrelated dirty files untouched?
