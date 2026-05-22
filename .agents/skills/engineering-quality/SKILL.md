---
name: engineering-quality
description: General engineering quality rules. Use before code edits, refactors, API/service changes, TypeScript or Python modifications, architecture cleanup, or code review.
---

# Engineering Quality

## Scope Control

- Solve the requested problem with the smallest coherent change.
- Prefer established local patterns over new abstractions.
- Add an abstraction only when it reduces real duplication or clarifies a repeated boundary.
- Avoid unrelated formatting churn, import churn, file moves, and broad refactors.

## Type and Contract Discipline

- Prefer precise types over `any`; use `unknown` for unstable external payloads.
- Do not declare temporary downstream response fields as final contracts.
- Validate inputs at API boundaries with the framework's local validation tool (`zod`, Pydantic, etc.).
- Keep error shapes consistent with neighboring endpoints or service methods.

## Service Boundaries

- Put external calls behind a service/client layer instead of calling remote services directly from UI code.
- Centralize base URLs, auth headers, timeouts, and response parsing in the client layer.
- Do not let UI components own credentials, tokens, private service URLs, or server-only config.
- Prefer health checks and read-only calls before mutations in new integrations.

## Frontend Quality

- Reuse the project's existing component library and layout primitives.
- Keep route/page files thin when the project has a feature-layer convention.
- Do not fetch server data directly in components if the project has a service/store/SWR pattern.
- Use i18n for user-facing text when the project already uses i18n.
- Check responsive layout and loading/error states for user-facing UI.

## Backend Quality

- Keep routers/controllers thin; put reusable HTTP or business integration logic in services.
- Log failures with enough context to diagnose, but never log secrets or full tokens.
- Rethrow framework-specific errors when appropriate; wrap unknown failures consistently.
- Prefer idempotent operations for migrations, setup scripts, and repeatable dev tasks.

## Review Checklist

Before finishing:

- No leftover `console.log` / `print` debug spam.
- No hardcoded secrets, tokens, private keys, or real credentials.
- No accidental persistence or downstream consumption in a walking skeleton.
- No duplicated utility that already exists locally.
- New logic has focused verification proportional to risk.
- Any skipped verification is stated clearly.
