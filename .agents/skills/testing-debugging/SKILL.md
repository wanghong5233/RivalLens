---
name: testing-debugging
description: Testing and debugging practices. Use when adding tests, fixing failing tests, choosing verification commands, adding debug logs, diagnosing API/service failures, or deciding when to stop after repeated failed attempts.
---

# Testing and Debugging

## Verification Strategy

- Run the narrowest meaningful test first.
- Prefer targeted file/module tests over full-suite commands unless the change is broad.
- Run type checks or lint checks when touching shared TypeScript contracts.
- For backend/service integrations, verify the called endpoint directly before debugging the caller.
- State any verification you could not run.

## Test Quality

- Test behavior, not implementation details.
- Prefer boundary mocks: network, database, filesystem, or external services.
- Avoid broad module mocks when a targeted spy or fixture is enough.
- Keep test data minimal and readable.
- Update or delete brittle white-box tests when they only duplicate implementation wiring.

## Debugging Flow

1. Reproduce the failure or inspect the latest error.
2. Identify which repository owns the failing layer.
3. Check env/config before rewriting logic.
4. Add temporary logs only when needed, and remove them before finalizing.
5. After one or two failed fix attempts, reassess assumptions instead of patching blindly.

## Logging Rules

- Never log secrets, full tokens, credentials, API keys, cookies, or full Authorization headers.
- Log stable context: provider name, endpoint name, status code, feature flag, request id, or sanitized error.
- Avoid leaving noisy `console.log` / `print` statements in committed code.
- Use the project's established debug logger when it has one.

## Integration Checks

For service-to-service work:

- Check the downstream service health endpoint.
- Confirm base URL and port from runtime env, not only from local files.
- Verify auth requirements before assuming demo mode or dev mode bypasses them.
- Capture the smallest response needed to prove the link works.

## RavenWeb Note

When testing RavenWeb, read `RavenWeb/.agents/skills/testing/SKILL.md` for exact commands and warnings. In that project, avoid full `bun run test` unless explicitly needed.
