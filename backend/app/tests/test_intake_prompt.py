from __future__ import annotations

from agents.nodes.intake import (
    _apply_patch,
    _merge_reply_into_draft,
    _clarify_target_satisfied,
    _fallback_clarify,
    _should_drop_optional_clarify,
    _unsatisfied_clarify_targets,
)
from schemas.intake import IntakeClarifyRequest, IntakeExchange, IntakeUserReply, RunIntakeDraft
from service.locale import detect_language
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


def test_detect_language_uses_chinese_character_ratio() -> None:
    assert detect_language("工业自动化设备销售团队要找国内 AI 工具") == "zh"
    assert detect_language("Compare CRM sales intelligence tools") == "en"
    assert detect_language("CRM 工具 compare pricing") == "zh"
    assert detect_language("") == "en"


def test_intake_prompt_exposes_response_language_contract() -> None:
    assert '"response_language": "zh" | "en" | null' in INTAKE_SYSTEM_PROMPT
    assert "response_language defaults to the detected language of user_query" in INTAKE_SYSTEM_PROMPT


def test_apply_patch_accepts_response_language_override() -> None:
    draft = RunIntakeDraft(user_query="请用英文输出国内销售工具分析")

    next_draft = _apply_patch(draft, {"response_language": "en"})

    assert next_draft.response_language == "en"


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
    assert _clarify_target_satisfied("market_scope", draft) is False

    scoped = draft.model_copy(update={"market_scope": "中国 / China"})
    assert _clarify_target_satisfied("market_scope", scoped) is True


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


def test_merge_reply_uses_selected_options_for_optional_text_fields() -> None:
    draft = RunIntakeDraft(
        user_query="找 one person company 方向",
        user_role="founder",
        analysis_intent="寻找适合一人公司的可变现方向",
        competitors_discovery_mode=True,
    )

    next_draft = _merge_reply_into_draft(
        draft,
        IntakeClarifyRequest(
            question="您主要关注哪个市场区域？",
            field_targets=["market_scope"],
            suggested_options=["全球 / Global", "中国 / China"],
        ),
        IntakeUserReply(text="", selected_options=["中国 / China"]),
    )

    assert next_draft.market_scope == "中国 / China"


def test_optional_clarify_repeat_is_dropped_after_complete_draft() -> None:
    history = [
        IntakeExchange(
            clarify=IntakeClarifyRequest(
                question="您主要关注哪个市场区域？",
                field_targets=["market_scope"],
            ),
            reply=IntakeUserReply(text="", selected_options=["中国 / China"]),
        )
    ]
    clarify = IntakeClarifyRequest(
        question="为了筛选高变现潜力方向，您希望重点考察哪个市场区域？",
        field_targets=["market_scope"],
    )

    assert _should_drop_optional_clarify(clarify, history) is True
