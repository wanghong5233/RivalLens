# Golden Eval Cases

This folder contains deterministic golden eval cases for RivalLens.

## Coverage

10 cases are grouped by scenario type:

- 3 baseline: normal completion and QA approval.
- 4 self-evolution: promoted blocking / warning / parse fallback and reject-retry paths.
- 3 tool abnormal: online fallback, desensitization boundary, semantic reject-retry.

## Files

- `cases/*.yaml`: case definitions with `setup`, `input`, and `assertions`.
- `runner.py`: apply per-case promoted setup, run `/api/runs`, evaluate assertions, emit metrics.
- `assertions.py`: shared assertion helpers.

## Notes

- Cases are designed to run with the fake LLM path and deterministic retry triggers.
- Per-case promoted rules are isolated by a temporary copied pack root.
- Generated markdown reports are written to `docs/private/` and are intentionally gitignored.

## Run

From `backend/app`:

```bash
python scripts/run_golden.py
```

