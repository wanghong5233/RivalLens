from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from core.config import settings
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
                "report_section_ids_include": ["market_landscape_map", "trend_summary"],
                "report_degraded_required_sections_count_lte": 0,
                "evidence_floor_count_lte": 0,
                "source_authority_distribution_includes": ["official"],
                "qa_warnings_count_gte": 1,
            },
        }
    )

    assert case.input.self_product == "AI眼镜"
    assert case.input.competitors_discovery_mode is True
    assert case.assertions.report_section_ids_include == ["market_landscape_map", "trend_summary"]
    assert case.assertions.report_degraded_required_sections_count_lte == 0
    assert case.assertions.evidence_floor_count_lte == 0
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


@pytest.mark.parametrize(
    "case_filename",
    [
        "02_baseline_two_competitors.yaml",
        "03_reject_writer_no_evidence.yaml",
        "05_promoted_pricing_blocks_then_passes.yaml",
        "06_promoted_warning_observed_only.yaml",
        "10_qa_semantic_reject_then_approve.yaml",
        "12_load_skill_progressive_disclosure.yaml",
    ],
)
def test_core_golden_yaml_cases_pass(
    test_client: TestClient,
    case_filename: str,
) -> None:
    case_path = Path(__file__).parent / "golden" / "cases" / case_filename
    loaded = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    result = run_case(case=GoldenCase.model_validate(loaded), client=test_client)
    assert result.passed is True, result.failures


def test_deep_short_report_golden_case_blocks(test_client: TestClient) -> None:
    case_path = Path(__file__).parent / "golden" / "cases" / "13_deep_short_report_blocks.yaml"
    loaded = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    result = run_case(case=GoldenCase.model_validate(loaded), client=test_client)
    assert result.passed is True


def test_reject_max_retry_force_degraded_golden_case_still_passes(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tests.golden.runner as golden_runner

    original_wait_for_terminal = golden_runner._wait_for_run_terminal

    def _wait_with_extended_timeout(
        run_id: str,
        *,
        timeout_seconds: float = 90.0,
    ) -> str:
        return original_wait_for_terminal(run_id, timeout_seconds=180.0)

    monkeypatch.setattr(
        golden_runner,
        "_wait_for_run_terminal",
        _wait_with_extended_timeout,
    )
    case_path = (
        Path(__file__).parent
        / "golden"
        / "cases"
        / "04_reject_max_retry_force_degraded.yaml"
    )
    loaded = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    result = run_case(case=GoldenCase.model_validate(loaded), client=test_client)
    assert result.qa_outcome == "force_degraded"
    assert result.qa_rejection_count <= 1


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


def test_ai_hardware_glasses_trajectory_golden_case_passes(
    test_client: TestClient,
) -> None:
    case_path = (
        Path(__file__).parent
        / "golden"
        / "cases"
        / "16_ai_hardware_glasses_trajectory.yaml"
    )
    loaded = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    result = run_case(case=GoldenCase.model_validate(loaded), client=test_client)
    assert result.passed is True


def test_landscape_style_explicit_competitor_run_completes_with_triplet_coverage(
    test_client: TestClient,
) -> None:
    case = GoldenCase.model_validate(
        {
            "id": "landscape_style_explicit_competitor_triplet",
            "description": "Landscape-style explicit competitor run should complete with triplet coverage.",
            "input": {
                "user_query": (
                    "请做 AI 硬件赛道 landscape：Meta Ray-Ban、XREAL、Rokid 的主流产品与发展趋势，"
                    "不要写 battlecard 式逐项胜负。"
                ),
                "competitors": ["Meta Ray-Ban", "XREAL", "Rokid"],
                "domain_hint": "AI hardware and smart glasses",
                "target_roles": ["pm"],
                "report_depth": "quick",
                "market_scope": "中国市场",
                "self_product": "AI眼镜",
                "competitors_discovery_mode": False,
            },
            "assertions": {},
        }
    )
    result = run_case(case=case, client=test_client)

    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with engine.connect() as connection:
            run_row = connection.execute(
                text(
                    "SELECT status FROM runs "
                    "WHERE run_id = :run_id"
                ),
                {"run_id": result.run_id},
            ).mappings().first()
            knowledge_row = connection.execute(
                text(
                    "SELECT jsonb_array_length(features) AS feature_count, "
                    "jsonb_array_length(pricings) AS pricing_count, "
                    "jsonb_array_length(feedback) AS feedback_count "
                    "FROM run_knowledge "
                    "WHERE run_id = :run_id "
                    "ORDER BY sequence_id DESC LIMIT 1"
                ),
                {"run_id": result.run_id},
            ).mappings().first()
    finally:
        engine.dispose()

    assert run_row is not None
    assert run_row["status"] == "completed"
    assert knowledge_row is not None
    assert int(knowledge_row["feature_count"]) >= 3
    assert int(knowledge_row["pricing_count"]) >= 3
    assert int(knowledge_row["feedback_count"]) >= 3


def _wait_for_plan_tree(
    test_client: TestClient,
    *,
    run_id: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        detail = test_client.get(f"/api/runs/{run_id}").json()
        candidate = detail.get("plan_tree")
        if isinstance(candidate, dict) and isinstance(candidate.get("tasks"), list):
            return candidate
        time.sleep(0.1)
    raise AssertionError(f"plan_tree not ready within {timeout_seconds}s for run_id={run_id}")


def _wait_for_intake_field(
    test_client: TestClient,
    *,
    run_id: str,
    field: str,
    timeout_seconds: float = 10.0,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        detail = test_client.get(f"/api/runs/{run_id}").json()
        draft = detail.get("intake_draft")
        if isinstance(draft, dict) and draft.get(field):
            return
        time.sleep(0.1)
    raise AssertionError(f"intake_draft.{field} not ready within {timeout_seconds}s for run_id={run_id}")


def _post_intake_reply_when_ready(
    test_client: TestClient,
    *,
    run_id: str,
    body: dict[str, object],
    timeout_seconds: float = 10.0,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = test_client.post(f"/api/runs/{run_id}/intake/reply", json=body)
        if response.status_code == 200:
            return
        if response.status_code == 409 and response.json().get("error_code") == "INTAKE_NOT_AWAITING_REPLY":
            time.sleep(0.1)
            continue
        raise AssertionError(
            f"unexpected intake reply response: status={response.status_code} body={response.text}"
        )
    raise AssertionError(f"intake/reply never became resumable within {timeout_seconds}s for run_id={run_id}")


def test_focus_run_lineage_schema_triplet_golden_case_passes(
    test_client: TestClient,
) -> None:
    case_path = (
        Path(__file__).parent
        / "golden"
        / "cases"
        / "18_focus_run_lineage_schema_triplet.yaml"
    )
    loaded = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)

    setup = loaded.get("setup")
    assertions = loaded.get("assertions")
    assert isinstance(setup, dict)
    assert isinstance(assertions, dict)

    parent_create_user_query = setup.get("parent_create_user_query")
    parent_patch = setup.get("parent_patch")
    child_request = setup.get("child_request")
    assert isinstance(parent_create_user_query, str)
    assert isinstance(parent_patch, dict)
    assert isinstance(child_request, dict)

    parent_create = test_client.post(
        "/api/runs/intake",
        json={"user_query": parent_create_user_query},
    )
    assert parent_create.status_code == 200, parent_create.text
    parent_run_id = parent_create.json()["run_id"]

    parent_intake_draft = parent_patch.get("intake_draft")
    parent_seed_ids = parent_patch.get("seed_competitor_ids")
    parent_competitors = parent_patch.get("competitors")
    parent_domain_hint = parent_patch.get("domain_hint")
    assert isinstance(parent_intake_draft, dict)
    assert isinstance(parent_seed_ids, list)
    assert isinstance(parent_competitors, list)
    assert isinstance(parent_domain_hint, str)

    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE runs SET "
                    "intake_draft = CAST(:intake_draft AS jsonb), "
                    "seed_competitor_ids = CAST(:seed_ids AS jsonb), "
                    "competitors = CAST(:competitors AS jsonb), "
                    "domain_hint = :domain_hint "
                    "WHERE run_id = :run_id"
                ),
                {
                    "run_id": parent_run_id,
                    "intake_draft": json.dumps(parent_intake_draft, ensure_ascii=False),
                    "seed_ids": json.dumps(parent_seed_ids, ensure_ascii=False),
                    "competitors": json.dumps(parent_competitors, ensure_ascii=False),
                    "domain_hint": parent_domain_hint,
                },
            )
    finally:
        engine.dispose()

    seed_competitor_ids = child_request.get("seed_competitor_ids")
    child_user_query = child_request.get("user_query")
    assert isinstance(seed_competitor_ids, list)
    assert isinstance(child_user_query, str)

    child_create = test_client.post(
        "/api/runs/intake",
        json={
            "user_query": child_user_query,
            "from_run_id": parent_run_id,
            "seed_competitor_ids": seed_competitor_ids,
        },
    )
    assert child_create.status_code == 200, child_create.text
    child_payload = child_create.json()
    child_run_id = child_payload["run_id"]
    child_draft = child_payload["intake_draft"]

    expected_analysis_archetype = assertions.get("analysis_archetype")
    expected_competitors = assertions.get("competitors_explicit")
    expected_domain_hint = assertions.get("domain_hint")
    expected_self_product = assertions.get("self_product")
    expected_market_scope = assertions.get("market_scope")
    required_focus_dimensions = assertions.get("required_focus_dimensions")
    assert isinstance(expected_analysis_archetype, str)
    assert isinstance(expected_competitors, list)
    assert isinstance(expected_domain_hint, str)
    assert isinstance(expected_self_product, str)
    assert isinstance(expected_market_scope, str)
    assert isinstance(required_focus_dimensions, list)

    assert child_draft["analysis_archetype"] == expected_analysis_archetype
    assert child_draft["competitors_explicit"] == expected_competitors
    assert child_draft["domain_hint"] == expected_domain_hint
    assert child_draft["self_product"] == expected_self_product
    assert child_draft["market_scope"] == expected_market_scope

    child_detail = test_client.get(f"/api/runs/{child_run_id}")
    assert child_detail.status_code == 200, child_detail.text
    child_detail_payload = child_detail.json()
    assert child_detail_payload["parent_run_id"] == parent_run_id
    assert child_detail_payload["seed_competitor_ids"] == seed_competitor_ids

    _post_intake_reply_when_ready(
        test_client,
        run_id=child_run_id,
        body={"text": "pm", "selected_options": ["pm"]},
    )
    _wait_for_intake_field(test_client, run_id=child_run_id, field="user_role")

    child_detail_payload = test_client.get(f"/api/runs/{child_run_id}").json()
    child_draft = child_detail_payload.get("intake_draft")
    if isinstance(child_draft, dict) and not child_draft.get("analysis_intent"):
        _post_intake_reply_when_ready(
            test_client,
            run_id=child_run_id,
            body={"text": "聚焦 Meta Ray-Ban 三件套对比"},
        )
        _wait_for_intake_field(test_client, run_id=child_run_id, field="analysis_intent")

    _post_intake_reply_when_ready(
        test_client,
        run_id=child_run_id,
        body={"text": "", "selected_options": ["quick"]},
    )

    child_detail_payload = test_client.get(f"/api/runs/{child_run_id}").json()
    child_draft_after_profile = child_detail_payload.get("intake_draft")
    assert isinstance(child_draft_after_profile, dict)
    assert child_draft_after_profile.get("analysis_archetype") == expected_analysis_archetype

    plan_tree = _wait_for_plan_tree(test_client, run_id=child_run_id)
    tasks = plan_tree.get("tasks")
    assert isinstance(tasks, list)
    target_competitor = str(expected_competitors[0])
    focus_dimensions: list[str] | None = None
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if task.get("stage") != "research":
            continue
        if task.get("competitor_id") != target_competitor:
            continue
        candidate_focus = task.get("focus_dimensions")
        if isinstance(candidate_focus, list):
            focus_dimensions = [str(item) for item in candidate_focus]
            break

    assert focus_dimensions is not None
    for dimension in required_focus_dimensions:
        assert isinstance(dimension, str)
        assert dimension in focus_dimensions
