---
name: env-secrets
description: Environment variable, secret, token, local URL, and config safety guide. Use before editing .env files, env examples, service base URLs, JWT handling, API keys, Docker Compose environment blocks, or config docs.
---

# Env and Secrets

## Safety Rules

- Never commit real secrets, API keys, tokens, passwords, private URLs, or `.env` files with real values.
- Treat provider endpoint IDs (for example `ep-...`) as sensitive and never keep real values in docs or code.
- Keep real local values in ignored local env files.
- Use `.env.example` files for names, comments, placeholders, and safe defaults only.
- Do not copy unrelated team secrets into a local project because a neighboring repository has them.
- Redact tokens in logs and final summaries.

## Env Source of Truth

- Identify which file or runtime owns a setting before changing it.
- Avoid duplicate defaults that fight each other, such as `.env` saying one value and Docker Compose overriding it.
- If Docker Compose passes an env var, confirm whether it should preserve the caller's value or provide a safe local default.
- Prefer one clear source of truth for provider selection, base URLs, feature flags, and local ports.

## Naming

- Use project-specific prefixes for cross-service temporary integrations.
- For temporary cross-service integrations, prefer names that include `DEV` or another explicit scope marker.
- Keep env names stable and descriptive: `<SERVICE>_<SCOPE>_<SETTING>`.

## Server vs Client Exposure

- Keep secrets server-side.
- Do not expose private service base URLs, tokens, or keys to browser bundles unless the project explicitly marks them public.
- In Next.js-style projects, treat `NEXT_PUBLIC_*` or equivalent public prefixes as browser-visible.

## JWT and Tokens

- Do not invent bypass headers.
- Use the target service's actual login/demo-token flow.
- Store and forward tokens only on the server side for BFF integrations unless product design explicitly requires browser ownership.
- Never log full `Authorization` headers.

## Env Example Changes

When updating examples:

- Add comments explaining purpose, safe default, and local override.
- Use placeholders such as `your-api-key` rather than real-looking credentials.
- Keep unrelated env example churn out of focused commits.
- If an existing dirty env example change is unrelated, leave it alone.

## Final Check

- Search changed files for `sk-`, `Bearer `, `token`, `secret`, `password`, `api_key`, and provider-specific key names.
- Search for endpoint-ID literals like `ep-<digits>-<suffix>` and replace them with placeholders.
- Run `python scripts/scan_secrets.py --staged` before commit.
- Confirm ignored local env files were not staged.
- Confirm Docker/env defaults do not silently override the intended local config.
