---
name: testing-debugging
description: Testing and debugging practices, incl. Vitest mocks and the `debug` package. Use when adding/fixing tests, choosing test or verification commands, mocking boundaries, adding debug logs or log namespaces, diagnosing API/service failures, or deciding when to stop after repeated failed attempts.
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
- Delete tests that only assert internal param forwarding when a higher-level behavior test already covers the outcome.

## JavaScript/TypeScript Tests (Vitest)

- Prefer targeted runs over the full suite (full runs are slow); use the repo's package runner from `AGENTS.md`:

```bash
npx vitest run --silent='passed-only' <file>
```

- Prefer `vi.spyOn` over broad `vi.mock`.
- Reset mocks between cases:

```ts
import { afterEach, beforeEach, vi } from 'vitest';

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.restoreAllMocks());
```

## Debugging Flow

1. Reproduce the failure or inspect the latest error.
2. Identify which repository owns the failing layer.
3. Check env/config before rewriting logic.
4. Add temporary logs only when needed, and remove them before finalizing.
5. After one or two failed fix attempts, reassess assumptions instead of patching blindly.

## Logging Rules

- Never log secrets, full tokens, credentials, API keys, cookies, or full Authorization headers.
- Log stable context: provider name, endpoint name, status code, feature flag, request id, or sanitized error.
- Avoid leaving noisy `console.log` / `print` / `console.debug` statements in committed code.
- `console.error` in a catch block is acceptable when it matches local style.
- Use the project's established debug logger when it has one.

## Debug Package Namespaces

When using the `debug` package, follow the project's namespace convention. A common shape is `<app>-<layer>:<module>` (e.g. `<app>-server:<module>` / `<app>-client:<module>`) so logs filter by layer.

```ts
import debug from 'debug';

const log = debug('myapp-server:health');
log('health status: %d', status);
```

Use `%O` for objects, `%s` for strings, `%d` for numbers.

## Integration Checks

For service-to-service work:

- Check the downstream service health endpoint.
- Confirm base URL and port from runtime env, not only from local files.
- Verify auth requirements before assuming demo mode or dev mode bypasses them.
- Capture the smallest response needed to prove the link works.

## Project Commands

Read the target repo's `AGENTS.md` for the canonical test command, and prefer targeted runs over full-suite commands unless the change is broad.
