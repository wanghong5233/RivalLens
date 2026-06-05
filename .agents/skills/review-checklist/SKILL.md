---
name: review-checklist
description: Pre-merge review checklist. Use before finalizing changes, reviewing diffs, preparing commits, or assessing PR risk.
---

# Review Checklist

## Correctness

- No leftover `console.log` / `console.debug`.
- Errors are not silently swallowed.
- `try/catch` async wrappers return awaited values where needed.
- The implementation is scoped, coherent, and compatible with existing patterns.

## Security

- No secrets, tokens, API keys, credentials, cookies, or private URLs in code/logs.
- No hardcoded real credentials.
- No server-only env exposed to browser code.

## Testing

- Bug fixes have focused coverage when practical.
- New services/stores/utilities have targeted tests when risk warrants it.
- Existing verification commands were run or explicitly skipped with reason.

## i18n and Copy

- User-facing strings use i18n when the project already uses it.
- Error messages say what happened and what the user can do next.
- Copy reuses the project's established product terms instead of inventing synonyms.

## UI

- Route files remain thin; logic lives in feature modules.
- New UI reuses the project's design-system components where appropriate.
- Styling avoids hardcoded colors when token / CSS-var equivalents exist.

## Data and DB

- Components do not call the data/RPC client directly for product data flows.
- External calls are behind services.
- Migrations are generated and idempotent.
- Queries use the project's established query-builder pattern.

## Git

- Only intended files are changed/staged.
- Unrelated dirty files are preserved.
- Env files with real values are not included.
