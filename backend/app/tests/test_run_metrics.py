from __future__ import annotations

import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from core.config import settings


def test_get_run_metrics_for_completed_run(test_client: TestClient) -> None:
    create_response = test_client.post(
        "/api/runs",
        json={
            "user_query": "metrics endpoint smoke",
            "competitors": ["comp_cursor", "comp_windsurf"],
            "industry_pack": "ai_coding_tools",
            "target_roles": ["pm"],
        },
    )
    assert create_response.status_code == 200
    run_id = create_response.json()["run_id"]

    metrics_response = test_client.get(f"/api/runs/{run_id}/metrics")
    payload = metrics_response.json()
    assert metrics_response.status_code == 200
    assert payload["run_id"] == run_id

    assert 0.0 <= payload["coverage_rate"] <= 1.0
    assert payload["evidence_count_total"] >= 1
    assert set(payload["evidence_count_by_competitor"].keys()) >= {"comp_cursor", "comp_windsurf"}
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
                    "INSERT INTO runs (run_id, user_query, industry_pack, status, target_roles, competitors) "
                    "VALUES (:run_id, :user_query, :industry_pack, :status, "
                    "CAST(:target_roles AS jsonb), CAST(:competitors AS jsonb))"
                ),
                {
                    "run_id": run_id,
                    "user_query": "empty run for metrics boundary",
                    "industry_pack": "ai_coding_tools",
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
