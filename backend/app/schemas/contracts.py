from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

_CONTRACT_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_CONTRACT_TOKEN_SEPARATOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9_]+")
_CONTRACT_TOKEN_LEADING_NON_ALPHA_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[^a-z]+")
_DIMENSION_ALIASES: Final[dict[str, str]] = {
    "china_vs_global": "market_differences",
    "global_vs_china": "market_differences",
    "china_vs_global_market_dynamics": "market_differences",
    "china_vs_global_market_differenc": "market_differences",
    "market_difference": "market_differences",
    "market_differenc": "market_differences",
    "market_dynamics": "market_differences",
    "enterprise_features": "enterprise_capabilities",
    "enterprise_feature": "enterprise_capabilities",
    "enterprise_capabilities_assessme": "enterprise_capabilities",
    "enterprise_capabilities_assessment": "enterprise_capabilities",
    "investment_recommendation": "strategic_recommendations",
    "product_positioning_analysis": "product_positioning",
    "pricing_strategy_comparison": "pricing_strategy",
    "strategic_investment": "strategic_recommendations",
    "strategic_investment_recommendat": "strategic_recommendations",
    "strategic_investment_recommendation": "strategic_recommendations",
    "strategic_recommendation": "strategic_recommendations",
}


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
    normalized = _validate_contract_token(value=value, field_name="dimension")
    return _DIMENSION_ALIASES.get(normalized, normalized)


def normalize_dimension_or_none(
    raw: object,
    *,
    allowed: list[str] | set[str],
) -> tuple[str | None, str | None]:
    if not isinstance(raw, str):
        return None, "missing"
    try:
        normalized = validate_dimension(raw)
    except ValueError:
        return None, "invalid"
    if allowed and normalized not in set(allowed):
        return None, "out_of_focus"
    return normalized, None


def validate_section_id(value: str) -> str:
    return _validate_contract_token(value=value, field_name="section_id")


def validate_template_id(value: str) -> str:
    return _validate_contract_token(value=value, field_name="template_id")


def validate_source_type(value: str) -> str:
    return _validate_contract_token(value=value, field_name="source_type")
