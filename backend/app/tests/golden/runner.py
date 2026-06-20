from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import time

import yaml
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from core.config import settings
from service.collector.registry import get_channel_registry
from service.skill_store import get_skill_store
from tests.golden.assertions import assert_contains, assert_equals, assert_gte


class GoldenCaseAssertions(BaseModel):
    final_qa_outcome: str | None = None
    qa_rejection_count_gte: int | None = None
    qa_rejection_count_lte: int | None = None
    qa_reject_to_includes: list[str] = Field(default_factory=list)
    warning_rule_ids_includes: list[str] = Field(default_factory=list)
    warning_rule_ids_excludes: list[str] = Field(default_factory=list)
    must_include_promoted_rule_id: str | None = None
    must_include_collector_action: str | None = None
    knowledge_feature_count_gte: int | None = None
    knowledge_pricing_count_gte: int | None = None
    knowledge_persona_count_gte: int | None = None
    knowledge_schema_coverage_rate_gte: float | None = None
    supervisor_iterations_lt: int | None = None
    analyze_count_lte: int | None = None
    report_section_count_gte: int | None = None
    report_section_ids_include: list[str] = Field(default_factory=list)
    report_degraded_required_sections_count_lte: int | None = None
    evidence_floor_count_lte: int | None = None
    source_authority_distribution_includes: list[str] = Field(default_factory=list)
    qa_warnings_count_gte: int | None = None


class PromotedQARuleFixture(BaseModel):
    rule_id: str
    rule_yaml: str


class GoldenCaseSetup(BaseModel):
    promoted_qa_rules: list[PromotedQARuleFixture] = Field(default_factory=list)
    llm_profile: str | None = None


class GoldenCaseInput(BaseModel):
    user_query: str
    competitors: list[str]
    domain_hint: str | None = None
    reference_urls: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=lambda: ["pm"])
    report_depth: str = "quick"
    market_scope: str | None = None
    self_product: str | None = None
    competitors_discovery_mode: bool = False


class GoldenCase(BaseModel):
    id: str
    description: str
    setup: GoldenCaseSetup = Field(default_factory=GoldenCaseSetup)
    input: GoldenCaseInput
    assertions: GoldenCaseAssertions = Field(default_factory=GoldenCaseAssertions)


def _query_with_llm_profile(*, user_query: str, llm_profile: str | None) -> str:
    if llm_profile is None:
        return user_query
    profile = llm_profile.strip()
    if not profile:
        return user_query
    return f"{user_query} test-profile:{profile}"


@dataclass(slots=True)
class GoldenCaseResult:
    case_id: str
    passed: bool
    run_id: str
    failures: list[str]
    qa_outcome: str | None
    qa_reject_to: str | None
    qa_rejection_count: int
    promoted_blocked_rule_ids: list[str]
    warning_rule_ids: list[str]
    coverage_rate: float | None
    knowledge_feature_count: int | None
    knowledge_pricing_count: int | None
    knowledge_persona_count: int | None
    knowledge_schema_coverage_rate: float | None
    llm_token_total: int | None
    run_wall_clock_seconds: int | None
    created_at: str
    collector_actions: list[str] = field(default_factory=list)
    supervisor_iterations: int | None = None
    analyze_count: int | None = None
    report_section_count: int | None = None
    source_authority_distribution: dict[str, int] | None = None
    qa_warnings_count: int | None = None
    report_section_ids: list[str] = field(default_factory=list)
    report_degraded_required_sections: list[str] = field(default_factory=list)
    evidence_floor_count: int | None = None


def _load_case(path: Path) -> GoldenCase:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RuntimeError(f"Golden case root must be object: {path}")
    return GoldenCase.model_validate(loaded)


_TERMINAL_RUN_STATUSES = {"completed", "degraded", "failed"}


def _wait_for_run_terminal(run_id: str, *, timeout_seconds: float = 90.0) -> str:
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


def _latest_qa_payload(run_id: str) -> dict[str, object]:
    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT payload FROM steps "
                    "WHERE run_id = :run_id AND agent_name = 'qa' "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"run_id": run_id},
            ).mappings().first()
    finally:
        engine.dispose()
    if row is None:
        raise RuntimeError(f"No QA step found for run_id={run_id}")
    payload = row["payload"]
    if not isinstance(payload, dict):
        raise RuntimeError(f"QA payload is not object for run_id={run_id}")
    return payload


def _qa_payloads_for_run(run_id: str) -> list[dict[str, object]]:
    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT payload FROM steps "
                    "WHERE run_id = :run_id AND agent_name = 'qa' "
                    "ORDER BY created_at ASC"
                ),
                {"run_id": run_id},
            ).mappings().all()
    finally:
        engine.dispose()
    payloads: list[dict[str, object]] = []
    for row in rows:
        payload = row["payload"]
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _last_qa_outcome(payloads: list[dict[str, object]]) -> str | None:
    for item in reversed(payloads):
        outcome_raw = item.get("qa_outcome")
        if isinstance(outcome_raw, str):
            return outcome_raw
    return None


def _last_qa_reject_to(payloads: list[dict[str, object]]) -> str | None:
    for item in reversed(payloads):
        reject_to_raw = item.get("qa_reject_to")
        if isinstance(reject_to_raw, str):
            return reject_to_raw
        reject_to_fallback_raw = item.get("reject_to")
        if isinstance(reject_to_fallback_raw, str):
            return reject_to_fallback_raw
    return None


def _write_promoted_rules_for_case(
    *,
    skills_root: Path,
    promoted_qa_rules: list[PromotedQARuleFixture],
) -> None:
    if not promoted_qa_rules:
        return
    for item in promoted_qa_rules:
        rule_dir = skills_root / "qa_rule" / item.rule_id
        rule_dir.mkdir(parents=True, exist_ok=True)
        frontmatter = {
            "name": item.rule_id,
            "description": "Golden-case promoted qa rule fixture.",
            "version": "1.0.0",
            "tags": ["golden_fixture"],
            "applies_to": "qa_rule",
        }
        skill_markdown = (
            f"---\n{yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip()}\n---\n\n"
            "## Rule DSL\n\n"
            "```yaml\n"
            f"{item.rule_yaml.strip()}\n"
            "```\n"
        )
        (rule_dir / "SKILL.md").write_text(skill_markdown, encoding="utf-8")


def _run_metrics_snapshot(*, run_id: str, client: TestClient) -> dict[str, object]:
    response = client.get(f"/api/runs/{run_id}/metrics")
    if response.status_code != 200:
        return {}
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _run_trajectory_snapshot(*, run_id: str) -> dict[str, object]:
    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with engine.connect() as connection:
            analyze_count = connection.execute(
                text(
                    "SELECT count(*) FROM supervisor_decisions "
                    "WHERE run_id = :run_id AND chosen_tool = 'Analyze'"
                ),
                {"run_id": run_id},
            ).scalar_one()
            report_row = connection.execute(
                text(
                    "SELECT content_json FROM reports "
                    "WHERE run_id = :run_id ORDER BY created_at DESC LIMIT 1"
                ),
                {"run_id": run_id},
            ).mappings().first()
    finally:
        engine.dispose()
    content_json = report_row["content_json"] if report_row is not None else {}
    if not isinstance(content_json, dict):
        content_json = {}
    sections_raw = content_json.get("sections")
    qa_warnings_raw = content_json.get("qa_warnings")
    executive_summary_raw = content_json.get("executive_summary")
    section_count = len(sections_raw) if isinstance(sections_raw, list) else 0
    if isinstance(executive_summary_raw, str) and executive_summary_raw.strip():
        section_count += 1
    return {
        "analyze_count": int(analyze_count),
        "report_section_count": section_count,
        "qa_warnings_count": len(qa_warnings_raw) if isinstance(qa_warnings_raw, list) else 0,
    }


def _final_report_snapshot(*, run_id: str) -> dict[str, object]:
    engine = create_engine(settings.DATABASE_URL_SYNC)
    try:
        with engine.connect() as connection:
            report_row = connection.execute(
                text(
                    "SELECT content_json FROM reports "
                    "WHERE run_id = :run_id ORDER BY created_at DESC LIMIT 1"
                ),
                {"run_id": run_id},
            ).mappings().first()
    finally:
        engine.dispose()
    content_json = report_row["content_json"] if report_row is not None else {}
    if not isinstance(content_json, dict):
        content_json = {}
    sections_raw = content_json.get("sections")
    section_ids = [
        str(item.get("section_id"))
        for item in sections_raw
        if isinstance(item, dict) and isinstance(item.get("section_id"), str)
    ] if isinstance(sections_raw, list) else []
    degraded_required_raw = content_json.get("report_degraded_required_sections")
    degraded_required = [
        str(item)
        for item in degraded_required_raw
        if isinstance(item, str)
    ] if isinstance(degraded_required_raw, list) else []
    return {
        "report_section_ids": section_ids,
        "report_degraded_required_sections": degraded_required,
    }


def run_case(*, case: GoldenCase, client: TestClient) -> GoldenCaseResult:
    invoked_actions: list[str] = []
    registry = get_channel_registry()
    original_invoke = registry.invoke
    skill_store = get_skill_store()
    original_skills_dir = skill_store.skills_dir

    async def _tracking_invoke(action: str, *, args: dict[str, object]):
        invoked_actions.append(action)
        return await original_invoke(action, args=args)

    registry.invoke = _tracking_invoke
    with tempfile.TemporaryDirectory(prefix="golden_case_skills_") as tmp_dir:
        skills_root = Path(tmp_dir) / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)
        _write_promoted_rules_for_case(
            skills_root=skills_root,
            promoted_qa_rules=case.setup.promoted_qa_rules,
        )
        skill_store.skills_dir = skills_root
        skill_store.invalidate()
        skill_store.scan()
        try:
            response = client.post(
                "/api/runs",
                json={
                    "user_query": _query_with_llm_profile(
                        user_query=case.input.user_query,
                        llm_profile=case.setup.llm_profile,
                    ),
                    "competitors": case.input.competitors,
                    "domain_hint": case.input.domain_hint,
                    "reference_urls": list(case.input.reference_urls),
                    "target_roles": case.input.target_roles,
                    "report_depth": case.input.report_depth,
                    "market_scope": case.input.market_scope,
                    "self_product": case.input.self_product,
                    "competitors_discovery_mode": case.input.competitors_discovery_mode,
                },
            )
        finally:
            registry.invoke = original_invoke
            skill_store.skills_dir = original_skills_dir
            skill_store.invalidate()
            skill_store.scan()
    if response.status_code != 200:
        return GoldenCaseResult(
            case_id=case.id,
            passed=False,
            run_id="",
            failures=[f"create_run_failed status={response.status_code} payload={response.text[:300]}"],
            qa_outcome=None,
            qa_reject_to=None,
            qa_rejection_count=0,
            promoted_blocked_rule_ids=[],
            warning_rule_ids=[],
            coverage_rate=None,
            knowledge_feature_count=None,
            knowledge_pricing_count=None,
            knowledge_persona_count=None,
            knowledge_schema_coverage_rate=None,
            llm_token_total=None,
            run_wall_clock_seconds=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            collector_actions=invoked_actions,
        )

    run_id = str(response.json()["run_id"])
    registry.invoke = _tracking_invoke
    try:
        _wait_for_run_terminal(run_id)
    finally:
        registry.invoke = original_invoke
    qa_payloads = _qa_payloads_for_run(run_id)
    qa_outcome = _last_qa_outcome(qa_payloads)
    qa_reject_to = _last_qa_reject_to(qa_payloads)
    qa_rejection_count = sum(
        1
        for item in qa_payloads
        if item.get("qa_outcome") in {"rejected", "force_degraded"}
    )
    reject_to_values = [
        value
        for item in qa_payloads
        if isinstance(item.get("reject_to"), str)
        for value in [item.get("reject_to")]
        if isinstance(value, str)
    ]
    failed_rule_ids: list[str] = []
    warning_rule_ids: list[str] = []
    promoted_blocked_rule_ids: list[str] = []
    for item in qa_payloads:
        failed_rule_ids_raw = item.get("failed_rule_ids")
        if isinstance(failed_rule_ids_raw, list):
            failed_rule_ids.extend(
                value for value in failed_rule_ids_raw if isinstance(value, str)
            )
        warning_rule_ids_raw = item.get("warning_rule_ids")
        if isinstance(warning_rule_ids_raw, list):
            warning_rule_ids.extend(
                value for value in warning_rule_ids_raw if isinstance(value, str)
            )
        blocked_rule_ids_raw = item.get("promoted_qa_blocked_rule_ids")
        if isinstance(blocked_rule_ids_raw, list):
            promoted_blocked_rule_ids.extend(
                value for value in blocked_rule_ids_raw if isinstance(value, str)
            )
    run_metrics = _run_metrics_snapshot(run_id=run_id, client=client)
    trajectory = _run_trajectory_snapshot(run_id=run_id)
    final_report = _final_report_snapshot(run_id=run_id)
    coverage_rate_raw = run_metrics.get("coverage_rate")
    llm_token_total_raw = run_metrics.get("llm_token_total")
    wall_clock_raw = run_metrics.get("run_wall_clock_seconds")
    knowledge_feature_count_raw = run_metrics.get("knowledge_feature_count")
    knowledge_pricing_count_raw = run_metrics.get("knowledge_pricing_count")
    knowledge_persona_count_raw = run_metrics.get("knowledge_persona_count")
    knowledge_schema_coverage_rate_raw = run_metrics.get("knowledge_schema_coverage_rate")
    supervisor_iterations_raw = run_metrics.get("supervisor_iterations")
    report_section_count_raw = run_metrics.get("report_section_count")
    source_authority_distribution_raw = run_metrics.get("source_authority_distribution")
    evidence_floor_count_raw = run_metrics.get("evidence_floor_count")
    analyze_count_raw = trajectory.get("analyze_count")
    qa_warnings_count_raw = trajectory.get("qa_warnings_count")
    report_section_ids_raw = final_report.get("report_section_ids")
    degraded_required_sections_raw = final_report.get("report_degraded_required_sections")
    coverage_rate = (
        float(coverage_rate_raw)
        if isinstance(coverage_rate_raw, (int, float))
        else None
    )
    knowledge_feature_count = (
        int(knowledge_feature_count_raw)
        if isinstance(knowledge_feature_count_raw, (int, float))
        else None
    )
    knowledge_pricing_count = (
        int(knowledge_pricing_count_raw)
        if isinstance(knowledge_pricing_count_raw, (int, float))
        else None
    )
    knowledge_persona_count = (
        int(knowledge_persona_count_raw)
        if isinstance(knowledge_persona_count_raw, (int, float))
        else None
    )
    knowledge_schema_coverage_rate = (
        float(knowledge_schema_coverage_rate_raw)
        if isinstance(knowledge_schema_coverage_rate_raw, (int, float))
        else None
    )
    llm_token_total = (
        int(llm_token_total_raw)
        if isinstance(llm_token_total_raw, (int, float))
        else None
    )
    run_wall_clock_seconds = (
        int(wall_clock_raw) if isinstance(wall_clock_raw, (int, float)) else None
    )
    supervisor_iterations = (
        int(supervisor_iterations_raw)
        if isinstance(supervisor_iterations_raw, (int, float))
        else None
    )
    analyze_count = (
        int(analyze_count_raw) if isinstance(analyze_count_raw, (int, float)) else None
    )
    report_section_count = (
        int(report_section_count_raw)
        if isinstance(report_section_count_raw, (int, float))
        else None
    )
    qa_warnings_count = (
        int(qa_warnings_count_raw)
        if isinstance(qa_warnings_count_raw, (int, float))
        else None
    )
    evidence_floor_count = (
        int(evidence_floor_count_raw)
        if isinstance(evidence_floor_count_raw, (int, float))
        else None
    )
    report_section_ids = (
        [item for item in report_section_ids_raw if isinstance(item, str)]
        if isinstance(report_section_ids_raw, list)
        else []
    )
    report_degraded_required_sections = (
        [item for item in degraded_required_sections_raw if isinstance(item, str)]
        if isinstance(degraded_required_sections_raw, list)
        else []
    )
    source_authority_distribution = (
        {
            key: int(value)
            for key, value in source_authority_distribution_raw.items()
            if isinstance(key, str) and isinstance(value, (int, float))
        }
        if isinstance(source_authority_distribution_raw, dict)
        else None
    )

    failures: list[str] = []
    if case.assertions.final_qa_outcome is not None:
        failed = assert_equals(
            actual=qa_outcome,
            expected=case.assertions.final_qa_outcome,
            field="final_qa_outcome",
        )
        if failed is not None:
            failures.append(failed)
    if case.assertions.qa_rejection_count_gte is not None:
        failed = assert_gte(
            actual=qa_rejection_count,
            expected=case.assertions.qa_rejection_count_gte,
            field="qa_rejection_count",
        )
        if failed is not None:
            failures.append(failed)
    if case.assertions.qa_rejection_count_lte is not None:
        if qa_rejection_count > case.assertions.qa_rejection_count_lte:
            failures.append(
                "qa_rejection_count expected <= "
                f"{case.assertions.qa_rejection_count_lte}, got {qa_rejection_count}"
            )
    if case.assertions.qa_reject_to_includes:
        for expected in case.assertions.qa_reject_to_includes:
            failed = assert_contains(
                values=reject_to_values,
                expected=expected,
                field="reject_to_history",
            )
            if failed is not None:
                failures.append(failed)
    if case.assertions.warning_rule_ids_includes:
        for expected in case.assertions.warning_rule_ids_includes:
            failed = assert_contains(
                values=warning_rule_ids,
                expected=expected,
                field="warning_rule_ids",
            )
            if failed is not None:
                failures.append(failed)
    if case.assertions.warning_rule_ids_excludes:
        for unexpected in case.assertions.warning_rule_ids_excludes:
            if unexpected in warning_rule_ids:
                failures.append(
                    f"warning_rule_ids expected to exclude {unexpected!r}, got {warning_rule_ids!r}"
                )
    if case.assertions.must_include_promoted_rule_id is not None:
        failed = assert_contains(
            values=failed_rule_ids,
            expected=case.assertions.must_include_promoted_rule_id,
            field="failed_rule_ids",
        )
        if failed is not None:
            failures.append(failed)
    if case.assertions.must_include_collector_action is not None:
        failed = assert_contains(
            values=invoked_actions,
            expected=case.assertions.must_include_collector_action,
            field="collector_actions",
        )
        if failed is not None:
            failures.append(failed)
    if case.assertions.knowledge_feature_count_gte is not None:
        failed = assert_gte(
            actual=knowledge_feature_count or 0,
            expected=case.assertions.knowledge_feature_count_gte,
            field="knowledge_feature_count",
        )
        if failed is not None:
            failures.append(failed)
    if case.assertions.knowledge_pricing_count_gte is not None:
        failed = assert_gte(
            actual=knowledge_pricing_count or 0,
            expected=case.assertions.knowledge_pricing_count_gte,
            field="knowledge_pricing_count",
        )
        if failed is not None:
            failures.append(failed)
    if case.assertions.knowledge_persona_count_gte is not None:
        failed = assert_gte(
            actual=knowledge_persona_count or 0,
            expected=case.assertions.knowledge_persona_count_gte,
            field="knowledge_persona_count",
        )
        if failed is not None:
            failures.append(failed)
    if case.assertions.knowledge_schema_coverage_rate_gte is not None:
        failed = assert_gte(
            actual=knowledge_schema_coverage_rate or 0.0,
            expected=case.assertions.knowledge_schema_coverage_rate_gte,
            field="knowledge_schema_coverage_rate",
        )
        if failed is not None:
            failures.append(failed)
    if case.assertions.supervisor_iterations_lt is not None:
        actual = supervisor_iterations if supervisor_iterations is not None else 10**9
        if actual >= case.assertions.supervisor_iterations_lt:
            failures.append(
                f"supervisor_iterations expected < {case.assertions.supervisor_iterations_lt}, got {actual}"
            )
    if case.assertions.analyze_count_lte is not None:
        actual = analyze_count if analyze_count is not None else 10**9
        if actual > case.assertions.analyze_count_lte:
            failures.append(
                f"analyze_count expected <= {case.assertions.analyze_count_lte}, got {actual}"
            )
    if case.assertions.report_section_count_gte is not None:
        failed = assert_gte(
            actual=report_section_count or 0,
            expected=case.assertions.report_section_count_gte,
            field="report_section_count",
        )
        if failed is not None:
            failures.append(failed)
    if case.assertions.report_section_ids_include:
        for expected in case.assertions.report_section_ids_include:
            failed = assert_contains(
                values=report_section_ids,
                expected=expected,
                field="report_section_ids",
            )
            if failed is not None:
                failures.append(failed)
    if case.assertions.report_degraded_required_sections_count_lte is not None:
        actual = len(report_degraded_required_sections)
        if actual > case.assertions.report_degraded_required_sections_count_lte:
            failures.append(
                "report_degraded_required_sections count expected <= "
                f"{case.assertions.report_degraded_required_sections_count_lte}, got {actual}: "
                f"{report_degraded_required_sections!r}"
            )
    if case.assertions.evidence_floor_count_lte is not None:
        actual = evidence_floor_count if evidence_floor_count is not None else 10**9
        if actual > case.assertions.evidence_floor_count_lte:
            failures.append(
                f"evidence_floor_count expected <= {case.assertions.evidence_floor_count_lte}, got {actual}"
            )
    if case.assertions.source_authority_distribution_includes:
        authority_keys = set((source_authority_distribution or {}).keys())
        for expected in case.assertions.source_authority_distribution_includes:
            if expected not in authority_keys:
                failures.append(
                    "source_authority_distribution expected to include "
                    f"{expected!r}, got {sorted(authority_keys)!r}"
                )
    if case.assertions.qa_warnings_count_gte is not None:
        failed = assert_gte(
            actual=qa_warnings_count or 0,
            expected=case.assertions.qa_warnings_count_gte,
            field="qa_warnings_count",
        )
        if failed is not None:
            failures.append(failed)

    return GoldenCaseResult(
        case_id=case.id,
        passed=not failures,
        run_id=run_id,
        failures=failures,
        qa_outcome=qa_outcome,
        qa_reject_to=qa_reject_to,
        qa_rejection_count=qa_rejection_count,
        promoted_blocked_rule_ids=promoted_blocked_rule_ids,
        warning_rule_ids=warning_rule_ids,
        coverage_rate=coverage_rate,
        knowledge_feature_count=knowledge_feature_count,
        knowledge_pricing_count=knowledge_pricing_count,
        knowledge_persona_count=knowledge_persona_count,
        knowledge_schema_coverage_rate=knowledge_schema_coverage_rate,
        llm_token_total=llm_token_total,
        run_wall_clock_seconds=run_wall_clock_seconds,
        created_at=datetime.now(timezone.utc).isoformat(),
        collector_actions=invoked_actions,
        supervisor_iterations=supervisor_iterations,
        analyze_count=analyze_count,
        report_section_count=report_section_count,
        source_authority_distribution=source_authority_distribution,
        qa_warnings_count=qa_warnings_count,
        report_section_ids=report_section_ids,
        report_degraded_required_sections=report_degraded_required_sections,
        evidence_floor_count=evidence_floor_count,
    )


def run_all_cases(*, cases_dir: Path, client: TestClient) -> list[GoldenCaseResult]:
    results: list[GoldenCaseResult] = []
    for case_path in sorted(cases_dir.glob("*.yaml")):
        case = _load_case(case_path)
        results.append(run_case(case=case, client=client))
    return results


def dump_markdown_report(*, results: list[GoldenCaseResult], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    passed_count = sum(1 for item in results if item.passed)
    lines = [
        "# Golden Eval Report",
        "",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- passed: {passed_count}/{len(results)}",
        "",
    ]
    for item in results:
        lines.append(f"## {item.case_id} {'PASS' if item.passed else 'FAIL'}")
        lines.append(f"- run_id: `{item.run_id}`")
        lines.append(f"- qa_outcome: `{item.qa_outcome}`")
        lines.append(f"- qa_reject_to: `{item.qa_reject_to}`")
        lines.append(f"- qa_rejection_count: {item.qa_rejection_count}")
        lines.append(f"- promoted_blocked_rule_ids: {item.promoted_blocked_rule_ids}")
        lines.append(f"- warning_rule_ids: {item.warning_rule_ids}")
        lines.append(f"- coverage_rate: {item.coverage_rate}")
        lines.append(f"- knowledge_feature_count: {item.knowledge_feature_count}")
        lines.append(f"- knowledge_pricing_count: {item.knowledge_pricing_count}")
        lines.append(f"- knowledge_persona_count: {item.knowledge_persona_count}")
        lines.append(f"- knowledge_schema_coverage_rate: {item.knowledge_schema_coverage_rate}")
        lines.append(f"- llm_token_total: {item.llm_token_total}")
        lines.append(f"- run_wall_clock_seconds: {item.run_wall_clock_seconds}")
        lines.append(f"- collector_actions: {item.collector_actions}")
        lines.append(f"- supervisor_iterations: {item.supervisor_iterations}")
        lines.append(f"- analyze_count: {item.analyze_count}")
        lines.append(f"- report_section_count: {item.report_section_count}")
        lines.append(f"- report_section_ids: {item.report_section_ids}")
        lines.append(
            f"- report_degraded_required_sections: {item.report_degraded_required_sections}"
        )
        lines.append(f"- evidence_floor_count: {item.evidence_floor_count}")
        lines.append(f"- source_authority_distribution: {item.source_authority_distribution}")
        lines.append(f"- qa_warnings_count: {item.qa_warnings_count}")
        if item.failures:
            lines.append("- failures:")
            for failure in item.failures:
                lines.append(f"  - {failure}")
        lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def to_dict_rows(results: list[GoldenCaseResult]) -> list[dict[str, object]]:
    return [asdict(item) for item in results]

