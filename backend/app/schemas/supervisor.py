from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from schemas.contracts import (
    validate_dimension,
    validate_section_id,
    validate_template_id,
    validate_token_list,
)


FocusDimension = str


class ConductResearch(BaseModel):
    research_topic: str
    competitor_id: str
    focus_dimensions: list[FocusDimension] = Field(default_factory=list)
    max_iterations: int = 6
    fallback_to_offline: bool = True

    @field_validator("focus_dimensions")
    @classmethod
    def _validate_focus_dimensions(cls, value: list[str]) -> list[str]:
        return validate_token_list(
            values=value,
            field_name="focus_dimensions",
            item_validator=validate_dimension,
            allow_empty=True,
        )


class ConductResearchBatch(BaseModel):
    topics: list[ConductResearch] = Field(min_length=1, max_length=8)
    parallelism_rationale: str


class Analyze(BaseModel):
    focus_dimensions: list[str] | None = None
    parallel_by_dimension: bool = False
    require_cross_competitor: bool = True

    @field_validator("focus_dimensions")
    @classmethod
    def _validate_focus_dimensions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return validate_token_list(
            values=value,
            field_name="focus_dimensions",
            item_validator=validate_dimension,
        )


class Write(BaseModel):
    template_id: str | None = None
    sections: list[str] | None = None

    @field_validator("template_id")
    @classmethod
    def _validate_template_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_template_id(value)

    @field_validator("sections")
    @classmethod
    def _validate_sections(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return validate_token_list(
            values=value,
            field_name="sections",
            item_validator=validate_section_id,
        )


class Finalize(BaseModel):
    completion_reason: Literal[
        "all_dimensions_covered",
        "max_iterations_hit",
        "fallback_path",
        "user_requested_stop",
    ]
    notes: str | None = None


class SupervisorDecision(BaseModel):
    id: str
    run_id: str
    iteration: int
    chosen_tool: Literal["ConductResearch", "ConductResearchBatch", "Analyze", "Write", "Finalize"]
    tool_args: dict
    reasoning_summary: str
    triggered_by: Literal[
        "user_query",
        "researcher_completion",
        "analyst_completion",
        "writer_completion",
        "qa_rejection",
        "qa_approval",
        "iteration_advance",
    ] | None = None
    outcome: Literal["dispatched", "rejected_by_qa", "succeeded", "failed"] | None = None
    outcome_recorded_at: str | None = None
    created_at: str
