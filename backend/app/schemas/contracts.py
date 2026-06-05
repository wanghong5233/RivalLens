from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

_CONTRACT_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_CONTRACT_TOKEN_SEPARATOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9_]+")
_CONTRACT_TOKEN_LEADING_NON_ALPHA_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[^a-z]+")


def _validate_contract_token(*, value: str, field_name: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty.")
    normalized = _CONTRACT_TOKEN_SEPARATOR_PATTERN.sub("_", normalized)
    normalized = _CONTRACT_TOKEN_LEADING_NON_ALPHA_PATTERN.sub("", normalized).strip("_")
    normalized = normalized[:32]
    if _CONTRACT_TOKEN_PATTERN.fullmatch(normalized) is None:
        raise ValueError(f"{field_name} must match ^[a-z][a-z0-9_]{{1,31}}$.")
    return normalized


def validate_token_list(
    *,
    values: list[str],
    field_name: str,
    item_validator: Callable[[str], str],
    allow_empty: bool = False,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        try:
            item = item_validator(value)
        except ValueError:
            continue
        if item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} must contain at least one value.")
    return normalized


def validate_dimension(value: str) -> str:
    return _validate_contract_token(value=value, field_name="dimension")


def validate_section_id(value: str) -> str:
    return _validate_contract_token(value=value, field_name="section_id")


def validate_template_id(value: str) -> str:
    return _validate_contract_token(value=value, field_name="template_id")


def validate_source_type(value: str) -> str:
    return _validate_contract_token(value=value, field_name="source_type")
