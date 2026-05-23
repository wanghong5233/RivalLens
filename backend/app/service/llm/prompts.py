from __future__ import annotations

import json
from collections.abc import Sequence

SUPERVISOR_ALLOWED_DIMENSIONS: tuple[str, ...] = (
    "feature",
    "pricing",
    "user_feedback",
    "positioning",
    "tech_stack",
)

SUPERVISOR_SYSTEM_PROMPT = """You are the RivalLens Supervisor planner.
You must choose exactly one tool in each iteration and return STRICT JSON.

Available tools:
1) ConductResearch
   - tool_args schema:
     {
       "research_topic": str,
       "competitor_id": str,
       "focus_dimensions": list[str],
       "max_iterations": int,
       "fallback_to_offline": bool
     }
2) Analyze
   - tool_args schema:
     {
       "focus_dimensions": list[str] | null,
       "parallel_by_dimension": bool,
       "require_cross_competitor": bool
     }
3) Write
   - tool_args schema:
     {
       "template_id": str,
       "sections": list[str] | null
     }
4) Finalize
   - tool_args schema:
     {
       "completion_reason": "all_dimensions_covered" | "max_iterations_hit" | "fallback_path" | "user_requested_stop",
       "notes": str | null
     }

Output JSON schema:
{
  "chosen_tool": "ConductResearch" | "Analyze" | "Write" | "Finalize",
  "tool_args": { ... valid for chosen_tool ... },
  "reasoning_summary": "short and concrete rationale"
}

Rules:
- Always return a JSON object and nothing else.
- Never invent competitor ids not present in the allowed list from user prompt.
- For ConductResearch, focus_dimensions must be a subset of the allowed dimensions list.
- Keep reasoning_summary concise and operational, no markdown.
"""

RESEARCHER_SYSTEM_PROMPT = """You are RivalLens Researcher in a ReAct loop.
You can only take one action each turn and must return STRICT JSON.

Allowed actions:
1) pack_lookup
   - args schema:
     {
       "competitor_id": str,
       "dimension": "feature" | "pricing" | "user_feedback" | "positioning" | "tech_stack"
     }
2) finalize
   - args schema:
     {
       "summary": str
     }

Output JSON schema:
{
  "action": "pack_lookup" | "finalize",
  "action_args": { ... valid for action ... },
  "reasoning_summary": "short and concrete rationale"
}

Hard constraints:
- Never fabricate evidence quotes, source_url, or source_title.
- Evidence can only come from tool observations.
- If enough dimensions are already covered, call finalize.
- Return JSON object only, no markdown.
"""

RESEARCHER_COMPRESSION_PROMPT = """You are compressing a long researcher trace.
Return STRICT JSON:
{
  "compressed_summary": str
}

Rules:
- Preserve concrete findings by dimension and source URL mentions.
- Keep summary concise and factual.
- Do not invent new facts.
"""


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_supervisor_user_prompt(
    *,
    user_query: str,
    iteration: int,
    competitors: Sequence[str],
    researched_competitors: Sequence[str],
    analysis_done: bool,
    report_draft_done: bool,
    qa_outcome: str | None,
    qa_reject_to: str | None,
    qa_reasons: Sequence[str],
) -> str:
    pending_competitors = [item for item in competitors if item not in researched_competitors]
    return (
        "Planning context:\n"
        f"- iteration: {iteration}\n"
        f"- user_query: {user_query}\n"
        f"- competitors: {_json(list(competitors))}\n"
        f"- researched_competitors: {_json(list(researched_competitors))}\n"
        f"- pending_competitors: {_json(pending_competitors)}\n"
        f"- analysis_done: {analysis_done}\n"
        f"- report_draft_done: {report_draft_done}\n"
        f"- qa_outcome: {qa_outcome}\n"
        f"- qa_reject_to: {qa_reject_to}\n"
        f"- qa_reasons: {_json(list(qa_reasons))}\n\n"
        "Hard constraints:\n"
        f"1) ConductResearch.tool_args.competitor_id must be in {_json(list(competitors))}.\n"
        "2) ConductResearch.tool_args.focus_dimensions must be subset of "
        f"{_json(list(SUPERVISOR_ALLOWED_DIMENSIONS))}.\n"
        "3) Return exactly one tool decision in this iteration.\n"
    )


def build_researcher_user_prompt(
    *,
    research_topic: str,
    competitor_id: str,
    focus_dimensions: Sequence[str],
    pending_dimensions: Sequence[str],
    queried_dimensions: Sequence[str],
    turn_count: int,
    max_turns: int,
    observations_log: Sequence[dict[str, object]],
) -> str:
    return (
        "Research assignment:\n"
        f"- research_topic: {research_topic}\n"
        f"- competitor_id: {competitor_id}\n"
        f"- focus_dimensions: {_json(list(focus_dimensions))}\n"
        f"- pending_dimensions: {_json(list(pending_dimensions))}\n"
        f"- queried_dimensions: {_json(list(queried_dimensions))}\n"
        f"- turn_count: {turn_count}\n"
        f"- max_turns: {max_turns}\n"
        f"- observations_log: {_json(list(observations_log)[-6:])}\n\n"
        "Action guidance:\n"
        "1) Prefer pack_lookup for pending dimensions.\n"
        "2) Use finalize when pending_dimensions is empty or evidence is sufficient.\n"
        "3) action_args.dimension must come from focus_dimensions.\n"
    )


def build_compression_user_prompt(
    *,
    messages: Sequence[dict[str, str]],
    observations_log: Sequence[dict[str, object]],
    evidence_drafts: Sequence[dict[str, object]],
) -> str:
    return (
        "Compress current researcher trace context.\n"
        f"- messages_tail: {_json(list(messages)[-10:])}\n"
        f"- observations_tail: {_json(list(observations_log)[-8:])}\n"
        f"- evidence_drafts_tail: {_json(list(evidence_drafts)[-8:])}\n"
    )
