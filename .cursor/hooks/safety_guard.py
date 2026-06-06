#!/usr/bin/env python
"""Cursor IDE safety guard for RivalLens.

Replaces the previous pure-allow stub. The IDE layer is L1 (auxiliary) per
docs/private/engineering-playbook/02-secret-leakage-defense-layers.md; the
authoritative interception lives at git client (L2) and server push protection
(L3). This guard adds two missing pieces in L1:

1. beforeShellExecution: deny obviously destructive / secret-bypassing commands
   so the AI agent gets immediate feedback (defense-in-depth, NOT the lock).
2. afterFileEdit / write-class events: deny edits to real env files; redirect
   to .env.example or local manual configuration.

Stdin payload shape varies per event (Cursor does not pass an event name).
We sniff fields:
- "command" + "cwd"               -> beforeShellExecution / beforeMCPExecution
- "file_path"                      -> beforeReadFile / afterFileEdit
- otherwise                        -> unknown, fall back to allow

Output: {"permission": "allow"|"deny", "user_message": "...", "agent_message": "..."}
Exit 0 always (Cursor reads the JSON; exit 2 would also block but we prefer
explicit JSON for clearer messaging).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import PurePath


SHELL_DENY_PATTERNS = (
    (r"\bgit\s+add\s+(\.|-A\b|--all\b)", "Use explicit file paths instead of `git add .`"),
    (r"\bgit\s+reset\s+--hard\b", "Destructive: requires explicit user approval"),
    (r"\bgit\s+clean\s+-[a-z]*f", "Destructive: requires explicit user approval"),
    (r"\bgit\s+push\b.*\s--force\b", "Force push requires explicit user approval"),
    (r"\bgit\s+push\b.*\s-f\b", "Force push requires explicit user approval"),
    (r"\brm\s+-[a-z]*r[a-z]*f\b", "Destructive recursive delete: requires explicit approval"),
    (r"\bRemove-Item\b.*\b-Recurse\b.*\b-Force\b", "Destructive recursive delete: requires explicit approval"),
)


def _emit(decision: str, user: str = "", agent: str = "") -> None:
    payload = {"permission": decision}
    if user:
        payload["user_message"] = user
    if agent:
        payload["agent_message"] = agent
    out = json.dumps(payload, ensure_ascii=True) + "\n"
    sys.stdout.write(out)
    sys.stdout.flush()


def _is_real_env_file(path: str) -> bool:
    name = PurePath(path.replace("\\", "/")).name.lower()
    if "example" in name or "sample" in name or name.endswith(".template"):
        return False
    if name == ".env":
        return True
    if name.startswith(".env."):
        return True
    return False


def _check_shell(command: str) -> tuple[str, str]:
    compact = re.sub(r"\s+", " ", command.strip())
    for pattern, reason in SHELL_DENY_PATTERNS:
        if re.search(pattern, compact, re.IGNORECASE):
            return "deny", reason
    return "allow", ""


def _check_file(file_path: str) -> tuple[str, str]:
    if _is_real_env_file(file_path):
        return "deny", (
            f"Blocked write to real env file: {file_path}. "
            f"Edit .env.example with __REPLACE__... placeholders, or write the "
            f"real value into your local untracked .env file directly."
        )
    return "allow", ""


def main() -> int:
    # Read stdin as bytes and decode UTF-8 ourselves. Cursor sends UTF-8, but on
    # Windows sys.stdin uses the locale codec (e.g. GBK) and raises
    # UnicodeDecodeError on non-ASCII payloads (repo path contains CJK chars),
    # which would crash the hook into a no-output, fail-closed block.
    try:
        raw_bytes = sys.stdin.buffer.read()
        raw = raw_bytes.decode("utf-8", errors="replace")
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError, OSError):
        # Fail-open on malformed payload to avoid blocking legitimate ops on
        # corrupted IDE input. L2/L3 still cover real-secret leakage.
        _emit("allow")
        return 0

    if isinstance(payload, dict) and isinstance(payload.get("command"), str) and "tool_name" not in payload:
        decision, reason = _check_shell(payload["command"])
        _emit(decision, user=reason, agent=reason)
        return 0

    file_path = None
    if isinstance(payload, dict):
        for key in ("file_path", "path"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                file_path = value
                break

    if file_path is not None:
        decision, reason = _check_file(file_path)
        _emit(decision, user=reason, agent=reason)
        return 0

    _emit("allow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
