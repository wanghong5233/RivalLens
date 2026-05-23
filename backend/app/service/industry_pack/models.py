from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.supervisor import FocusDimension


class DimensionSnippet(BaseModel):
    quote: str
    source_url: str
    source_title: str
    desensitized: bool


class CompetitorSnapshot(BaseModel):
    id: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    official_url: str
    category: str
    snapshots: dict[FocusDimension, list[DimensionSnippet]] = Field(default_factory=dict)


class PackMetadata(BaseModel):
    id: str
    name: str
    version: str
    default_focus_dimensions: list[FocusDimension] = Field(default_factory=list)
    description: str
    competitor_files: list[str] = Field(default_factory=list)


class IndustryPack(BaseModel):
    id: str
    name: str
    version: str
    default_focus_dimensions: list[FocusDimension] = Field(default_factory=list)
    description: str
    competitors: dict[str, CompetitorSnapshot] = Field(default_factory=dict)
