#!/usr/bin/env python3
"""Codex pre-tool safety guard for RivalLens.

Blocks broad/destructive shell commands and edits to real .env files
to prevent secret leakage and accidental working-tree corruption.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import PurePath
from typing import Any


def block(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(0)


def basename(path: str) -> str:
    return PurePath(path.replace("\\", "/")).name.lower()


def is_real_env_file(path: str) -> bool:
    name = basename(path)
    if "example" in name or "sample" in name or name.endswith(".template"):
        return False
    return name == ".env" or name.startswith(".env.")


def get_command(tool_input: Any) -> str:
    if isinstance(tool_input, dict):
        value = tool_input.get("command")
        if isinstance(value, str):
            return value
    return ""


def check_shell(command: str) -> None:
    compact = re.sub(r"\s+", " ", command.strip().lower())
    blocked = [
        r"\bgit\s+add\s+(\.|-a\b|--all\b)",
        r"\bgit\s+reset\s+--hard\b",
        r"\bgit\s+clean\s+-[a-z]*f",
        r"\brm\s+-[a-z]*r[a-z]*f\b",
        r"\bremove-item\b.*\b-recurse\b.*\b-force\b",
    ]

    for pattern in blocked:
        if re.search(pattern, compact):
            block(
                "Blocked broad/destructive command. Use explicit paths or ask for approval."
            )


def check_patch(command: str) -> None:
    for match in re.finditer(
        r"^\*\*\* (?:Add|Update|Delete) File:\s+(.+)$", command, re.MULTILINE
    ):
        path = match.group(1).strip()
        if is_real_env_file(path):
            block(
                f"Blocked edit to real env file: {path}. Edit an example file or ask for non-secret values."
            )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    tool_name = payload.get("tool_name")
    command = get_command(payload.get("tool_input"))

    if tool_name == "Bash":
        check_shell(command)
    elif tool_name in {"apply_patch", "Edit", "Write"}:
        check_patch(command)


if __name__ == "__main__":
    main()
