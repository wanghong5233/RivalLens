from __future__ import annotations

from service.qa.engine import build_qa_outcome
from service.qa.rules import RuleResult, rule_knowledge_schema_conformance
from schemas.qa import Rejection


def test_knowledge_schema_conformance_rejects_malformed_complete_claims() -> None:
    result = rule_knowledge_schema_conformance(
        knowledge={
            "schema_version": "schema_v0.2",
            "features": [
                {
                    "id": "feat_1",
                    "competitor_id": "Cursor",
                    "name": "Repo context",
                    "evidence_ids": [],
                }
            ],
            "pricings": [],
            "personas": [
                {
                    "id": "persona_1",
                    "name": "Buyer",
                    "role": "",
                    "pain_points": [],
                    "jobs_to_be_done": [],
                }
            ],
            "coverage": {"Cursor": {"feature": "complete", "pricing": "complete"}},
        },
        expected_competitors=["Cursor"],
    )

    assert result.passed is False
    assert result.severity == "blocking"
    assert result.reject_to == "analyst"
    assert "feature missing evidence_ids" in result.message
    assert "pricing missing" in result.message
    assert "persona missing" in result.message


def test_knowledge_schema_conformance_allows_honest_insufficient_coverage() -> None:
    result = rule_knowledge_schema_conformance(
        knowledge={
            "schema_version": "schema_v0.2",
            "features": [],
            "pricings": [],
            "personas": [],
            "coverage": {
                "Cursor": {
                    "feature": "insufficient_data",
                    "pricing": "insufficient_data",
                }
            },
        },
        expected_competitors=["Cursor"],
    )

    assert result.passed is True


def test_knowledge_schema_conformance_passes_complete_minimum_schema() -> None:
    result = rule_knowledge_schema_conformance(
        knowledge={
            "schema_version": "schema_v0.2",
            "features": [
                {
                    "id": f"feat_{index}",
                    "competitor_id": "Cursor",
                    "name": f"Feature {index}",
                    "evidence_ids": [f"ev_{index}"],
                }
                for index in range(3)
            ],
            "pricings": [
                {
                    "id": "price_1",
                    "competitor_id": "Cursor",
                    "model": "seat",
                    "evidence_ids": ["ev_price"],
                }
            ],
            "personas": [
                {
                    "id": "persona_1",
                    "name": "Engineering manager",
                    "role": "engineering_manager",
                    "pain_points": ["Manual review load"],
                    "jobs_to_be_done": [],
                }
            ],
            "coverage": {"Cursor": {"feature": "complete", "pricing": "complete"}},
        },
        expected_competitors=["Cursor"],
    )

    assert result.passed is True


def test_knowledge_schema_conformance_routes_blocking_failure_to_analyst() -> None:
    rule_results: list[RuleResult] = [
        rule_knowledge_schema_conformance(
            knowledge={
                "schema_version": "schema_v0.2",
                "features": [],
                "pricings": [],
                "personas": [],
                "coverage": {},
            },
            expected_competitors=["Cursor"],
        )
    ]

    result = build_qa_outcome(
        target_step_id="step_writer_001",
        reviewer_step_id="step_qa_001",
        rule_results=rule_results,
        qa_rejection_count=0,
    )

    assert isinstance(result, Rejection)
    assert result.reject_to == "analyst"
    assert result.failed_rule_ids == ["rule_knowledge_schema_conformance"]
