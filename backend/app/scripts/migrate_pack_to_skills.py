from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

import yaml


@dataclass(frozen=True)
class MigrationContext:
    repo_root: Path
    pack_root: Path
    skills_root: Path
    fixtures_root: Path


RULE_ID_PATTERN = re.compile(r"^\s*id:\s*(?P<rule_id>[a-z0-9_:-]+)\s*$")


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Required file does not exist: {path}")
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _dump_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        yaml.safe_dump(payload, file, allow_unicode=True, sort_keys=False)


def _rule_id_from_yaml(rule_yaml: str) -> str | None:
    for line in rule_yaml.splitlines():
        match = RULE_ID_PATTERN.match(line)
        if match is not None:
            return match.group("rule_id")
    return None


def _render_skill_markdown(*, frontmatter: dict[str, Any], body: str) -> str:
    frontmatter_yaml = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    normalized_body = body.strip()
    return f"---\n{frontmatter_yaml}\n---\n\n{normalized_body}\n"


def _migrate_promoted_rules(ctx: MigrationContext) -> tuple[int, int]:
    qa_rules_path = ctx.pack_root / "skills" / "qa_rules_promoted.yaml"
    loaded = _read_yaml(qa_rules_path)
    entries = loaded if isinstance(loaded, list) else []

    migrated_count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rule_yaml_raw = entry.get("rule_yaml")
        if not isinstance(rule_yaml_raw, str) or not rule_yaml_raw.strip():
            continue

        rule_id_raw = entry.get("rule_id")
        rule_id = rule_id_raw if isinstance(rule_id_raw, str) and rule_id_raw.strip() else None
        if rule_id is None:
            rule_id = _rule_id_from_yaml(rule_yaml_raw)
        if rule_id is None:
            rule_id = f"migrated_rule_{migrated_count + 1:03d}"

        candidate_id_raw = entry.get("candidate_id")
        candidate_id = candidate_id_raw if isinstance(candidate_id_raw, str) else ""
        approved_by_raw = entry.get("approved_by")
        approved_by = approved_by_raw if isinstance(approved_by_raw, str) else ""
        approved_at_raw = entry.get("approved_at")
        approved_at = approved_at_raw if isinstance(approved_at_raw, str) else ""
        supporting_runs_raw = entry.get("supporting_run_ids")
        supporting_run_ids = (
            [item for item in supporting_runs_raw if isinstance(item, str)]
            if isinstance(supporting_runs_raw, list)
            else []
        )

        frontmatter = {
            "name": rule_id,
            "description": "Promoted QA rule migrated from legacy industry pack.",
            "version": "1.0.0",
            "tags": ["ai_coding_tools", "migrated"],
            "applies_to": "qa_rule",
            "source": {
                "pack_id": "ai_coding_tools",
                "candidate_id": candidate_id,
                "approved_by": approved_by,
                "approved_at": approved_at,
                "supporting_run_ids": supporting_run_ids,
            },
        }
        body = (
            "## Rule DSL\n\n"
            "```yaml\n"
            f"{rule_yaml_raw.strip()}\n"
            "```\n"
        )
        output_path = ctx.skills_root / "qa_rule" / rule_id / "SKILL.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            _render_skill_markdown(frontmatter=frontmatter, body=body),
            encoding="utf-8",
            newline="\n",
        )
        migrated_count += 1

    return migrated_count, len(entries)


def _migrate_competitor_seed(ctx: MigrationContext) -> int:
    pack_meta_raw = _read_yaml(ctx.pack_root / "pack.yaml")
    if not isinstance(pack_meta_raw, dict):
        raise ValueError("pack.yaml root must be an object.")

    competitor_files_raw = pack_meta_raw.get("competitor_files", [])
    competitor_files = (
        [item for item in competitor_files_raw if isinstance(item, str)]
        if isinstance(competitor_files_raw, list)
        else []
    )

    competitors_seed: list[dict[str, Any]] = []
    for relative_path in competitor_files:
        competitor_raw = _read_yaml(ctx.pack_root / relative_path)
        if not isinstance(competitor_raw, dict):
            continue
        aliases_raw = competitor_raw.get("aliases", [])
        aliases = [item for item in aliases_raw if isinstance(item, str)] if isinstance(aliases_raw, list) else []
        competitors_seed.append(
            {
                "id": competitor_raw.get("id"),
                "display_name": competitor_raw.get("display_name"),
                "aliases": aliases,
                "official_url": competitor_raw.get("official_url"),
                "category": competitor_raw.get("category"),
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_pack_id": "ai_coding_tools",
        "competitors": competitors_seed,
    }
    _dump_yaml(ctx.fixtures_root / "competitors_seed.yaml", payload)
    return len(competitors_seed)


def run() -> int:
    script_path = Path(__file__).resolve()
    ctx = MigrationContext(
        repo_root=script_path.parents[3],
        pack_root=script_path.parents[3] / "industry_packs" / "ai_coding_tools",
        skills_root=script_path.parents[2] / "skills",
        fixtures_root=script_path.parents[3] / "demo_fixtures",
    )
    migrated_rules, source_entries = _migrate_promoted_rules(ctx)
    competitors_count = _migrate_competitor_seed(ctx)
    print(
        (
            "pack_to_skills_migration_complete "
            f"promoted_rules_migrated={migrated_rules}/{source_entries} "
            f"competitors_seed_count={competitors_count} "
            f"skills_root={ctx.skills_root} fixtures_root={ctx.fixtures_root}"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
