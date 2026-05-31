from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from schemas.intake import IntakeClarifyRequest, IntakeExchange, RunIntakeDraft
from schemas.plan import FollowUpRequest, PlanTree
from schemas.supervisor import SupervisorDecision


def _last_write_wins(_: object, new: object) -> object:
    return new


RunPhase = Literal["intake", "planning", "executing", "done"]


class AgentState(TypedDict, total=False):
    run_id: str
    user_query: str
    domain_hint: str | None
    reference_urls: list[str]
    competitors: Annotated[list[str], operator.add]
    discovered_competitors: Annotated[list[str], operator.add]
    current_iteration: int
    pending_tool_args: Annotated[dict[str, object], _last_write_wins]
    next_action: Literal["discovery", "researcher", "analyst", "writer", "finalize"]
    last_completed_node: Annotated[
        Literal["researcher", "analyst", "writer"] | None,
        _last_write_wins,
    ]
    qa_outcome: Literal["approved", "rejected", "force_degraded"] | None
    qa_reject_to: Literal["researcher", "analyst", "writer", "supervisor"] | None
    qa_rejection_count: int
    pending_review_target_step_id: str | None
    qa_reasons: list[str]
    researched_competitors: Annotated[list[str], operator.add]
    analysis_done: bool
    report_draft_done: bool
    decisions: list[SupervisorDecision]
    status: Annotated[str, _last_write_wins]
    session_factory: async_sessionmaker[AsyncSession]

    # --- Phase 1+ Agent-native intake + plan-then-execute (contract; nodes TBD) ---
    # `phase` drives the conditional entry route (Invariant B). Legacy runs omit it
    # and fall through to `supervisor` for backward compatibility.
    phase: RunPhase
    intake_draft: RunIntakeDraft
    intake_history: list[IntakeExchange]
    plan_tree: PlanTree | None
    follow_up_queue: Annotated[list[FollowUpRequest], operator.add]
    # Invariant A cross-node carriers: written by the *_generate_node (which commits),
    # read+interrupted by the *_wait_node. NOT a single-node "skip LLM" cache.
    pending_clarify: IntakeClarifyRequest | None
    pending_plan_tree: PlanTree | None
