from __future__ import annotations

from service.collector.base import BaseChannel, CollectorObservation, SourceType, ToolObservationResult
from service.collector.errors import ChannelError
from service.llm.client import get_llm_client
from schemas.contracts import validate_source_type

from agents.tools.parse_page import infer_source_type

EXTRACT_STRUCTURED_SYSTEM_PROMPT = """You are a data extraction helper for RivalLens.
Return STRICT JSON:
{
  "quote": str,
  "source_title": str | null
}

Rules:
- Keep quote factual and concise.
- Do not invent facts not present in input text.
- Return JSON object only.
"""


class ExtractStructuredChannel(BaseChannel):
    name = "extract_structured"

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        text = kwargs.get("text")
        source_url = kwargs.get("source_url")
        source_title = kwargs.get("source_title")
        source_type_raw = kwargs.get("source_type")
        if not isinstance(text, str) or not text.strip():
            raise ChannelError("extract_structured requires non-empty text.")
        if source_url is not None and not isinstance(source_url, str):
            raise ChannelError("extract_structured source_url must be string when provided.")
        if source_title is not None and not isinstance(source_title, str):
            raise ChannelError("extract_structured source_title must be string when provided.")

        source_type: SourceType
        if isinstance(source_type_raw, str):
            try:
                source_type = validate_source_type(source_type_raw)
            except ValueError:
                source_type = "article"
        else:
            source_type = infer_source_type(source_url=source_url, official_hosts=None)

        prompt_text = text[:4000]
        llm_response = await get_llm_client().complete_json(
            model_slot="research",
            system_prompt=EXTRACT_STRUCTURED_SYSTEM_PROMPT,
            user_prompt=f"Extract from text:\n{prompt_text}",
            fallback_system_prompt=EXTRACT_STRUCTURED_SYSTEM_PROMPT,
            fallback_user_prompt=f"Return minimal JSON quote for text:\n{prompt_text[:1200]}",
        )
        quote_raw = llm_response.content.get("quote")
        title_raw = llm_response.content.get("source_title")
        quote = quote_raw.strip() if isinstance(quote_raw, str) and quote_raw.strip() else text[:1200]
        normalized_title = (
            title_raw.strip()
            if isinstance(title_raw, str) and title_raw.strip()
            else (source_title if isinstance(source_title, str) else "structured_extract")
        )
        snippet = self._build_snippet(
            raw_text=quote,
            source_type=source_type,
            source_url=source_url if isinstance(source_url, str) else None,
            source_title=normalized_title,
            metadata={
                "source": "extract_structured",
                "llm_error": llm_response.error or "",
            },
        )
        return CollectorObservation(
            channel=self.name,
            args={
                "source_url": source_url,
                "source_title": source_title,
                "source_type": source_type_raw,
            },
            result=ToolObservationResult(
                snippets=[snippet],
                metadata={"source_type": source_type},
            ),
        )
