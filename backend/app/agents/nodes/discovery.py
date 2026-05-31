from __future__ import annotations

from datetime import datetime, timezone

from agents.state import AgentState
from agents.tools import get_channel_registry
from db.engine import get_session_factory
from models.step import Step
from schemas.ids import make_id
from service.collector.errors import ChannelError
from service.event_bus import RunEventType, emit_run_event
from service.llm.client import get_llm_client
from utils.log_node import log_node
from utils.logger import bind_step, get_logger

log = get_logger("agents.discovery")

DISCOVERY_EXTRACT_PROMPT = """You are a competitive intelligence analyst.
Given the following search results about a market/track, extract a list of competitor product names.

Rules:
- Return ONLY a JSON object: {"competitors": ["Name1", "Name2", ...]}
- Each name should be the commonly known product name (not company name unless they are the same).
- Deduplicate: if the same product appears multiple times, include it only once.
- Return between 3 and 10 competitors, prioritizing the most relevant ones.
- Do NOT include generic terms, categories, or non-product entities.

Search results:
{search_results}

Domain context: {domain_context}
User query: {user_query}
"""


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
        try:
            observation = await registry.invoke(
                "search_web", args={"query": query, "max_results": min(max_results, 10)}
            )
            for snippet in observation.result.snippets:
                text = snippet.sanitized_text or snippet.quote
                if text:
                    all_snippets.append(text[:500])
        except (ChannelError, Exception) as exc:
            log.warning("discovery.search_failed", query=query, error=str(exc))

    discovered: list[str] = []
    if all_snippets:
        combined_results = "\n---\n".join(all_snippets[:20])
        extract_prompt = DISCOVERY_EXTRACT_PROMPT.format(
            search_results=combined_results,
            domain_context=domain_context,
            user_query=user_query,
        )
        llm_response = await get_llm_client().complete_json(
            model_slot="research",
            system_prompt="You extract competitor names from search results. Return valid JSON only.",
            user_prompt=extract_prompt,
        )
        content = llm_response.content
        if isinstance(content, dict):
            raw_competitors = content.get("competitors", [])
            if isinstance(raw_competitors, list):
                for item in raw_competitors:
                    name = str(item).strip() if item else ""
                    if name and name not in discovered:
                        discovered.append(name)

    with bind_step(step_id):
        log.info("discovery.complete", discovered_count=len(discovered), queries=search_queries)

    async with session_factory() as session:
        step_record = await session.get(Step, step_id)
        if step_record is not None:
            step_record.status = "completed"
            step_record.finished_at = datetime.now(timezone.utc)
            step_record.payload = {
                **(step_record.payload or {}),
                "discovered_competitors": discovered,
            }
            await session.commit()

    await emit_run_event(
        run_id=run_id,
        event_type=RunEventType.STEP_FINISH,
        step_id=step_id,
        payload={"agent_name": "discovery", "discovered_competitors": discovered},
    )

    return {
        "competitors": discovered,
        "discovered_competitors": discovered,
        "last_completed_node": None,
    }
