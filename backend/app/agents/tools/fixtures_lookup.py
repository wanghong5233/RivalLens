from __future__ import annotations

from schemas.supervisor import FocusDimension
from service.collector.base import BaseChannel, CollectorObservation, ToolObservationResult
from service.collector.errors import ChannelError

from agents.tools.pack_lookup import ToolError, pack_lookup


class FixturesLookupChannel(BaseChannel):
    name = "fixtures_lookup"

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        industry_pack_id = kwargs.get("industry_pack_id")
        competitor_id = kwargs.get("competitor_id")
        dimension = kwargs.get("dimension")
        if not isinstance(industry_pack_id, str) or not isinstance(competitor_id, str):
            raise ChannelError("fixtures_lookup requires industry_pack_id and competitor_id.")
        if not isinstance(dimension, str):
            raise ChannelError("fixtures_lookup requires string dimension.")
        focus_dimension: FocusDimension = dimension

        try:
            snapshot = pack_lookup(
                industry_pack_id=industry_pack_id,
                competitor_id=competitor_id,
                dimension=focus_dimension,
            )
        except ToolError as exc:
            raise ChannelError(str(exc)) from exc

        snippets: list = []
        for snippet_row in snapshot.result.get("snippets", []):
            if not isinstance(snippet_row, dict):
                continue
            quote = snippet_row.get("quote")
            source_url = snippet_row.get("source_url")
            source_title = snippet_row.get("source_title")
            if not isinstance(quote, str):
                continue
            snippets.append(
                self._build_snippet(
                    raw_text=quote,
                    source_type="local_note",
                    source_url=source_url if isinstance(source_url, str) else None,
                    source_title=source_title if isinstance(source_title, str) else None,
                    metadata={
                        "dimension": focus_dimension,
                        "pack_id": industry_pack_id,
                        "competitor_id": competitor_id,
                        "source": "industry_pack_snapshot",
                    },
                )
            )

        return CollectorObservation(
            channel=self.name,
            args={
                "industry_pack_id": industry_pack_id,
                "competitor_id": competitor_id,
                "dimension": focus_dimension,
            },
            result=ToolObservationResult(
                snippets=snippets,
                metadata={
                    "competitor_id": competitor_id,
                    "dimension": focus_dimension,
                },
            ),
        )
