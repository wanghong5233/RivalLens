from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from schemas.contracts import validate_dimension, validate_token_list
from schemas.supervisor import FocusDimension


class DimensionSnippet(BaseModel):
    quote: str
    source_url: str
    source_title: str
    desensitized: bool


class CompetitorSnapshot(BaseModel):
    id: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    official_url: str
    category: str
    snapshots: dict[FocusDimension, list[DimensionSnippet]] = Field(default_factory=dict)

    @staticmethod
    def _normalize_snapshots(value: dict[str, list[DimensionSnippet]]) -> dict[str, list[DimensionSnippet]]:
        normalized: dict[str, list[DimensionSnippet]] = {}
        for key, snippets in value.items():
            normalized[validate_dimension(key)] = snippets
        return normalized

    @field_validator("snapshots")
    @classmethod
    def _validate_snapshots(
        cls,
        value: dict[str, list[DimensionSnippet]],
    ) -> dict[str, list[DimensionSnippet]]:
        return cls._normalize_snapshots(value)


class PackMetadata(BaseModel):
    id: str
    name: str
    version: str
    default_focus_dimensions: list[FocusDimension] = Field(default_factory=list)
    description: str
    competitor_files: list[str] = Field(default_factory=list)

    @field_validator("default_focus_dimensions")
    @classmethod
    def _validate_default_focus_dimensions(cls, value: list[str]) -> list[str]:
        return validate_token_list(
            values=value,
            field_name="default_focus_dimensions",
            item_validator=validate_dimension,
            allow_empty=True,
        )


class PromotedQARule(BaseModel):
    rule_id: str
    rule_yaml: str
    candidate_id: str
    approved_by: str
    approved_at: str
    supporting_run_ids: list[str] = Field(default_factory=list)


class IndustryPack(BaseModel):
    id: str
    name: str
    version: str
    default_focus_dimensions: list[FocusDimension] = Field(default_factory=list)
    description: str
    competitors: dict[str, CompetitorSnapshot] = Field(default_factory=dict)
    promoted_qa_rules: list[PromotedQARule] = Field(default_factory=list)

    @field_validator("default_focus_dimensions")
    @classmethod
    def _validate_default_focus_dimensions(cls, value: list[str]) -> list[str]:
        return validate_token_list(
            values=value,
            field_name="default_focus_dimensions",
            item_validator=validate_dimension,
            allow_empty=True,
        )
