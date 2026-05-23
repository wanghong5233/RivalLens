from __future__ import annotations

from fastapi.testclient import TestClient

from schemas.agent_message import AgentMessage
from schemas.business import Evidence
from schemas.qa import Rejection, RetryPolicy
from schemas.skill import SkillCandidate
from schemas.supervisor import SupervisorDecision


def test_health_endpoint(test_client: TestClient) -> None:
    response = test_client.get("/health")
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "ok"


def test_create_run_stub(test_client: TestClient) -> None:
    response = test_client.post(
        "/api/runs",
        json={
            "competitors": ["comp_cursor", "comp_windsurf"],
            "industry_pack": "ai_coding_tools",
            "target_roles": ["pm", "founder"],
        },
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "stub"
    assert payload["run_id"].startswith("run_")


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
