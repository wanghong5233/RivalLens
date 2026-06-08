#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

IGNORED_TRACKED_FILES: set[str] = {
    "frontend/package-lock.json",
}

PLACEHOLDER_HINTS: tuple[str, ...] = (
    "replace",
    "your-",
    "example",
    "sample",
    "fake",
    "dummy",
    "test",
    "changeme",
    "placeholder",
    "todo",
    "xxx",
)

# 结构化占位符前缀（团队约定的"模板专用"标记）。
# 命中即认为是合法 placeholder，参见 PITFALL §1.3 / playbook 02。
STRUCTURED_PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(
    r"^__REPLACE__[A-Z0-9_]+__$"
)

LITERAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Bearer token literal",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b"),
    ),
    (
        "Cloud/API key literal",
        re.compile(
            r"\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
            r"AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
        ),
    ),
    (
        "Volcano Engine ARK key literal",
        re.compile(r"\bark-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-[0-9a-f]{4,}\b"),
    ),
    (
        "Doubao endpoint id literal",
        re.compile(r"\bep-[0-9]{10,}-[a-z0-9]{4,}\b"),
    ),
    # 见 PITFALL §4.1 Root Cause #6：从指令片段（KEY=VALUE / export KEY=VALUE）整段
    # 复制粘贴产生的双等号特征。无法由手敲产生，命中即视为指令复制式泄露。
    (
        "Double-assignment paste (instruction-copy)",
        re.compile(r"^[A-Z][A-Z0-9_]*\s*=\s*[A-Z][A-Z0-9_]*\s*=\s*\S", re.MULTILINE),
    ),
)

SENSITIVE_ASSIGNMENT_PATTERN: re.Pattern[str] = re.compile(
    r"""(?ix)
    ^\s*(?P<name>
        DOUBAO_API_KEY
        |OPENAI_API_KEY
        |QWEN_API_KEY
        |TAVILY_API_KEY
        |BOCHA_API_KEY
        |ANTHROPIC_API_KEY
        |GITHUB_TOKEN
        |DOUBAO_EP
    )\b
    \s*(?P<delimiter>[:=])\s*
    (?P<value>["']?[^"'\s#]+["']?)
    """
)

DIFF_HUNK_PATTERN: re.Pattern[str] = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class Finding:
    file_path: str
    line_no: int
    reason: str
    snippet: str


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def _is_ignored_file(path: str) -> bool:
    return _normalize_path(path) in IGNORED_TRACKED_FILES


def _is_placeholder_value(raw_value: str) -> bool:
    stripped = raw_value.strip().strip("'\"")
    if STRUCTURED_PLACEHOLDER_PATTERN.match(stripped):
        return True
    normalized = stripped.lower()
    if not normalized:
        return True
    if normalized in {"none", "null"}:
        return True
    return any(hint in normalized for hint in PLACEHOLDER_HINTS)


def _line_reasons(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return []

    reasons: list[str] = []
    for label, pattern in LITERAL_PATTERNS:
        if pattern.search(line):
            reasons.append(label)

    for match in SENSITIVE_ASSIGNMENT_PATTERN.finditer(line):
        delimiter = match.group("delimiter")
        tail = line[match.end() :].split("#", maxsplit=1)[0]
        if delimiter == ":" and "=" in tail:
            continue

        value = match.group("value")
        if _is_placeholder_value(value):
            continue
        name = match.group("name").upper()
        reasons.append(f"{name} has non-placeholder value")

    return reasons


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def _iter_staged_added_lines(diff_text: str) -> Iterable[tuple[str, int, str]]:
    current_file: str | None = None
    current_line: int | None = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = _normalize_path(raw_line[6:])
            current_line = None
            continue

        if raw_line.startswith("@@"):
            match = DIFF_HUNK_PATTERN.match(raw_line)
            if match is None:
                current_line = None
                continue
            current_line = int(match.group(1)) - 1
            continue

        if current_file is None or current_line is None:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            current_line += 1
            yield current_file, current_line, raw_line[1:]
            continue

        if raw_line.startswith("-") and not raw_line.startswith("---"):
            continue

        current_line += 1


def _scan_added_lines(lines: Iterable[tuple[str, int, str]]) -> list[Finding]:
    findings: list[Finding] = []
    for file_path, line_no, content in lines:
        if _is_ignored_file(file_path):
            continue

        reasons = _line_reasons(content)
        for reason in reasons:
            findings.append(
                Finding(
                    file_path=file_path,
                    line_no=line_no,
                    reason=reason,
                    snippet=content.strip()[:200],
                )
            )
    return findings


def scan_staged() -> list[Finding]:
    diff = _run_git(
        [
            "diff",
            "--cached",
            "--unified=0",
            "--no-color",
            "--diff-filter=ACMRTUXB",
        ]
    )
    if not diff.strip():
        return []
    return _scan_added_lines(_iter_staged_added_lines(diff))


def scan_all_tracked() -> list[Finding]:
    tracked_raw = _run_git(["ls-files", "-z"])
    tracked_paths = [item for item in tracked_raw.split("\0") if item]

    findings: list[Finding] = []
    for rel_path in tracked_paths:
        normalized_path = _normalize_path(rel_path)
        if _is_ignored_file(normalized_path):
            continue

        file_path = Path(normalized_path)
        if not file_path.exists():
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for line_no, line in enumerate(content.splitlines(), start=1):
            reasons = _line_reasons(line)
            for reason in reasons:
                findings.append(
                    Finding(
                        file_path=normalized_path,
                        line_no=line_no,
                        reason=reason,
                        snippet=line.strip()[:200],
                    )
                )

    return findings


def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, int, str]] = set()
    unique: list[Finding] = []
    for finding in findings:
        key = (finding.file_path, finding.line_no, finding.reason)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def _print_findings(findings: list[Finding], *, quiet: bool, max_findings: int) -> None:
    if quiet:
        first = findings[0]
        print(
            f"secret-scan: {first.file_path}:{first.line_no} {first.reason}: {first.snippet}",
            file=sys.stderr,
        )
        return

    print("secret-scan: potential secret exposure detected.", file=sys.stderr)
    for finding in findings[:max_findings]:
        print(
            f"- {finding.file_path}:{finding.line_no} [{finding.reason}] {finding.snippet}",
            file=sys.stderr,
        )

    remaining = len(findings) - max_findings
    if remaining > 0:
        print(f"... and {remaining} more finding(s).", file=sys.stderr)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan staged changes or tracked files for potential secret leakage."
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--staged",
        action="store_true",
        help="scan staged added lines (default mode)",
    )
    mode_group.add_argument(
        "--all-tracked",
        action="store_true",
        help="scan all tracked files in repository",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print only the first finding",
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=50,
        help="maximum findings to print in non-quiet mode",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    scan_mode = "all-tracked" if args.all_tracked else "staged"

    try:
        findings = scan_all_tracked() if scan_mode == "all-tracked" else scan_staged()
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if isinstance(exc.stderr, str) else ""
        message = stderr or str(exc)
        print(f"secret-scan: git command failed: {message}", file=sys.stderr)
        return 2

    findings = _dedupe_findings(findings)
    if findings:
        _print_findings(findings, quiet=args.quiet, max_findings=max(1, args.max_findings))
        return 1

    if not args.quiet:
        print("secret-scan: passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
