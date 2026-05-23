from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from core.config import settings
from schemas.agent_message import AgentMessage
from schemas.business import Evidence
from schemas.qa import Rejection, RetryPolicy
from schemas.skill import SkillCandidate
from schemas.supervisor import SupervisorDecision


def _fetch_persisted_snapshot(run_id: str) -> dict[str, int | str | bool | float]:
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
            first_decision_row = connection.execute(
                text(
                    "SELECT chosen_tool FROM supervisor_decisions "
                    "WHERE run_id = :run_id ORDER BY created_at ASC LIMIT 1"
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
            analyst_step_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM steps "
                    "WHERE run_id = :run_id AND agent_name = 'analyst'"
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
            analyst_llm_call_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM llm_calls l "
                    "JOIN steps s ON s.step_id = l.step_id "
                    "WHERE s.run_id = :run_id AND s.agent_name = 'analyst'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            analyst_llm_summarization_slot_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM llm_calls l "
                    "JOIN steps s ON s.step_id = l.step_id "
                    "WHERE s.run_id = :run_id AND s.agent_name = 'analyst' "
                    "AND l.model_slot = 'summarization'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            analyst_fallback_mode_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM steps "
                    "WHERE run_id = :run_id AND agent_name = 'analyst' "
                    "AND payload ->> 'analysis_mode' = 'fallback'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            qa_llm_call_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM llm_calls l "
                    "JOIN steps s ON s.step_id = l.step_id "
                    "WHERE s.run_id = :run_id AND s.agent_name = 'qa' "
                    "AND l.model_slot = 'qa'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            qa_semantic_degraded_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM steps "
                    "WHERE run_id = :run_id AND agent_name = 'qa' "
                    "AND payload ->> 'qa_semantic_mode' = 'degraded_rule_only'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            writer_llm_call_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM llm_calls l "
                    "JOIN steps s ON s.step_id = l.step_id "
                    "WHERE s.run_id = :run_id AND s.agent_name = 'writer' "
                    "AND l.model_slot = 'writer'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            researcher_llm_call_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM llm_calls l "
                    "JOIN steps s ON s.step_id = l.step_id "
                    "WHERE s.run_id = :run_id AND s.agent_name = 'researcher'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            researcher_llm_research_slot_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM llm_calls l "
                    "JOIN steps s ON s.step_id = l.step_id "
                    "WHERE s.run_id = :run_id AND s.agent_name = 'researcher' "
                    "AND l.model_slot = 'research'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            researcher_step_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM steps "
                    "WHERE run_id = :run_id AND agent_name = 'researcher'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            researcher_started_span_seconds_raw = connection.execute(
                text(
                    "SELECT COALESCE(EXTRACT(EPOCH FROM (MAX(started_at) - MIN(started_at))), 0) AS span "
                    "FROM steps WHERE run_id = :run_id AND agent_name = 'researcher'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            checkpoint_row_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM checkpoints "
                    "WHERE thread_id = :run_id"
                ),
                {"run_id": run_id},
            ).scalar_one()
            checkpoint_writes_row_count = connection.execute(
                text(
                    "SELECT COUNT(*) AS count FROM checkpoint_writes "
                    "WHERE thread_id = :run_id"
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
            latest_report_row = connection.execute(
                text(
                    "SELECT content_json, content_markdown FROM reports "
                    "WHERE run_id = :run_id ORDER BY created_at DESC LIMIT 1"
                ),
                {"run_id": run_id},
            ).mappings().first()
    finally:
        engine.dispose()

    if latest_report_row is not None:
        report_json_raw = latest_report_row["content_json"]
        report_markdown_raw = latest_report_row["content_markdown"]
        if isinstance(report_json_raw, dict):
            sections_raw = report_json_raw.get("sections")
        else:
            sections_raw = []
        if isinstance(sections_raw, list):
            report_sections_content_count = len(
                [
                    section
                    for section in sections_raw
                    if isinstance(section, dict)
                    and isinstance(section.get("content_markdown"), str)
                    and bool(section["content_markdown"].strip())
                ]
            )
        else:
            report_sections_content_count = 0
        if isinstance(report_markdown_raw, str):
            report_has_evidence_citation = "[ev_" in report_markdown_raw
        else:
            report_has_evidence_citation = False
    else:
        report_sections_content_count = 0
        report_has_evidence_citation = False

    return {
        "run_status": run_row["status"] if run_row else "missing",
        "step_count": int(step_count),
        "first_tool": first_decision_row["chosen_tool"] if first_decision_row else "missing",
        "latest_tool": decision_row["chosen_tool"] if decision_row else "missing",
        "qa_step_count": int(qa_step_count),
        "qa_rejection_count": int(qa_rejection_count),
        "supervisor_step_count": int(supervisor_step_count),
        "analyst_step_count": int(analyst_step_count),
        "supervisor_llm_call_count": int(supervisor_llm_call_count),
        "supervisor_llm_success_count": int(supervisor_llm_success_count),
        "supervisor_llm_prompt_hash_count": int(supervisor_llm_prompt_hash_count),
        "analyst_llm_call_count": int(analyst_llm_call_count),
        "analyst_llm_summarization_slot_count": int(analyst_llm_summarization_slot_count),
        "analyst_fallback_mode_count": int(analyst_fallback_mode_count),
        "qa_llm_call_count": int(qa_llm_call_count),
        "qa_semantic_degraded_count": int(qa_semantic_degraded_count),
        "writer_llm_call_count": int(writer_llm_call_count),
        "researcher_llm_call_count": int(researcher_llm_call_count),
        "researcher_llm_research_slot_count": int(researcher_llm_research_slot_count),
        "researcher_step_count": int(researcher_step_count),
        "researcher_started_span_seconds": float(researcher_started_span_seconds_raw),
        "checkpoint_row_count": int(checkpoint_row_count),
        "checkpoint_writes_row_count": int(checkpoint_writes_row_count),
        "evidence_count": int(evidence_count),
        "industry_pack_evidence_count": int(industry_pack_evidence_count),
        "evidence_url_count": int(evidence_url_count),
        "expected_phrase_count": int(expected_phrase_count),
        "report_sections_content_count": int(report_sections_content_count),
        "report_has_evidence_citation": report_has_evidence_citation,
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
    assert snapshot["first_tool"] == "ConductResearchBatch"
    assert snapshot["latest_tool"] == "Finalize"
    assert snapshot["qa_step_count"] >= 1
    assert snapshot["qa_rejection_count"] == 0
    assert snapshot["supervisor_llm_call_count"] >= snapshot["supervisor_step_count"]
    assert snapshot["supervisor_llm_success_count"] >= 1
    assert snapshot["supervisor_llm_prompt_hash_count"] >= 1
    assert snapshot["analyst_step_count"] >= 1
    assert snapshot["analyst_llm_call_count"] >= 1
    assert snapshot["analyst_llm_summarization_slot_count"] >= 1
    assert snapshot["analyst_fallback_mode_count"] >= 1
    assert snapshot["qa_llm_call_count"] >= 1
    assert snapshot["qa_semantic_degraded_count"] >= 1
    assert snapshot["writer_llm_call_count"] >= 1
    assert snapshot["researcher_llm_call_count"] >= 1
    assert snapshot["researcher_llm_research_slot_count"] >= 1
    assert snapshot["researcher_step_count"] >= 2
    assert snapshot["researcher_started_span_seconds"] < 2.0
    assert snapshot["checkpoint_row_count"] >= 1
    assert snapshot["checkpoint_writes_row_count"] >= 1
    assert snapshot["evidence_count"] >= 1
    assert snapshot["industry_pack_evidence_count"] >= 1
    assert snapshot["evidence_url_count"] >= 1
    assert snapshot["expected_phrase_count"] >= 1
    assert snapshot["report_sections_content_count"] >= 3
    assert snapshot["report_has_evidence_citation"] is True


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


def test_get_run_integration_endpoints(test_client: TestClient) -> None:
    create_response = test_client.post(
        "/api/runs",
        json={
            "user_query": "integration endpoints check",
            "competitors": ["comp_cursor", "comp_windsurf"],
            "industry_pack": "ai_coding_tools",
            "target_roles": ["pm"],
        },
    )
    assert create_response.status_code == 200
    run_id = create_response.json()["run_id"]

    list_response = test_client.get("/api/runs", params={"status": "completed", "limit": 20, "offset": 0})
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert isinstance(list_payload["items"], list)
    run_items = [item for item in list_payload["items"] if item["run_id"] == run_id]
    assert run_items
    listed_run = run_items[0]
    assert listed_run["step_count"] >= 1
    assert listed_run["evidence_count"] >= 1
    assert listed_run["has_report"] is True

    report_response = test_client.get(f"/api/runs/{run_id}/report")
    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert report_payload["run_id"] == run_id
    assert isinstance(report_payload["content_markdown"], str)
    assert report_payload["content_markdown"].strip()
    assert isinstance(report_payload["evidence_id_to_brief"], dict)
    assert report_payload["evidence_id_to_brief"]

    evidence_response = test_client.get(f"/api/runs/{run_id}/evidence")
    assert evidence_response.status_code == 200
    evidence_payload = evidence_response.json()
    assert isinstance(evidence_payload, list)
    assert evidence_payload
    assert all(item["run_id"] == run_id for item in evidence_payload)

    competitor_filtered_response = test_client.get(
        f"/api/runs/{run_id}/evidence",
        params={"competitor_id": "comp_cursor"},
    )
    assert competitor_filtered_response.status_code == 200
    competitor_filtered_payload = competitor_filtered_response.json()
    assert competitor_filtered_payload
    assert all(item["competitor_id"] == "comp_cursor" for item in competitor_filtered_payload)

    source_type_filtered_response = test_client.get(
        f"/api/runs/{run_id}/evidence",
        params={"source_type": "industry_pack_snapshot"},
    )
    assert source_type_filtered_response.status_code == 200
    source_type_filtered_payload = source_type_filtered_response.json()
    assert source_type_filtered_payload
    assert all(item["source_type"] == "industry_pack_snapshot" for item in source_type_filtered_payload)

    packs_response = test_client.get("/api/industry-packs")
    assert packs_response.status_code == 200
    packs_payload = packs_response.json()
    assert isinstance(packs_payload, list)
    target_pack = next((item for item in packs_payload if item["id"] == "ai_coding_tools"), None)
    assert target_pack is not None
    assert target_pack["display_name"] == "AI Coding Tools"
    competitor_ids = {item["id"] for item in target_pack["competitors"]}
    assert {"comp_cursor", "comp_windsurf"}.issubset(competitor_ids)
    assert set(target_pack["research_dimensions"]) >= {"feature", "pricing", "user_feedback"}


def test_resume_run_continues_from_checkpoint(test_client: TestClient) -> None:
    create_response = test_client.post(
        "/api/runs",
        json={
            "user_query": "resume from checkpoint",
            "competitors": ["comp_cursor", "comp_windsurf"],
            "industry_pack": "ai_coding_tools",
            "target_roles": ["pm"],
        },
    )
    assert create_response.status_code == 200
    run_id = create_response.json()["run_id"]

    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE runs SET status = 'running', finished_at = :finished_at "
                    "WHERE run_id = :run_id"
                ),
                {"run_id": run_id, "finished_at": None},
            )
    finally:
        engine.dispose()

    resume_response = test_client.post(f"/api/runs/{run_id}/resume")
    assert resume_response.status_code == 200
    resume_payload = resume_response.json()
    assert resume_payload["run_id"] == run_id
    assert resume_payload["status"] == "completed"

    detail_response = test_client.get(f"/api/runs/{run_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["status"] == "completed"
    assert detail_payload["finished_at"] is not None

    non_resumable_response = test_client.post(f"/api/runs/{run_id}/resume")
    assert non_resumable_response.status_code == 409
    assert non_resumable_response.json()["error_code"] == "RUN_NOT_RESUMABLE"


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
