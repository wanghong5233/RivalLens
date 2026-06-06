from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from core.config import settings
from models.evidence import EvidenceRecord
from models.run import Run
from models.supervisor_decision import SupervisorDecisionRecord
from router.run_rt import _build_run_summary_fields
from service.metrics import RunMetricsSnapshot, build_run_metrics_snapshot

_TERMINAL_RUN_STATUSES = {"completed", "degraded", "failed"}


def test_build_run_summary_fields_uses_public_metrics_contract() -> None:
    snapshot = RunMetricsSnapshot(
        run_id="run_summary_fields",
        coverage_rate=0.5,
        evidence_count_total=3,
        evidence_count_by_competitor={"comp_cursor": 2},
        evidence_count_by_dimension={"pricing": 2},
        dimension_coverage_rate=0.5,
        source_type_distribution={"web": 3},
        desensitization_coverage=1.0,
        qa_total_steps=2,
        qa_rejected_steps=1,
        qa_rejection_rate=0.5,
        supervisor_iterations=4,
        llm_token_total=1234,
        llm_call_count=5,
        llm_latency_p50_ms=321,
        manual_review_rate=0.0,
        manual_review_is_proxy=True,
        run_wall_clock_seconds=42,
    )

    fields = _build_run_summary_fields(snapshot=snapshot, status="completed")

    assert fields == {
        "status": "completed",
        "run_wall_clock_seconds": 42,
        "llm_call_count": 5,
        "llm_token_total": 1234,
        "llm_latency_p50_ms": 321,
        "coverage_rate": 0.5,
        "evidence_count_total": 3,
        "qa_rejection_rate": 0.5,
        "supervisor_iterations": 4,
    }


def _wait_for_run_terminal(run_id: str, *, timeout_seconds: float = 30.0) -> str:
    """Poll until the async POST /api/runs background graph task reaches a terminal status."""
    deadline = time.time() + timeout_seconds
    last_status = "running"
    while time.time() < deadline:
        engine = create_engine(settings.DATABASE_URL_SYNC)
        try:
            with engine.connect() as connection:
                row = connection.execute(
                    text("SELECT status FROM runs WHERE run_id = :run_id"),
                    {"run_id": run_id},
                ).mappings().first()
        finally:
            engine.dispose()
        if row is not None:
            last_status = str(row["status"])
            if last_status in _TERMINAL_RUN_STATUSES:
                return last_status
        time.sleep(0.1)
    raise RuntimeError(
        f"run_id={run_id} did not reach a terminal status within {timeout_seconds}s (last={last_status})"
    )


def test_build_run_metrics_snapshot_reports_dimension_coverage() -> None:
    run = Run(
        run_id="run_dimension_metrics",
        user_query="dimension metrics",
        status="completed",
        target_roles=["pm"],
        competitors=["comp_cursor"],
        plan_tree={
            "tasks": [
                {
                    "stage": "research",
                    "focus_dimensions": ["pricing", "security", "integrations"],
                }
            ]
        },
    )
    collected_at = datetime.now(timezone.utc)
    evidence_rows = [
        EvidenceRecord(
            id="ev_pricing",
            run_id=run.run_id,
            source_type="pricing_page",
            source_url="https://cursor.com/pricing",
            source_title="Cursor Pricing",
            quote="Cursor publishes pricing details.",
            sanitized_text="Cursor publishes pricing details.",
            span={"dimension": "pricing", "competitor_id": "comp_cursor"},
            collected_by="step_researcher",
            collected_at=collected_at,
            desensitized=True,
        ),
        EvidenceRecord(
            id="ev_security",
            run_id=run.run_id,
            source_type="docs",
            source_url="https://cursor.com/security",
            source_title="Cursor Security",
            quote="Cursor describes security controls.",
            sanitized_text="Cursor describes security controls.",
            span={"dimension": "security", "competitor_id": "comp_cursor"},
            collected_by="step_researcher",
            collected_at=collected_at,
            desensitized=True,
        ),
    ]

    snapshot = build_run_metrics_snapshot(
        run=run,
        evidence_rows=evidence_rows,
        step_rows=[],
        llm_rows=[],
        decision_rows=[],
        candidate_rows=[],
    )

    assert snapshot.evidence_count_by_dimension == {
        "integrations": 0,
        "pricing": 1,
        "security": 1,
    }
    assert snapshot.dimension_coverage_rate == 2 / 3


def test_build_run_metrics_snapshot_uses_supervisor_dimensions_without_plan_tree() -> None:
    run = Run(
        run_id="run_decision_dimension_metrics",
        user_query="dimension metrics",
        status="completed",
        target_roles=["pm"],
        competitors=["comp_cursor"],
        plan_tree=None,
    )
    collected_at = datetime.now(timezone.utc)
    evidence_rows = [
        EvidenceRecord(
            id="ev_pricing",
            run_id=run.run_id,
            source_type="pricing_page",
            source_url="https://cursor.com/pricing",
            source_title="Cursor Pricing",
            quote="Cursor publishes pricing details.",
            sanitized_text="Cursor publishes pricing details.",
            span={"dimension": "pricing", "competitor_id": "comp_cursor"},
            collected_by="step_researcher",
            collected_at=collected_at,
            desensitized=True,
        )
    ]
    decision_rows = [
        SupervisorDecisionRecord(
            id="decision_dimensions",
            run_id=run.run_id,
            iteration=1,
            chosen_tool="ConductResearchBatch",
            tool_args={
                "topics": [
                    {
                        "competitor_id": "Cursor",
                        "focus_dimensions": ["pricing", "security"],
                    }
                ]
            },
            reasoning_summary="batch",
        )
    ]

    snapshot = build_run_metrics_snapshot(
        run=run,
        evidence_rows=evidence_rows,
        step_rows=[],
        llm_rows=[],
        decision_rows=decision_rows,
        candidate_rows=[],
    )

    assert snapshot.evidence_count_by_dimension == {"pricing": 1, "security": 0}
    assert snapshot.dimension_coverage_rate == 0.5


def test_get_run_metrics_for_completed_run(test_client: TestClient) -> None:
    create_response = test_client.post(
        "/api/runs",
        json={
            "user_query": "metrics endpoint smoke",
            "competitors": ["comp_cursor", "comp_windsurf"],
            "domain_hint": "ai coding assistants",
            "reference_urls": ["https://cursor.com/pricing"],
            "target_roles": ["pm"],
        },
    )
    assert create_response.status_code == 200
    run_id = create_response.json()["run_id"]
    assert _wait_for_run_terminal(run_id) == "completed"

    metrics_response = test_client.get(f"/api/runs/{run_id}/metrics")
    payload = metrics_response.json()
    assert metrics_response.status_code == 200
    assert payload["run_id"] == run_id

    assert 0.0 <= payload["coverage_rate"] <= 1.0
    assert payload["evidence_count_total"] >= 1
    assert set(payload["evidence_count_by_competitor"].keys()) >= {"comp_cursor", "comp_windsurf"}
    assert isinstance(payload["evidence_count_by_dimension"], dict)
    assert 0.0 <= payload["dimension_coverage_rate"] <= 1.0
    assert isinstance(payload["source_type_distribution"], dict)
    assert payload["source_type_distribution"]
    assert 0.0 <= payload["desensitization_coverage"] <= 1.0

    assert payload["qa_total_steps"] >= 1
    assert 0 <= payload["qa_rejected_steps"] <= payload["qa_total_steps"]
    assert 0.0 <= payload["qa_rejection_rate"] <= 1.0

    assert payload["supervisor_iterations"] >= 1
    assert payload["llm_token_total"] >= 0
    assert payload["llm_call_count"] >= 1
    assert payload["llm_latency_p50_ms"] is None or payload["llm_latency_p50_ms"] >= 0

    assert payload["manual_review_is_proxy"] is True
    assert 0.0 <= payload["manual_review_rate"] <= 1.0
    assert payload["run_wall_clock_seconds"] is None or payload["run_wall_clock_seconds"] >= 0


def test_get_run_metrics_for_empty_run(test_client: TestClient) -> None:
    run_id = f"run_metrics_empty_{uuid4().hex[:8]}"
    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO runs (run_id, user_query, domain_hint, reference_urls, status, target_roles, competitors) "
                    "VALUES (:run_id, :user_query, :domain_hint, CAST(:reference_urls AS jsonb), :status, "
                    "CAST(:target_roles AS jsonb), CAST(:competitors AS jsonb))"
                ),
                {
                    "run_id": run_id,
                    "user_query": "empty run for metrics boundary",
                    "domain_hint": "",
                    "reference_urls": json.dumps([]),
                    "status": "running",
                    "target_roles": json.dumps(["pm"]),
                    "competitors": json.dumps(["comp_cursor"]),
                },
            )

        metrics_response = test_client.get(f"/api/runs/{run_id}/metrics")
        payload = metrics_response.json()
        assert metrics_response.status_code == 200
        assert payload["run_id"] == run_id
        assert payload["coverage_rate"] == 0.0
        assert payload["evidence_count_total"] == 0
        assert payload["evidence_count_by_competitor"] == {"comp_cursor": 0}
        assert payload["evidence_count_by_dimension"] == {}
        assert payload["dimension_coverage_rate"] == 0.0
        assert payload["source_type_distribution"] == {}
        assert payload["desensitization_coverage"] == 0.0
        assert payload["qa_total_steps"] == 0
        assert payload["qa_rejected_steps"] == 0
        assert payload["qa_rejection_rate"] == 0.0
        assert payload["supervisor_iterations"] == 0
        assert payload["llm_token_total"] == 0
        assert payload["llm_call_count"] == 0
        assert payload["llm_latency_p50_ms"] is None
        assert payload["manual_review_rate"] == 0.0
        assert payload["manual_review_is_proxy"] is True
        assert payload["run_wall_clock_seconds"] is None
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM runs WHERE run_id = :run_id"), {"run_id": run_id})
        engine.dispose()
