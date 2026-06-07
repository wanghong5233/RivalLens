from __future__ import annotations

from agents.nodes.intake import (
    _clarify_target_satisfied,
    _fallback_clarify,
    _unsatisfied_clarify_targets,
)
from schemas.intake import IntakeClarifyRequest, RunIntakeDraft
from service.llm.prompts import INTAKE_SYSTEM_PROMPT


def test_intake_prompt_uses_cross_domain_examples() -> None:
    assert "供应链 SaaS" in INTAKE_SYSTEM_PROMPT
    assert "CRM tools" in INTAKE_SYSTEM_PROMPT
    assert "AI 编程工具" in INTAKE_SYSTEM_PROMPT
    assert "供应链 ERP 调研" in INTAKE_SYSTEM_PROMPT
    assert "CRM 续费风险" in INTAKE_SYSTEM_PROMPT


def test_intake_prompt_removes_specific_ai_coding_title_templates() -> None:
    assert "TRAE" not in INTAKE_SYSTEM_PROMPT
    assert "Copilot" not in INTAKE_SYSTEM_PROMPT
    assert "[产品A] vs [产品B]" in INTAKE_SYSTEM_PROMPT


def test_fallback_clarify_analysis_intent_is_domain_neutral() -> None:
    draft = RunIntakeDraft(
        user_query="我是产品经理，想调研供应链 ERP 的实施与集成差异。",
        user_role="pm",
    )

    clarify = _fallback_clarify(draft)

    assert clarify.field_targets == ["analysis_intent"]
    assert clarify.suggested_answer is not None
    assert "目标赛道" in clarify.suggested_answer
    assert "AI 编程" not in clarify.suggested_answer
    assert "TRAE" not in clarify.suggested_answer
    assert "Copilot" not in clarify.suggested_answer


def test_clarify_target_satisfied_tracks_completion_fields() -> None:
    draft = RunIntakeDraft(
        user_query="对比 Notion 和 Cursor 的定价策略",
        user_role="pm",
        analysis_intent="对比定价",
        competitors_explicit=["Notion", "Cursor"],
    )

    assert _clarify_target_satisfied("user_role", draft) is True
    assert _clarify_target_satisfied("analysis_intent", draft) is True
    assert _clarify_target_satisfied("competitors_explicit", draft) is True
    assert _clarify_target_satisfied("competitors_discovery_mode", draft) is True
    # Unknown / optional targets are never treated as satisfied.
    assert _clarify_target_satisfied("report_depth", draft) is False


def test_unsatisfied_targets_empty_when_user_already_supplied_required_fields() -> None:
    # R8: complete draft + LLM re-asking a field the user already gave (user_role).
    draft = RunIntakeDraft(
        user_query="我是 pm，对比 Notion 和 Cursor 的定价策略",
        user_role="pm",
        analysis_intent="对比定价",
        competitors_explicit=["Notion", "Cursor"],
    )
    clarify = IntakeClarifyRequest(
        question="请问您的角色是？",
        field_targets=["user_role"],
    )

    assert draft.is_complete is True
    assert _unsatisfied_clarify_targets(clarify, draft) == []


def test_unsatisfied_targets_preserves_genuinely_new_question() -> None:
    draft = RunIntakeDraft(
        user_query="对比 Notion 和 Cursor",
        user_role="pm",
        analysis_intent="对比定价",
        competitors_discovery_mode=True,
    )
    clarify = IntakeClarifyRequest(
        question="想补充关注的分析维度吗？",
        field_targets=["focus_dimensions"],
    )

    assert _unsatisfied_clarify_targets(clarify, draft) == ["focus_dimensions"]
