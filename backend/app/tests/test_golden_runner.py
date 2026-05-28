from __future__ import annotations

from pathlib import Path

from tests.golden.runner import GoldenCase, dump_markdown_report, to_dict_rows


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
                "industry_pack": "ai_coding_tools",
                "target_roles": ["pm"],
            },
            "assertions": {"final_qa_outcome": "approved"},
        }
    )
    assert case.id == "golden_case_schema_test"
    assert case.input.industry_pack == "ai_coding_tools"
    assert case.assertions.final_qa_outcome == "approved"
    assert case.setup.promoted_qa_rules == []


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
        coverage_rate=1.0,
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
                coverage_rate=0.9,
                llm_token_total=88,
                run_wall_clock_seconds=24,
                created_at="2026-05-28T00:00:00+00:00",
            )
        ]
    )
    assert len(rows) == 1
    assert rows[0]["case_id"] == "case_2"
    assert rows[0]["passed"] is False

