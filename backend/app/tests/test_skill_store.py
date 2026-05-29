from __future__ import annotations

from pathlib import Path

from service.skill_store import SkillStore


def _write_skill(
    *,
    base_dir: Path,
    applies_to: str,
    skill_name: str,
    body_markdown: str,
) -> Path:
    skill_dir = base_dir / applies_to / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(
        (
            "---\n"
            f"name: {skill_name}\n"
            "description: test skill\n"
            "version: 1.0.0\n"
            "tags:\n"
            "- generic\n"
            f"applies_to: {applies_to}\n"
            "---\n\n"
            f"{body_markdown}\n"
        ),
        encoding="utf-8",
    )
    return path


def test_skill_store_scan_and_query(tmp_path: Path) -> None:
    _write_skill(
        base_dir=tmp_path,
        applies_to="qa_rule",
        skill_name="rule_pricing_recent",
        body_markdown="## Rule\n\n```yaml\nid: rule_pricing_recent\n```",
    )
    _write_skill(
        base_dir=tmp_path,
        applies_to="prompt_template",
        skill_name="writer_summary_template",
        body_markdown="## Template\n\n```text\nsummary body\n```",
    )
    supporting_file = tmp_path / "qa_rule" / "rule_pricing_recent" / "examples.md"
    supporting_file.write_text("# examples", encoding="utf-8")

    store = SkillStore(tmp_path)
    metadata_map = store.scan()

    assert sorted(metadata_map.keys()) == ["rule_pricing_recent", "writer_summary_template"]
    assert store.list_by_applies_to("qa_rule") == ["rule_pricing_recent"]
    assert store.list_by_tag("generic") == ["rule_pricing_recent", "writer_summary_template"]
    assert store.list_supporting_files("rule_pricing_recent") == ["examples.md"]


def test_skill_store_read_supporting_file(tmp_path: Path) -> None:
    _write_skill(
        base_dir=tmp_path,
        applies_to="source_routing",
        skill_name="prefer_docs_source",
        body_markdown="## Routing\n\n```yaml\nsource_type: docs\n```",
    )
    note_path = tmp_path / "source_routing" / "prefer_docs_source" / "note.txt"
    note_path.write_text("hello", encoding="utf-8")

    store = SkillStore(tmp_path)
    store.scan()

    assert store.read_supporting_file("prefer_docs_source", "note.txt") == "hello"
