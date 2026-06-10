from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from core.config import settings


def _insert_watchlist_digest_fixture() -> dict[str, object]:
    suffix = uuid4().hex[:8]
    competitor_base = f"cursor_digest_{suffix}"
    run_old_id = f"run_watch_old_{suffix}"
    run_new_id = f"run_watch_new_{suffix}"
    step_old_id = f"step_watch_old_{suffix}"
    step_new_id = f"step_watch_new_{suffix}"
    conclusion_old_id = f"concl_watch_old_{suffix}"
    conclusion_new_id = f"concl_watch_new_{suffix}"
    watch_id = f"watch_{suffix}"
    evidence_old_id = f"ev_watch_old_{suffix}"
    evidence_new_primary_id = f"ev_watch_new_a_{suffix}"
    evidence_new_secondary_id = f"ev_watch_new_b_{suffix}"

    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=4)
    new_time = now - timedelta(hours=1)

    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO runs ("
                    "run_id, user_query, title, status, target_roles, competitors, started_at, created_at"
                    ") VALUES ("
                    ":run_id, :user_query, :title, :status, "
                    "CAST(:target_roles AS jsonb), CAST(:competitors AS jsonb), :started_at, :created_at"
                    ")"
                ),
                {
                    "run_id": run_old_id,
                    "user_query": "watch digest old run",
                    "title": "Cursor pricing baseline",
                    "status": "completed",
                    "target_roles": "[]",
                    "competitors": json.dumps([competitor_base], ensure_ascii=False),
                    "started_at": old_time,
                    "created_at": old_time,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO runs ("
                    "run_id, user_query, title, status, target_roles, competitors, started_at, created_at"
                    ") VALUES ("
                    ":run_id, :user_query, :title, :status, "
                    "CAST(:target_roles AS jsonb), CAST(:competitors AS jsonb), :started_at, :created_at"
                    ")"
                ),
                {
                    "run_id": run_new_id,
                    "user_query": "Cursor launch recap",
                    "title": None,
                    "status": "completed",
                    "target_roles": "[]",
                    "competitors": json.dumps([competitor_base], ensure_ascii=False),
                    "started_at": new_time,
                    "created_at": new_time,
                },
            )

            connection.execute(
                text(
                    "INSERT INTO steps (step_id, run_id, agent_name, status, retry_count, payload, created_at) "
                    "VALUES (:step_id, :run_id, 'analyst', 'completed', 0, CAST(:payload AS jsonb), :created_at)"
                ),
                {"step_id": step_old_id, "run_id": run_old_id, "payload": "{}", "created_at": old_time},
            )
            connection.execute(
                text(
                    "INSERT INTO steps (step_id, run_id, agent_name, status, retry_count, payload, created_at) "
                    "VALUES (:step_id, :run_id, 'analyst', 'completed', 0, CAST(:payload AS jsonb), :created_at)"
                ),
                {"step_id": step_new_id, "run_id": run_new_id, "payload": "{}", "created_at": new_time},
            )

            for evidence_id, run_id, step_id in (
                (evidence_old_id, run_old_id, step_old_id),
                (evidence_new_primary_id, run_new_id, step_new_id),
                (evidence_new_secondary_id, run_new_id, step_new_id),
            ):
                connection.execute(
                    text(
                        "INSERT INTO evidence ("
                        "id, run_id, source_type, source_url, source_title, quote, sanitized_text, "
                        "span, collected_by, collected_at, desensitized"
                        ") VALUES ("
                        ":id, :run_id, 'article', :source_url, :source_title, :quote, :sanitized_text, "
                        "CAST(:span AS jsonb), :collected_by, :collected_at, :desensitized"
                        ")"
                    ),
                    {
                        "id": evidence_id,
                        "run_id": run_id,
                        "source_url": f"https://example.com/{evidence_id}",
                        "source_title": f"source {evidence_id}",
                        "quote": f"quote {evidence_id}",
                        "sanitized_text": f"sanitized {evidence_id}",
                        "span": json.dumps({"competitor_id": competitor_base}, ensure_ascii=False),
                        "collected_by": step_id,
                        "collected_at": new_time,
                        "desensitized": True,
                    },
                )

            connection.execute(
                text(
                    "INSERT INTO conclusions ("
                    "conclusion_id, run_id, step_id, section, claim, confidence, competitor_ids, risk_flags, created_at"
                    ") VALUES ("
                    ":conclusion_id, :run_id, :step_id, :section, :claim, :confidence, "
                    "CAST(:competitor_ids AS jsonb), CAST(:risk_flags AS jsonb), :created_at"
                    ")"
                ),
                {
                    "conclusion_id": conclusion_old_id,
                    "run_id": run_old_id,
                    "step_id": step_old_id,
                    "section": "pricing",
                    "claim": "Old pricing signal.",
                    "confidence": "medium",
                    "competitor_ids": json.dumps([competitor_base], ensure_ascii=False),
                    "risk_flags": "[]",
                    "created_at": old_time,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO conclusions ("
                    "conclusion_id, run_id, step_id, section, claim, confidence, competitor_ids, risk_flags, created_at"
                    ") VALUES ("
                    ":conclusion_id, :run_id, :step_id, :section, :claim, :confidence, "
                    "CAST(:competitor_ids AS jsonb), CAST(:risk_flags AS jsonb), :created_at"
                    ")"
                ),
                {
                    "conclusion_id": conclusion_new_id,
                    "run_id": run_new_id,
                    "step_id": step_new_id,
                    "section": "feature",
                    "claim": "New feature launch signal.",
                    "confidence": "high",
                    "competitor_ids": json.dumps([f"  {competitor_base.upper()}  "], ensure_ascii=False),
                    "risk_flags": "[]",
                    "created_at": new_time,
                },
            )

            connection.execute(
                text(
                    "INSERT INTO conclusion_evidence (conclusion_id, evidence_id, relevance_rank) "
                    "VALUES (:conclusion_id, :evidence_id, :relevance_rank)"
                ),
                {
                    "conclusion_id": conclusion_old_id,
                    "evidence_id": evidence_old_id,
                    "relevance_rank": 0,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO conclusion_evidence (conclusion_id, evidence_id, relevance_rank) "
                    "VALUES (:conclusion_id, :evidence_id, :relevance_rank)"
                ),
                {
                    "conclusion_id": conclusion_new_id,
                    "evidence_id": evidence_new_secondary_id,
                    "relevance_rank": 1,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO conclusion_evidence (conclusion_id, evidence_id, relevance_rank) "
                    "VALUES (:conclusion_id, :evidence_id, :relevance_rank)"
                ),
                {
                    "conclusion_id": conclusion_new_id,
                    "evidence_id": evidence_new_primary_id,
                    "relevance_rank": 0,
                },
            )

            connection.execute(
                text(
                    "INSERT INTO watchlist (watch_id, competitor_id, note, created_at) "
                    "VALUES (:watch_id, :competitor_id, :note, :created_at)"
                ),
                {
                    "watch_id": watch_id,
                    "competitor_id": competitor_base.lower(),
                    "note": "pricing and launch",
                    "created_at": now,
                },
            )
    finally:
        engine.dispose()

    return {
        "watch_id": watch_id,
        "run_old_id": run_old_id,
        "run_new_id": run_new_id,
        "conclusion_old_id": conclusion_old_id,
        "conclusion_new_id": conclusion_new_id,
        "evidence_old_id": evidence_old_id,
        "evidence_new_ids": [evidence_new_primary_id, evidence_new_secondary_id],
    }


def _cleanup_watchlist_digest_fixture(*, watch_id: str, run_ids: list[str]) -> None:
    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM watchlist WHERE watch_id = :watch_id"),
                {"watch_id": watch_id},
            )
            for run_id in run_ids:
                connection.execute(
                    text("DELETE FROM runs WHERE run_id = :run_id"),
                    {"run_id": run_id},
                )
    finally:
        engine.dispose()


def test_watchlist_digest_groups_conclusions_case_insensitive(test_client: TestClient) -> None:
    fixture = _insert_watchlist_digest_fixture()
    try:
        response = test_client.get("/api/watchlist/digest")
        assert response.status_code == 200, response.text
        payload = response.json()

        watch_item = next(
            item
            for item in payload
            if item["watch_id"] == fixture["watch_id"]
        )
        assert watch_item["insight_count"] == 2
        assert watch_item["run_count"] == 2
        assert watch_item["latest_run_id"] == fixture["run_new_id"]
        assert watch_item["last_updated_at"] is not None
        assert len(watch_item["items"]) == 2

        latest_item = watch_item["items"][0]
        previous_item = watch_item["items"][1]

        assert latest_item["conclusion_id"] == fixture["conclusion_new_id"]
        assert latest_item["run_id"] == fixture["run_new_id"]
        assert latest_item["run_title"] == "Cursor launch recap"
        assert latest_item["evidence_ids"] == fixture["evidence_new_ids"]

        assert previous_item["conclusion_id"] == fixture["conclusion_old_id"]
        assert previous_item["run_id"] == fixture["run_old_id"]
        assert previous_item["run_title"] == "Cursor pricing baseline"
        assert previous_item["evidence_ids"] == [fixture["evidence_old_id"]]
    finally:
        _cleanup_watchlist_digest_fixture(
            watch_id=str(fixture["watch_id"]),
            run_ids=[str(fixture["run_old_id"]), str(fixture["run_new_id"])],
        )
