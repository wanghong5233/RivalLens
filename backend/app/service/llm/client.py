from __future__ import annotations

import asyncio
from typing import Any

from core.config import settings


class LLMClient:
    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(settings.LLM_GLOBAL_CONCURRENCY)

    async def complete_json(self, prompt: str, model_slot: str = "research") -> dict[str, Any]:
        # Walking skeleton returns deterministic output so callers can integrate
        # against a stable shape before model provider wiring is added.
        async with self._semaphore:
            return {
                "model_slot": model_slot,
                "provider": "doubao_stub",
                "prompt_preview": prompt[:128],
                "content": {},
            }


llm_client = LLMClient()
