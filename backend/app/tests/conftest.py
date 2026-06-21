from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Generator
from typing import Callable
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app_main import app
from core.config import settings
from schemas.report_sections import default_outline_for_archetype
from service.llm.response import LLMResponse


@pytest.fixture(autouse=True)
def _disable_external_bocha_key_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "BOCHA_API_KEY", None)


@pytest.fixture(autouse=True)
def _langchain_debug_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    # Compatibility shim for mixed local environments where langchain package
    # exists but does not expose legacy module-level flags expected by
    # langchain-core 0.3.x callback manager.
    try:
        import langchain  # type: ignore
    except ImportError:
        return
    monkeypatch.setattr(langchain, "debug", False, raising=False)
    monkeypatch.setattr(langchain, "verbose", False, raising=False)


@pytest.fixture(autouse=True)
def _windows_selector_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


_GOLDEN_PROFILE_LIBRARY: tuple[dict[str, object], ...] = (
    {
        "name": "Cursor",
        "track": "coding",
        "candidate_role": "direct_competitor",
        "official_url": "https://www.cursor.com/pricing",
        "evidence_quote": "Cursor 在目标市场提供可落地产品并持续迭代核心功能。",
        "aliases": ("cursor", "comp_cursor", "ai coding assistants"),
    },
    {
        "name": "Windsurf",
        "track": "coding",
        "candidate_role": "direct_competitor",
        "official_url": "https://windsurf.com/pricing",
        "evidence_quote": "Windsurf 在目标市场提供可落地产品并持续迭代核心功能。",
        "aliases": ("windsurf", "comp_windsurf"),
    },
    {
        "name": "TRAE",
        "track": "coding",
        "candidate_role": "direct_competitor",
        "official_url": "https://www.trae.ai",
        "evidence_quote": "TRAE 在目标市场提供可落地产品并持续迭代核心功能。",
        "aliases": ("trae", "comp_trae"),
    },
    {
        "name": "Claude Code",
        "track": "coding",
        "candidate_role": "adjacent_competitor",
        "official_url": "https://www.anthropic.com/claude-code",
        "evidence_quote": "Claude Code 在目标市场提供可落地产品并持续迭代核心功能。",
        "aliases": ("claude code", "comp_claude_code"),
    },
    {
        "name": "Meta Ray-Ban",
        "track": "hardware",
        "candidate_role": "direct_competitor",
        "official_url": "https://www.meta.com/smart-glasses",
        "evidence_quote": "Meta Ray-Ban 在目标市场提供可落地产品并持续迭代核心功能。",
        "aliases": ("meta ray-ban", "ray-ban", "smart glasses"),
    },
    {
        "name": "XREAL",
        "track": "hardware",
        "candidate_role": "direct_competitor",
        "official_url": "https://www.xreal.com",
        "evidence_quote": "XREAL 在目标市场提供可落地产品并持续迭代核心功能。",
        "aliases": ("xreal",),
    },
    {
        "name": "Rokid",
        "track": "hardware",
        "candidate_role": "adjacent_competitor",
        "official_url": "https://global.rokid.com",
        "evidence_quote": "Rokid 在目标市场提供可落地产品并持续迭代核心功能。",
        "aliases": ("rokid", "ai 硬件", "眼镜"),
    },
)
_GOLDEN_TRACK_HINTS: dict[str, tuple[str, ...]] = {
    "coding": ("ai coding", "coding assistants", "cursor", "windsurf", "claude code", "trae"),
    "hardware": ("ai 硬件", "smart glasses", "眼镜", "ray-ban", "xreal", "rokid"),
}


def _profile_source_domain(official_url: str) -> str:
    parsed = urlsplit(official_url)
    return parsed.netloc.lower().removeprefix("www.")


def _profile_matches_prompt(profile: dict[str, object], prompt_lower: str) -> bool:
    aliases = profile.get("aliases", ())
    if not isinstance(aliases, tuple):
        return False
    return any(alias in prompt_lower for alias in aliases if isinstance(alias, str))


def _select_golden_profiles(prompt_text: str) -> list[dict[str, object]]:
    prompt_lower = prompt_text.casefold()
    explicit_matches = [
        profile
        for profile in _GOLDEN_PROFILE_LIBRARY
        if _profile_matches_prompt(profile, prompt_lower)
    ]
    for track, hints in _GOLDEN_TRACK_HINTS.items():
        if any(hint in prompt_lower for hint in hints):
            track_profiles = [
                profile
                for profile in _GOLDEN_PROFILE_LIBRARY
                if isinstance(profile.get("track"), str) and profile["track"] == track
            ]
            if explicit_matches and len(explicit_matches) >= 2:
                return explicit_matches
            return track_profiles
    if explicit_matches:
        return explicit_matches
    return [profile for profile in _GOLDEN_PROFILE_LIBRARY if profile.get("track") == "coding"][:2]


def _build_discovery_candidates_for_prompt(prompt_text: str) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for profile in _select_golden_profiles(prompt_text)[:10]:
        official_url = str(profile.get("official_url") or "")
        role = str(profile.get("candidate_role") or "adjacent_competitor")
        track = str(profile.get("track") or "coding")
        candidates.append(
            {
                "name": str(profile.get("name") or ""),
                "is_competitor": True,
                "candidate_role": role,
                "relevance_reason": (
                    "同类 AI 编码产品，服务相近开发效率与工程协作场景。"
                    if track == "coding"
                    else "同类 AI 眼镜产品，服务相近终端使用与交互场景。"
                ),
                "evidence_quote": str(profile.get("evidence_quote") or ""),
                "official_url": official_url,
                "source_domain": _profile_source_domain(official_url),
            }
        )
    return candidates


class _FakeLLMClient:
    def __init__(self) -> None:
        self._response = LLMResponse(
            model_slot="research",
            provider="fake_llm",
            model_name="fake-research-model",
            prompt_preview="fake-prompt-preview",
            prompt_hash="fake_prompt_hash",
            content={},
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1,
            error=None,
        )
        self._override_enabled = False
        self._supervisor_call_count = 0
        self._writer_retry_demo_served = False
        self._writer_no_evidence_demo_served = False
        self._qa_semantic_retry_demo_served = False
        self._qa_writer_no_evidence_demo_served = False
        self._load_skill_demo_served = False

    @staticmethod
    def _derive_dimensions(user_query: str) -> list[str]:
        query = user_query.lower()
        dimensions: list[str] = []
        if "pricing" in query or "定价" in query:
            dimensions.append("pricing")
        if "review" in query or "feedback" in query or "口碑" in query:
            dimensions.append("user_feedback")
        if "feature" in query or "功能" in query:
            dimensions.append("feature")
        if not dimensions:
            dimensions = ["feature", "pricing", "user_feedback"]
        if len(dimensions) < 3:
            dimensions = ["feature", "pricing", "user_feedback"]
        return dimensions[:5]

    def override_response(self, response: LLMResponse) -> None:
        self._response = response
        self._override_enabled = True

    @staticmethod
    def _extract_json_value(user_prompt: str, field_name: str) -> object | None:
        matched = re.search(rf"- {field_name}: ([^\n]*)", user_prompt)
        if matched is None:
            return None
        raw_value = matched.group(1)
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_json_list(user_prompt: str, field_name: str) -> list[str]:
        parsed = _FakeLLMClient._extract_json_value(user_prompt, field_name)
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, str)]

    def _build_response(self, *, model_slot: str, content: dict[str, object]) -> LLMResponse:
        return LLMResponse(
            model_slot=model_slot,
            provider=self._response.provider,
            model_name=self._response.model_name,
            prompt_preview=self._response.prompt_preview,
            prompt_hash=self._response.prompt_hash,
            content=content,
            prompt_tokens=self._response.prompt_tokens,
            completion_tokens=self._response.completion_tokens,
            latency_ms=self._response.latency_ms,
            error=None,
        )

    @staticmethod
    def _derive_intake_patch(user_prompt: str) -> dict[str, object]:
        """Derive a draft_patch from the latest exchange, mimicking a real LLM.

        Reads exchange_history JSON, inspects the LAST entry's field_targets +
        reply, and proposes a patch on those specific fields. Conservative: only
        patches the fields the previous clarify targeted.
        """
        match = re.search(r"- exchange_history \(oldest first\): (\[.*\])\n", user_prompt)
        if match is None:
            return {}
        try:
            history = json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}
        if not isinstance(history, list) or not history:
            return {}
        last = history[-1]
        if not isinstance(last, dict):
            return {}
        targets_raw = last.get("field_targets")
        targets = (
            [t for t in targets_raw if isinstance(t, str)]
            if isinstance(targets_raw, list)
            else []
        )
        reply_text = last.get("reply_text") if isinstance(last.get("reply_text"), str) else ""
        options_raw = last.get("reply_options")
        options = (
            [o for o in options_raw if isinstance(o, str)]
            if isinstance(options_raw, list)
            else []
        )
        patch: dict[str, object] = {}
        if "user_role" in targets:
            role_value: str | None = None
            for option in options:
                if option in {"pm", "founder", "sales", "investor"}:
                    role_value = option
                    break
            if role_value is None and reply_text.strip() in {
                "pm",
                "founder",
                "sales",
                "investor",
            }:
                role_value = reply_text.strip()
            if role_value is not None:
                patch["user_role"] = role_value
        if "analysis_intent" in targets and reply_text.strip():
            patch["analysis_intent"] = reply_text.strip()
        if "competitors_explicit" in targets or "competitors_discovery_mode" in targets:
            if "让 Agent 帮我发现" in options:
                patch["competitors_discovery_mode"] = True
            else:
                candidates = [
                    name.strip()
                    for name in re.split(r"[,，;；/]\s*", reply_text)
                    if name.strip()
                ]
                if candidates:
                    patch["competitors_explicit"] = candidates
                elif "已有名单" in options:
                    # User picked "have a list" but didn't include any names; ask again later.
                    pass
        return patch

    @staticmethod
    def _extract_intake_draft_from_planner_prompt(user_prompt: str) -> dict[str, object]:
        match = re.search(r"- intake_draft: (\{.*?\})\n", user_prompt)
        if match is None:
            return {}
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _build_planner_response(self, user_prompt: str) -> LLMResponse:
        # Deterministic plan: one discover task (if discovery mode or empty), one
        # research task per explicit competitor, one analyze, one write. Mirrors
        # planner_generate_node._fallback_tasks so tests can assert structure.
        draft = self._extract_intake_draft_from_planner_prompt(user_prompt)
        competitors_raw = draft.get("competitors_explicit")
        competitors = (
            [c for c in competitors_raw if isinstance(c, str) and c.strip()]
            if isinstance(competitors_raw, list)
            else []
        )
        discovery_mode = bool(draft.get("competitors_discovery_mode"))
        focus_raw = draft.get("focus_dimensions")
        focus = (
            [d for d in focus_raw if isinstance(d, str) and d.strip()]
            if isinstance(focus_raw, list)
            else []
        )
        if not focus:
            focus = ["feature", "pricing", "user_feedback"]

        tasks: list[dict[str, object]] = []
        if discovery_mode or not competitors:
            tasks.append(
                {
                    "stage": "discover",
                    "title": "Discover competitors",
                    "description": "Find leading competitors in the track.",
                    "competitor_id": None,
                    "focus_dimensions": focus,
                }
            )
        for competitor in competitors[:8]:
            tasks.append(
                {
                    "stage": "research",
                    "title": f"Research {competitor}",
                    "description": f"Collect evidence on {competitor} per focus dimensions.",
                    "competitor_id": competitor,
                    "focus_dimensions": focus,
                }
            )
        tasks.append(
            {
                "stage": "analyze",
                "title": "Cross-competitor analysis",
                "description": "Synthesize differentiators from collected evidence.",
                "competitor_id": None,
                "focus_dimensions": focus,
            }
        )
        tasks.append(
            {
                "stage": "write",
                "title": "Write final report",
                "description": "Produce the battlecard report.",
                "competitor_id": None,
                "focus_dimensions": focus,
            }
        )
        content: dict[str, object] = {
            "rationale": "fake planner: research each known competitor then analyze and write.",
            "tasks": tasks,
        }
        return self._build_response(model_slot="research", content=content)

    def _build_intake_response(self, user_prompt: str) -> LLMResponse:
        # Parse current_draft JSON and infer the next ask/complete decision.
        current_draft_raw = re.search(r"- current_draft: (\{.*?\})\n", user_prompt)
        try:
            current_draft = (
                json.loads(current_draft_raw.group(1)) if current_draft_raw else {}
            )
        except json.JSONDecodeError:
            current_draft = {}

        patch = self._derive_intake_patch(user_prompt)
        merged = {**current_draft, **patch}

        user_role = merged.get("user_role")
        analysis_intent = merged.get("analysis_intent")
        competitors_explicit = merged.get("competitors_explicit") or []
        competitors_discovery_mode = bool(merged.get("competitors_discovery_mode"))
        has_competitor_path = bool(competitors_explicit) or competitors_discovery_mode

        if not user_role:
            content: dict[str, object] = {
                "action": "ask",
                "draft_patch": patch,
                "clarify_request": {
                    "question": "请问您的角色是？",
                    "field_targets": ["user_role"],
                    "suggested_options": ["pm", "founder", "sales", "investor"],
                },
                "reasoning_summary": "fake: ask user_role first",
            }
        elif not (isinstance(analysis_intent, str) and analysis_intent.strip()):
            content = {
                "action": "ask",
                "draft_patch": patch,
                "clarify_request": {
                    "question": "请用一句话描述您最想了解的内容。",
                    "field_targets": ["analysis_intent"],
                    "suggested_options": None,
                },
                "reasoning_summary": "fake: ask analysis_intent",
            }
        elif not has_competitor_path:
            content = {
                "action": "ask",
                "draft_patch": patch,
                "clarify_request": {
                    "question": "您是否已经有想分析的竞品名单？",
                    "field_targets": [
                        "competitors_explicit",
                        "competitors_discovery_mode",
                    ],
                    "suggested_options": ["已有名单", "让 Agent 帮我发现"],
                },
                "reasoning_summary": "fake: ask competitor path",
            }
        else:
            content = {
                "action": "complete",
                "draft_patch": patch,
                "clarify_request": None,
                "reasoning_summary": "fake: draft satisfies all required fields",
            }
        return self._build_response(model_slot="research", content=content)

    def _build_supervisor_decision_response(self, user_prompt: str) -> LLMResponse:
        pending_competitors = self._extract_json_list(user_prompt, "pending_competitors")
        analysis_done = "- analysis_done: True" in user_prompt
        report_draft_done = "- report_draft_done: True" in user_prompt
        user_query_match = re.search(r"- user_query: ([^\n]+)", user_prompt)
        user_query = user_query_match.group(1).strip() if user_query_match is not None else "generic analysis"
        dynamic_dimensions = self._derive_dimensions(user_query)

        if self._supervisor_call_count == 0 and len(pending_competitors) >= 2:
            topics: list[dict[str, object]] = []
            for competitor_id in pending_competitors:
                topics.append(
                    {
                        "research_topic": f"{competitor_id} vs user_query=fake",
                        "competitor_id": competitor_id,
                        "focus_dimensions": dynamic_dimensions,
                        "max_iterations": 6,
                        "fallback_to_offline": True,
                    }
                )
            content: dict[str, object] = {
                "chosen_tool": "ConductResearchBatch",
                "tool_args": {
                    "topics": topics,
                    "parallelism_rationale": "parallelize independent competitor research",
                },
                "reasoning_summary": "Batch pending competitors in one decision for faster completion.",
            }
        elif pending_competitors:
            competitor_id = pending_competitors[0]
            content = {
                "chosen_tool": "ConductResearch",
                "tool_args": {
                    "research_topic": f"{competitor_id} vs user_query=fake",
                    "competitor_id": competitor_id,
                    "focus_dimensions": dynamic_dimensions,
                    "max_iterations": 6,
                    "fallback_to_offline": True,
                },
                "reasoning_summary": "Select next pending competitor for research.",
            }
        elif not analysis_done:
            content = {
                "chosen_tool": "Analyze",
                "tool_args": {
                    "focus_dimensions": dynamic_dimensions,
                    "parallel_by_dimension": False,
                    "require_cross_competitor": True,
                },
                "reasoning_summary": "All competitors researched; move to analysis.",
            }
        elif not report_draft_done:
            content = {
                "chosen_tool": "Write",
                "tool_args": {
                    "template_id": None,
                    "sections": [*dynamic_dimensions, "differentiation"],
                },
                "reasoning_summary": "Analysis completed; move to writer.",
            }
        else:
            content = {
                "chosen_tool": "Finalize",
                "tool_args": {
                    "completion_reason": "all_dimensions_covered",
                    "notes": "Done",
                },
                "reasoning_summary": "Workflow completed.",
            }
        self._supervisor_call_count += 1
        return self._build_response(model_slot="research", content=content)

    def _build_researcher_response(self, user_prompt: str) -> LLMResponse:
        pending_dimensions = self._extract_json_list(user_prompt, "pending_dimensions")
        prompt_lower = user_prompt.casefold()
        competitor_match = re.search(r"- competitor_id: ([^\n]+)", user_prompt)
        competitor_id = (
            competitor_match.group(1).strip()
            if competitor_match is not None and competitor_match.group(1).strip()
            else "comp_cursor"
        )
        if pending_dimensions:
            if (
                "progressive-disclosure-demo" in prompt_lower
                or "test-profile:progressive_disclosure" in prompt_lower
                and not self._load_skill_demo_served
            ):
                self._load_skill_demo_served = True
                content = {
                    "action": "load_skill",
                    "action_args": {"skill_id": "evidence-must-cite-source"},
                    "reasoning_summary": "Load reusable QA knowledge before collecting evidence.",
                }
                return self._build_response(model_slot="research", content=content)
            base_evidence_text = (
                f"{competitor_id} {pending_dimensions[0]} signal extracted in deterministic test mode. "
                "Public sources describe concrete product capabilities, commercial packaging, "
                "and user feedback patterns with release cadence, integration examples, and target "
                "segment context, so the evidence can be reused for grounded comparisons and "
                "section-level citations without placeholder scaffolding."
            )
            content = {
                "action": "extract_structured",
                "action_args": {
                    "text": (
                        f"{competitor_id} {pending_dimensions[0]} 中文资料，"
                        "用于国内市场竞品分析，并包含功能、定价与口碑的可验证描述，"
                        "覆盖发布节奏、目标客群和商业化策略等核心字段；"
                        "同时补充生态合作、典型场景落地和版本迭代事实，"
                        "确保该证据文本可以通过语义质量阈值并用于后续结构化对比。"
                    )
                    if "locale-zh-demo" in prompt_lower
                    else base_evidence_text,
                    "source_url": (
                        f"https://example.cn/{competitor_id}/{pending_dimensions[0]}"
                        if "locale-zh-demo" in prompt_lower
                        else f"https://example.com/{competitor_id}/{pending_dimensions[0]}"
                    ),
                    "source_title": (
                        f"{competitor_id} {pending_dimensions[0]} 中文来源"
                        if "locale-zh-demo" in prompt_lower
                        else f"{competitor_id} {pending_dimensions[0]}"
                    ),
                    "source_type": "article",
                    "competitor_id": competitor_id,
                    "dimension": pending_dimensions[0],
                    "response_language": "zh" if "locale-zh-demo" in prompt_lower else "en",
                },
                "reasoning_summary": "Use deterministic extract_structured path for researcher tests.",
            }
            return self._build_response(model_slot="research", content=content)
        return self._build_response(model_slot="research", content={})

    def _build_analyst_response(self, user_prompt: str) -> LLMResponse:
        focus_dimensions = self._extract_json_list(user_prompt, "focus_dimensions")
        competitors = self._extract_json_list(user_prompt, "competitors")
        archetype_match = re.search(r"- analysis_archetype: ([^\n]+)", user_prompt)
        analysis_archetype = (
            archetype_match.group(1).strip()
            if archetype_match is not None and archetype_match.group(1).strip()
            else "comparison"
        )
        evidence_briefs_raw = self._extract_json_value(user_prompt, "evidence_briefs")
        evidence_briefs = (
            [item for item in evidence_briefs_raw if isinstance(item, dict)]
            if isinstance(evidence_briefs_raw, list)
            else []
        )
        if not focus_dimensions:
            focus_dimensions = ["feature", "pricing", "user_feedback"]

        insights: list[dict[str, object]] = []
        comparisons: list[dict[str, object]] = []
        for dimension in focus_dimensions:
            dimension_evidence = [
                item
                for item in evidence_briefs
                if item.get("dimension") == dimension and isinstance(item.get("evidence_id"), str)
            ]
            if dimension_evidence:
                insights.append(
                    {
                        "dimension": dimension,
                        "finding": f"{dimension} differs across competitors in deterministic analyst mode.",
                        "evidence_ids": [dimension_evidence[0]["evidence_id"]],
                        "confidence": "medium",
                    }
                )
            cells: list[dict[str, object]] = []
            for index, competitor_id in enumerate(competitors):
                competitor_evidence = [
                    item
                    for item in dimension_evidence
                    if item.get("competitor_id") == competitor_id
                    and isinstance(item.get("evidence_id"), str)
                ]
                evidence_ids = [item["evidence_id"] for item in competitor_evidence[:2]]
                cells.append(
                    {
                        "competitor_id": competitor_id,
                        "stance": "leader" if index == 0 and evidence_ids else "competitive" if evidence_ids else "unknown",
                        "summary": (
                            f"{competitor_id} has grounded {dimension} evidence."
                            if evidence_ids
                            else f"{competitor_id} lacks grounded {dimension} evidence."
                        ),
                        "evidence_ids": evidence_ids,
                    }
                )
            if len(cells) >= 2:
                comparisons.append({"dimension": dimension, "cells": cells})

        if not insights and evidence_briefs:
            first = evidence_briefs[0]
            evidence_id = first.get("evidence_id")
            dimension = first.get("dimension") if isinstance(first.get("dimension"), str) else "general"
            if isinstance(evidence_id, str):
                insights.append(
                    {
                        "dimension": dimension,
                        "finding": "Fallback deterministic analyst insight.",
                        "evidence_ids": [evidence_id],
                        "confidence": "low",
                    }
                )
        content = {
            "schema_version": "schema_v0.2",
            "summary": "Deterministic analyst summary with structured comparisons.",
            "insights": insights,
            "comparisons": comparisons,
            "risk_flags": [],
            "recommended_sections": focus_dimensions,
            "report_outline": [
                {"section_id": section_id}
                for section_id in default_outline_for_archetype(analysis_archetype)
            ],
        }
        return self._build_response(model_slot="summarization", content=content)

    def _build_discovery_extract_response(self, user_prompt: str) -> LLMResponse:
        if "Fallback competitor extraction request" in user_prompt:
            return self._build_response(model_slot="research", content={"candidates": []})
        candidates = _build_discovery_candidates_for_prompt(user_prompt)
        return self._build_response(
            model_slot="research",
            content={"candidates": candidates},
        )

    def _build_knowledge_extraction_response(self, user_prompt: str) -> LLMResponse:
        competitors = self._extract_json_list(user_prompt, "competitors")
        evidence_briefs_raw = self._extract_json_value(user_prompt, "evidence_briefs")
        evidence_briefs = (
            [item for item in evidence_briefs_raw if isinstance(item, dict)]
            if isinstance(evidence_briefs_raw, list)
            else []
        )
        if not competitors:
            inferred_competitors: list[str] = []
            for item in evidence_briefs:
                competitor_raw = item.get("competitor_id")
                if not isinstance(competitor_raw, str):
                    continue
                competitor_id = competitor_raw.strip()
                if competitor_id and competitor_id not in inferred_competitors:
                    inferred_competitors.append(competitor_id)
            competitors = inferred_competitors

        evidence_by_competitor: dict[str, list[str]] = {}
        evidence_by_dimension: dict[tuple[str, str], list[str]] = {}
        for item in evidence_briefs:
            competitor_raw = item.get("competitor_id")
            evidence_id_raw = item.get("evidence_id")
            dimension_raw = item.get("dimension")
            if not isinstance(competitor_raw, str) or not isinstance(evidence_id_raw, str):
                continue
            competitor_id = competitor_raw.strip()
            evidence_id = evidence_id_raw.strip()
            if not competitor_id or not evidence_id:
                continue
            dimension = (
                dimension_raw.strip()
                if isinstance(dimension_raw, str) and dimension_raw.strip()
                else "feature"
            )
            competitor_evidence = evidence_by_competitor.setdefault(competitor_id, [])
            if evidence_id not in competitor_evidence:
                competitor_evidence.append(evidence_id)
            dimension_evidence = evidence_by_dimension.setdefault((competitor_id, dimension), [])
            if evidence_id not in dimension_evidence:
                dimension_evidence.append(evidence_id)

        if not competitors:
            competitors = ["comp_cursor"]
            evidence_by_competitor.setdefault("comp_cursor", ["ev_fake_001"])
            evidence_by_dimension.setdefault(("comp_cursor", "feature"), ["ev_fake_001"])

        features: list[dict[str, object]] = []
        pricings: list[dict[str, object]] = []
        personas: list[dict[str, object]] = []
        feedback: list[dict[str, object]] = []
        for competitor_id in competitors:
            competitor_evidence = evidence_by_competitor.get(competitor_id, [])
            feature_evidence = evidence_by_dimension.get((competitor_id, "feature"), []) or competitor_evidence
            pricing_evidence = evidence_by_dimension.get((competitor_id, "pricing"), []) or competitor_evidence
            feedback_evidence = (
                evidence_by_dimension.get((competitor_id, "user_feedback"), []) or competitor_evidence
            )
            persona_evidence = feedback_evidence or feature_evidence or pricing_evidence

            for index, evidence_id in enumerate(feature_evidence[:3], start=1):
                features.append(
                    {
                        "id": f"feat_{competitor_id}_{index}",
                        "competitor_id": competitor_id,
                        "name": f"{competitor_id} feature {index}",
                        "description": f"Deterministic feature extraction for {competitor_id}.",
                        "maturity": "advanced" if index == 1 else "basic",
                        "evidence_ids": [evidence_id],
                    }
                )
            if pricing_evidence:
                pricings.append(
                    {
                        "id": f"price_{competitor_id}",
                        "competitor_id": competitor_id,
                        "model": "subscription",
                        "tiers": [
                            {"name": "pro", "price": "$20/mo"},
                            {"name": "business", "price": "$40/user/mo"},
                        ],
                        "free_plan": True,
                        "enterprise_plan": True,
                        "evidence_ids": pricing_evidence[:2],
                    }
                )
            if feedback_evidence:
                feedback.append(
                    {
                        "id": f"feedback_{competitor_id}",
                        "competitor_id": competitor_id,
                        "sentiment": "neutral",
                        "topic": "onboarding",
                        "summary": f"Deterministic feedback signal for {competitor_id}.",
                        "evidence_ids": feedback_evidence[:1],
                    }
                )
            if persona_evidence:
                personas.append(
                    {
                        "id": f"persona_{competitor_id}",
                        "competitor_id": competitor_id,
                        "name": f"{competitor_id} engineering manager",
                        "role": "engineering_manager",
                        "pain_points": ["delivery pressure"],
                        "jobs_to_be_done": ["improve developer productivity"],
                        "evidence_ids": persona_evidence[:1],
                    }
                )

        content = {
            "schema_version": "schema_v0.2",
            "features": features,
            "pricings": pricings,
            "personas": personas,
            "feedback": feedback,
        }
        return self._build_response(model_slot="summarization", content=content)

    def _build_writer_response(self, user_prompt: str) -> LLMResponse:
        template_id_match = re.search(r"- template_id: ([^\n]+)", user_prompt)
        template_id = (
            template_id_match.group(1).strip()
            if template_id_match is not None and template_id_match.group(1).strip() not in {"", "None", "null"}
            else "default"
        )
        requested_sections = self._extract_json_list(user_prompt, "requested_sections")
        if not requested_sections:
            requested_sections = self._extract_json_list(user_prompt, "target_sections")
        evidence_briefs_raw = self._extract_json_value(user_prompt, "evidence_briefs")
        if isinstance(evidence_briefs_raw, list):
            evidence_ids = [
                item["evidence_id"]
                for item in evidence_briefs_raw
                if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
            ]
        else:
            evidence_ids = []
        analyst_insights_raw = self._extract_json_value(user_prompt, "analyst_insights")
        if isinstance(analyst_insights_raw, list):
            analyst_insights = [item for item in analyst_insights_raw if isinstance(item, dict)]
        else:
            analyst_insights = []
        risk_flags = self._extract_json_list(user_prompt, "risk_flags")
        analyst_summary_match = re.search(r"- analyst_summary: ([^\n]*)", user_prompt)
        analyst_summary = (
            analyst_summary_match.group(1).strip()
            if analyst_summary_match is not None and analyst_summary_match.group(1).strip()
            else "Summary generated by fake writer client."
        )
        user_query_match = re.search(r"- user_query: ([^\n]+)", user_prompt)
        user_query = user_query_match.group(1).strip() if user_query_match is not None else ""

        if not requested_sections:
            requested_sections = list(default_outline_for_archetype("comparison"))
        if not evidence_ids:
            evidence_ids = ["ev_fake_001"]

        section_title_map = {
            "executive_summary": "Executive Summary",
            "competitor_profiles": "Competitor Profiles",
            "comparison_matrix": "Comparison Matrix",
            "positioning_map": "Positioning Map",
            "self_positioning": "Self Positioning",
            "executive_takeaways": "Executive Takeaways",
            "market_definition": "Market Definition",
            "market_size_growth": "Market Size and Growth",
            "market_segmentation": "Market Segmentation",
            "competitive_landscape": "Competitive Landscape",
            "key_players": "Key Players",
            "value_chain": "Value Chain",
            "opportunities_risks": "Opportunities and Risks",
            "strategic_recommendations": "Strategic Recommendations",
            "methodology_limits": "Methodology and Limits",
        }
        sections: list[dict[str, object]] = []
        for section_id in requested_sections:
            section_insights = [
                item
                for item in analyst_insights
                if isinstance(item.get("dimension"), str) and item.get("dimension") == section_id
            ]
            if not section_insights:
                section_insights = analyst_insights[:1]
            evidence_refs: list[str] = []
            insight_refs: list[str] = []
            for item in section_insights:
                insight_id = item.get("insight_id")
                if isinstance(insight_id, str):
                    insight_refs.append(insight_id)
                evidence_ids_raw = item.get("evidence_ids")
                if isinstance(evidence_ids_raw, list):
                    evidence_refs.extend(
                        evidence_id
                        for evidence_id in evidence_ids_raw
                        if isinstance(evidence_id, str) and evidence_id in evidence_ids
                    )
            if not evidence_refs:
                evidence_refs = evidence_ids[:1]
            if not insight_refs:
                insight_refs = ["insight_1"]
            if (
                "semantic-force-degraded-demo" in user_query.casefold()
                or "test-profile:semantic_force_degraded" in user_query.casefold()
            ):
                content_markdown = (
                    "semantic-force-degraded-demo marker for deterministic force-degraded path."
                )
            elif (
                "semantic-reject-demo" in user_query.casefold()
                or "test-profile:semantic_reject" in user_query.casefold()
            ):
                content_markdown = (
                    "semantic-reject-demo content generated by fake writer for deterministic "
                    "semantic QA retry verification."
                )
            elif (
                "writer-no-evidence-demo" in user_query.casefold()
                or "test-profile:writer_no_evidence" in user_query.casefold()
            ):
                if not self._writer_no_evidence_demo_served:
                    self._writer_no_evidence_demo_served = True
                content_markdown = (
                    "writer-no-evidence-demo semantic marker for deterministic retry. "
                    "The actual evidence validation is controlled by semantic QA mock."
                )
            elif "retry-demo" in user_query.casefold() or "test-profile:retry" in user_query.casefold():
                if not self._writer_retry_demo_served and section_id in {"pricing", "strategic_recommendations"}:
                    content_markdown = (
                        "retry demo short content with minimal but valid detail for first-pass "
                        "promoted rule blocking checks."
                    )
                    self._writer_retry_demo_served = True
                else:
                    content_markdown = (
                        "This section is generated by fake writer LLM for deterministic tests. "
                        "It summarizes competitive signals and keeps evidence links for QA validation. "
                        "This expanded retry content is intentionally longer to satisfy promoted QA "
                        "section length checks after a writer redo cycle."
                    )
            else:
                content_markdown = (
                    "This section is generated by fake writer LLM for deterministic tests. "
                    "It summarizes competitive signals and keeps evidence links for QA validation."
                )
            sections.append(
                {
                    "section_id": section_id,
                    "title": section_title_map.get(section_id, section_id.title()),
                    "content_markdown": content_markdown,
                    "evidence_refs": evidence_refs,
                    "insight_refs": insight_refs,
                }
            )

        content = {
            "template_id": template_id,
            "title": "RivalLens Test Battlecard",
            "executive_summary": analyst_summary,
            "sections": sections,
            "risk_callouts": risk_flags or ["fake_writer_mode"],
        }
        return self._build_response(model_slot="writer", content=content)

    def _build_qa_semantic_response(self, user_prompt: str) -> LLMResponse:
        def _payload(
            *,
            semantic_audit_passed: bool,
            reject_to: str,
            severity: str,
            finding: str,
            required_fields: list[str],
        ) -> dict[str, object]:
            if semantic_audit_passed:
                dimension_results = {
                    "depth": True,
                    "citation_coverage": True,
                    "faithfulness": True,
                    "instruction_following": True,
                }
            else:
                dimension_results = {
                    "depth": False,
                    "citation_coverage": False,
                    "faithfulness": True,
                    "instruction_following": True,
                }
            return {
                "semantic_audit_passed": semantic_audit_passed,
                "reject_to": reject_to,
                "severity": severity,
                "finding": finding,
                "required_fields": required_fields,
                "unsupported_numeric_claims": [],
                "dimension_results": dimension_results,
            }

        if (
            "semantic-force-degraded-demo" in user_prompt.casefold()
            or "test-profile:semantic_force_degraded" in user_prompt.casefold()
        ):
            content = _payload(
                semantic_audit_passed=False,
                reject_to="writer",
                severity="blocking",
                finding="Semantic force degraded demo keeps rejecting writer output.",
                required_fields=["reports.content_json.sections[].content_markdown"],
            )
            return self._build_response(model_slot="qa", content=content)
        if (
            "writer-no-evidence-demo" in user_prompt.casefold()
            or "test-profile:writer_no_evidence" in user_prompt.casefold()
        ):
            if not self._qa_writer_no_evidence_demo_served:
                self._qa_writer_no_evidence_demo_served = True
                content = _payload(
                    semantic_audit_passed=False,
                    reject_to="writer",
                    severity="blocking",
                    finding="Writer no evidence demo requires one rewrite pass.",
                    required_fields=["reports.content_json.sections[].evidence_refs"],
                )
            else:
                content = _payload(
                    semantic_audit_passed=True,
                    reject_to="writer",
                    severity="warning",
                    finding="Writer no evidence demo passes after rewrite.",
                    required_fields=[],
                )
            return self._build_response(model_slot="qa", content=content)
        if (
            "semantic-reject-demo" in user_prompt.casefold()
            or "test-profile:semantic_reject" in user_prompt.casefold()
        ):
            if not self._qa_semantic_retry_demo_served:
                self._qa_semantic_retry_demo_served = True
                content = _payload(
                    semantic_audit_passed=False,
                    reject_to="writer",
                    severity="blocking",
                    finding="Semantic retry demo requires one writer rewrite pass.",
                    required_fields=["reports.content_json.sections[].content_markdown"],
                )
            else:
                content = _payload(
                    semantic_audit_passed=True,
                    reject_to="writer",
                    severity="warning",
                    finding="Semantic retry demo passes after writer rewrite.",
                    required_fields=[],
                )
            return self._build_response(model_slot="qa", content=content)
        return self._build_response(
            model_slot="qa",
            content=_payload(
                semantic_audit_passed=True,
                reject_to="writer",
                severity="warning",
                finding="QA semantic check passed in deterministic test mode.",
                required_fields=[],
            ),
        )

    def _build_skill_curator_response(self, user_prompt: str) -> LLMResponse:
        run_id_match = re.search(r"- run_id: ([^\n]+)", user_prompt)
        run_id = run_id_match.group(1).strip() if run_id_match is not None else "run_fake"
        if "Curator context (qa_rule)" in user_prompt or "Fallback curator request (qa_rule)" in user_prompt:
            content = {
                "candidates": [
                    {
                        "candidate_type": "qa_rule",
                        "payload": {
                            "rule_yaml": (
                                "id: rule_pricing_requires_recent_source\n"
                                "when:\n"
                                "  section_id_in: [pricing]\n"
                                "require:\n"
                                "  evidence_refs_count_gte: 1\n"
                            ),
                            "triggered_failures_count": 1,
                            "similar_existing_rules": [],
                        },
                        "rationale": "Pricing evidence freshness should be enforced for recurring review reliability.",
                        "confidence": "medium",
                        "supporting_run_ids": [run_id],
                    }
                ]
            }
            return self._build_response(model_slot="qa", content=content)
        if (
            "Curator context (prompt_template)" in user_prompt
            or "Fallback curator request (prompt_template)" in user_prompt
        ):
            content = {
                "candidates": [
                    {
                        "candidate_type": "prompt_template",
                        "payload": {
                            "target_agent": "writer",
                            "template_name": "writer_battlecard_enhanced",
                            "template_body": "Use explicit evidence refs per section.",
                            "replaces_template_id": "battlecard_default",
                            "evidence_quality_delta": 0.1,
                            "rejection_rate_delta": -0.05,
                        },
                        "rationale": "Writer prompt variant correlates with lower rejection rate.",
                        "confidence": "medium",
                        "supporting_run_ids": [run_id],
                    }
                ]
            }
            return self._build_response(model_slot="qa", content=content)
        if (
            "Curator context (source_routing)" in user_prompt
            or "Fallback curator request (source_routing)" in user_prompt
        ):
            content = {
                "candidates": [
                    {
                        "candidate_type": "source_routing",
                        "payload": {
                            "source_type": "pricing_page",
                            "competitor_category": "ai_coding_tool",
                            "priority_delta": 1,
                            "quality_score_sample": [0.8, 0.9],
                        },
                        "rationale": "Pricing page source repeatedly yields higher quality evidence.",
                        "confidence": "medium",
                        "supporting_run_ids": [run_id],
                    }
                ]
            }
            return self._build_response(model_slot="qa", content=content)
        content = {
            "candidates": [
                {
                    "candidate_type": "qa_rule",
                    "payload": {
                        "rule_yaml": (
                            "id: rule_pricing_requires_recent_source\n"
                            "when:\n"
                            "  section_id_in: [pricing]\n"
                            "require:\n"
                            "  evidence_refs_count_gte: 1\n"
                        ),
                        "triggered_failures_count": 1,
                        "similar_existing_rules": [],
                    },
                    "rationale": "Pricing evidence freshness should be enforced for recurring review reliability.",
                    "confidence": "medium",
                    "supporting_run_ids": [run_id],
                }
            ]
        }
        return self._build_response(model_slot="qa", content=content)

    async def complete_json(
        self,
        *,
        model_slot: str = "research",
        system_prompt: str | None = None,
        user_prompt: str | None = None,
        prompt: str | None = None,
        fallback_system_prompt: str | None = None,
        fallback_user_prompt: str | None = None,
    ) -> LLMResponse:
        del prompt, fallback_system_prompt, fallback_user_prompt
        if self._override_enabled:
            if self._response.model_slot == model_slot:
                return self._response
            return LLMResponse(
                model_slot=model_slot,
                provider=self._response.provider,
                model_name=self._response.model_name,
                prompt_preview=self._response.prompt_preview,
                prompt_hash=self._response.prompt_hash,
                content=self._response.content,
                prompt_tokens=self._response.prompt_tokens,
                completion_tokens=self._response.completion_tokens,
                latency_ms=self._response.latency_ms,
                error=self._response.error,
                fallback_used=self._response.fallback_used,
                fallback_reason=self._response.fallback_reason,
            )

        if (
            model_slot == "research"
            and isinstance(system_prompt, str)
            and "RivalLens Intake assistant" in system_prompt
            and isinstance(user_prompt, str)
            and "Intake clarification" in user_prompt
        ):
            return self._build_intake_response(user_prompt)
        if (
            model_slot == "research"
            and isinstance(system_prompt, str)
            and "RivalLens Planner" in system_prompt
            and isinstance(user_prompt, str)
            and (
                "Plan generation context" in user_prompt
                or "Fallback plan generation" in user_prompt
            )
        ):
            return self._build_planner_response(user_prompt)
        if (
            model_slot == "research"
            and isinstance(system_prompt, str)
            and "Supervisor planner" in system_prompt
            and isinstance(user_prompt, str)
            and "Planning context" in user_prompt
        ):
            return self._build_supervisor_decision_response(user_prompt)
        if (
            model_slot == "research"
            and isinstance(system_prompt, str)
            and "RivalLens Researcher in a ReAct loop" in system_prompt
            and isinstance(user_prompt, str)
            and "Research assignment" in user_prompt
        ):
            return self._build_researcher_response(user_prompt)
        if (
            model_slot == "research"
            and isinstance(system_prompt, str)
            and "extract grounded competitor candidates" in system_prompt
            and isinstance(user_prompt, str)
        ):
            return self._build_discovery_extract_response(user_prompt)
        if (
            model_slot == "summarization"
            and isinstance(system_prompt, str)
            and "RivalLens Analyst" in system_prompt
            and isinstance(user_prompt, str)
            and (
                "Analysis context" in user_prompt
                or "Fallback analysis request" in user_prompt
                or "Repair analysis JSON" in user_prompt
            )
        ):
            return self._build_analyst_response(user_prompt)
        if (
            model_slot == "summarization"
            and isinstance(system_prompt, str)
            and "RivalLens structured knowledge extractor" in system_prompt
            and isinstance(user_prompt, str)
            and (
                "Knowledge extraction context" in user_prompt
                or "Fallback knowledge extraction request" in user_prompt
                or "Repair knowledge extraction JSON" in user_prompt
            )
        ):
            return self._build_knowledge_extraction_response(user_prompt)
        if (
            model_slot == "writer"
            and isinstance(system_prompt, str)
            and "RivalLens Writer" in system_prompt
            and isinstance(user_prompt, str)
        ):
            return self._build_writer_response(user_prompt)
        if (
            model_slot == "qa"
            and isinstance(system_prompt, str)
            and "RivalLens QA semantic auditor" in system_prompt
            and isinstance(user_prompt, str)
            and "QA semantic audit context" in user_prompt
        ):
            return self._build_qa_semantic_response(user_prompt)
        if (
            model_slot == "qa"
            and isinstance(system_prompt, str)
            and "RivalLens Skill Curator" in system_prompt
            and isinstance(user_prompt, str)
            and (
                "Curator context" in user_prompt
                or "Fallback curator request" in user_prompt
            )
        ):
            return self._build_skill_curator_response(user_prompt)

        if self._response.model_slot == model_slot:
            return self._response
        return LLMResponse(
            model_slot=model_slot,
            provider=self._response.provider,
            model_name=self._response.model_name,
            prompt_preview=self._response.prompt_preview,
            prompt_hash=self._response.prompt_hash,
            content=self._response.content,
            prompt_tokens=self._response.prompt_tokens,
            completion_tokens=self._response.completion_tokens,
            latency_ms=self._response.latency_ms,
            error=self._response.error,
            fallback_used=self._response.fallback_used,
            fallback_reason=self._response.fallback_reason,
        )


@pytest.fixture(autouse=True)
def fake_llm_client(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> _FakeLLMClient | None:
    node_path = str(request.node.path)
    if any(
        name in node_path
        for name in (
            "test_llm_client.py",
            "test_llm_providers.py",
            "test_llm_routing.py",
            "test_llm_harness.py",
        )
    ):
        return None

    fake_client = _FakeLLMClient()
    monkeypatch.setattr("service.llm.client.get_llm_client", lambda: fake_client)
    monkeypatch.setattr("service.llm.harness.get_llm_client", lambda: fake_client)
    return fake_client


@pytest.fixture()
def override_llm_response(
    fake_llm_client: _FakeLLMClient | None,
) -> Callable[[LLMResponse], None]:
    if fake_llm_client is None:
        raise RuntimeError("override_llm_response fixture is unavailable for llm service tests.")

    def _override(response: LLMResponse) -> None:
        fake_llm_client.override_response(response)

    return _override


@pytest.fixture()
def test_client() -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client
