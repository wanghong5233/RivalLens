#!/usr/bin/env python3
"""Cursor pre-tool safety guard for RivalLens.

Blocks broad/destructive shell commands and reads/edits of real .env files
to prevent secret leakage and accidental working-tree corruption.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import PurePath


def deny(reason: str) -> None:
    print(
        json.dumps(
            {"permission": "deny", "userMessage": reason},
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


def check_shell(payload: dict) -> None:
    command = str(payload.get("command", ""))
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
            deny(
                "Blocked broad/destructive command. Use explicit paths or ask for approval."
            )


def check_read(payload: dict) -> None:
    path = str(payload.get("path", "") or payload.get("file_path", ""))
    if is_real_env_file(path):
        deny(
            f"Blocked read of real env file: {path}. Read .env.example or ask for non-secret values."
        )


def allow() -> None:
    print(json.dumps({"permission": "allow"}, ensure_ascii=False))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
        return

    if isinstance(payload, dict):
        if "command" in payload:
            check_shell(payload)
        elif "path" in payload or "file_path" in payload:
            check_read(payload)

    allow()


if __name__ == "__main__":
    main()
