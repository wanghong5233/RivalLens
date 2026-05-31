from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from schemas.ids import make_id

PlanTaskStage = Literal["discover", "research", "analyze", "write"]
PlanTaskSource = Literal["agent", "user"]
PlanTaskPriority = Literal["normal", "user_pinned"]


class PlanTask(BaseModel):
    """One executable unit in the Agent's proposed plan, shown in the Plan Tree."""

    task_id: str = Field(default_factory=lambda: make_id("ptask_"))
    stage: PlanTaskStage
    title: str
    description: str = ""
    competitor_id: str | None = None
    focus_dimensions: list[str] = Field(default_factory=list)
    source: PlanTaskSource = "agent"
    enabled: bool = True
    priority: PlanTaskPriority = "normal"


class PlanTree(BaseModel):
    """The Agent's full proposed plan; `version` bumps on each user edit."""

    plan_id: str = Field(default_factory=lambda: make_id("plan_"))
    tasks: list[PlanTask] = Field(default_factory=list)
    rationale: str = ""
    version: int = 1


class PlanConfirmRequest(BaseModel):
    """Resume payload for the plan-confirm interrupt."""

    disabled_task_ids: list[str] = Field(default_factory=list)
    # Phase β: user-injected tasks (forced priority="user_pinned" by the planner node).
    additional_tasks: list[PlanTask] = Field(default_factory=list)


class FollowUpRequest(BaseModel):
    """Phase 4: mid-run user addendum consumed by the supervisor."""

    text: str
    applies_to_stage: PlanTaskStage | None = None
