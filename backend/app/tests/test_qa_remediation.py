from __future__ import annotations

from service.qa.remediation import RULE_REMEDIATION_HINTS, build_remediation_hints
from service.qa.rules import rule_writer_must_cite_evidence


def test_build_remediation_hints_uses_rule_templates() -> None:
    failed = [rule_writer_must_cite_evidence(content_json={"sections": []}, allowed_evidence_ids={"ev_1"})]
    hints = build_remediation_hints(failed)
    assert failed[0].rule_id in hints
    assert hints[failed[0].rule_id] == RULE_REMEDIATION_HINTS[failed[0].rule_id]
