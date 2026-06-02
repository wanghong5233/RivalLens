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


def _post_intake_reply_when_ready(
    test_client: TestClient,
    *,
    run_id: str,
    body: dict[str, object],
    timeout_seconds: float = 10.0,
) -> None:
    """Retry intake/reply until graph is paused at intake_wait."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = test_client.post(f"/api/runs/{run_id}/intake/reply", json=body)
        if response.status_code == 200:
            return
        if response.status_code == 409 and response.json().get("error_code") == "INTAKE_NOT_AWAITING_REPLY":
            time.sleep(0.1)
            continue
        pytest.fail(f"unexpected intake reply response: {response.status_code} {response.text}")
    pytest.fail("intake/reply never became resumable within timeout")


def test_intake_create_returns_accepted(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/runs/intake",
        json={"user_query": "我想分析定价竞品"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["phase"] == "intake"
    assert payload["run_id"].startswith("run_")
    assert payload.get("first_clarify_request") is None

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


def test_intake_create_idempotency_replay_returns_same_run(test_client: TestClient) -> None:
    key = "test-idempotency-key"
    first = test_client.post(
        "/api/runs/intake",
        headers={"Idempotency-Key": key},
        json={"user_query": "我想分析定价竞品"},
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()

    second = test_client.post(
        "/api/runs/intake",
        headers={"Idempotency-Key": key},
        json={"user_query": "我想分析定价竞品"},
    )
    assert second.status_code == 200, second.text
    second_payload = second.json()
    assert second_payload["run_id"] == first_payload["run_id"]


def test_intake_create_idempotency_conflict_returns_409(test_client: TestClient) -> None:
    key = "test-idempotency-conflict-key"
    first = test_client.post(
        "/api/runs/intake",
        headers={"Idempotency-Key": key},
        json={"user_query": "query A"},
    )
    assert first.status_code == 200, first.text

    second = test_client.post(
        "/api/runs/intake",
        headers={"Idempotency-Key": key},
        json={"user_query": "query B"},
    )
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error_code"] == "INTAKE_CREATE_IDEMPOTENCY_CONFLICT"


def test_intake_reply_completes_and_publishes_plan(test_client: TestClient) -> None:
    """Phase 2: after the final intake reply the graph hands off to the planner.

    The run remains `status="running"` paused at planner_wait until Phase 2's
    /plan/confirm endpoint resumes it. We assert that the planner published a
    plan_tree onto the Run row so the FE PlanConfirmPage can render it.
    """
    create = test_client.post(
        "/api/runs/intake",
        json={"user_query": "我想分析定价竞品"},
    )
    assert create.status_code == 200
    run_id = create.json()["run_id"]

    _post_intake_reply_when_ready(
        test_client,
        run_id=run_id,
        body={"text": "pm", "selected_options": ["pm"]},
    )

    deadline = time.time() + 10.0
    while time.time() < deadline:
        detail = test_client.get(f"/api/runs/{run_id}").json()
        draft = detail.get("intake_draft") or {}
        if draft.get("user_role") == "pm":
            break
        time.sleep(0.1)
    else:
        pytest.fail("intake_draft.user_role never merged after first reply")

    _post_intake_reply_when_ready(
        test_client,
        run_id=run_id,
        body={"text": "对比 Notion 和 Cursor 的定价策略"},
    )

    deadline = time.time() + 10.0
    while time.time() < deadline:
        draft = (test_client.get(f"/api/runs/{run_id}").json() or {}).get("intake_draft") or {}
        if draft.get("analysis_intent"):
            break
        time.sleep(0.1)
    else:
        pytest.fail("intake_draft.analysis_intent never merged after second reply")

    # Reply 3: completes intake → planner publishes a plan and pauses at planner_wait.
    _post_intake_reply_when_ready(
        test_client,
        run_id=run_id,
        body={"text": "Notion, Cursor", "selected_options": ["已有名单"]},
    )

    # Poll Run.plan_tree until the planner has published. Run.status stays
    # "running" because the graph is paused at planner_wait, not terminal.
    deadline = time.time() + 30.0
    while time.time() < deadline:
        detail = test_client.get(f"/api/runs/{run_id}").json()
        if detail.get("plan_tree") is not None:
            break
        time.sleep(0.1)
    else:
        pytest.fail("plan_tree never published after intake completed")

    detail = test_client.get(f"/api/runs/{run_id}").json()
    assert detail["status"] == "running"
    assert detail["phase"] == "planning"
    plan = detail["plan_tree"]
    assert plan is not None
    assert plan["confirmed_at"] is None
    assert plan["version"] == 1
    stages = [task["stage"] for task in plan["tasks"]]
    # Fake planner emits: research(Notion), research(Cursor), analyze, write.
    assert "research" in stages
    assert "analyze" in stages
    assert "write" in stages

    draft = detail["intake_draft"]
    assert draft is not None
    assert draft["user_role"] == "pm"
    assert "Notion" in draft["competitors_explicit"]


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
    assert create.status_code == 200
    run_id = create.json()["run_id"]
    _post_intake_reply_when_ready(
        test_client,
        run_id=run_id,
        body={"text": "pm", "selected_options": ["pm"]},
    )
    reply = test_client.post(f"/api/runs/{run_id}/intake/reply", json={"text": "", "selected_options": []})
    assert reply.status_code == 422


# Phase 2: POST /api/runs/{id}/plan/confirm tests live in test_plan_api.py so
# this module stays focused on intake-stage assertions.
