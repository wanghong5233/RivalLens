from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.config import settings
from service.llm.exceptions import LLMRequestError
from service.llm.routing import resolve_slot


@dataclass
class _DummyProvider:
    default_model: str


def test_resolve_slot_defaults_to_provider_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER_RESEARCH", "doubao")
    monkeypatch.setattr(settings, "LLM_MODEL_RESEARCH", None)

    provider_name, model_name = resolve_slot(
        slot="research",
        providers={"doubao": _DummyProvider(default_model="ep-default")},
    )

    assert provider_name == "doubao"
    assert model_name == "ep-default"


def test_resolve_slot_respects_override_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER_RESEARCH", "openai")
    monkeypatch.setattr(settings, "LLM_MODEL_RESEARCH", "gpt-4o")

    provider_name, model_name = resolve_slot(
        slot="research",
        providers={"openai": _DummyProvider(default_model="gpt-4o-mini")},
    )

    assert provider_name == "openai"
    assert model_name == "gpt-4o"


def test_resolve_slot_supports_qwen_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER_QA", "qwen")
    monkeypatch.setattr(settings, "LLM_MODEL_QA", None)

    provider_name, model_name = resolve_slot(
        slot="qa",
        providers={"qwen": _DummyProvider(default_model="qwen-plus")},
    )

    assert provider_name == "qwen"
    assert model_name == "qwen-plus"


def test_resolve_slot_rejects_unsupported_slot() -> None:
    with pytest.raises(LLMRequestError):
        resolve_slot(
            slot="invalid-slot",
            providers={"doubao": _DummyProvider(default_model="ep-default")},
        )


def test_resolve_slot_rejects_missing_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LLM_PROVIDER_QA", "openai")
    monkeypatch.setattr(settings, "LLM_MODEL_QA", None)

    with pytest.raises(LLMRequestError):
        resolve_slot(
            slot="qa",
            providers={"doubao": _DummyProvider(default_model="ep-default")},
        )
