from __future__ import annotations

from fastapi.testclient import TestClient


def _create_run_and_get_staging_candidate_id(test_client: TestClient) -> tuple[str, str]:
    create_response = test_client.post(
        "/api/runs",
        json={
            "user_query": "generate skill candidate for review api",
            "competitors": ["comp_cursor"],
            "industry_pack": "ai_coding_tools",
            "target_roles": ["pm"],
        },
    )
    assert create_response.status_code == 200
    run_id = create_response.json()["run_id"]

    list_response = test_client.get(
        "/api/skill-candidates",
        params={"status": "staging", "industry_pack": "ai_coding_tools", "limit": 50, "offset": 0},
    )
    assert list_response.status_code == 200
    list_payload = list_response.json()
    candidate = next(
        (item for item in list_payload["items"] if run_id in item["supporting_run_ids"]),
        None,
    )
    assert candidate is not None
    return run_id, candidate["id"]


def test_list_skill_candidates(test_client: TestClient) -> None:
    run_id, candidate_id = _create_run_and_get_staging_candidate_id(test_client)
    response = test_client.get(
        "/api/skill-candidates",
        params={"status": "staging", "industry_pack": "ai_coding_tools", "limit": 20, "offset": 0},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["total"] >= 1
    listed = next((item for item in payload["items"] if item["id"] == candidate_id), None)
    assert listed is not None
    assert listed["industry_pack"] == "ai_coding_tools"
    assert run_id in listed["supporting_run_ids"]
    assert listed["status"] == "staging"


def test_approve_skill_candidate(test_client: TestClient) -> None:
    _, candidate_id = _create_run_and_get_staging_candidate_id(test_client)
    approve_response = test_client.post(
        f"/api/skill-candidates/{candidate_id}/approve",
        json={"reviewed_by": "owner_wh"},
    )
    approve_payload = approve_response.json()
    assert approve_response.status_code == 200
    assert approve_payload["id"] == candidate_id
    assert approve_payload["status"] == "approved"
    assert approve_payload["reviewed_by"] == "owner_wh"


def test_reject_skill_candidate(test_client: TestClient) -> None:
    _, candidate_id = _create_run_and_get_staging_candidate_id(test_client)
    reject_response = test_client.post(
        f"/api/skill-candidates/{candidate_id}/reject",
        json={"reviewed_by": "owner_wh"},
    )
    reject_payload = reject_response.json()
    assert reject_response.status_code == 200
    assert reject_payload["id"] == candidate_id
    assert reject_payload["status"] == "rejected"
    assert reject_payload["reviewed_by"] == "owner_wh"


def test_approve_skill_candidate_rejects_non_staging(test_client: TestClient) -> None:
    _, candidate_id = _create_run_and_get_staging_candidate_id(test_client)
    first_response = test_client.post(
        f"/api/skill-candidates/{candidate_id}/approve",
        json={"reviewed_by": "owner_wh"},
    )
    assert first_response.status_code == 200

    second_response = test_client.post(
        f"/api/skill-candidates/{candidate_id}/approve",
        json={"reviewed_by": "owner_wh"},
    )
    second_payload = second_response.json()
    assert second_response.status_code == 409
    assert second_payload["error_code"] == "SKILL_CANDIDATE_NOT_REVIEWABLE"
