# RivalLens Trae Rules

Single-repository monorepo. Top-level packages: `backend/` (Python/FastAPI/LangGraph + PostgreSQL), `frontend/` (React/Vite/TypeScript), `docs/` (specs).

Use shared skills via `.trae/skills -> ../.agents/skills`.

Always use: `engineering-quality`, `env-secrets`, `git-change-control`, `testing-debugging`, `pr`, `review-checklist`.

For frontend work also use: `typescript`, `react`.

Guardrails: preserve unrelated dirty files; run commands from the repo root; prefer explicit paths; never use `git add .` / `git add -A` / `git reset --hard` / `git clean -fd` / recursive forced delete without explicit approval; never commit real `.env` values, tokens, secrets, credentials, cookies, API keys, private keys, or private URLs; keep temporary integrations visibly temporary.
