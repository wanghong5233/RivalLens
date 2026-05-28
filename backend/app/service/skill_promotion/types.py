from __future__ import annotations

from typing import Literal, TypedDict


class PromotedArtifact(TypedDict):
    path: str
    action: Literal["created", "appended"]
    entry_id: str
