from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from tests.golden.runner import GoldenCase, dump_markdown_report, run_case, to_dict_rows


def test_golden_case_schema_parses_minimal_case() -> None:
    case = GoldenCase.model_validate(
        {
            "id": "golden_case_schema_test",
            "description": "schema parse test",
            "setup": {
                "promoted_qa_rules": [],
            },
            "input": {
                "user_query": "test",
                "competitors": ["comp_cursor"],
                "domain_hint": "ai_coding_tools",
                "reference_urls": ["https://example.com/pricing"],
                "target_roles": ["pm"],
            },
            "assertions": {"final_qa_outcome": "approved"},
        }
    )
    assert case.id == "golden_case_schema_test"
    assert case.input.domain_hint == "ai_coding_tools"
    assert case.input.reference_urls == ["https://example.com/pricing"]
    assert case.input.report_depth == "quick"
    assert case.input.market_scope is None
    assert case.assertions.final_qa_outcome == "approved"
    assert case.setup.promoted_qa_rules == []


def test_golden_case_schema_accepts_report_depth() -> None:
    case = GoldenCase.model_validate(
        {
            "id": "golden_case_schema_deep",
            "description": "schema parse with report depth",
            "input": {
                "user_query": "deep report gate",
                "competitors": ["comp_cursor"],
                "domain_hint": "ai_coding_tools",
                "reference_urls": [],
                "target_roles": ["pm"],
                "report_depth": "deep",
                "market_scope": "中国大陆",
            },
            "assertions": {
                "final_qa_outcome": "force_degraded",
                "warning_rule_ids_includes": ["rule_locale_mismatch"],
            },
        }
    )
    assert case.input.report_depth == "deep"
    assert case.input.market_scope == "中国大陆"
    assert case.assertions.warning_rule_ids_includes == ["rule_locale_mismatch"]


def test_golden_case_schema_accepts_knowledge_assertions() -> None:
    case = GoldenCase.model_validate(
        {
            "id": "golden_case_schema_knowledge",
            "description": "schema parse with knowledge assertions",
            "input": {
                "user_query": "compare coding tools",
                "competitors": ["comp_cursor", "comp_windsurf"],
                "target_roles": ["pm"],
            },
            "assertions": {
                "knowledge_feature_count_gte": 2,
                "knowledge_pricing_count_gte": 1,
                "knowledge_persona_count_gte": 1,
                "knowledge_schema_coverage_rate_gte": 0.5,
            },
        }
    )

    assert case.assertions.knowledge_feature_count_gte == 2
    assert case.assertions.knowledge_pricing_count_gte == 1
    assert case.assertions.knowledge_persona_count_gte == 1
    assert case.assertions.knowledge_schema_coverage_rate_gte == 0.5


def test_golden_case_schema_accepts_trajectory_assertions() -> None:
    case = GoldenCase.model_validate(
        {
            "id": "golden_case_schema_trajectory",
            "description": "schema parse with trajectory assertions",
            "input": {
                "user_query": "AI 硬件的主流产品以及发展趋势。",
                "competitors": [],
                "target_roles": ["pm"],
                "self_product": "AI眼镜",
                "competitors_discovery_mode": True,
            },
            "assertions": {
                "supervisor_iterations_lt": 8,
                "analyze_count_lte": 2,
                "report_section_count_gte": 4,
                "source_authority_distribution_includes": ["official"],
                "qa_warnings_count_gte": 1,
            },
        }
    )

    assert case.input.self_product == "AI眼镜"
    assert case.input.competitors_discovery_mode is True
    assert case.assertions.supervisor_iterations_lt == 8
    assert case.assertions.analyze_count_lte == 2
    assert case.assertions.report_section_count_gte == 4
    assert case.assertions.source_authority_distribution_includes == ["official"]
    assert case.assertions.qa_warnings_count_gte == 1


def test_golden_case_schema_accepts_null_pack() -> None:
    case = GoldenCase.model_validate(
        {
            "id": "golden_case_schema_no_pack",
            "description": "schema parse without pack",
            "input": {
                "user_query": "generic note app comparison",
                "competitors": ["Notion", "Obsidian"],
                "domain_hint": None,
                "reference_urls": [],
                "target_roles": ["pm"],
            },
            "assertions": {"final_qa_outcome": "approved"},
        }
    )
    assert case.input.domain_hint is None


def test_dump_markdown_report_writes_file(tmp_path: Path) -> None:
    from tests.golden.runner import GoldenCaseResult

    report_path = tmp_path / "golden_report.md"
    result = GoldenCaseResult(
        case_id="case_1",
        passed=True,
        run_id="run_1",
        failures=[],
        qa_outcome="approved",
        qa_reject_to=None,
        qa_rejection_count=0,
        promoted_blocked_rule_ids=[],
        warning_rule_ids=[],
        coverage_rate=1.0,
        knowledge_feature_count=3,
        knowledge_pricing_count=1,
        knowledge_persona_count=1,
        knowledge_schema_coverage_rate=0.75,
        llm_token_total=42,
        run_wall_clock_seconds=12,
        created_at="2026-05-28T00:00:00+00:00",
    )
    dump_markdown_report(results=[result], report_path=report_path)
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "Golden Eval Report" in content
    assert "case_1 PASS" in content


def test_to_dict_rows_returns_serializable_shape() -> None:
    from tests.golden.runner import GoldenCaseResult

    rows = to_dict_rows(
        [
            GoldenCaseResult(
                case_id="case_2",
                passed=False,
                run_id="run_2",
                failures=["f1"],
                qa_outcome="rejected",
                qa_reject_to="writer",
                qa_rejection_count=1,
                promoted_blocked_rule_ids=["rule_promoted_demo"],
                warning_rule_ids=["rule_locale_mismatch"],
                coverage_rate=0.9,
                knowledge_feature_count=2,
                knowledge_pricing_count=1,
                knowledge_persona_count=1,
                knowledge_schema_coverage_rate=0.66,
                llm_token_total=88,
                run_wall_clock_seconds=24,
                created_at="2026-05-28T00:00:00+00:00",
            )
        ]
    )
    assert len(rows) == 1
    assert rows[0]["case_id"] == "case_2"
    assert rows[0]["passed"] is False


def test_deep_short_report_golden_case_blocks(test_client: TestClient) -> None:
    case_path = Path(__file__).parent / "golden" / "cases" / "13_deep_short_report_blocks.yaml"
    loaded = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    result = run_case(case=GoldenCase.model_validate(loaded), client=test_client)
    assert result.passed is True


def test_locale_zh_domestic_golden_case_passes_without_locale_warning(
    test_client: TestClient,
) -> None:
    case_path = Path(__file__).parent / "golden" / "cases" / "14_locale_zh_domestic.yaml"
    loaded = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    result = run_case(case=GoldenCase.model_validate(loaded), client=test_client)
    assert result.passed is True


def test_locale_zh_mismatch_warning_golden_case_passes(
    test_client: TestClient,
) -> None:
    case_path = (
        Path(__file__).parent
        / "golden"
        / "cases"
        / "17_locale_zh_mismatch_warning.yaml"
    )
    loaded = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    result = run_case(case=GoldenCase.model_validate(loaded), client=test_client)
    assert result.passed is True


def test_ai_coding_enterprise_schema_triplet_golden_case_passes(
    test_client: TestClient,
) -> None:
    case_path = (
        Path(__file__).parent
        / "golden"
        / "cases"
        / "15_ai_coding_enterprise_schema_triplet.yaml"
    )
    loaded = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    result = run_case(case=GoldenCase.model_validate(loaded), client=test_client)
    assert result.passed is True
