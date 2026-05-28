from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml


class PromotionWriteError(RuntimeError):
    pass


def _safe_load_list(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PromotionWriteError(f"Invalid YAML in {path}") from exc
    if loaded is None:
        return []
    if not isinstance(loaded, list):
        raise PromotionWriteError(f"Expected list YAML root in {path}")
    normalized: list[dict[str, object]] = []
    for index, item in enumerate(loaded):
        if not isinstance(item, dict):
            raise PromotionWriteError(
                f"Entry at index={index} in {path} must be an object."
            )
        normalized.append(item)
    return normalized


def _atomic_dump_yaml(*, path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as tmp_file:
            yaml.safe_dump(
                data,
                tmp_file,
                sort_keys=False,
                allow_unicode=True,
            )
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            tmp_path = tmp_file.name
        os.replace(tmp_path, path)
    except OSError as exc:
        raise PromotionWriteError(f"Failed to atomically write {path}") from exc
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def append_qa_rule_entry(*, path: Path, entry: dict[str, object]) -> str:
    existing = _safe_load_list(path)
    action = "appended" if path.exists() else "created"
    existing.append(entry)
    _atomic_dump_yaml(path=path, data=existing)
    return action


def append_source_routing_entry(*, path: Path, entry: dict[str, object]) -> str:
    existing = _safe_load_list(path)
    action = "appended" if path.exists() else "created"
    existing.append(entry)
    _atomic_dump_yaml(path=path, data=existing)
    return action


def write_prompt_template_entry(*, path: Path, entry: dict[str, object]) -> str:
    action = "appended" if path.exists() else "created"
    _atomic_dump_yaml(path=path, data=entry)
    return action
