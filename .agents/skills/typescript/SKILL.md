---
name: typescript
description: TypeScript code style and safety rules. MUST use before writing or modifying .ts, .tsx, or .mts files, including service clients, routers, stores, tests, and shared types.
---

# TypeScript

## Types

- Avoid `any`; use precise types or `unknown` at unstable boundaries.
- Prefer `interface` for object shapes and props; use `type` for unions/intersections.
- Prefer inference for local variables when clear.
- Use `Record<PropertyKey, unknown>` instead of loose `object`.
- Prefer `@ts-expect-error` over `@ts-ignore`, and explain why.
- Avoid meaningless optional/null parameters; design strict function contracts.

## Imports

- Use separate type-only imports:

```ts
import type { Foo } from 'pkg';
import { bar } from 'pkg';
```

- Prefer separate `import type` statements over inline `import { type Foo }` when the repo's lint config requires it.
- Keep type and value imports from the same package as separate statements when both exist.
- Sort named specifiers alphabetically where practical.

## Async and Utilities

- Prefer `async`/`await` over callback or `.then()` chains.
- Use `Promise.all` for independent concurrent work.
- Prefer existing utilities in the repo before adding helpers.
- Assign `Date.now()` once to a constant when reused in one operation.

## Logging

- Never log secrets, tokens, API keys, cookies, or private user data.
- Use `console.error` in catch blocks when the project does not have a debug logger.
- Do not silently swallow errors with empty `.catch(() => ...)`.

## Boundaries

- Use `unknown` for temporary external HTTP payloads.
- Keep server-only code out of browser/client modules.
- Respect import and lint conventions already present in neighboring files.
