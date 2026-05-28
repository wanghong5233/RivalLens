from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from service.skill_promotion.writers import (
    PromotionWriteError,
    append_qa_rule_entry,
    append_source_routing_entry,
    write_prompt_template_entry,
)


def _read_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_append_qa_rule_entry_creates_then_appends(tmp_path: Path) -> None:
    path = tmp_path / "qa_rules_promoted.yaml"
    action_1 = append_qa_rule_entry(
        path=path,
        entry={"rule_id": "rule_1", "rule_yaml": "id: rule_1"},
    )
    action_2 = append_qa_rule_entry(
        path=path,
        entry={"rule_id": "rule_2", "rule_yaml": "id: rule_2"},
    )

    assert action_1 == "created"
    assert action_2 == "appended"
    loaded = _read_yaml(path)
    assert isinstance(loaded, list)
    assert len(loaded) == 2
    assert loaded[0]["rule_id"] == "rule_1"
    assert loaded[1]["rule_id"] == "rule_2"


def test_write_prompt_template_entry_is_atomic(tmp_path: Path) -> None:
    path = tmp_path / "prompt_templates" / "template__skill_1.yaml"
    action = write_prompt_template_entry(
        path=path,
        entry={"template_name": "template", "template_body": "hello"},
    )
    assert action == "created"
    loaded = _read_yaml(path)
    assert isinstance(loaded, dict)
    assert loaded["template_name"] == "template"


def test_append_source_routing_entry_handles_invalid_existing_yaml(tmp_path: Path) -> None:
    path = tmp_path / "source_routing.yaml"
    path.write_text("invalid: root", encoding="utf-8")
    with pytest.raises(PromotionWriteError):
        append_source_routing_entry(
            path=path,
            entry={"source_type": "docs"},
        )
