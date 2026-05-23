from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from core.config import settings
from schemas.agent_message import AgentMessage
from schemas.business import Evidence
from schemas.qa import Rejection, RetryPolicy
from schemas.skill import SkillCandidate
from schemas.supervisor import SupervisorDecision


def _fetch_persisted_snapshot(run_id: str) -> dict[str, int | str | bool]:
    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with engine.connect() as connection:
            run_row = connection.execute(
                text("SELECT status FROM runs WHERE run_id = :run_id"),
                {"run_id": run_id},
            ).mappings().first()
            step_count = connection.execute(
                text("SELECT COUNT(*) AS count FROM steps WHERE run_id = :run_id"),
                {"run_id": run_id},
            ).scalar_one()
            decision_row = connection.execute(
                text(
                    "SELECT chosen_tool FROM supervisor_decisions "
                    "WHERE run_id = :run_id ORDER BY created_at DESC LIMIT 1"
                ),
                {"run_id": run_id},
            ).mappings().first()
            qa_step_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM steps "
                    "WHERE run_id = :run_id AND agent_name = 'qa'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            qa_rejection_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM steps "
                    "WHERE run_id = :run_id AND agent_name = 'qa' "
                    "AND rejection_reason IS NOT NULL"
                ),
                {"run_id": run_id},
            ).scalar_one()
            supervisor_step_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM steps "
                    "WHERE run_id = :run_id AND agent_name = 'supervisor'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            supervisor_llm_call_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM llm_calls l "
                    "JOIN steps s ON s.step_id = l.step_id "
                    "WHERE s.run_id = :run_id AND s.agent_name = 'supervisor'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            supervisor_llm_success_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM llm_calls l "
                    "JOIN steps s ON s.step_id = l.step_id "
                    "WHERE s.run_id = :run_id AND s.agent_name = 'supervisor' "
                    "AND l.model_slot = 'research' AND l.error IS NULL"
                ),
                {"run_id": run_id},
            ).scalar_one()
            supervisor_llm_prompt_hash_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM llm_calls l "
                    "JOIN steps s ON s.step_id = l.step_id "
                    "WHERE s.run_id = :run_id AND s.agent_name = 'supervisor' "
                    "AND l.prompt_hash IS NOT NULL"
                ),
                {"run_id": run_id},
            ).scalar_one()
            evidence_count = connection.execute(
                text("SELECT COUNT(*) AS count FROM evidence WHERE run_id = :run_id"),
                {"run_id": run_id},
            ).scalar_one()
            industry_pack_evidence_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM evidence "
                    "WHERE run_id = :run_id AND source_type = 'industry_pack_snapshot'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            evidence_url_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM evidence "
                    "WHERE run_id = :run_id AND source_url IS NOT NULL"
                ),
                {"run_id": run_id},
            ).scalar_one()
            expected_phrase_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM evidence "
                    "WHERE run_id = :run_id AND "
                    "(sanitized_text ILIKE :cursor_phrase OR sanitized_text ILIKE :windsurf_phrase)"
                ),
                {
                    "run_id": run_id,
                    "cursor_phrase": "%repository-level context indexing%",
                    "windsurf_phrase": "%inline AI pair programming%",
                },
            ).scalar_one()
    finally:
        engine.dispose()

    return {
        "run_status": run_row["status"] if run_row else "missing",
        "step_count": int(step_count),
        "latest_tool": decision_row["chosen_tool"] if decision_row else "missing",
        "qa_step_count": int(qa_step_count),
        "qa_rejection_count": int(qa_rejection_count),
        "supervisor_step_count": int(supervisor_step_count),
        "supervisor_llm_call_count": int(supervisor_llm_call_count),
        "supervisor_llm_success_count": int(supervisor_llm_success_count),
        "supervisor_llm_prompt_hash_count": int(supervisor_llm_prompt_hash_count),
        "evidence_count": int(evidence_count),
        "industry_pack_evidence_count": int(industry_pack_evidence_count),
        "evidence_url_count": int(evidence_url_count),
        "expected_phrase_count": int(expected_phrase_count),
    }


def test_health_endpoint(test_client: TestClient) -> None:
    response = test_client.get("/health")
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "ok"


def test_create_run_persists_rows(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/runs",
        json={
            "user_query": "compare cursor and windsurf for founders",
            "competitors": ["comp_cursor", "comp_windsurf"],
            "industry_pack": "ai_coding_tools",
            "target_roles": ["pm", "founder"],
        },
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "completed"
    assert payload["run_id"].startswith("run_")

    snapshot = _fetch_persisted_snapshot(payload["run_id"])
    assert snapshot["run_status"] == "completed"
    assert snapshot["step_count"] >= 5
    assert snapshot["latest_tool"] == "Finalize"
    assert snapshot["qa_step_count"] >= 1
    assert snapshot["qa_rejection_count"] == 0
    assert snapshot["supervisor_llm_call_count"] >= snapshot["supervisor_step_count"]
    assert snapshot["supervisor_llm_success_count"] >= 1
    assert snapshot["supervisor_llm_prompt_hash_count"] >= 1
    assert snapshot["evidence_count"] >= 1
    assert snapshot["industry_pack_evidence_count"] >= 1
    assert snapshot["evidence_url_count"] >= 1
    assert snapshot["expected_phrase_count"] >= 1


def test_get_run_detail_and_trace(test_client: TestClient) -> None:
    create_response = test_client.post(
        "/api/runs",
        json={
            "user_query": "what is the pricing differentiation",
            "competitors": ["comp_cursor"],
            "industry_pack": "ai_coding_tools",
            "target_roles": ["pm"],
        },
    )
    assert create_response.status_code == 200
    run_id = create_response.json()["run_id"]

    detail_response = test_client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["run_id"] == run_id
    assert detail_payload["status"] == "completed"
    assert detail_payload["industry_pack"] == "ai_coding_tools"
    assert detail_payload["user_query"] == "what is the pricing differentiation"

    trace_response = test_client.get(f"/api/runs/{run_id}/trace")
    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["run"]["run_id"] == run_id
    assert len(trace_payload["steps"]) >= 4
    assert len(trace_payload["supervisor_decisions"]) >= 4
    decision_tools = [item["chosen_tool"] for item in trace_payload["supervisor_decisions"]]
    step_agents = [item["agent_name"] for item in trace_payload["steps"]]
    assert decision_tools[-1] == "Finalize"
    assert "ConductResearch" in decision_tools
    assert "Analyze" in decision_tools
    assert "Write" in decision_tools
    assert "researcher" in step_agents
    assert "analyst" in step_agents
    assert "writer" in step_agents
    assert "qa" in step_agents

    not_found_response = test_client.get("/api/runs/run_not_exists")
    assert not_found_response.status_code == 404
    assert not_found_response.json()["error_code"] == "RUN_NOT_FOUND"


def test_schema_models_instantiation() -> None:
    now = "2026-05-23T00:00:00+00:00"

    evidence = Evidence(
        id="ev_cursor_001",
        run_id="run_demo_001",
        source_type="official_site",
        source_url="https://cursor.com",
        source_title="Cursor",
        quote="Cursor supports repository context.",
        sanitized_text="Cursor supports repository context.",
        span={"start": 0, "end": 35},
        collected_by="step_researcher_001",
        collected_at=now,
        desensitized=True,
    )
    assert evidence.id.startswith("ev_")

    agent_message = AgentMessage(
        message_id="msg_001",
        run_id="run_demo_001",
        step_id="step_001",
        trace_id="trace_001",
        source_agent="researcher",
        target_agent="supervisor",
        status="completed",
        payload_type="evidence_batch",
        payload={"evidence_ids": ["ev_cursor_001"]},
        evidence_refs=["ev_cursor_001"],
        artifact_refs=["artifact_001"],
        created_at=now,
    )
    assert agent_message.payload_type == "evidence_batch"

    decision = SupervisorDecision(
        id="decision_001",
        run_id="run_demo_001",
        iteration=1,
        chosen_tool="Finalize",
        tool_args={"completion_reason": "user_requested_stop"},
        reasoning_summary="Skeleton run.",
        triggered_by="user_query",
        outcome="succeeded",
        outcome_recorded_at=now,
        created_at=now,
    )
    assert decision.chosen_tool == "Finalize"

    rejection = Rejection(
        rejection_id="rejection_001",
        step_id="step_qa_001",
        reject_to="researcher",
        failed_rule_ids=["rule_pricing_requires_evidence"],
        semantic_findings=["Missing official source"],
        required_fields=["pricing.evidence_ids"],
        retry_policy=RetryPolicy(max_retry=3, current_retry=1),
        severity="blocking",
        reviewer_step_id="step_qa_001",
        created_at=now,
    )
    assert rejection.retry_policy.max_retry == 3

    candidate = SkillCandidate(
        id="skill_001",
        candidate_type="qa_rule",
        industry_pack="ai_coding_tools",
        payload={"rule_yaml": "id: rule_x"},
        rationale="Recurring QA failure pattern",
        supporting_run_ids=["run_demo_001"],
        confidence="medium",
        created_at=now,
    )
    assert candidate.status == "staging"


def test_create_run_rejects_missing_industry_pack(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/runs",
        json={
            "user_query": "invalid industry pack",
            "competitors": ["comp_cursor"],
            "industry_pack": "not_existing_pack",
            "target_roles": ["pm"],
        },
    )
    payload = response.json()
    assert response.status_code == 400
    assert payload["error_code"] == "INDUSTRY_PACK_NOT_FOUND"


def test_create_run_rejects_missing_competitor_in_pack(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/runs",
        json={
            "user_query": "invalid competitor",
            "competitors": ["comp_unknown"],
            "industry_pack": "ai_coding_tools",
            "target_roles": ["pm"],
        },
    )
    payload = response.json()
    assert response.status_code == 400
    assert payload["error_code"] == "COMPETITOR_NOT_IN_PACK"
