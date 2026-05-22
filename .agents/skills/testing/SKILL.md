---
name: testing
description: Vitest testing guide. Use when writing tests, fixing failing tests, debugging mocks, choosing test commands, or improving coverage.
---

# Testing

## Commands

For RavenWeb, prefer targeted commands:

```bash
bunx vitest run --silent='passed-only' <file>
```

Avoid full `bun run test` unless explicitly needed; it is slow.

## Principles

- Test observable behavior, not implementation details.
- Prefer `vi.spyOn` over broad `vi.mock`.
- Mock at boundaries: network, DB, filesystem, browser APIs, external services.
- Keep fixtures small and readable.
- Run type-check when shared TypeScript contracts changed, if feasible.

## Test Structure

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});
```

## Fix or Delete

Keep tests that verify external behavior. Delete or replace tests that only assert internal param forwarding when a higher-level behavior test already covers the same outcome.

## Debugging Failures

- Reproduce with the narrowest test.
- Check env/setup before changing logic.
- If two fix attempts fail, reassess assumptions and inspect the owning layer.
