from __future__ import annotations

from typing import Mapping

from core.config import settings
from service.llm.exceptions import LLMRequestError
from service.llm.providers import LLMProvider

SLOT_NAMES: tuple[str, ...] = (
    "research",
    "summarization",
    "compression",
    "qa",
    "writer",
)


def _slot_provider(slot: str) -> str:
    provider_raw = getattr(settings, f"LLM_PROVIDER_{slot.upper()}", None)
    if not isinstance(provider_raw, str):
        raise LLMRequestError(f"Provider for model_slot={slot} is not configured.")
    provider = provider_raw.strip().lower()
    if not provider:
        raise LLMRequestError(f"Provider for model_slot={slot} is empty.")
    return provider


def _slot_model_override(slot: str) -> str | None:
    model_raw = getattr(settings, f"LLM_MODEL_{slot.upper()}", None)
    if model_raw is None:
        return None
    if not isinstance(model_raw, str):
        raise LLMRequestError(f"Model override for model_slot={slot} must be a string.")

    model = model_raw.strip()
    return model or None


def resolve_slot(*, slot: str, providers: Mapping[str, LLMProvider]) -> tuple[str, str]:
    if slot not in SLOT_NAMES:
        raise LLMRequestError(
            f"Unsupported model_slot={slot}. Expected one of: {', '.join(SLOT_NAMES)}."
        )

    provider_name = _slot_provider(slot)
    provider = providers.get(provider_name)
    if provider is None:
        raise LLMRequestError(
            f"Provider `{provider_name}` for model_slot={slot} is not initialized."
        )

    model_name = _slot_model_override(slot) or provider.default_model
    if not model_name:
        raise LLMRequestError(f"Model for model_slot={slot} is empty.")
    return provider_name, model_name
