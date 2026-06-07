from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

UserRole = Literal["pm", "founder", "sales", "investor"]
FocusDimension = str


class RunIntakeDraft(BaseModel):
    """Structured intent accumulated across Agent-native intake turns.

    The IntakeAgent keeps clarifying until `is_complete` is True, at which point the
    run advances from `intake` to `planning`. `is_complete` is computed (not stored)
    so it can never drift from the underlying fields.
    """

    user_query: str
    user_role: UserRole | None = None
    analysis_intent: str | None = None
    competitors_explicit: list[str] = Field(default_factory=list)
    competitors_discovery_mode: bool = False
    domain_hint: str | None = None
    focus_dimensions: list[FocusDimension] = Field(default_factory=list)
    report_depth: Literal["quick", "deep"] = "quick"
    reference_urls: list[str] = Field(default_factory=list)
    # Quality-enriching context (optional; never gate completion). These let the
    # Planner/Analyst frame competitors RELATIVE to the requester and scope the
    # research, which is what separates a neutral listing from actionable CI.
    # `self_product`: requester's own product/positioning anchor.
    # `market_scope`: target market / geography / segment (e.g. China vs overseas).
    # `time_context`: decision timing or data-recency requirement.
    self_product: str | None = None
    market_scope: str | None = None
    time_context: str | None = None

    @computed_field
    @property
    def is_complete(self) -> bool:
        # Completion gate (product decision): know who the user is, what they want,
        # and either an explicit competitor set or an opt-in to Agent discovery.
        has_identity = self.user_role is not None
        has_intent = bool(self.analysis_intent and self.analysis_intent.strip())
        has_competitor_path = bool(self.competitors_explicit) or self.competitors_discovery_mode
        return has_identity and has_intent and has_competitor_path


class IntakeClarifyRequest(BaseModel):
    """A single clarifying question the Agent asks to fill specific draft fields."""

    question: str
    field_targets: list[str] = Field(default_factory=list)
    suggested_options: list[str] | None = None
    suggested_answer: str | None = None


class IntakeUserReply(BaseModel):
    """User answer to an IntakeClarifyRequest (resume payload for the intake interrupt).

    At least one of `text` / `selected_options` must be non-empty — empty replies would
    feed the IntakeAgent an empty observation and trigger a re-ask loop on the same field.
    """

    text: str = ""
    selected_options: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_nonempty_signal(self) -> "IntakeUserReply":
        if not self.text.strip() and not self.selected_options:
            raise ValueError("IntakeUserReply requires non-empty text or selected_options")
        return self


class IntakeExchange(BaseModel):
    """One completed clarify+reply round, appended to AgentState.intake_history.

    Modeled (not a raw tuple) so it survives checkpoint JSON round-trips intact.
    Only fully-resolved rounds belong in history; an in-flight clarify lives in
    `AgentState.pending_clarify`, not here.
    """

    clarify: IntakeClarifyRequest
    reply: IntakeUserReply
