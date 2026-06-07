from __future__ import annotations

from service.collector.base import BaseChannel, CollectorObservation, ToolObservationResult
from service.collector.errors import ChannelError
from schemas.agent_outputs import ParseImagesOutput
from service.llm import PARSE_IMAGES_SYSTEM_PROMPT, build_parse_images_repair_user_prompt
from service.llm.harness import complete_structured

from agents.tools.parse_page import infer_source_type


def _normalize_image_urls(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
    return urls


class ParseImagesChannel(BaseChannel):
    name = "parse_images"

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        image_urls_raw = kwargs.get("image_urls")
        source_url = kwargs.get("source_url")
        source_title = kwargs.get("source_title")
        context_raw = kwargs.get("context")

        image_urls = _normalize_image_urls(image_urls_raw)
        if not image_urls:
            raise ChannelError("parse_images requires non-empty image_urls list.")

        from core.config import settings

        max_images = max(1, settings.PARSE_IMAGES_MAX_PER_PAGE)
        selected_urls = image_urls[:max_images]
        context = (
            context_raw.strip()
            if isinstance(context_raw, str) and context_raw.strip()
            else (
                source_url.strip()
                if isinstance(source_url, str) and source_url.strip()
                else "competitor page"
            )
        )
        user_prompt: list[dict[str, object]] = [
            {
                "type": "text",
                "text": (
                    f"Extract visible product information from these images (pricing, "
                    f"feature matrix, architecture). Source page: {context}"
                ),
            },
            *[
                {"type": "image_url", "image_url": {"url": url}}
                for url in selected_urls
            ],
        ]
        harness_result = await complete_structured(
            model_slot="vision",
            system_prompt=PARSE_IMAGES_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_model=ParseImagesOutput,
            parser=ParseImagesOutput.parse_llm_content,
            fallback_system_prompt=PARSE_IMAGES_SYSTEM_PROMPT,
            fallback_user_prompt=(
                f"Describe product information visible in images from {context}. "
                'Return JSON: {{"description":"..."}}'
            ),
            repair_user_prompt_builder=lambda errors: build_parse_images_repair_user_prompt(
                validation_errors=errors,
                context=context,
            ),
            log_event="parse_images.harness.finish",
        )
        if harness_result.value is None:
            raise ChannelError(
                harness_result.schema_error or "parse_images vision model returned invalid output."
            )
        description = harness_result.value.description.strip()
        if not description:
            raise ChannelError("parse_images vision model returned empty description.")

        source_type = infer_source_type(
            source_url=source_url if isinstance(source_url, str) else None,
            official_hosts=None,
        )
        snippet = self._build_snippet(
            raw_text=description,
            source_type=source_type,
            source_url=source_url if isinstance(source_url, str) else None,
            source_title=(
                source_title if isinstance(source_title, str) else "parsed_images"
            ),
            metadata={
                "source": "parse_images",
                "image_count": len(selected_urls),
            },
        )
        return CollectorObservation(
            channel=self.name,
            args={
                "image_urls": selected_urls,
                "source_url": source_url,
                "source_title": source_title,
                "context": context,
            },
            result=ToolObservationResult(
                snippets=[snippet],
                metadata={"image_count": len(selected_urls)},
            ),
        )
