# RivalLens Agent Guidelines

Engineering guardrails for the RivalLens repository — an AI-driven competitive intelligence agent system built for the ByteDance AI Full-Stack Challenge.

## Scope

This file is the persistent Codex instruction layer for RivalLens. Keep it stable, short, and operational.

- Use it for repository boundaries, safety rules, recurring workflows, and skill routing.
- Do not use it for one-off plans, chat history, PRDs, secrets, or long troubleshooting notes.
- If a procedure grows into a multi-step playbook, move the details into `.agents/skills/` and keep only the trigger here.
- Target size: about 80-160 lines and under 8-12 KiB. If it approaches 20 KiB, split rules into skills.

## Repository Model

Single-repository monorepo. Top-level packages:

- `backend/` — Python 3.11 + FastAPI + LangGraph agent core, PostgreSQL persistence.
- `frontend/` — React + Vite + TypeScript visualization console.
- `docs/` — source-of-truth specs (problem, demo, architecture, schema, ownership, prior art).
- `backend/skills/` — skill library (`applies_to` in `qa_rule`, `prompt_template`, `source_routing`) loaded via `load_skill` / `read_skill_file`.
- `backend/demo_fixtures/` — demo seeds (competitor autocomplete source, not a hard constraint set).
- `configs/` — shared YAML/JSON configuration.
- `data/` — raw and processed competitive data (gitignored where appropriate).
- `scripts/` — utility scripts.

## Always-On Engineering Rules

- Read existing patterns before introducing new ones.
- Fail fast at boundaries; do not silently swallow exceptions or return empty defaults to hide failures.
- Prefer explicit file paths over broad operations.
- Use `rg` / `rg --files` first for text and file search; fall back only if `rg` is unavailable.
- Never use `git add .` or `git add -A`.
- Never run destructive Git or filesystem commands without explicit approval (`git reset --hard`, `git clean -fd`, recursive forced deletes).
- Preserve unrelated dirty files when staging.
- Never commit real `.env` values, API keys, tokens, credentials, or cookies — only `.env.example` placeholders.
- Type hints on all Python function signatures; explicit types on TypeScript boundaries.
- Comments explain WHY, never WHAT. No narrative comments that restate code.
- No bare `except` / `except Exception` — catch specific exceptions.
- No wrapper classes that merely delegate (avoid Ghost Layers).
- YAGNI: no features beyond what is explicitly requested.

## Verification

Canonical commands (skills delegate here for exact commands):

- Backend tests run inside the dev container: `docker compose -f backend/docker-compose.dev.yml exec -T rivallens_api pytest <paths> -q`.
- Prefer targeted pytest paths over the full suite unless the change is broad.
- Frontend has no test runner yet; verify with `npm run type-check` (and `npm run build` for broad changes) in `frontend/`.
- Commit style: follow the recent `git log` of this repo.

## Codex And Cursor Collaboration

Cursor and Codex are separate execution contexts. Cursor Chat / Composer history is not automatically available to Codex CLI.

- Treat IDE context as hints about open files, not as guaranteed file contents.
- When decisions depend on file contents, read the file from disk.
- Ask the user for a plan path when no `.plan.md` file is clearly provided or open.
- Prefer one execution line: Cursor drafts the plan; Codex implements, runs commands, verifies, and reports.
- Do not edit a Cursor plan unless the user explicitly asks to update the plan itself.

## Cursor Plan Execution

Use this protocol when the user explicitly asks to execute an open/current Cursor plan. Matching phrases include `执行当前打开的 Cursor plan`, `按当前 plan 执行`, `build current plan`, and `run the open plan`. Do not treat vague phrases like `继续`, `开始`, or `开干` as plan execution unless the current conversation clearly refers to a Cursor plan.

### Plan Selection

- Prefer the `.plan.md` file listed in IDE open tabs.
- If exactly one `.plan.md` file is open, use it as the execution plan.
- If multiple `.plan.md` files are open, ask which one to use before editing.
- If no `.plan.md` file is open, ask for the plan path.
- Read the plan first with `Get-Content -Encoding UTF8` on Windows PowerShell.
- Treat the plan as a strong proposal, not as authority over repository rules, user constraints, security, or engineering judgment.

### Pre-Flight

Before editing:

- Summarize the objective, stages, write scope, and expected verification.
- Inspect `git status --short`.
- Separate pre-existing user changes from planned edits.
- Load only the relevant skills for the planned work.
- Check for conflicts with env, secrets, migrations, routing, tests, service boundaries, and repository rules.
- Ask a focused question only when ambiguity could cause damage or wasted implementation.

### Execution

- Execute by the plan's stages instead of broad refactors.
- Keep each stage scoped to its stated outcome.
- Use existing patterns, package managers, service layers, and API boundaries.
- Do not expand the plan into persistence, deployment, destructive cleanup, or commits unless explicitly requested.
- If the plan is materially wrong, explain the mismatch and choose the smallest safe correction or ask for direction.

### Verification And Handoff

- Run verification proportional to the change: tests, type checks, lint, compile checks, focused scripts, health checks, or document-only review.
- If verification cannot run because of missing dependencies, services, env, Docker, or network, state the exact blocker and what was still checked.
- Before finishing, review changed files, confirm unrelated dirty files were preserved, and summarize completed work, verification, and residual risks.

## Windows PowerShell And Sandbox

When using Windows PowerShell, avoid silent encoding and sandbox failures.

- Read Markdown, JSON, YAML, TypeScript, TSX, Python, shell scripts, and Chinese text with `Get-Content -Encoding UTF8`.
- For previews, combine UTF-8 decoding with explicit limits, such as `Get-Content -Encoding UTF8 -TotalCount 120`.
- If output looks garbled, retry with explicit UTF-8 before drawing conclusions.
- If Codex reports `windows sandbox: spawn setup refresh` or logs show `os error 740`, check `%USERPROFILE%\.codex\.sandbox\sandbox.YYYY-MM-DD.log`.
- The usual Windows fix is `[windows] sandbox = "unelevated"` in `~/.codex/config.toml`; restart Codex after changing config.
- Confirm commands actually ran by checking for normal command output, not only assistant narration.

## Skills

Reusable procedures live under `.agents/skills/`. Each skill has a YAML `description` that controls when it auto-loads.

Skill usage should stay narrow and relevant. Use the smallest set that covers the request.

**Agent engineering (cross-project, from `agent-engineering-kit`):**

- `agent-debugging` — system-level debugging across UI / API / retrieval / tool / provider / async / persistence layers
- `llm-observability-and-evals` — trace contracts, decision logs, golden eval sets, pass gates
- `tool-and-mcp-design` — tool/MCP schema, permission model, error semantics, idempotency
- `llm-cost-optimizer` — per-feature cost logging, model routing, prompt cache, output control
- `bootstrap-cursor-package` — when starting a new agent project's `.cursor/`

**Writing & documentation:**

- `writing-deslop` — shared anti-slop tone core (去AI味); pairs with every format skill below
- `writing-architecture-docs` — current-state + first-principles design/ADR docs
- `writing-readme` — 10-second-scannable READMEs (standard-readme spec)
- `writing-tech-article` — high-density tech blog + cross-project engineering playbook variant
- `writing-problem-records` — active Known-Issues/Backlog + converged Pitfall Archive
- `writing-skill` — meta: how to write a good SKILL.md

**Project workflow:**

- `engineering-quality` — general code quality
- `env-secrets` — env / secret / token hygiene
- `git-change-control` — safe Git workflow
- `pr` — branch and PR conventions
- `review-checklist` — pre-merge review bias
- `testing-debugging` — verification, Vitest mocks, and debug logging

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
- Is this `AGENTS.md` still in the sweet spot: stable rules, about 80-160 lines, under 8-12 KiB, and no copied project-specific leftovers?
