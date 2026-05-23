from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from service.industry_pack.registry import get_industry_pack_registry

router = APIRouter()


class IndustryPackCompetitorResponse(BaseModel):
    id: str
    display_name: str


class IndustryPackListItemResponse(BaseModel):
    id: str
    display_name: str
    description: str
    competitors: list[IndustryPackCompetitorResponse]
    research_dimensions: list[str]


@router.get("/api/industry-packs", response_model=list[IndustryPackListItemResponse])
async def list_industry_packs() -> list[IndustryPackListItemResponse]:
    registry = get_industry_pack_registry()
    responses: list[IndustryPackListItemResponse] = []
    for pack_id in registry.list_ids():
        pack = registry.get(pack_id)
        competitors = [
            IndustryPackCompetitorResponse(id=competitor.id, display_name=competitor.display_name)
            for competitor in sorted(pack.competitors.values(), key=lambda item: item.display_name)
        ]
        responses.append(
            IndustryPackListItemResponse(
                id=pack.id,
                display_name=pack.name,
                description=pack.description,
                competitors=competitors,
                research_dimensions=[str(item) for item in pack.default_focus_dimensions],
            )
        )
    return responses
