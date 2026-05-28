from __future__ import annotations


def assert_equals(*, actual: object, expected: object, field: str) -> str | None:
    if actual == expected:
        return None
    return f"{field} expected={expected!r} actual={actual!r}"


def assert_gte(*, actual: int | float, expected: int | float, field: str) -> str | None:
    if actual >= expected:
        return None
    return f"{field} expected>={expected!r} actual={actual!r}"


def assert_contains(*, values: list[str], expected: str, field: str) -> str | None:
    if expected in values:
        return None
    return f"{field} missing expected={expected!r} values={values!r}"

