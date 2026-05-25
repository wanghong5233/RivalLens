from __future__ import annotations

from pathlib import Path

from core.config import settings
from schemas.supervisor import FocusDimension
from service.collector.base import BaseChannel, CollectorObservation, ToolObservationResult
from service.collector.errors import ChannelError

from agents.tools.pack_lookup import ToolError, pack_lookup


class OfflineSnapshotChannel(BaseChannel):
    name = "lookup_offline_snapshot"

    @staticmethod
    def _candidate_paths(
        *,
        snapshot_root: Path,
        industry_pack_id: str,
        competitor_id: str,
        dimension: FocusDimension,
    ) -> list[Path]:
        return [
            snapshot_root / industry_pack_id / competitor_id / f"{dimension}.txt",
            snapshot_root / industry_pack_id / competitor_id / f"{dimension}.md",
            snapshot_root / industry_pack_id / competitor_id / f"{dimension}.html",
            snapshot_root / competitor_id / f"{dimension}.txt",
            snapshot_root / competitor_id / f"{dimension}.md",
            snapshot_root / competitor_id / f"{dimension}.html",
        ]

    @staticmethod
    def _load_snapshot_text(paths: list[Path]) -> tuple[str, Path] | None:
        for path in paths:
            if path.exists() and path.is_file():
                return path.read_text(encoding="utf-8"), path
        return None

    async def invoke(self, **kwargs: object) -> CollectorObservation:
        industry_pack_id = kwargs.get("industry_pack_id")
        competitor_id = kwargs.get("competitor_id")
        dimension = kwargs.get("dimension")
        if not isinstance(industry_pack_id, str) or not isinstance(competitor_id, str):
            raise ChannelError("lookup_offline_snapshot requires industry_pack_id and competitor_id.")
        if not isinstance(dimension, str):
            raise ChannelError("lookup_offline_snapshot requires string dimension.")
        focus_dimension: FocusDimension = dimension

        snapshot_root = Path(settings.COLLECTOR_OFFLINE_SNAPSHOT_DIR)
        snapshot_file = self._load_snapshot_text(
            self._candidate_paths(
                snapshot_root=snapshot_root,
                industry_pack_id=industry_pack_id,
                competitor_id=competitor_id,
                dimension=focus_dimension,
            )
        )
        snippets: list = []
        if snapshot_file is not None:
            raw_text, path = snapshot_file
            snippets.append(
                self._build_snippet(
                    raw_text=raw_text,
                    source_type="offline_snapshot",
                    source_url=f"offline://{path.as_posix()}",
                    source_title=f"offline snapshot {competitor_id}/{focus_dimension}",
                    metadata={
                        "pack_id": industry_pack_id,
                        "dimension": focus_dimension,
                        "competitor_id": competitor_id,
                        "source": "file_snapshot",
                    },
                )
            )
        else:
            try:
                fallback = pack_lookup(
                    industry_pack_id=industry_pack_id,
                    competitor_id=competitor_id,
                    dimension=focus_dimension,
                )
            except ToolError as exc:
                raise ChannelError(str(exc)) from exc
            for snippet_row in fallback.result.get("snippets", []):
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
                        source_type="offline_snapshot",
                        source_url=source_url if isinstance(source_url, str) else None,
                        source_title=source_title if isinstance(source_title, str) else None,
                        metadata={
                            "pack_id": industry_pack_id,
                            "dimension": focus_dimension,
                            "competitor_id": competitor_id,
                            "source": "industry_pack_fallback",
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
                    "from_file_snapshot": snapshot_file is not None,
                },
            ),
        )
