from __future__ import annotations

import time
from datetime import datetime, timezone

from agents.nodes.planner import reconcile_plan_tree_after_discovery
from agents.state import AgentState
from agents.state_coercion import coerce_plan_tree
from agents.tools import get_channel_registry
from db.engine import get_session_factory
from models.run import Run
from models.step import Step
from schemas.ids import make_id
from service.collector.errors import ChannelError
from service.event_bus import RunEventType, emit_run_event
from schemas.agent_outputs import DiscoveryExtractOutput
from service.llm import (
    DISCOVERY_EXTRACT_SYSTEM_PROMPT,
    build_discovery_extract_fallback_user_prompt,
    build_discovery_extract_repair_user_prompt,
    build_discovery_extract_user_prompt,
)
from service.llm.harness import complete_structured
from utils.log_node import log_node
from utils.logger import bind_step, get_logger

log = get_logger("agents.discovery")


@log_node("discovery")
async def discovery_node(state: AgentState) -> AgentState:
    """Execute competitor discovery via web search + LLM extraction."""
    run_id = state.get("run_id", "unknown")
    pending_tool_args = state.get("pending_tool_args", {})
    user_query = state.get("user_query", "")

    search_queries: list[str] = pending_tool_args.get("search_queries", [user_query])
    domain_context: str = pending_tool_args.get("domain_context", user_query)
    max_results: int = pending_tool_args.get("max_results", 8)

    session_factory = state.get("session_factory") or get_session_factory()

    step_id = make_id("step_")
    async with session_factory() as session:
        step = Step(
            step_id=step_id,
            run_id=run_id,
            agent_name="discovery",
            status="running",
            retry_count=0,
            payload={"search_queries": search_queries, "domain_context": domain_context},
        )
        session.add(step)
        await session.commit()

    registry = get_channel_registry()
    all_snippets: list[str] = []

    for query in search_queries[:5]:
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.TOOL_START,
            step_id=step_id,
            payload={
                "tool": "search_web",
                "competitor_id": None,
                "dimension": None,
                "args_summary": {"query": query, "max_results": min(max_results, 10)},
            },
        )
        tool_started_at = time.monotonic()
        snippets_added = 0
        error_text: str | None = None
        try:
            observation = await registry.invoke(
                "search_web", args={"query": query, "max_results": min(max_results, 10)}
            )
            for snippet in observation.result.snippets:
                text = snippet.sanitized_text or snippet.quote
                if text:
                    all_snippets.append(text[:500])
                    snippets_added += 1
        except ChannelError as exc:
            # Channel boundary contract: every recoverable failure inside the
            # search channel (rate-limit, timeout, auth, no-snippet) is
            # surfaced as ChannelError. Anything else (asyncio.CancelledError,
            # KeyError from a bug, etc.) must propagate so node.error fires.
            error_text = f"{type(exc).__name__}: {exc}"
            with bind_step(step_id):
                log.warning(
                    "discovery.search_failed",
                    query=query,
                    error_type=type(exc).__name__,
                    error=str(exc)[:300],
                )
        latency_ms = int((time.monotonic() - tool_started_at) * 1000)
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.TOOL_FINISH,
            step_id=step_id,
            payload={
                "tool": "search_web",
                "competitor_id": None,
                "dimension": None,
                "success": error_text is None,
                "snippet_count": snippets_added,
                "latency_ms": latency_ms,
                "error": error_text[:300] if error_text else None,
            },
        )

    discovered: list[str] = []
    extract_error: str | None = None
    snippet_count = len(all_snippets)
    if all_snippets:
        combined_results = "\n---\n".join(all_snippets[:20])
        extract_prompt = build_discovery_extract_user_prompt(
            search_results=combined_results,
            domain_context=domain_context,
            user_query=user_query,
        )
        fallback_prompt = build_discovery_extract_fallback_user_prompt(
            domain_context=domain_context,
            user_query=user_query,
        )
        try:
            harness_result = await complete_structured(
                model_slot="research",
                system_prompt=DISCOVERY_EXTRACT_SYSTEM_PROMPT,
                user_prompt=extract_prompt,
                output_model=DiscoveryExtractOutput,
                parser=DiscoveryExtractOutput.parse_llm_content,
                fallback_system_prompt=DISCOVERY_EXTRACT_SYSTEM_PROMPT,
                fallback_user_prompt=fallback_prompt,
                repair_user_prompt_builder=lambda errors: build_discovery_extract_repair_user_prompt(
                    validation_errors=errors,
                    domain_context=domain_context,
                ),
                log_event="discovery.harness.finish",
            )
            if harness_result.value is not None:
                discovered = list(harness_result.value.competitors)
            elif harness_result.llm_response.error is not None:
                extract_error = harness_result.llm_response.error[:300]
        except (KeyError, ValueError) as exc:
            extract_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            with bind_step(step_id):
                log.exception(
                    "discovery.extract_failed",
                    error_type=type(exc).__name__,
                    snippet_count=snippet_count,
                )

    with bind_step(step_id):
        log.info(
            "discovery.complete",
            discovered_count=len(discovered),
            snippet_count=snippet_count,
            queries=search_queries,
            extract_error=extract_error,
        )

    async with session_factory() as session:
        step_record = await session.get(Step, step_id)
        if step_record is not None:
            step_record.status = "completed" if discovered else "failed"
            step_record.finished_at = datetime.now(timezone.utc)
            step_record.payload = {
                **(step_record.payload or {}),
                "discovered_competitors": discovered,
                "snippet_count": snippet_count,
                "extract_error": extract_error,
            }
            await session.commit()

    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.STEP_FINISH,
        step_id=step_id,
        payload={"agent_name": "discovery", "discovered_competitors": discovered},
    )

    reconciled_plan_tree: dict[str, object] | None = None
    plan = coerce_plan_tree(state.get("plan_tree"))
    if discovered and plan is not None:
        intake_draft = state.get("intake_draft")
        focus_dimensions: list[str] | None = None
        if intake_draft is not None and hasattr(intake_draft, "focus_dimensions"):
            focus_dimensions = list(intake_draft.focus_dimensions)
        reconciled = reconcile_plan_tree_after_discovery(
            plan_tree=plan,
            discovered_competitors=discovered,
            focus_dimensions=focus_dimensions,
        )
        reconciled_plan_tree = reconciled.model_dump()
        async with session_factory() as session:
            run_row = await session.get(Run, run_id)
            if run_row is not None:
                run_row.plan_tree = reconciled_plan_tree
                await session.commit()
        await emit_run_event(
            run_id=run_id,
            event_type=RunEventType.PLAN_RECONCILED,
            payload={
                "plan_id": reconciled.plan_id,
                "task_count": len(reconciled.tasks),
                "version": reconciled.version,
                "plan_tree": reconciled_plan_tree,
                "discovered_competitors": discovered,
            },
        )

    result: dict[str, object] = {
        "competitors": discovered,
        "discovered_competitors": discovered,
        "last_completed_node": None,
    }
    if reconciled_plan_tree is not None:
        result["plan_tree"] = reconciled_plan_tree
    return result
