"""Phase 1b intake API tests: end-to-end through FastAPI TestClient.

Exercises the full request path (lifespan → compile_graph → AsyncPostgresSaver),
which catches integration regressions that the unit-level test_intake_flow.py
cannot — e.g., wrong field names in the response model, missing imports, broken
background-task wiring, or stale stub raisers.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from core.config import settings


def _wait_for_run_status(
    run_id: str,
    expected_statuses: set[str],
    *,
    timeout_seconds: float = 30.0,
) -> str:
    """Poll the runs table until status enters `expected_statuses` (or timeout)."""
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
            if last_status in expected_statuses:
                return last_status
        time.sleep(0.1)
    return last_status


def test_intake_create_returns_first_clarify(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/runs/intake",
        json={"user_query": "我想分析定价竞品"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["phase"] == "intake"
    assert payload["run_id"].startswith("run_")
    clarify = payload["first_clarify_request"]
    assert clarify is not None
    assert clarify["field_targets"] == ["user_role"]
    assert isinstance(clarify["question"], str) and clarify["question"]

    # Run row should already carry the initial intake_draft snapshot.
    detail = test_client.get(f"/api/runs/{payload['run_id']}").json()
    assert detail["phase"] == "intake"
    assert detail["intake_draft"] is not None
    assert detail["intake_draft"]["user_query"] == "我想分析定价竞品"
    assert detail["plan_tree"] is None


def test_intake_expert_mode_returns_422(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/runs/intake?mode=expert",
        json={
            "user_query": "Notion vs Cursor pricing",
            "user_role": "pm",
            "competitors_explicit": ["Notion", "Cursor"],
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "EXPERT_MODE_NOT_AVAILABLE"


def test_intake_reply_resumes_and_eventually_finishes(test_client: TestClient) -> None:
    create = test_client.post(
        "/api/runs/intake",
        json={"user_query": "我想分析定价竞品"},
    )
    assert create.status_code == 200
    run_id = create.json()["run_id"]

    # Reply 1: user_role.
    reply_1 = test_client.post(
        f"/api/runs/{run_id}/intake/reply",
        json={"text": "pm", "selected_options": ["pm"]},
    )
    assert reply_1.status_code == 200
    assert reply_1.json()["status"] == "running"

    # The background resume yields another clarify; poll the detail endpoint
    # until the intake_draft snapshot shows the user_role merged.
    deadline = time.time() + 10.0
    while time.time() < deadline:
        detail = test_client.get(f"/api/runs/{run_id}").json()
        draft = detail.get("intake_draft") or {}
        if draft.get("user_role") == "pm":
            break
        time.sleep(0.1)
    else:
        pytest.fail("intake_draft.user_role never merged after first reply")

    # Reply 2: analysis_intent.
    reply_2 = test_client.post(
        f"/api/runs/{run_id}/intake/reply",
        json={"text": "对比 Notion 和 Cursor 的定价策略"},
    )
    assert reply_2.status_code == 200

    deadline = time.time() + 10.0
    while time.time() < deadline:
        draft = (test_client.get(f"/api/runs/{run_id}").json() or {}).get("intake_draft") or {}
        if draft.get("analysis_intent"):
            break
        time.sleep(0.1)
    else:
        pytest.fail("intake_draft.analysis_intent never merged after second reply")

    # Reply 3: competitor path → completes intake → runs the supervisor pipeline.
    reply_3 = test_client.post(
        f"/api/runs/{run_id}/intake/reply",
        json={"text": "Notion, Cursor", "selected_options": ["已有名单"]},
    )
    assert reply_3.status_code == 200

    final_status = _wait_for_run_status(
        run_id,
        expected_statuses={"completed", "degraded", "failed"},
        timeout_seconds=60.0,
    )
    assert final_status in {"completed", "degraded"}, f"expected terminal success, got {final_status}"

    detail = test_client.get(f"/api/runs/{run_id}").json()
    draft = detail["intake_draft"]
    assert draft is not None
    assert draft["user_role"] == "pm"
    assert "Notion" in draft["competitors_explicit"]
    assert detail["phase"] == "done"


def test_intake_reply_rejects_when_not_paused(test_client: TestClient) -> None:
    # Legacy POST /api/runs creates a run that runs straight through supervisor
    # to a terminal state without ever pausing at intake_wait.
    response = test_client.post(
        "/api/runs",
        json={
            "user_query": "legacy run",
            "competitors": ["comp_a", "comp_b"],
        },
    )
    run_id = response.json()["run_id"]
    final_status = _wait_for_run_status(
        run_id,
        expected_statuses={"completed", "degraded", "failed"},
        timeout_seconds=60.0,
    )
    assert final_status in {"completed", "degraded"}

    reply = test_client.post(
        f"/api/runs/{run_id}/intake/reply",
        json={"text": "should be rejected"},
    )
    assert reply.status_code == 409
    body = reply.json()
    assert body["error_code"] == "RUN_NOT_RESUMABLE"


def test_intake_reply_empty_payload_returns_422(test_client: TestClient) -> None:
    create = test_client.post(
        "/api/runs/intake",
        json={"user_query": "empty reply test"},
    )
    run_id = create.json()["run_id"]
    reply = test_client.post(
        f"/api/runs/{run_id}/intake/reply",
        json={"text": "", "selected_options": []},
    )
    assert reply.status_code == 422


# Note: POST /api/runs/{id}/plan/confirm is intentionally still raising
# NotImplementedError until Phase 2 lands. We don't test it here because
# Starlette's TestClient re-raises `NotImplementedError` past the global
# `unhandled_exception` handler, so the response shape is asserted only after
# Phase 2 implements the endpoint with a structured response.
