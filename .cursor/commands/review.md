Review the current git diff (staged + unstaged), or specified files, for production-grade Agent or backend code.

Check issues in this order.

## Critical

- Hardcoded secrets, API keys, credentials, private endpoints, or tokens.
- Bare `except` / `except Exception` (or equivalent in other languages) that hide unknown failures.
- SQL / command / prompt injection risk (string concatenation in queries, untrusted input passed to shell, unsanitized prompt assembly).
- Silent fallbacks for provider, parser, retrieval, tool, MCP, persistence, or streaming failures.
- LLM / tool output consumed by code without schema validation.
- Backend / frontend / API contract drift (response schema vs typed client).
- Agent answers, RAG output, research output, or tool results without evidence, trace, or citation when claims depend on external context.
- Magic numbers / magic strings for thresholds, timeouts, page sizes, model names, or provider names. Configuration must be centralized.
- Destructive git, shell, database, or production operations without explicit user intent.

## Important

- Missing type hints on function signatures.
- New dependencies without lockfile / package manifest updates, or with suspicious / typosquat-like names.
- Functions or components with multiple responsibilities; functions exceeding ~40 lines without clear reason.
- Ghost layers (wrapper classes that only delegate without owning policy or state).
- Comments that restate code instead of explaining intent or constraints.
- Tool schemas with vague names, ambiguous parameters, missing permission model, or unclear error semantics.
- Async jobs without status, retry, timeout, or audit fields.
- Free-form prose returned where the caller expects structured JSON.
- Public deployment changes that expose admin, debug, internal, or secret-bearing endpoints.

## Style

- Inconsistent naming (language-specific casing, unclear identifier roles).
- Missing docstrings on public functions / exported APIs.
- `print` (or equivalent) used in runtime code instead of structured logging.
- User-facing copy mixed into code identifiers.

## Output format

For each issue found, report:

```text
Severity: critical | important | style
File: path:line
Problem: what is wrong
Fix: concrete change
Why: what failure this prevents
```

If no actionable issue is found, say so and list the categories you checked.
