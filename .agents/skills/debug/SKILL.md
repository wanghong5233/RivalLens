---
name: debug
description: Debug logging guide. Use when adding debug logs, choosing log namespaces, diagnosing server/client/router issues, or deciding what can be logged safely.
---

# Debug

## Safety

- Never log secrets, full tokens, cookies, API keys, private URLs, or user private data.
- Prefer status codes, provider names, endpoint names, request IDs, and sanitized errors.
- Remove temporary logs before finalizing.

## RavenWeb Namespace Pattern

When using the `debug` package:

- Server: `lobe-server:<module>`
- Client: `lobe-client:<module>`
- Router: `lobe-<type>-router:<module>`
- Desktop: `lobe-desktop:<module>`

```ts
import debug from 'debug';

const log = debug('lobe-server:scriptlens');
log('health status: %d', status);
```

Use `%O` for objects, `%s` for strings, and `%d` for numbers.

## Console

- `console.error` is acceptable in catch blocks when matching local style.
- Avoid committed `console.log` / `console.debug`.
