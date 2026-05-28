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
QA_SEMANTIC_ALLOWED_REJECT_TO: tuple[str, ...] = (
    "supervisor",
    "researcher",
    "analyst",
    "writer",
)
WRITER_ALLOWED_SECTION_IDS: tuple[str, ...] = (
    "feature",
    "pricing",
    "user_feedback",
    "differentiation",
    "swot",
)
SKILL_CURATOR_ALLOWED_TYPES: tuple[str, ...] = (
    "qa_rule",
    "prompt_template",
    "source_routing",
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
2) ConductResearchBatch
   - tool_args schema:
     {
       "topics": [
         {
           "research_topic": str,
           "competitor_id": str,
           "focus_dimensions": list[str],
           "max_iterations": int,
           "fallback_to_offline": bool
         }
       ],
       "parallelism_rationale": str
     }
3) Analyze
   - tool_args schema:
     {
       "focus_dimensions": list[str] | null,
       "parallel_by_dimension": bool,
       "require_cross_competitor": bool
     }
4) Write
   - tool_args schema:
     {
       "template_id": str,
       "sections": list[str] | null
     }
5) Finalize
   - tool_args schema:
     {
       "completion_reason": "all_dimensions_covered" | "max_iterations_hit" | "fallback_path" | "user_requested_stop",
       "notes": str | null
     }

Output JSON schema:
{
  "chosen_tool": "ConductResearch" | "ConductResearchBatch" | "Analyze" | "Write" | "Finalize",
  "tool_args": { ... valid for chosen_tool ... },
  "reasoning_summary": "short and concrete rationale"
}

Rules:
- Always return a JSON object and nothing else.
- Never invent competitor ids not present in the allowed list from user prompt.
- For ConductResearch, focus_dimensions must be a subset of the allowed dimensions list.
- For ConductResearchBatch, topics length must be between 1 and 8, topic.competitor_id must be unique and from allowed competitors, and each topic.focus_dimensions must be a subset of the allowed dimensions list.
- Prefer ConductResearchBatch when pending_competitors has 2+ independent competitors and analysis_done is false.
- Keep reasoning_summary concise and operational, no markdown.
"""

RESEARCHER_SYSTEM_PROMPT = """You are RivalLens Researcher in a ReAct loop.
You can only take one action each turn and must return STRICT JSON.

Allowed actions:
1) search_web
   - args schema:
     {
       "query": str,
       "max_results": int
     }
2) fetch_url
   - args schema:
     {
       "url": str
     }
3) parse_page
   - args schema:
     {
       "html": str,
       "source_url": str | null,
       "source_title": str | null
     }
4) extract_structured
   - args schema:
     {
       "text": str,
       "source_url": str | null,
       "source_title": str | null
     }
5) lookup_offline_snapshot
   - args schema:
     {
       "competitor_id": str,
       "dimension": "feature" | "pricing" | "user_feedback" | "positioning" | "tech_stack"
     }
6) finalize
   - args schema:
     {
       "summary": str
     }

Output JSON schema:
{
  "action": "search_web" | "fetch_url" | "parse_page" | "extract_structured" | "lookup_offline_snapshot" | "finalize",
  "action_args": { ... valid for action ... },
  "reasoning_summary": "short and concrete rationale"
}

Hard constraints:
- Never fabricate evidence quotes, source_url, or source_title.
- Evidence can only come from tool observations.
- If enough dimensions are already covered, call finalize.
- Prefer lookup_offline_snapshot for hard fallback when online channels fail.
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

ANALYST_SYSTEM_PROMPT = """You are RivalLens Analyst.
You must produce cross-competitor analysis in STRICT JSON.

Output JSON schema:
{
  "summary": str,
  "insights": [
    {
      "dimension": "feature" | "pricing" | "user_feedback" | "positioning" | "tech_stack",
      "finding": str,
      "evidence_ids": list[str],
      "confidence": "high" | "medium" | "low"
    }
  ],
  "risk_flags": list[str],
  "recommended_sections": list[str]
}

Rules:
- Every insight must reference existing evidence_ids from user prompt.
- Do not fabricate competitor facts.
- Return JSON object only.
"""

QA_SEMANTIC_SYSTEM_PROMPT = """You are RivalLens QA semantic auditor.
You review report coherence and evidence consistency in STRICT JSON.

Output JSON schema:
{
  "semantic_audit_passed": bool,
  "reject_to": "supervisor" | "researcher" | "analyst" | "writer",
  "severity": "blocking" | "warning",
  "finding": str,
  "required_fields": list[str]
}

Rules:
- If semantic_audit_passed is true, finding should still be concise.
- If false, reject_to must be actionable and required_fields must be specific.
- Return JSON object only.
"""

WRITER_SYSTEM_PROMPT = """You are RivalLens Writer.
Generate a battlecard report in STRICT JSON with evidence-grounded sections.

Output JSON schema:
{
  "template_id": str,
  "title": str,
  "executive_summary": str,
  "sections": [
    {
      "section_id": "feature" | "pricing" | "user_feedback" | "differentiation" | "swot",
      "title": str,
      "content_markdown": str,
      "evidence_refs": list[str],
      "insight_refs": list[str]
    }
  ],
  "risk_callouts": list[str]
}

Rules:
- template_id must match the requested template_id from user prompt.
- Every section must include non-empty content_markdown.
- Every section must cite evidence_refs using ids provided in user prompt.
- Do not fabricate evidence ids or insight refs.
- Return JSON object only.
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
        "2) ConductResearchBatch.tool_args.topics[*].competitor_id must be unique and all in "
        f"{_json(list(competitors))}.\n"
        "3) ConductResearch.tool_args.focus_dimensions and ConductResearchBatch.tool_args.topics[*].focus_dimensions must be subsets of "
        f"{_json(list(SUPERVISOR_ALLOWED_DIMENSIONS))}.\n"
        "4) Return exactly one tool decision in this iteration.\n"
    )


def build_supervisor_fallback_user_prompt(
    *,
    user_query: str,
    competitors: Sequence[str],
    researched_competitors: Sequence[str],
    analysis_done: bool,
    report_draft_done: bool,
) -> str:
    pending_competitors = [item for item in competitors if item not in researched_competitors]
    preferred_tool_hint: str
    if len(pending_competitors) >= 2:
        preferred_tool_hint = "ConductResearchBatch"
    elif len(pending_competitors) == 1:
        preferred_tool_hint = "ConductResearch"
    elif not analysis_done:
        preferred_tool_hint = "Analyze"
    elif not report_draft_done:
        preferred_tool_hint = "Write"
    else:
        preferred_tool_hint = "Finalize"
    return (
        "Fallback planning context:\n"
        f"- user_query: {user_query}\n"
        f"- competitors: {_json(list(competitors))}\n"
        f"- pending_competitors: {_json(pending_competitors)}\n"
        f"- analysis_done: {analysis_done}\n"
        f"- report_draft_done: {report_draft_done}\n"
        f"- preferred_tool_hint: {preferred_tool_hint}\n\n"
        "Pick exactly one next tool and keep tool_args minimal but valid.\n"
        "When pending_competitors has 2+ entries, prefer ConductResearchBatch with one unique competitor per topic."
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
        "1) Prefer search_web -> fetch_url -> parse_page -> extract_structured for online collection.\n"
        "2) Use lookup_offline_snapshot for pending dimensions when online sources are missing/unreliable.\n"
        "3) Use finalize when pending_dimensions is empty or evidence is sufficient.\n"
        "4) action_args.dimension must come from focus_dimensions for lookup_offline_snapshot.\n"
    )


def build_researcher_fallback_user_prompt(
    *,
    competitor_id: str,
    pending_dimensions: Sequence[str],
    queried_dimensions: Sequence[str],
    turn_count: int,
    max_turns: int,
) -> str:
    return (
        "Fallback researcher action request:\n"
        f"- competitor_id: {competitor_id}\n"
        f"- pending_dimensions: {_json(list(pending_dimensions))}\n"
        f"- queried_dimensions: {_json(list(queried_dimensions))}\n"
        f"- turn_count: {turn_count}\n"
        f"- max_turns: {max_turns}\n\n"
        "Return one action with valid action_args. Prefer lookup_offline_snapshot on pending dimensions."
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


def build_compression_fallback_user_prompt(
    *,
    observations_log: Sequence[dict[str, object]],
    evidence_drafts: Sequence[dict[str, object]],
) -> str:
    return (
        "Fallback compression request:\n"
        f"- observations_count: {len(list(observations_log))}\n"
        f"- evidence_count: {len(list(evidence_drafts))}\n\n"
        "Return a compact compressed_summary with key findings only."
    )


def build_analyst_user_prompt(
    *,
    user_query: str,
    competitors: Sequence[str],
    focus_dimensions: Sequence[str],
    evidence_briefs: Sequence[dict[str, object]],
) -> str:
    return (
        "Analysis context:\n"
        f"- user_query: {user_query}\n"
        f"- competitors: {_json(list(competitors))}\n"
        f"- focus_dimensions: {_json(list(focus_dimensions))}\n"
        f"- evidence_briefs: {_json(list(evidence_briefs)[-24:])}\n\n"
        "Produce cross-competitor insights with explicit evidence_ids."
    )


def build_analyst_fallback_user_prompt(
    *,
    competitors: Sequence[str],
    focus_dimensions: Sequence[str],
    evidence_ids: Sequence[str],
) -> str:
    return (
        "Fallback analysis request:\n"
        f"- competitors: {_json(list(competitors))}\n"
        f"- focus_dimensions: {_json(list(focus_dimensions))}\n"
        f"- evidence_ids: {_json(list(evidence_ids))}\n\n"
        "Return minimal valid JSON with at least one insight."
    )


def build_qa_semantic_user_prompt(
    *,
    report_markdown: str,
    report_json: dict[str, object],
    failed_rule_ids: Sequence[str],
    evidence_briefs: Sequence[dict[str, object]],
) -> str:
    return (
        "QA semantic audit context:\n"
        f"- failed_rule_ids: {_json(list(failed_rule_ids))}\n"
        f"- report_json: {_json(report_json)}\n"
        f"- report_markdown_preview: {_json(report_markdown[:600])}\n"
        f"- evidence_briefs: {_json(list(evidence_briefs)[-20:])}\n\n"
        f"reject_to must be one of {_json(list(QA_SEMANTIC_ALLOWED_REJECT_TO))}."
    )


def build_qa_semantic_fallback_user_prompt(
    *,
    failed_rule_ids: Sequence[str],
    evidence_count: int,
) -> str:
    return (
        "Fallback QA semantic audit request:\n"
        f"- failed_rule_ids: {_json(list(failed_rule_ids))}\n"
        f"- evidence_count: {evidence_count}\n\n"
        "Return minimal valid JSON for semantic_audit_passed/reject_to/severity/finding/required_fields."
    )


def build_writer_user_prompt(
    *,
    user_query: str,
    template_id: str,
    requested_sections: Sequence[str],
    competitors: Sequence[str],
    evidence_briefs: Sequence[dict[str, object]],
    analyst_summary: str,
    analyst_insights: Sequence[dict[str, object]],
    risk_flags: Sequence[str],
    recommended_sections: Sequence[str],
) -> str:
    return (
        "Writer context:\n"
        f"- user_query: {user_query}\n"
        f"- template_id: {template_id}\n"
        f"- requested_sections: {_json(list(requested_sections))}\n"
        f"- allowed_section_ids: {_json(list(WRITER_ALLOWED_SECTION_IDS))}\n"
        f"- competitors: {_json(list(competitors))}\n"
        f"- evidence_briefs: {_json(list(evidence_briefs)[-24:])}\n"
        f"- analyst_summary: {analyst_summary}\n"
        f"- analyst_insights: {_json(list(analyst_insights)[:10])}\n"
        f"- risk_flags: {_json(list(risk_flags))}\n"
        f"- recommended_sections: {_json(list(recommended_sections))}\n\n"
        "Write a battlecard with grounded evidence refs. Prefer requested_sections; "
        "if requested_sections is empty, follow recommended_sections."
    )


def build_writer_fallback_user_prompt(
    *,
    template_id: str,
    requested_sections: Sequence[str],
    evidence_ids: Sequence[str],
    analyst_summary: str,
) -> str:
    return (
        "Fallback writer request:\n"
        f"- template_id: {template_id}\n"
        f"- requested_sections: {_json(list(requested_sections))}\n"
        f"- evidence_ids: {_json(list(evidence_ids))}\n"
        f"- allowed_section_ids: {_json(list(WRITER_ALLOWED_SECTION_IDS))}\n"
        f"- analyst_summary: {analyst_summary}\n\n"
        "Return minimal valid battlecard JSON with at least one section and evidence_refs."
    )


