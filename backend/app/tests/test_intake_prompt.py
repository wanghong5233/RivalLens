from __future__ import annotations

from agents.nodes.intake import _fallback_clarify
from schemas.intake import RunIntakeDraft
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
