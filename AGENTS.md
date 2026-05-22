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

Reusable procedures live under `.agents/skills/`:

- `engineering-quality` — general code quality
- `env-secrets` — env and secret hygiene
- `git-change-control` — safe Git workflow
- `pr` — pull request and branch workflow
- `review-checklist` — pre-merge review bias
- `testing` / `testing-debugging` — verification
- `debug` — debug logging
- `typescript` / `react` — frontend conventions

## Review Bias

Before finalizing changes:

- Is the change limited to what was requested? (YAGNI)
- Are env and secret changes safe?
- Are logs free of sensitive data?
- Is verification proportional to the risk?
- Are unrelated dirty files untouched?
