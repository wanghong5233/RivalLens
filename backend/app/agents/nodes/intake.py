from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from langgraph.types import interrupt
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.state import AgentState
from db.engine import get_session_factory
from models.llm_call import LLMCall
from models.step import Step
from schemas.ids import make_id
from schemas.intake import (
    IntakeClarifyRequest,
    IntakeExchange,
    IntakeUserReply,
    RunIntakeDraft,
)
from service.event_bus import RunEventType, emit_run_event
from service.llm import (
    INTAKE_SYSTEM_PROMPT,
    build_intake_fallback_user_prompt,
    build_intake_user_prompt,
)
from service.llm.client import get_llm_client
from service.llm.response import LLMResponse
from utils.log_node import log_node
from utils.logger import bind_step, get_logger

log = get_logger("agents.intake")

# Optional draft fields the IntakeAgent is allowed to patch. Any unknown key in
# `draft_patch` is silently dropped to keep the contract tight.
_PATCHABLE_FIELDS: frozenset[str] = frozenset(
    {
        "user_role",
        "analysis_intent",
        "competitors_explicit",
        "competitors_discovery_mode",
        "domain_hint",
        "focus_dimensions",
        "report_depth",
        "reference_urls",
    }
)
_USER_ROLES: frozenset[str] = frozenset({"pm", "founder", "sales", "investor"})

# Keyword-based normalization tables for the wait node's deterministic merge.
# Why: user-facing chips show bilingual labels (e.g. "PM / 产品经理"), and the
# LLM may also emit free-form Chinese options. The wait node MUST translate any
# of these back to internal enum values so user_role / discovery_mode reliably
# land in `intake_draft` without depending on the next LLM turn's parsing.
_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pm", ("pm", "product manager", "产品经理", "产品负责人")),
    ("founder", ("founder", "co-founder", "创始人", "创业者", "ceo")),
    ("sales", ("sales", "销售", "bd", "客户成功")),
    ("investor", ("investor", "vc", "投资人", "投资经理", "分析师")),
)
_DISCOVERY_ON_KEYWORDS: tuple[str, ...] = (
    "auto-discover",
    "discover",
    "帮我发现",
    "agent 帮",
    "agent帮",
    "由 agent",
    "由agent",
    "自动发现",
)
_DISCOVERY_OFF_KEYWORDS: tuple[str, ...] = (
    "我已有名单",
    "已有名单",
    "explicit",
    "已知",
    "我自己来",
)
_DEPTH_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("quick", ("quick", "速览", "快速")),
    ("deep", ("deep", "深度", "完整", "详细")),
)


def _match_keyword(text: str, table: tuple[tuple[str, tuple[str, ...]], ...]) -> str | None:
    needle = text.casefold().strip()
    if not needle:
        return None
    for value, keywords in table:
        if any(keyword.casefold() in needle for keyword in keywords):
            return value
    return None


def _split_competitor_list(text: str) -> list[str]:
    """Best-effort parse: user might list competitors in free text, comma/顿号/换行 separated."""
    if not text or not text.strip():
        return []
    # Replace common CJK separators with comma, then split.
    normalized = text.replace("、", ",").replace("，", ",").replace(";", ",").replace("\n", ",")
    parts = [piece.strip() for piece in normalized.split(",")]
    # Strip surrounding quotes / bullets that users often paste.
    cleaned = [piece.strip(" \"'·-•*") for piece in parts if piece.strip(" \"'·-•*")]
    # De-dup preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for item in cleaned:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _resolve_session_factory(state: AgentState) -> async_sessionmaker[AsyncSession]:
    session_factory = state.get("session_factory")
    if session_factory is not None:
        return session_factory
    return get_session_factory()


def _coerce_draft(state: AgentState) -> RunIntakeDraft:
    draft = state.get("intake_draft")
    if isinstance(draft, RunIntakeDraft):
        return draft
    if isinstance(draft, dict):
        # Checkpoint round-trip may serialize Pydantic models to dicts.
        return RunIntakeDraft.model_validate(draft)
    user_query = state.get("user_query") or ""
    return RunIntakeDraft(user_query=user_query)


def _coerce_history(state: AgentState) -> list[IntakeExchange]:
    raw = state.get("intake_history") or []
    out: list[IntakeExchange] = []
    for item in raw:
        if isinstance(item, IntakeExchange):
            out.append(item)
            continue
        if isinstance(item, dict):
            try:
                out.append(IntakeExchange.model_validate(item))
            except ValidationError:
                continue
    return out


def _history_to_prompt(history: list[IntakeExchange]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for exchange in history:
        rows.append(
            {
                "question": exchange.clarify.question,
                "field_targets": list(exchange.clarify.field_targets),
                "reply_text": exchange.reply.text,
                "reply_options": list(exchange.reply.selected_options),
            }
        )
    return rows


def _sanitize_patch(raw_patch: object) -> dict[str, object]:
    if not isinstance(raw_patch, dict):
        return {}
    clean: dict[str, object] = {}
    for key, value in raw_patch.items():
        if key not in _PATCHABLE_FIELDS:
            continue
        if value is None:
            continue
        clean[key] = value
    return clean


def _apply_patch(draft: RunIntakeDraft, patch: dict[str, object]) -> RunIntakeDraft:
    if not patch:
        return draft
    base = draft.model_dump(exclude={"is_complete"})
    role_raw = patch.get("user_role")
    if isinstance(role_raw, str) and role_raw in _USER_ROLES:
        base["user_role"] = role_raw
    intent_raw = patch.get("analysis_intent")
    if isinstance(intent_raw, str) and intent_raw.strip():
        base["analysis_intent"] = intent_raw.strip()
    explicit_raw = patch.get("competitors_explicit")
    if isinstance(explicit_raw, list):
        normalized = [str(c).strip() for c in explicit_raw if isinstance(c, str) and c.strip()]
        if normalized:
            base["competitors_explicit"] = normalized
    discovery_raw = patch.get("competitors_discovery_mode")
    if isinstance(discovery_raw, bool):
        base["competitors_discovery_mode"] = discovery_raw
    domain_raw = patch.get("domain_hint")
    if isinstance(domain_raw, str) and domain_raw.strip():
        base["domain_hint"] = domain_raw.strip()
    focus_raw = patch.get("focus_dimensions")
    if isinstance(focus_raw, list):
        normalized = [str(d).strip() for d in focus_raw if isinstance(d, str) and d.strip()]
        if normalized:
            base["focus_dimensions"] = normalized
    depth_raw = patch.get("report_depth")
    if isinstance(depth_raw, str) and depth_raw in {"quick", "deep"}:
        base["report_depth"] = depth_raw
    urls_raw = patch.get("reference_urls")
    if isinstance(urls_raw, list):
        normalized = [str(u).strip() for u in urls_raw if isinstance(u, str) and u.strip()]
        if normalized:
            base["reference_urls"] = normalized
    return RunIntakeDraft.model_validate(base)


def _parse_clarify(raw_clarify: object) -> IntakeClarifyRequest | None:
    if not isinstance(raw_clarify, dict):
        return None
    question = raw_clarify.get("question")
    if not isinstance(question, str) or not question.strip():
        return None
    field_targets_raw = raw_clarify.get("field_targets")
    field_targets = (
        [str(f) for f in field_targets_raw if isinstance(f, str) and f.strip()]
        if isinstance(field_targets_raw, list)
        else []
    )
    suggested_raw = raw_clarify.get("suggested_options")
    suggested = (
        [str(s) for s in suggested_raw if isinstance(s, str) and s.strip()]
        if isinstance(suggested_raw, list)
        else None
    )
    try:
        return IntakeClarifyRequest(
            question=question.strip(),
            field_targets=field_targets,
            suggested_options=suggested,
        )
    except ValidationError:
        return None


def _fallback_clarify(draft: RunIntakeDraft) -> IntakeClarifyRequest:
    """Deterministic clarify question when the LLM output is unusable.

    Picks the first missing required field so the run can still make progress without LLM.
    Bilingual labels: chip text is what users see; the wait-node normalizer
    handles label → internal value translation in one place.
    """
    if draft.user_role is None:
        return IntakeClarifyRequest(
            question="请问您在工作中更接近以下哪个角色？",
            field_targets=["user_role"],
            suggested_options=[
                "PM / 产品经理",
                "Founder / 创业者",
                "Sales / 销售",
                "Investor / 投资人",
            ],
        )
    if not (draft.analysis_intent and draft.analysis_intent.strip()):
        return IntakeClarifyRequest(
            question="请用一句话描述这次分析您最想了解什么？例如「了解 X 赛道头部玩家的定价策略」。",
            field_targets=["analysis_intent"],
        )
    return IntakeClarifyRequest(
        question="您已经有想分析的竞品名单吗？没有的话可以让 Agent 帮您发现。",
        field_targets=["competitors_explicit", "competitors_discovery_mode"],
        suggested_options=["我已有名单 (explicit)", "让 Agent 帮我发现 (auto-discover)"],
    )


def _merge_reply_into_draft(
    draft: RunIntakeDraft,
    clarify: IntakeClarifyRequest,
    reply: IntakeUserReply,
) -> RunIntakeDraft:
    """Deterministically merge a user reply into the draft based on field_targets.

    This is the critical fix for the "Agent repeats the same question" bug:
    previously the wait node only appended to history and trusted the next LLM
    turn to re-parse the reply. With unstable LLMs that turn would often emit
    an empty draft_patch, leaving required fields null and triggering a re-ask.

    Now any user reply whose target field can be unambiguously decoded from
    selected_options or free text is written into the draft immediately. The
    next LLM turn still gets to refine optional fields and decide complete/ask.
    """
    if not clarify.field_targets:
        return draft

    targets = set(clarify.field_targets)
    base = draft.model_dump(exclude={"is_complete"})
    candidates: list[str] = [*reply.selected_options, reply.text]
    combined = " ".join(c for c in candidates if c).strip()

    if "user_role" in targets and base.get("user_role") is None:
        for candidate in candidates:
            role = _match_keyword(candidate, _ROLE_KEYWORDS)
            if role is not None:
                base["user_role"] = role
                break

    if "analysis_intent" in targets:
        intent_current = base.get("analysis_intent")
        # Prefer free-text reply when present; fall back to selected_options join.
        if reply.text.strip():
            base["analysis_intent"] = reply.text.strip()
        elif not intent_current and reply.selected_options:
            base["analysis_intent"] = ", ".join(reply.selected_options)

    discovery_changed = False
    if "competitors_discovery_mode" in targets or "competitors_explicit" in targets:
        for candidate in candidates:
            lowered = candidate.casefold()
            if any(k.casefold() in lowered for k in _DISCOVERY_ON_KEYWORDS):
                base["competitors_discovery_mode"] = True
                discovery_changed = True
                break
            if any(k.casefold() in lowered for k in _DISCOVERY_OFF_KEYWORDS):
                base["competitors_discovery_mode"] = False
                discovery_changed = True
                break

    if "competitors_explicit" in targets and reply.text.strip():
        parsed = _split_competitor_list(reply.text)
        if parsed:
            existing = base.get("competitors_explicit") or []
            existing_keys = {c.casefold() for c in existing if isinstance(c, str)}
            merged = list(existing)
            for item in parsed:
                if item.casefold() not in existing_keys:
                    merged.append(item)
                    existing_keys.add(item.casefold())
            base["competitors_explicit"] = merged
            # User listed actual competitors → discovery_mode no longer required
            # unless they also explicitly opted in.
            if not discovery_changed:
                base["competitors_discovery_mode"] = base.get("competitors_discovery_mode", False)

    if "report_depth" in targets:
        for candidate in candidates:
            depth = _match_keyword(candidate, _DEPTH_KEYWORDS)
            if depth is not None:
                base["report_depth"] = depth
                break

    if "domain_hint" in targets and reply.text.strip():
        # No closed-set normalization; accept the user's domain phrase verbatim.
        base["domain_hint"] = reply.text.strip()

    # focus_dimensions / reference_urls intentionally left to the LLM —
    # they need richer parsing the wait node should not own.
    _ = combined  # reserved for future heuristic; keep variable to signal intent

    return RunIntakeDraft.model_validate(base)


async def _persist_intake_step(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: str,
    turn: int,
    action: str,
    draft: RunIntakeDraft,
    clarify: IntakeClarifyRequest | None,
    llm_response: LLMResponse,
    reasoning_summary: str,
) -> str:
    async with session_factory() as session:
        step = Step(
            step_id=make_id("step_"),
            run_id=run_id,
            agent_name="intake_agent",
            status="running",
            retry_count=0,
            payload={
                "phase": "intake",
                "turn": turn,
                "action": action,
                "draft_complete": bool(draft.is_complete),
                "clarify_field_targets": list(clarify.field_targets) if clarify else [],
                "llm_provider": llm_response.provider,
                "llm_fallback_used": llm_response.fallback_used,
                "llm_fallback_reason": llm_response.fallback_reason,
                "reasoning_summary": reasoning_summary[:1000] if reasoning_summary else "",
            },
        )
        session.add(step)
        await session.flush()
        llm_call_error = (
            llm_response.error[:2000] if llm_response.error is not None else None
        )
        session.add(
            LLMCall(
                step_id=step.step_id,
                model_slot=llm_response.model_slot,
                provider=llm_response.provider,
                model_name=llm_response.model_name,
                prompt_hash=llm_response.prompt_hash,
                prompt_tokens=llm_response.prompt_tokens,
                completion_tokens=llm_response.completion_tokens,
                latency_ms=llm_response.latency_ms,
                error=llm_call_error,
            )
        )
        step.status = "completed"
        step.finished_at = datetime.now(timezone.utc)
        await session.commit()
        return step.step_id


@log_node("intake_generate")
async def intake_generate_node(state: AgentState) -> AgentState:
    """LLM-driven intake turn. Decides ask vs. complete and writes pending_clarify.

    Invariant A: this node is the *generate* half of the split. All side effects
    (LLM call, Step+LLMCall persistence, INTAKE_* events) happen here so they
    are committed before the wait node's interrupt(). Resumes after interrupt
    re-execute only the wait node, never this one.
    """
    session_factory = _resolve_session_factory(state)
    run_id = state.get("run_id") or make_id("run_")
    user_query = state.get("user_query") or ""
    draft = _coerce_draft(state)
    history = _coerce_history(state)
    turn = len(history) + 1

    user_prompt = build_intake_user_prompt(
        user_query=user_query,
        current_draft=draft.model_dump(exclude={"is_complete"}),
        history=_history_to_prompt(history),
    )
    fallback_user_prompt = build_intake_fallback_user_prompt(
        user_query=user_query,
        current_draft=draft.model_dump(exclude={"is_complete"}),
    )
    llm_response = await get_llm_client().complete_json(
        model_slot="research",
        system_prompt=INTAKE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        fallback_system_prompt=INTAKE_SYSTEM_PROMPT,
        fallback_user_prompt=fallback_user_prompt,
    )

    content = llm_response.content if isinstance(llm_response.content, dict) else {}
    action_raw = content.get("action")
    patch = _sanitize_patch(content.get("draft_patch"))
    next_draft = _apply_patch(draft, patch)
    raw_clarify = content.get("clarify_request")
    parsed_clarify = _parse_clarify(raw_clarify)
    reasoning_summary_raw = content.get("reasoning_summary")
    reasoning_summary = (
        reasoning_summary_raw.strip()
        if isinstance(reasoning_summary_raw, str)
        else ""
    )

    if action_raw == "complete" and next_draft.is_complete:
        action: str = "complete"
        clarify: IntakeClarifyRequest | None = None
    elif action_raw == "ask" and parsed_clarify is not None:
        action = "ask"
        clarify = parsed_clarify
    else:
        # Fallback: LLM output was unusable OR proposed complete on an incomplete draft.
        action = "ask"
        clarify = _fallback_clarify(next_draft)

    step_id = await _persist_intake_step(
        session_factory=session_factory,
        run_id=run_id,
        turn=turn,
        action=action,
        draft=next_draft,
        clarify=clarify,
        llm_response=llm_response,
        reasoning_summary=reasoning_summary,
    )
    with bind_step(step_id):
        log.info(
            "intake.generate",
            run_id=run_id,
            turn=turn,
            action=action,
            draft_complete=bool(next_draft.is_complete),
            llm_provider=llm_response.provider,
            llm_fallback_used=llm_response.fallback_used,
        )

    if action == "complete":
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.INTAKE_COMPLETE,
            step_id=step_id,
            payload={
                "turn": turn,
                "draft": next_draft.model_dump(exclude={"is_complete"}),
            },
        )
        # Phase 2: intake.complete hands off to the planner. The graph's
        # _route_after_intake_generate reads `phase` and routes to planner_generate.
        return {
            **state,
            "run_id": run_id,
            "phase": "planning",
            "intake_draft": next_draft,
            "intake_history": history,
            "pending_clarify": None,
        }

    assert clarify is not None  # narrowing for type checker; action=="ask" guarantees this
    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.INTAKE_CLARIFY_REQUEST,
        step_id=step_id,
        payload={
            "turn": turn,
            "question": clarify.question,
            "field_targets": list(clarify.field_targets),
            "suggested_options": list(clarify.suggested_options or []),
            "draft_complete": bool(next_draft.is_complete),
            # Phase 1b fix: include the live draft so FE can update the
            # requirement checklist immediately (was previously relying on a
            # racey GET /api/runs/{id} from the SSE handler).
            "draft": next_draft.model_dump(exclude={"is_complete"}),
        },
    )
    return {
        **state,
        "run_id": run_id,
        "phase": "intake",
        "intake_draft": next_draft,
        "intake_history": history,
        "pending_clarify": clarify,
    }


def _coerce_pending_clarify(state: AgentState) -> IntakeClarifyRequest:
    """Read pending_clarify from state; raises if generate_node didn't set it.

    Fails fast at the boundary instead of silently injecting a fake clarify —
    a missing pending_clarify means the graph topology is wrong, not a recoverable input.
    """
    pending = state.get("pending_clarify")
    if isinstance(pending, IntakeClarifyRequest):
        return pending
    if isinstance(pending, dict):
        return IntakeClarifyRequest.model_validate(pending)
    raise RuntimeError(
        "intake_wait_node entered without pending_clarify in state; check graph wiring."
    )


@log_node("intake_wait")
async def intake_wait_node(state: AgentState) -> AgentState:
    """Pure interrupt node. Idempotent: on replay it just re-issues interrupt().

    Invariant A: this node carries NO LLM calls, NO DB writes before interrupt().
    All side effects after interrupt() run exactly once per resume.
    """
    clarify = _coerce_pending_clarify(state)
    raw_reply: Any = interrupt(clarify.model_dump())

    try:
        reply = IntakeUserReply.model_validate(raw_reply)
    except ValidationError as exc:
        # Re-raise as RuntimeError; the resume endpoint is the only writer of resume
        # values and must validate them before passing Command(resume=...). Reaching here
        # means the endpoint contract was bypassed.
        raise RuntimeError(f"intake_wait resume value failed validation: {exc}") from exc

    run_id = state.get("run_id") or make_id("run_")
    history = _coerce_history(state)
    history = [*history, IntakeExchange(clarify=clarify, reply=reply)]

    # CRITICAL FIX: merge the reply into the draft right here, NOT in the next
    # generate turn. Letting the LLM be the only writer of draft fields means
    # any flaky LLM turn drops user-provided info and re-asks the same question.
    # The wait node owns the deterministic floor; the LLM enriches on top.
    current_draft = _coerce_draft(state)
    next_draft = _merge_reply_into_draft(current_draft, clarify, reply)

    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.INTAKE_USER_REPLY,
        step_id=None,
        payload={
            "turn": len(history),
            "reply_text": reply.text,
            "reply_options": list(reply.selected_options),
            # Mirror the post-merge draft so the FE checklist updates the moment
            # the user sends, without waiting for the next clarify turn.
            "draft": next_draft.model_dump(exclude={"is_complete"}),
        },
    )

    return {
        **cast(dict[str, Any], state),
        "run_id": run_id,
        "phase": "intake",
        "intake_draft": next_draft,
        "intake_history": history,
        "pending_clarify": None,
    }
