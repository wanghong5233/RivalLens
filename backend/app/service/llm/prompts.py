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
- self_product: the requester's OWN product / team / positioning, used to frame competitors RELATIVE to them (turns a neutral listing into "where should WE invest")
- market_scope: target market / geography / segment (e.g. "中国", "海外", "全球", "中小企业") — scopes which sources matter
- time_context: decision timing or data-recency need (e.g. "下月给高层汇报", "只看近一年")

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
    "reference_urls": list[str] | null,
    "self_product": str | null,
    "market_scope": str | null,
    "time_context": str | null,
    "response_language": "zh" | "en" | null
  },
  "clarify_request": {                       // required iff action="ask", must be null iff action="complete"
    "question": str,
    "field_targets": list[str],              // which required/optional fields this question aims to fill
    "suggested_options": list[str] | null,   // quick-pick options (recommended for short-answer fields)
    "suggested_answer": str | null           // one editable example answer for open-ended fields
  } | null,
  "summary_title": str | null,               // required iff action="complete"; 6-15 chars, user_query's language
  "reasoning_summary": str
}

Rules:
- EXTRACT FIRST, ASK SECOND. Before deciding to ask anything, scan user_query
  and the latest exchange_history reply, and emit ALL fields you can confidently
  infer into draft_patch. Example signals you must catch:
    * "我是产品经理" / "I'm a PM at..." → user_role="pm"
    * "我们是做工业自动化设备销售的" / "我是销售运营" → user_role="sales"
    * "我们是初创公司创始人" / "I'm a co-founder" → user_role="founder"
    * "我们想对标 X、Y、Z" → competitors_explicit=["X","Y","Z"]
    * "想了解 X 赛道有哪些玩家" with no names → competitors_discovery_mode=true
    * Industry phrases ("AI 编程"/"AI coding", "供应链"/"supply chain", "ERP"/"CRM") → domain_hint
    * "我们是某大厂 AI 工具团队" / "我们做的是一款 AI 简历工具" → self_product
    * "中国 vs 海外", "面向中小企业", "国内市场" → market_scope
    * "下个月要汇报", "下周给老板方案", "只看近一年的数据" → time_context
    * Explicit output-language requests ("用英文输出", "Please answer in Chinese") → response_language
  Only ask about fields you genuinely cannot infer from the available text.
- response_language defaults to the detected language of user_query. Set it in
  draft_patch ONLY when the user explicitly requests Chinese/English output.
- Issue ONE question per turn. Never bundle multiple questions into one prompt.
- Ask the most blocking missing required field first.
- After ALL THREE required fields are filled, do NOT immediately complete if a HIGH-VALUE
  optional field is still empty AND cannot be inferred. Ask at most ONE such optional
  question (one per turn), prioritizing in this order: self_product (relative framing) >
  market_scope (source scoping) > focus_dimensions/report_depth/time_context. Skip any
  optional you already inferred. Never ask more than 1-2 optional questions total — if the
  user gives a short/skip answer ("不用了" / "skip" / "随便"), complete immediately.
- self_product is most valuable when analysis_intent implies a "我方该怎么做" decision
  (投入方向 / 定位 / 差异化); for a pure neutral market scan it may be irrelevant — use judgment.
- Prefer suggested_options for closed-set fields (user_role, report_depth, competitors_discovery_mode).
- suggested_options should be USER-FRIENDLY bilingual labels, NOT raw enum values.
  Good: ["PM / 产品经理", "Founder / 创业者", "Sales / 销售", "Investor / 投资人"]
  Bad:  ["pm", "founder", "sales", "investor"]
  Good: ["我已有名单 (explicit)", "让 Agent 帮我发现 (auto-discover)"]
  Good: ["速览 (quick)", "深度报告 (deep)"]
  The backend wait-node normalizes labels back to enum values, so options can be
  freely phrased. Always pair the localized term with its internal English keyword
  in parentheses for the closed-set discovery / depth questions.
- For open-ended fields (especially analysis_intent / domain_hint), provide
  clarify_request.suggested_answer:
    * Language MUST match user_query.
    * <= 60 characters.
    * A direct editable statement (not a question, not meta-instructions).
    * Must add concrete context beyond repeating question text.
  Example good suggested_answer:
    * "想了解供应链 SaaS 的实施风险、集成与定价差异。"
    * "Need a market scan of CRM tools for renewal-risk teams."
    * "想比较 AI 编程工具的企业版功能与合规差异。"
  Bad:
    * "请问您想了解什么？" (question)
    * "我想了解这个问题" (too vague)
    * Exact substring copied from question.
- If suggested_options is non-empty for a closed-set field, suggested_answer
  may be null.
- NEVER re-ask a field that is already populated in current_draft. If you find
  yourself wanting to re-confirm, prefer action="complete" or move on to the
  next missing field.
- For competitors path, if the user clearly knows specific competitors, set competitors_explicit; if the user describes a domain/track without naming companies, propose competitors_discovery_mode=true and ask for confirmation.
- When action="complete", draft_patch may be empty if you have nothing new to merge, but the resulting draft (current + patch) MUST satisfy all required fields.
- When action="complete", MUST also produce summary_title:
    * 6-15 characters, single line, in the language of user_query.
    * A noun phrase the user would recognize as the *subject* of the analysis,
      not a verb phrase. Good: "供应链 ERP 调研", "CRM 续费风险", "AI 编程工具对比".
      Bad: "我要分析竞品" (verb phrase, generic), "如何让产品更好" (question).
    * Prefer key product/track names if explicit competitors are known
      (e.g. "[产品A] vs [产品B] · 企业版"); otherwise capture the domain
      (e.g. "智能制造 ERP 调研").
    * No quotation marks, no trailing punctuation.
- When action="ask", summary_title MUST be null.
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
5) focus_dimensions per task: use intake_draft.focus_dimensions if non-empty; otherwise derive 3-4 concise dimensions from analysis_intent.
   focus_dimensions MUST be English snake_case contract ids, even when titles/descriptions are Chinese.
   Each focus_dimension MUST be <= 32 chars, use a-z0-9_ only, and be 1-3 words.
   Prefer canonical ids such as product_positioning, pricing_strategy, enterprise_capabilities, market_differences, feature, pricing, user_feedback.
6) Cap research tasks at 8; if competitors_explicit is larger, drop the lowest-priority entries beyond 8.
7) Use the language of analysis_intent for titles/descriptions (Chinese for Chinese intents, English for English).
8) If intake_draft.self_product is set, the analyze/write tasks MUST frame findings RELATIVE to it
   (gaps vs self, where self wins/loses, actionable direction) — reflect this in their description.
9) If intake_draft.market_scope is set, reflect that scope in research task descriptions (e.g. prioritize
   sources for that geography/segment); if it implies a comparison (e.g. "中国 vs 海外"), ensure the
   analyze task covers that axis.

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
- For DiscoverCompetitors, construct 2-4 search queries that cover the track/domain from different angles; when market_scope is provided, include that geography/segment and use language variants aligned with the user's language.
- For ConductResearch and ConductResearchBatch, choose 3-5 focus_dimensions in concise snake_case aligned with user_query.
- Each focus_dimension MUST be <= 32 chars, use a-z0-9_ only, and be 1-3 words.
- Set max_iterations >= the number of focus_dimensions so each requested dimension can get at least one tool turn.
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
       "query": str | null,
       "dimension": str | null
     }
3) extract_structured
   - args schema:
     {
       "text": str,
       "source_url": str | null,
       "source_title": str | null,
       "source_type": str | null,
       "dimension": str | null,
       "competitor_id": str | null
     }
4) load_skill
   - args schema:
     {
       "skill_id": str
     }
5) read_skill_file
   - args schema:
     {
       "skill_id": str,
       "filename": str
     }
6) finalize
   - args schema:
     {
       "summary": str
     }

Output JSON schema:
{
  "action": "search_web" | "fetch_url" | "extract_structured" | "load_skill" | "read_skill_file" | "finalize",
  "action_args": { ... valid for action ... },
  "reasoning_summary": "short and concrete rationale"
}

Hard constraints:
- Never fabricate evidence quotes, source_url, or source_title.
- Evidence can only come from tool observations.
- If enough dimensions are already covered, call finalize.
- Prefer online collection first; use load_skill when domain-specific extraction guidance is needed.
- For buyer-critical dimensions (pricing, enterprise, security, compliance), gather evidence from the vendor's OWN site first (e.g. search `site:<official-domain> pricing`, or fetch the official pricing/security/docs page); fall back to third-party articles only when the official source yields nothing.
- When action_args.dimension is present, it MUST be exactly one value from focus_dimensions. Do not invent compound dimensions.
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
  "comparisons": [
    {
      "dimension": str,
      "cells": [
        {
          "competitor_id": str,
          "stance": "leader" | "competitive" | "laggard" | "unknown",
          "summary": str,
          "evidence_ids": list[str]
        }
      ]
    }
  ],
  "schema_version": "schema_v0.2",
  "features": [
    {
      "id": str,
      "competitor_id": str,
      "name": str,
      "parent_id": str | null,
      "description": str | null,
      "maturity": "unknown" | "basic" | "advanced" | "leading" | null,
      "evidence_ids": list[str]
    }
  ],
  "pricings": [
    {
      "id": str,
      "competitor_id": str,
      "model": str,
      "tiers": list[dict],
      "free_plan": bool | null,
      "enterprise_plan": bool | null,
      "evidence_ids": list[str]
    }
  ],
  "personas": [
    {
      "id": str,
      "name": str,
      "role": str,
      "pain_points": list[str],
      "jobs_to_be_done": list[str],
      "evidence_ids": list[str]
    }
  ],
  "coverage": {
    "<competitor_id>": {
      "feature": "complete" | "partial" | "insufficient_data" | "missing",
      "pricing": "complete" | "partial" | "insufficient_data" | "missing",
      "feedback": "complete" | "partial" | "insufficient_data" | "missing"
    }
  },
  "risk_flags": list[str],
  "recommended_sections": list[str]
}

Rules:
- Write all analysis output in response_language when provided (zh = Chinese, en = English);
  otherwise default to the language of user_query.
- Evidence may be in any language. Translate and synthesize its meaning into response_language;
  do NOT skip or down-weight a fact because its source is in another language. The carrier
  language is irrelevant to evidence value. Keep source_url and source identifiers (evidence_ids)
  unchanged for citation; never translate ids.
- Every insight must reference existing evidence_ids from user prompt.
- Produce at least one insight per focus dimension that has grounded evidence; keep findings cross-competitor when evidence allows.
- For comparisons, create one group per focus dimension when at least two competitors have evidence or can be marked unknown.
- Each comparison cell must use a competitor_id from the user prompt; stance is qualitative, not numeric.
- Use evidence_ids to ground each cell when available; if evidence is insufficient, set stance="unknown" and evidence_ids=[].
- Also synthesize the predefined knowledge schema: features, pricings, personas, and coverage.
- Feature and pricing items must cite existing evidence_ids. If evidence is missing, omit the item and mark coverage honestly.
- Build feature hierarchy with parent_id when evidence supports a parent/child relationship; otherwise use null.
- For pricing, if the pricing model is unclear but pricing evidence exists, set model="unknown".
- Personas should reflect buyer/user roles, pain points, and jobs-to-be-done only when evidence supports them.
- For each competitor, mark coverage as complete/partial/insufficient_data/missing. Do not invent data to fill coverage.
- recommended_sections must use snake_case section ids that match insight dimension values.
- Do not fabricate competitor facts.
- Return JSON object only.
"""

QA_SEMANTIC_SYSTEM_PROMPT = """You are RivalLens QA semantic auditor.
You review report quality and evidence consistency in STRICT JSON.

Output JSON schema:
{
  "semantic_audit_passed": bool,
  "reject_to": "supervisor" | "researcher" | "analyst" | "writer",
  "severity": "blocking" | "warning",
  "finding": str,
  "required_fields": list[str],
  "unsupported_numeric_claims": list[{"claim": str, "section_id": str, "reason": str}],
  "dimension_results": {
    "depth": bool,
    "citation_coverage": bool,
    "faithfulness": bool,
    "instruction_following": bool
  }
}

Rules:
- Use deterministic judgment: same input should produce the same JSON.
- depth: true only when a deep report gives concrete cross-competitor analysis, not thin summaries.
- citation_coverage: true only when important claims are tied to evidence_refs from the prompt.
- faithfulness: true only when claims are supported by the provided evidence and do not invent sources.
- instruction_following: true only when sections match requested target sections and report_depth.
- For every numeric_claim in the prompt, decide whether any cited evidence item supports that exact number or a directly computable equivalent. One supporting cited evidence item is sufficient; do not require every cited evidence item to contain the same number.
- Add an item to unsupported_numeric_claims only when no cited evidence item clearly supports the number. Do not include supported claims in unsupported_numeric_claims, and do not write self-correcting reasoning such as "actually supported" inside unsupported_numeric_claims.
- If unsupported_numeric_claims is non-empty, semantic_audit_passed should be false unless deterministic QA has already told you the report is being accepted with warnings.
- If semantic_audit_passed is true, finding should still be concise.
- If false, reject_to must be actionable and required_fields must be specific.
- Semantic findings are advisory unless deterministic QA already produced blocking failures.
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
- Write all report output in response_language when provided (zh = Chinese, en = English);
  otherwise default to the language of user_query.
- Evidence may be in any language. Translate its content into response_language when writing the
  report; never omit a relevant fact because its source is foreign-language. Keep source_url and
  evidence ids in their original form for citation; cite [ev_xxx] as-is.
- If template_id is provided in user prompt, keep it unchanged. If not provided, set template_id to "default".
- Every section must include non-empty content_markdown.
- Every section must cite evidence_refs using ids provided in user prompt.
- In content_markdown, cite inline evidence only as [ev_xxx] using ids from allowed_evidence_ids.
- Never emit bare ev_xxx ids, unknown evidence ids, or insight_x ids in content_markdown.
- Exact numbers such as percentages, prices, counts, dates, and time savings must be directly supported by cited evidence containing the same number or a directly computable equivalent.
- If QA feedback lists unsupported_numeric_claims, remove those exact numbers, rewrite them as qualitative statements, or label them clearly as proposals instead of factual claims.
- During QA rewrites, avoid introducing new exact funding amounts, market-share percentages, acceptance rates, or time windows unless the exact value appears verbatim in evidence_briefs.
- For report_depth=deep, write a materially deeper report: cover every target section, cite evidence in each section, and include concrete competitor comparisons.
- Do not fabricate evidence ids or insight refs.
- section_id must be snake_case and meaningful for the user query.
- Return JSON object only.
"""

RESEARCHER_SYSTEM_PROMPT = _inject_catalog(
    RESEARCHER_SYSTEM_PROMPT,
    applies_to_filter=("general", "source_routing"),
)
ANALYST_SYSTEM_PROMPT = _inject_catalog(
    ANALYST_SYSTEM_PROMPT,
    applies_to_filter=("general",),
)
WRITER_SYSTEM_PROMPT = _inject_catalog(
    WRITER_SYSTEM_PROMPT,
    applies_to_filter=("general",),
)
QA_SEMANTIC_SYSTEM_PROMPT = _inject_catalog(
    QA_SEMANTIC_SYSTEM_PROMPT,
    applies_to_filter=("general", "qa_rule"),
)

def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


RESEARCH_PROMPT_CHAR_BUDGET = 8000
COMPRESSION_PROMPT_CHAR_BUDGET = 12000
OBSERVATION_BRIEF_QUOTE_LIMIT = 200
EVIDENCE_BRIEF_PROMPT_LIMIT = 24
ANALYST_EVIDENCE_BRIEF_PROMPT_LIMIT = 80


def truncate_for_prompt(value: object, *, max_chars: int) -> str:
    serialized = _json(value)
    if len(serialized) <= max_chars:
        return serialized
    return serialized[: max_chars - 3] + "..."


def select_layered_evidence_briefs(
    evidence_briefs: Sequence[dict[str, object]],
    *,
    limit: int = EVIDENCE_BRIEF_PROMPT_LIMIT,
) -> list[dict[str, object]]:
    if limit <= 0:
        return []
    rows = [item for item in evidence_briefs if isinstance(item, dict)]
    if len(rows) <= limit:
        return rows

    # Per (competitor, dimension) group keep one representative. Prefer an official
    # source over a third-party one so buyer-critical claims surface vendor evidence
    # when it exists; within the same authority tier, keep the latest (R10).
    group_official_index: dict[tuple[str, str], int] = {}
    group_latest_index: dict[tuple[str, str], int] = {}
    for index in range(len(rows) - 1, -1, -1):
        item = rows[index]
        competitor_raw = item.get("competitor_id")
        dimension_raw = item.get("dimension")
        competitor_id = competitor_raw if isinstance(competitor_raw, str) and competitor_raw else "unknown"
        dimension = dimension_raw if isinstance(dimension_raw, str) and dimension_raw else "unknown"
        key = (competitor_id, dimension)
        if key not in group_latest_index:
            group_latest_index[key] = index
        if item.get("source_authority") == "official" and key not in group_official_index:
            group_official_index[key] = index

    selected: set[int] = set()
    for key, latest_index in group_latest_index.items():
        selected.add(group_official_index.get(key, latest_index))
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for index in range(len(rows) - 1, -1, -1):
            selected.add(index)
            if len(selected) >= limit:
                break
    return [rows[index] for index in sorted(selected)]


def evidence_draft_refs_for_prompt(
    evidence_drafts: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for draft in list(evidence_drafts)[-8:]:
        if not isinstance(draft, dict):
            continue
        quote_raw = draft.get("quote") or draft.get("sanitized_text")
        quote_len = len(quote_raw) if isinstance(quote_raw, str) else 0
        refs.append(
            {
                "dimension": draft.get("dimension"),
                "competitor_id": draft.get("competitor_id"),
                "source_url": draft.get("source_url"),
                "source_title": draft.get("source_title"),
                "quote_len": quote_len,
            }
        )
    return refs


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
    market_scope: str | None = None,
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
            "   If market_scope is set, include it in discovery search queries and prefer that region/segment.\n"
            "3) Do NOT call ConductResearch or ConductResearchBatch until competitors are discovered.\n"
            "4) Return exactly one tool decision in this iteration.\n"
        )
    else:
        constraints = (
            "Hard constraints:\n"
            f"1) ConductResearch.tool_args.competitor_id must be in {_json(list(competitors))}.\n"
            "2) ConductResearchBatch.tool_args.topics[*].competitor_id must be unique and all in "
            f"{_json(list(competitors))}.\n"
            "3) focus_dimensions must be 3-5 concise snake_case dimensions relevant to user_query; "
            "each value MUST be <= 32 chars, use a-z0-9_ only, and be 1-3 words; avoid hardcoded templates.\n"
            "4) max_iterations must be >= len(focus_dimensions) for every ConductResearch topic.\n"
            "5) Return exactly one tool decision in this iteration.\n"
        )

    return (
        "Planning context:\n"
        f"- iteration: {iteration}\n"
        f"- user_query: {user_query}\n"
        f"- market_scope: {market_scope}\n"
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
    market_scope: str | None = None,
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
        f"- market_scope: {market_scope}\n"
        f"- competitors: {_json(list(competitors))}\n"
        f"- pending_competitors: {_json(pending_competitors)}\n"
        f"- analysis_done: {analysis_done}\n"
        f"- report_draft_done: {report_draft_done}\n"
        f"- preferred_tool_hint: {preferred_tool_hint}\n"
        f"{_format_user_pinned_research(user_pinned_research)}"
        f"{_format_pending_follow_ups(pending_follow_ups)}\n"
        "Pick exactly one next tool and keep tool_args minimal but valid.\n"
        "If competitors is empty, you MUST use DiscoverCompetitors and include market_scope in search_queries when present.\n"
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
    observation_briefs: Sequence[dict[str, object]],
    compressed_summary: str = "",
    domain_hint: str | None = None,
    reference_urls: Sequence[str] | None = None,
    discovered_urls: Sequence[str] | None = None,
) -> str:
    reference_urls_row = list(reference_urls) if reference_urls is not None else []
    discovered_urls_row = list(discovered_urls) if discovered_urls is not None else []
    summary_block = compressed_summary.strip() if compressed_summary.strip() else "(none)"
    briefs_payload = truncate_for_prompt(
        list(observation_briefs)[-6:],
        max_chars=RESEARCH_PROMPT_CHAR_BUDGET // 2,
    )
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
        f"- discovered_urls: {_json(discovered_urls_row)}\n"
        f"- compressed_summary: {summary_block}\n"
        f"- observation_briefs: {briefs_payload}\n\n"
        "Action guidance:\n"
        "1) Prefer search_web -> fetch_url -> extract_structured for online collection.\n"
        "2) Use fetch_url only with URLs from discovered_urls or reference_urls; pass the current research_topic as query when useful.\n"
        "3) Use load_skill when domain_hint implies specialized schema or source routing.\n"
        "4) Use finalize when pending_dimensions is empty or evidence is sufficient.\n"
        "5) action_args.dimension must be one exact value from focus_dimensions; never create compound dimensions.\n"
        "6) If proposing future focus_dimensions in summaries or tool context, keep each concise snake_case <= 32 chars.\n"
    )


def build_researcher_minimal_user_prompt(
    *,
    competitor_id: str,
    pending_dimensions: Sequence[str],
    compressed_summary: str,
    observation_briefs: Sequence[dict[str, object]],
) -> str:
    summary_block = compressed_summary.strip() if compressed_summary.strip() else "(none)"
    briefs_payload = truncate_for_prompt(
        list(observation_briefs)[-2:],
        max_chars=RESEARCH_PROMPT_CHAR_BUDGET // 4,
    )
    return (
        "Minimal researcher action request (context reduced after format error):\n"
        f"- competitor_id: {competitor_id}\n"
        f"- pending_dimensions: {_json(list(pending_dimensions))}\n"
        f"- compressed_summary: {summary_block}\n"
        f"- recent_observation_briefs: {briefs_payload}\n\n"
        "Return one valid JSON action. Prefer finalize if evidence is sufficient."
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
        "Return one action with valid action_args. Prefer search_web/fetch_url/extract_structured or load_skill. "
        "Use only pending_dimensions values for action_args.dimension. "
        "Do not invent long compound dimension names; focus dimensions are concise snake_case <= 32 chars."
    )


def build_compression_user_prompt(
    *,
    messages: Sequence[dict[str, str]],
    observation_briefs: Sequence[dict[str, object]],
    evidence_drafts: Sequence[dict[str, object]],
    compressed_summary: str = "",
) -> str:
    summary_block = compressed_summary.strip() if compressed_summary.strip() else "(none)"
    briefs_payload = truncate_for_prompt(
        list(observation_briefs)[-10:],
        max_chars=COMPRESSION_PROMPT_CHAR_BUDGET // 3,
    )
    refs_payload = truncate_for_prompt(
        evidence_draft_refs_for_prompt(evidence_drafts),
        max_chars=COMPRESSION_PROMPT_CHAR_BUDGET // 3,
    )
    messages_payload = truncate_for_prompt(
        list(messages)[-6:],
        max_chars=COMPRESSION_PROMPT_CHAR_BUDGET // 4,
    )
    return (
        "Compress current researcher trace context.\n"
        f"- prior_compressed_summary: {summary_block}\n"
        f"- messages_tail: {messages_payload}\n"
        f"- observation_briefs: {briefs_payload}\n"
        f"- evidence_refs: {refs_payload}\n"
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
    analysis_intent: str | None = None,
    market_scope: str | None = None,
    response_language: str | None = None,
) -> str:
    selected_evidence_briefs = select_layered_evidence_briefs(
        evidence_briefs,
        limit=ANALYST_EVIDENCE_BRIEF_PROMPT_LIMIT,
    )
    return (
        "Analysis context:\n"
        f"- user_query: {user_query}\n"
        f"- analysis_intent: {analysis_intent}\n"
        f"- market_scope: {market_scope}\n"
        f"- response_language: {response_language}\n"
        f"- competitors: {_json(list(competitors))}\n"
        f"- focus_dimensions: {_json(list(focus_dimensions))}\n"
        f"- domain_hint: {domain_hint}\n"
        f"- evidence_briefs: {_json(selected_evidence_briefs)}\n\n"
        "Produce cross-competitor insights with explicit evidence_ids. "
        "For each focus dimension that has grounded evidence in evidence_briefs, produce at least one insight. "
        "Also produce comparisons: per focus dimension, compare each competitor with stance, summary, and grounded evidence_ids."
        " Also produce structured features, pricings, personas, and coverage from the same evidence. "
        "If evidence is insufficient for a competitor, say so in coverage instead of inventing fields."
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
        "Return minimal valid JSON with at least one insight, empty features/pricings/personas, "
        "and coverage marked insufficient_data for each competitor."
    )


def build_analyst_repair_user_prompt(
    *,
    validation_errors: Sequence[str],
    focus_dimensions: Sequence[str],
    evidence_ids: Sequence[str],
) -> str:
    return (
        "Repair analysis JSON to satisfy schema validation.\n"
        f"- validation_errors: {_json(list(validation_errors))}\n"
        f"- focus_dimensions: {_json(list(focus_dimensions))}\n"
        f"- evidence_ids: {_json(list(evidence_ids))}\n\n"
        "Rules:\n"
        "- recommended_sections must be snake_case ids matching insight dimension values.\n"
        "- Every insight must cite only evidence_ids listed above.\n"
        "- Feature and pricing evidence_ids must cite only evidence_ids listed above.\n"
        "- If structured knowledge is uncertain, return empty features/pricings/personas and coverage=insufficient_data.\n"
        "- Return JSON object only."
    )


def build_qa_semantic_user_prompt(
    *,
    report_markdown: str,
    report_json: dict[str, object],
    failed_rule_ids: Sequence[str],
    evidence_briefs: Sequence[dict[str, object]],
    report_depth: str = "quick",
    target_sections: Sequence[str] = (),
    numeric_claims: Sequence[dict[str, object]] = (),
) -> str:
    selected_evidence_briefs = select_layered_evidence_briefs(evidence_briefs)
    return (
        "QA semantic audit context:\n"
        f"- report_depth: {report_depth}\n"
        f"- target_sections: {_json(list(target_sections))}\n"
        f"- failed_rule_ids: {_json(list(failed_rule_ids))}\n"
        f"- report_json: {_json(report_json)}\n"
        f"- report_markdown: {truncate_for_prompt(report_markdown, max_chars=8000)}\n"
        f"- evidence_briefs: {_json(selected_evidence_briefs)}\n\n"
        f"- numeric_claims: {_json(list(numeric_claims))}\n\n"
        "Judge depth, citation_coverage, faithfulness, and instruction_following separately. "
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
    target_sections: Sequence[str],
    requested_sections: Sequence[str],
    competitors: Sequence[str],
    evidence_briefs: Sequence[dict[str, object]],
    allowed_evidence_ids: Sequence[str],
    analyst_summary: str,
    analyst_insights: Sequence[dict[str, object]],
    risk_flags: Sequence[str],
    recommended_sections: Sequence[str],
    qa_reasons: Sequence[str] = (),
    unsupported_numeric_claims: Sequence[dict[str, object]] = (),
    report_depth: str = "quick",
    domain_hint: str | None = None,
    analysis_intent: str | None = None,
    market_scope: str | None = None,
    response_language: str | None = None,
) -> str:
    selected_evidence_briefs = select_layered_evidence_briefs(evidence_briefs)
    return (
        "Writer context:\n"
        f"- user_query: {user_query}\n"
        f"- analysis_intent: {analysis_intent}\n"
        f"- market_scope: {market_scope}\n"
        f"- response_language: {response_language}\n"
        f"- report_depth: {report_depth}\n"
        f"- template_id: {template_id}\n"
        f"- domain_hint: {domain_hint}\n"
        f"- target_sections: {_json(list(target_sections))}\n"
        f"- requested_sections: {_json(list(requested_sections))}\n"
        f"- recommended_sections: {_json(list(recommended_sections))}\n"
        f"- allowed_evidence_ids: {_json(list(allowed_evidence_ids))}\n"
        f"- competitors: {_json(list(competitors))}\n"
        f"- evidence_briefs: {_json(selected_evidence_briefs)}\n"
        f"- analyst_summary: {analyst_summary}\n"
        f"- analyst_insights: {_json(list(analyst_insights)[:10])}\n"
        f"- risk_flags: {_json(list(risk_flags))}\n\n"
        f"- qa_reasons: {_json(list(qa_reasons))}\n"
        f"- unsupported_numeric_claims: {_json(list(unsupported_numeric_claims)[:12])}\n\n"
        "Write a battlecard with grounded evidence refs. "
        "section_id must exactly match target_sections entries. "
        "Inline citations in content_markdown must use [ev_xxx] only from allowed_evidence_ids; "
        "never output bare ev_xxx or insight_x ids in markdown. "
        "If unsupported_numeric_claims is non-empty, do not repeat those exact numbers unless the "
        "current evidence_briefs directly support them; use qualitative wording or mark strategic "
        "estimates as proposals. "
        "For report_depth=deep, each target section needs enough concrete, cited analysis to pass deep QA gates."
    )


def build_writer_repair_user_prompt(
    *,
    validation_errors: Sequence[str],
    template_id: str | None,
    target_sections: Sequence[str],
    evidence_ids: Sequence[str],
    analyst_summary: str,
) -> str:
    return (
        "Repair writer JSON to satisfy schema validation.\n"
        f"- validation_errors: {_json(list(validation_errors))}\n"
        f"- template_id: {template_id}\n"
        f"- target_sections: {_json(list(target_sections))}\n"
        f"- evidence_ids: {_json(list(evidence_ids))}\n"
        f"- analyst_summary: {analyst_summary}\n\n"
        "Rules:\n"
        "- Every section must include content_markdown (>=60 chars) and evidence_refs from evidence_ids.\n"
        "- section_id must exactly match target_sections.\n"
        "- Return JSON object only."
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


def build_intake_repair_user_prompt(
    *,
    validation_errors: Sequence[str],
    user_query: str,
    current_draft: dict[str, object],
) -> str:
    return (
        "Repair intake JSON to satisfy schema validation.\n"
        f"- validation_errors: {_json(list(validation_errors))}\n"
        f"- user_query: {user_query}\n"
        f"- current_draft: {_json(current_draft)}\n\n"
        "Rules:\n"
        "- action must be ask or complete.\n"
        "- action=ask requires clarify_request with non-empty question.\n"
        "- action=complete requires clarify_request=null.\n"
        "- draft_patch keys must be patchable intake fields only.\n"
        "- Return JSON object only."
    )


def build_planner_repair_user_prompt(
    *,
    validation_errors: Sequence[str],
    intake_draft: dict[str, object],
) -> str:
    return (
        "Repair planner JSON to satisfy schema validation.\n"
        f"- validation_errors: {_json(list(validation_errors))}\n"
        f"- intake_draft: {_json(intake_draft)}\n\n"
        "Rules:\n"
        "- tasks must be a non-empty list with valid stage/title.\n"
        "- research tasks require competitor_id.\n"
        "- Return JSON object only."
    )


def build_supervisor_repair_user_prompt(
    *,
    validation_errors: Sequence[str],
    user_query: str,
    iteration: int,
    competitors: Sequence[str],
) -> str:
    return (
        "Repair supervisor JSON to satisfy schema validation.\n"
        f"- validation_errors: {_json(list(validation_errors))}\n"
        f"- user_query: {user_query}\n"
        f"- iteration: {iteration}\n"
        f"- competitors: {_json(list(competitors))}\n\n"
        "Rules:\n"
        "- chosen_tool must be a valid supervisor tool name.\n"
        "- tool_args must match the chosen_tool schema.\n"
        "- reasoning_summary must be non-empty.\n"
        "- Return JSON object only."
    )


DISCOVERY_EXTRACT_SYSTEM_PROMPT = (
    "You extract grounded competitor candidates from search results. Return valid JSON only. "
    "Use only names and evidence that appear in the provided search_results. Do not invent competitors."
)


def build_discovery_extract_user_prompt(
    *,
    search_results: str,
    domain_context: str,
    user_query: str,
    market_scope: str | None = None,
    analysis_intent: str | None = None,
    response_language: str | None = None,
) -> str:
    reason_language = (
        "Chinese" if response_language == "zh" else "English" if response_language == "en" else "the user query language"
    )
    return (
        "You are a competitive intelligence analyst.\n"
        "Given the following search results about a market/track, extract competitor candidates.\n\n"
        "Context:\n"
        f"- domain_context: {domain_context}\n"
        f"- user_query: {user_query}\n"
        f"- market_scope: {market_scope}\n"
        f"- analysis_intent: {analysis_intent}\n"
        f"- response_language: {response_language}\n\n"
        "Rules:\n"
        "- Return ONLY a JSON object with this schema:\n"
        '  {"candidates":[{"name":"Product","is_competitor":true,'
        '"relevance_reason":"Why it competes in this market",'
        '"evidence_quote":"Exact short quote copied from search_results"}]}\n'
        "- Include only products or companies mentioned in search_results.\n"
        "- Set is_competitor=false when a mentioned entity is adjacent, media-only, or not a direct competitor.\n"
        "- evidence_quote must be an exact short substring copied from search_results.\n"
        "- Disambiguate polysemous entity names by market_scope and analysis_intent. "
        "For example, OPC may mean an industrial protocol, a stock ticker, or outsourcing; "
        "keep only the meaning that matches the user's context and mark unrelated meanings as is_competitor=false.\n"
        "- When market_scope names a region or segment, prefer candidates that operate in that market and mark off-scope candidates false unless they are clearly relevant.\n"
        f"- Write relevance_reason in {reason_language}.\n"
        "- If no search-grounded competitor exists, return {\"candidates\":[]}.\n"
        "- Each name should be the commonly known product name.\n"
        "- Deduplicate and return at most 10 candidates.\n\n"
        f"Search results:\n{search_results}\n\n"
        "Use only the Search results above for names and evidence quotes."
    )


def build_discovery_extract_fallback_user_prompt(
    *,
    domain_context: str,
    user_query: str,
) -> str:
    return (
        "Fallback competitor extraction request:\n"
        f"- domain_context: {domain_context}\n"
        f"- user_query: {user_query}\n\n"
        "No trustworthy search-grounded candidates are available in this fallback path.\n"
        'Return minimal valid JSON: {"candidates":[]}.'
    )


def build_discovery_extract_repair_user_prompt(
    *,
    validation_errors: Sequence[str],
    domain_context: str,
) -> str:
    return (
        "Repair discovery extract JSON to satisfy schema validation.\n"
        f"- validation_errors: {_json(list(validation_errors))}\n"
        f"- domain_context: {domain_context}\n\n"
        "Rules:\n"
        "- Return ONLY a JSON object with a candidates list.\n"
        "- Each candidate must include name, is_competitor, relevance_reason, and evidence_quote.\n"
        "- evidence_quote must be copied from the provided search results; if unavailable, return an empty candidates list.\n"
        "- Do not invent competitor names or quotes.\n"
        "- Return JSON object only."
    )


def build_researcher_repair_user_prompt(
    *,
    validation_errors: Sequence[str],
    competitor_id: str,
    pending_dimensions: Sequence[str],
) -> str:
    return (
        "Repair researcher decision JSON to satisfy schema validation.\n"
        f"- validation_errors: {_json(list(validation_errors))}\n"
        f"- competitor_id: {competitor_id}\n"
        f"- pending_dimensions: {_json(list(pending_dimensions))}\n\n"
        "Rules:\n"
        "- action must be a valid researcher action.\n"
        "- action_args must include required fields for the chosen action.\n"
        "- Return JSON object only."
    )


def build_compression_repair_user_prompt(
    *,
    validation_errors: Sequence[str],
    observation_count: int,
) -> str:
    return (
        "Repair compression JSON to satisfy schema validation.\n"
        f"- validation_errors: {_json(list(validation_errors))}\n"
        f"- observation_count: {observation_count}\n\n"
        "Rules:\n"
        "- compressed_summary must be a non-empty string.\n"
        "- Return JSON object only."
    )


def build_qa_semantic_repair_user_prompt(
    *,
    validation_errors: Sequence[str],
    failed_rule_ids: Sequence[str],
) -> str:
    return (
        "Repair QA semantic audit JSON to satisfy schema validation.\n"
        f"- validation_errors: {_json(list(validation_errors))}\n"
        f"- failed_rule_ids: {_json(list(failed_rule_ids))}\n\n"
        f"reject_to must be one of {_json(list(QA_SEMANTIC_ALLOWED_REJECT_TO))}.\n"
        "Return JSON object only."
    )


EXTRACT_STRUCTURED_SYSTEM_PROMPT = """You are a data extraction helper for RivalLens.
Return STRICT JSON:
{
  "quote": str,
  "source_title": str | null
}

Rules:
- Keep quote factual and concise.
- Do not invent facts not present in input text.
- Return JSON object only.
"""


def build_extract_structured_repair_user_prompt(
    *,
    validation_errors: Sequence[str],
    text_preview: str,
) -> str:
    return (
        "Repair extract_structured JSON to satisfy schema validation.\n"
        f"- validation_errors: {_json(list(validation_errors))}\n"
        f"- text_preview: {_json(text_preview[:600])}\n\n"
        "Rules:\n"
        "- quote must be a non-empty string grounded in the input text.\n"
        "- Return JSON object only."
    )


