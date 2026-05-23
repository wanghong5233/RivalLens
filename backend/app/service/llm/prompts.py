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
