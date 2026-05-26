#!/usr/bin/env python3
"""Claude Code pre-tool safety guard for RivalLens.

Blocks broad/destructive shell commands and edits to real .env files,
and runs secret scan before git commit/push.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import PurePath


def deny(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(2)


def basename(path: str) -> str:
    return PurePath(path.replace("\\", "/")).name.lower()


def is_real_env_file(path: str) -> bool:
    name = basename(path)
    if "example" in name or "sample" in name or name.endswith(".template"):
        return False
    return name == ".env" or name.startswith(".env.")


def paths_from_input(tool_input: object) -> list[str]:
    if not isinstance(tool_input, dict):
        return []

    paths: list[str] = []
    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            paths.append(value)

    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict):
                for key in ("file_path", "path"):
                    value = edit.get(key)
                    if isinstance(value, str):
                        paths.append(value)

    return paths


def check_file_edit(tool_input: object) -> None:
    for path in paths_from_input(tool_input):
        if is_real_env_file(path):
            deny(
                f"Blocked edit to real env file: {path}. Edit an example file or use local manual configuration."
            )


def check_bash(tool_input: object) -> None:
    if not isinstance(tool_input, dict):
        return

    command = str(tool_input.get("command", ""))
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

    if re.search(r"\bgit\s+commit\b", compact):
        check_passed, message = run_secret_scan("--staged")
        if not check_passed:
            deny(f"Blocked git commit by secret scan: {message}")

    if re.search(r"\bgit\s+push\b", compact):
        check_passed, message = run_secret_scan("--all-tracked")
        if not check_passed:
            deny(f"Blocked git push by secret scan: {message}")


def run_secret_scan(mode_flag: str) -> tuple[bool, str]:
    command = [sys.executable, "scripts/scan_secrets.py", mode_flag, "--quiet"]
    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return False, f"secret scan execution failed ({type(exc).__name__})"

    if result.returncode == 0:
        return True, ""

    output = result.stderr.strip() or result.stdout.strip()
    if not output:
        output = "secret scan found suspicious content."
    return False, output


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input", {})

    if tool_name == "Bash":
        check_bash(tool_input)
    elif tool_name in {"Write", "Edit", "MultiEdit"}:
        check_file_edit(tool_input)


if __name__ == "__main__":
    main()
