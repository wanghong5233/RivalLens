from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


FocusDimension = Literal["feature", "pricing", "user_feedback", "positioning", "tech_stack"]


class ConductResearch(BaseModel):
    research_topic: str
    competitor_id: str
    focus_dimensions: list[FocusDimension] = Field(default_factory=list)
    max_iterations: int = 6
    fallback_to_offline: bool = True


class ConductResearchBatch(BaseModel):
    topics: list[ConductResearch] = Field(min_length=1, max_length=8)
    parallelism_rationale: str


class Analyze(BaseModel):
    focus_dimensions: list[str] | None = None
    parallel_by_dimension: bool = False
    require_cross_competitor: bool = True


class Write(BaseModel):
    template_id: str
    sections: list[str] | None = None


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
