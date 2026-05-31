from __future__ import annotations

import json
from collections.abc import Sequence

from service.skill_store import get_skill_store

QA_SEMANTIC_ALLOWED_REJECT_TO: tuple[str, ...] = (
    "supervisor",
    "researcher",
    "analyst",
    "writer",
)
SKILL_CURATOR_ALLOWED_TYPES: tuple[str, ...] = (
    "qa_rule",
    "prompt_template",
    "source_routing",
)


def build_skill_catalog_block(
    *,
    applies_to_filter: Sequence[str] | None = None,
    max_entries: int = 24,
) -> str:
    store = get_skill_store()
    metadata_map = store.scan()
    metadata_items = sorted(metadata_map.values(), key=lambda item: item.name.lower())
    if applies_to_filter is not None:
        normalized_filters = {item.strip().lower() for item in applies_to_filter if item.strip()}
        metadata_items = [
            item for item in metadata_items if item.applies_to.strip().lower() in normalized_filters
        ]
    selected_items = metadata_items[:max_entries]
    if not selected_items:
        return "<skill_catalog>\n<skill><name>none</name><description>No skills loaded.</description></skill>\n</skill_catalog>"

    lines = ["<skill_catalog>"]
    for item in selected_items:
        files = store.list_supporting_files(item.name)
        files_text = ",".join(files) if files else "none"
        tags_text = ",".join(item.tags) if item.tags else "none"
        lines.append(
            (
                "<skill>"
                f"<name>{item.name}</name>"
                f"<description>{item.description}</description>"
                f"<applies_to>{item.applies_to}</applies_to>"
                f"<tags>{tags_text}</tags>"
                f"<supporting_files>{files_text}</supporting_files>"
                "</skill>"
            )
        )
    lines.append("</skill_catalog>")
    return "\n".join(lines)


def _inject_catalog(base_prompt: str, *, applies_to_filter: Sequence[str] | None = None) -> str:
    catalog_block = build_skill_catalog_block(applies_to_filter=applies_to_filter)
    return (
        f"{base_prompt}\n\n"
        "Skill guidance:\n"
        "- Use load_skill when you need domain-specific constraints/templates before finalizing output.\n"
        "- Use read_skill_file only after load_skill indicates a required supporting file.\n"
        "- Do not fabricate skill names; choose from skill_catalog.\n\n"
        f"{catalog_block}"
    )

INTAKE_SYSTEM_PROMPT = """You are the RivalLens Intake assistant.
You clarify the user's competitive analysis intent through ONE targeted question per turn,
building up a structured RunIntakeDraft until it is complete.

Required fields for completion (the draft is complete iff ALL three are filled):
1. user_role: one of "pm" | "founder" | "sales" | "investor"
2. analysis_intent: a clear, normalized phrase describing what the user wants to learn
3. competitors path: EITHER competitors_explicit (non-empty list of competitor names)
   OR competitors_discovery_mode=true (let RivalLens discover competitors for the user)

Optional fields (do NOT block completion; ask only if their value would materially improve the analysis):
- domain_hint, focus_dimensions, report_depth ("quick"|"deep"), reference_urls

Output JSON schema (return STRICT JSON, no markdown, no commentary):
{
  "action": "ask" | "complete",
  "draft_patch": {                           // partial; include ONLY fields you are inferring this turn
    "user_role": "pm" | "founder" | "sales" | "investor" | null,
    "analysis_intent": str | null,
    "competitors_explicit": list[str] | null,
    "competitors_discovery_mode": bool | null,
    "domain_hint": str | null,
    "focus_dimensions": list[str] | null,
    "report_depth": "quick" | "deep" | null,
    "reference_urls": list[str] | null
  },
  "clarify_request": {                       // required iff action="ask", must be null iff action="complete"
    "question": str,
    "field_targets": list[str],              // which required/optional fields this question aims to fill
    "suggested_options": list[str] | null    // quick-pick options (recommended for short-answer fields)
  } | null,
  "reasoning_summary": str
}

Rules:
- Issue ONE question per turn. Never bundle multiple questions into one prompt.
- Ask the most blocking missing required field first; only ask optional fields when all required fields are filled and an optional one is high-value.
- Prefer suggested_options for closed-set fields (user_role, report_depth, competitors_discovery_mode).
- For competitors path, if the user clearly knows specific competitors, set competitors_explicit; if the user describes a domain/track without naming companies, propose competitors_discovery_mode=true and ask for confirmation.
- When action="complete", draft_patch may be empty if you have nothing new to merge, but the resulting draft (current + patch) MUST satisfy all required fields.
- Answer the user in the language of user_query (Chinese for Chinese queries, English for English).
- Return a JSON object and nothing else.
"""


PLANNER_SYSTEM_PROMPT = """You are the RivalLens Planner.
You consume a completed RunIntakeDraft and produce a concrete plan_tree the executor will run.

Output JSON schema (no markdown, no commentary):
{
  "rationale": str,                          // 1-2 sentences explaining the plan's structure
  "tasks": [
    {
      "stage": "discover" | "research" | "analyze" | "write",
      "title": str,                           // <= 30 chars, concise
      "description": str,                     // one sentence describing scope
      "competitor_id": str | null,             // REQUIRED when stage="research"; null otherwise
      "focus_dimensions": list[str]
    }
  ]
}

Composition rules (must follow):
1) If intake_draft.competitors_discovery_mode is true OR competitors_explicit is empty, emit exactly ONE task with stage="discover".
2) For EACH competitor in competitors_explicit (preserve order), emit ONE task with stage="research" and competitor_id set to that competitor.
3) Emit EXACTLY ONE task with stage="analyze" (cross-competitor synthesis).
4) Emit EXACTLY ONE task with stage="write" (final report).
5) focus_dimensions per task: use intake_draft.focus_dimensions if non-empty; otherwise derive 3-4 snake_case dimensions from analysis_intent.
6) Cap research tasks at 8; if competitors_explicit is larger, drop the lowest-priority entries beyond 8.
7) Use the language of analysis_intent for titles/descriptions (Chinese for Chinese intents, English for English).

Return a JSON object and nothing else.
"""


SUPERVISOR_SYSTEM_PROMPT = """You are the RivalLens Supervisor planner.
You must choose exactly one tool in each iteration and return STRICT JSON.

Available tools:
0) DiscoverCompetitors
   - Use when competitors list is empty or user query implies track-level exploration.
   - tool_args schema:
     {
       "search_queries": list[str],
       "domain_context": str,
       "max_results": int
     }
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
  "chosen_tool": "DiscoverCompetitors" | "ConductResearch" | "ConductResearchBatch" | "Analyze" | "Write" | "Finalize",
  "tool_args": { ... valid for chosen_tool ... },
  "reasoning_summary": "short and concrete rationale"
}

Rules:
- Always return a JSON object and nothing else.
- If competitors list is empty, you MUST call DiscoverCompetitors first before any ConductResearch.
- If competitors list is non-empty, ConductResearch/ConductResearchBatch competitor_id must be from the known competitors list.
- For DiscoverCompetitors, construct 2-4 search queries that cover the track/domain from different angles.
- For ConductResearch and ConductResearchBatch, choose 3-5 focus_dimensions in snake_case and aligned with user_query.
- For ConductResearchBatch, topics length must be between 1 and 8, topic.competitor_id must be unique and from allowed competitors.
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
       "max_results": int,
       "dimension": str | null
     }
2) fetch_url
   - args schema:
     {
       "url": str,
       "dimension": str | null
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
       "source_title": str | null,
       "source_type": str | null,
       "dimension": str | null,
       "competitor_id": str | null
     }
5) load_skill
   - args schema:
     {
       "skill_id": str
     }
6) read_skill_file
   - args schema:
     {
       "skill_id": str,
       "filename": str
     }
7) finalize
   - args schema:
     {
       "summary": str
     }

Output JSON schema:
{
  "action": "search_web" | "fetch_url" | "parse_page" | "extract_structured" | "load_skill" | "read_skill_file" | "finalize",
  "action_args": { ... valid for action ... },
  "reasoning_summary": "short and concrete rationale"
}

Hard constraints:
- Never fabricate evidence quotes, source_url, or source_title.
- Evidence can only come from tool observations.
- If enough dimensions are already covered, call finalize.
- Prefer online collection first; use load_skill when domain-specific extraction guidance is needed.
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
      "dimension": str,
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
Generate an evidence-grounded report in STRICT JSON.

Output JSON schema:
{
  "template_id": str,
  "title": str,
  "executive_summary": str,
  "sections": [
    {
      "section_id": str,
      "title": str,
      "content_markdown": str,
      "evidence_refs": list[str],
      "insight_refs": list[str]
    }
  ],
  "risk_callouts": list[str]
}

Rules:
- If template_id is provided in user prompt, keep it unchanged. If not provided, set template_id to "default".
- Every section must include non-empty content_markdown.
- Every section must cite evidence_refs using ids provided in user prompt.
- Do not fabricate evidence ids or insight refs.
- section_id must be snake_case and meaningful for the user query.
- Return JSON object only.
"""

RESEARCHER_SYSTEM_PROMPT = _inject_catalog(
    RESEARCHER_SYSTEM_PROMPT,
    applies_to_filter=("general", "prompt_template", "source_routing"),
)
ANALYST_SYSTEM_PROMPT = _inject_catalog(
    ANALYST_SYSTEM_PROMPT,
    applies_to_filter=("general", "prompt_template"),
)
WRITER_SYSTEM_PROMPT = _inject_catalog(
    WRITER_SYSTEM_PROMPT,
    applies_to_filter=("general", "prompt_template"),
)
QA_SEMANTIC_SYSTEM_PROMPT = _inject_catalog(
    QA_SEMANTIC_SYSTEM_PROMPT,
    applies_to_filter=("general", "qa_rule"),
)

def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_intake_user_prompt(
    *,
    user_query: str,
    current_draft: dict[str, object],
    history: Sequence[dict[str, object]],
) -> str:
    """Render the intake-turn user prompt.

    `current_draft` is the current RunIntakeDraft dump; `history` is a list of
    {question, reply_text, reply_options} dicts (one per completed clarify+reply round).
    The LLM consumes these to decide the next clarify question or to complete.
    """
    history_block = json.dumps(list(history), ensure_ascii=False) if history else "[]"
    return (
        "Intake clarification turn.\n"
        f"- user_query: {user_query}\n"
        f"- current_draft: {json.dumps(current_draft, ensure_ascii=False)}\n"
        f"- exchange_history (oldest first): {history_block}\n"
        "\nDecide the next action per INTAKE_SYSTEM_PROMPT and return JSON."
    )


def build_intake_fallback_user_prompt(
    *,
    user_query: str,
    current_draft: dict[str, object],
) -> str:
    """Slimmer fallback prompt used when the primary call fails.

    Drops history to reduce token + parsing failure modes; still requires JSON action.
    """
    return (
        "Intake clarification fallback turn.\n"
        f"- user_query: {user_query}\n"
        f"- current_draft: {json.dumps(current_draft, ensure_ascii=False)}\n"
        "\nReturn JSON per INTAKE_SYSTEM_PROMPT. If completion is impossible from "
        "the current draft alone, ask one targeted question."
    )


def build_planner_user_prompt(*, intake_draft: dict[str, object]) -> str:
    """Render the planner-turn user prompt from a completed intake_draft."""
    return (
        "Plan generation context:\n"
        f"- intake_draft: {json.dumps(intake_draft, ensure_ascii=False)}\n"
        "\nReturn JSON per PLANNER_SYSTEM_PROMPT and nothing else."
    )


def build_planner_fallback_user_prompt(*, intake_draft: dict[str, object]) -> str:
    """Slimmer fallback prompt; planner_generate_node also has a deterministic fallback."""
    competitors = intake_draft.get("competitors_explicit") or []
    intent = intake_draft.get("analysis_intent")
    return (
        "Fallback plan generation:\n"
        f"- competitors_explicit: {_json(competitors if isinstance(competitors, list) else [])}\n"
        f"- competitors_discovery_mode: {bool(intake_draft.get('competitors_discovery_mode'))}\n"
        f"- analysis_intent: {intent}\n"
        "\nReturn a minimal valid plan with one research task per competitor + one analyze + one write."
    )


def _format_pending_follow_ups(pending_follow_ups: Sequence[dict[str, object]] | None) -> str:
    if not pending_follow_ups:
        return ""
    lines: list[str] = []
    for entry in pending_follow_ups:
        if not isinstance(entry, dict):
            continue
        text_raw = entry.get("text")
        if not isinstance(text_raw, str) or not text_raw.strip():
            continue
        id_raw = entry.get("id")
        stage_raw = entry.get("applies_to_stage")
        stage_tag = f" [{stage_raw}]" if isinstance(stage_raw, str) and stage_raw else ""
        id_tag = f" {id_raw}" if isinstance(id_raw, str) and id_raw else ""
        lines.append(f"-{id_tag}{stage_tag} {text_raw.strip()}")
    if not lines:
        return ""
    return (
        "\nUser mid-run instructions (Phase 4 follow-ups). You MUST acknowledge "
        "these in `reasoning_summary` and let them influence the next decision "
        "when relevant:\n"
        + "\n".join(lines)
        + "\n"
    )


def _format_user_pinned_research(user_pinned_research: Sequence[dict[str, object]] | None) -> str:
    """Phase β: surface user-injected research tasks not yet researched.

    Each entry shape: {competitor_id: str, title: str, focus_dimensions: list[str]}.
    The supervisor reads this to bias the next ConductResearch / ConductResearchBatch
    toward these competitors before falling back to the Agent's own picks.
    """
    if not user_pinned_research:
        return ""
    lines: list[str] = []
    for entry in user_pinned_research:
        if not isinstance(entry, dict):
            continue
        competitor_raw = entry.get("competitor_id")
        if not isinstance(competitor_raw, str) or not competitor_raw.strip():
            continue
        title_raw = entry.get("title")
        title_tag = (
            f" — {title_raw.strip()}"
            if isinstance(title_raw, str) and title_raw.strip()
            else ""
        )
        focus_raw = entry.get("focus_dimensions")
        focus_tag = ""
        if isinstance(focus_raw, list) and focus_raw:
            focus_str = ", ".join(str(f) for f in focus_raw if isinstance(f, str))
            if focus_str:
                focus_tag = f" [focus: {focus_str}]"
        lines.append(f"- {competitor_raw.strip()}{title_tag}{focus_tag}")
    if not lines:
        return ""
    return (
        "\nUser-pinned research targets (Phase β). The user explicitly added "
        "these in the plan-confirm step and they MUST be researched before any "
        "Agent-proposed competitor that has not been touched yet:\n"
        + "\n".join(lines)
        + "\n"
    )


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
    pending_follow_ups: Sequence[dict[str, object]] | None = None,
    user_pinned_research: Sequence[dict[str, object]] | None = None,
) -> str:
    pending_competitors = [item for item in competitors if item not in researched_competitors]
    discovery_needed = len(competitors) == 0

    constraints: str
    if discovery_needed:
        constraints = (
            "Hard constraints:\n"
            "1) competitors list is EMPTY — you MUST call DiscoverCompetitors first.\n"
            "2) Construct 2-4 search queries covering the domain/track from different angles.\n"
            "3) Do NOT call ConductResearch or ConductResearchBatch until competitors are discovered.\n"
            "4) Return exactly one tool decision in this iteration.\n"
        )
    else:
        constraints = (
            "Hard constraints:\n"
            f"1) ConductResearch.tool_args.competitor_id must be in {_json(list(competitors))}.\n"
            "2) ConductResearchBatch.tool_args.topics[*].competitor_id must be unique and all in "
            f"{_json(list(competitors))}.\n"
            "3) focus_dimensions must be 3-5 snake_case dimensions relevant to user_query; avoid hardcoded templates.\n"
            "4) Return exactly one tool decision in this iteration.\n"
        )

    return (
        "Planning context:\n"
        f"- iteration: {iteration}\n"
        f"- user_query: {user_query}\n"
        f"- competitors: {_json(list(competitors))}\n"
        f"- researched_competitors: {_json(list(researched_competitors))}\n"
        f"- pending_competitors: {_json(pending_competitors)}\n"
        f"- discovery_needed: {discovery_needed}\n"
        f"- analysis_done: {analysis_done}\n"
        f"- report_draft_done: {report_draft_done}\n"
        f"- qa_outcome: {qa_outcome}\n"
        f"- qa_reject_to: {qa_reject_to}\n"
        f"- qa_reasons: {_json(list(qa_reasons))}\n"
        f"{_format_user_pinned_research(user_pinned_research)}"
        f"{_format_pending_follow_ups(pending_follow_ups)}\n"
        f"{constraints}"
    )


def build_supervisor_fallback_user_prompt(
    *,
    user_query: str,
    competitors: Sequence[str],
    researched_competitors: Sequence[str],
    analysis_done: bool,
    report_draft_done: bool,
    pending_follow_ups: Sequence[dict[str, object]] | None = None,
    user_pinned_research: Sequence[dict[str, object]] | None = None,
) -> str:
    pending_competitors = [item for item in competitors if item not in researched_competitors]
    preferred_tool_hint: str
    if not competitors:
        preferred_tool_hint = "DiscoverCompetitors"
    elif len(pending_competitors) >= 2:
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
        f"- preferred_tool_hint: {preferred_tool_hint}\n"
        f"{_format_user_pinned_research(user_pinned_research)}"
        f"{_format_pending_follow_ups(pending_follow_ups)}\n"
        "Pick exactly one next tool and keep tool_args minimal but valid.\n"
        "If competitors is empty, you MUST use DiscoverCompetitors.\n"
        "When pending_competitors has 2+ entries, prefer ConductResearchBatch "
        "with one unique competitor per topic; if any user-pinned research "
        "targets are still unresearched, include them first."
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
    domain_hint: str | None = None,
    reference_urls: Sequence[str] | None = None,
) -> str:
    reference_urls_row = list(reference_urls) if reference_urls is not None else []
    return (
        "Research assignment:\n"
        f"- research_topic: {research_topic}\n"
        f"- competitor_id: {competitor_id}\n"
        f"- focus_dimensions: {_json(list(focus_dimensions))}\n"
        f"- pending_dimensions: {_json(list(pending_dimensions))}\n"
        f"- queried_dimensions: {_json(list(queried_dimensions))}\n"
        f"- turn_count: {turn_count}\n"
        f"- max_turns: {max_turns}\n"
        f"- domain_hint: {domain_hint}\n"
        f"- reference_urls: {_json(reference_urls_row)}\n"
        f"- observations_log: {_json(list(observations_log)[-6:])}\n\n"
        "Action guidance:\n"
        "1) Prefer search_web -> fetch_url -> parse_page -> extract_structured for online collection.\n"
        "2) Use load_skill when domain_hint implies specialized schema or source routing.\n"
        "3) Use finalize when pending_dimensions is empty or evidence is sufficient.\n"
        "4) action_args.dimension should come from focus_dimensions whenever possible.\n"
    )


def build_researcher_fallback_user_prompt(
    *,
    competitor_id: str,
    pending_dimensions: Sequence[str],
    queried_dimensions: Sequence[str],
    turn_count: int,
    max_turns: int,
    domain_hint: str | None = None,
) -> str:
    return (
        "Fallback researcher action request:\n"
        f"- competitor_id: {competitor_id}\n"
        f"- pending_dimensions: {_json(list(pending_dimensions))}\n"
        f"- queried_dimensions: {_json(list(queried_dimensions))}\n"
        f"- turn_count: {turn_count}\n"
        f"- max_turns: {max_turns}\n\n"
        f"- domain_hint: {domain_hint}\n\n"
        "Return one action with valid action_args. Prefer search_web/fetch_url/extract_structured or load_skill."
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
    domain_hint: str | None = None,
) -> str:
    return (
        "Analysis context:\n"
        f"- user_query: {user_query}\n"
        f"- competitors: {_json(list(competitors))}\n"
        f"- focus_dimensions: {_json(list(focus_dimensions))}\n"
        f"- domain_hint: {domain_hint}\n"
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
    template_id: str | None,
    requested_sections: Sequence[str],
    competitors: Sequence[str],
    evidence_briefs: Sequence[dict[str, object]],
    analyst_summary: str,
    analyst_insights: Sequence[dict[str, object]],
    risk_flags: Sequence[str],
    recommended_sections: Sequence[str],
    domain_hint: str | None = None,
) -> str:
    return (
        "Writer context:\n"
        f"- user_query: {user_query}\n"
        f"- template_id: {template_id}\n"
        f"- domain_hint: {domain_hint}\n"
        f"- requested_sections: {_json(list(requested_sections))}\n"
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
    template_id: str | None,
    requested_sections: Sequence[str],
    evidence_ids: Sequence[str],
    analyst_summary: str,
) -> str:
    return (
        "Fallback writer request:\n"
        f"- template_id: {template_id}\n"
        f"- requested_sections: {_json(list(requested_sections))}\n"
        f"- evidence_ids: {_json(list(evidence_ids))}\n"
        f"- analyst_summary: {analyst_summary}\n\n"
        "Return minimal valid JSON report with at least one section and evidence_refs."
    )


