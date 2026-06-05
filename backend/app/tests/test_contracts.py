from __future__ import annotations

import pytest

from schemas.contracts import (
    normalize_dimension_or_none,
    validate_dimension,
    validate_section_id,
    validate_token_list,
)


def test_validate_dimension_slugifies_human_readable_value() -> None:
    assert validate_dimension("User Feedback") == "user_feedback"


def test_validate_section_id_slugifies_symbols() -> None:
    assert validate_section_id("Pricing & Cost") == "pricing_cost"


def test_validate_dimension_raises_when_slug_becomes_empty() -> None:
    with pytest.raises(ValueError, match="dimension must match"):
        validate_dimension("!!!")


def test_validate_token_list_skips_items_that_cannot_be_normalized() -> None:
    values = ["Feature", "!!!", "User Feedback", "feature"]
    normalized = validate_token_list(
        values=values,
        field_name="focus_dimensions",
        item_validator=validate_dimension,
    )
    assert normalized == ["feature", "user_feedback"]


def test_normalize_dimension_or_none_accepts_slugified_allowed_value() -> None:
    assert normalize_dimension_or_none("User Feedback", allowed=["user_feedback"]) == (
        "user_feedback",
        None,
    )


def test_normalize_dimension_or_none_reports_missing_invalid_and_out_of_focus() -> None:
    assert normalize_dimension_or_none(None, allowed=["pricing"]) == (None, "missing")
    assert normalize_dimension_or_none("!!!", allowed=["pricing"]) == (None, "invalid")
    assert normalize_dimension_or_none("User Feedback", allowed=["pricing"]) == (
        None,
        "out_of_focus",
    )
