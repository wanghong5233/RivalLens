from __future__ import annotations

from pathlib import Path

from service.industry_pack.models import IndustryPack


class IndustryPackNotFound(RuntimeError):
    pass


class IndustryPackRegistry:
    def __init__(self) -> None:
        self._packs: dict[str, IndustryPack] = {}

    def load_all(self, root: Path) -> None:
        if not root.exists():
            raise IndustryPackNotFound(f"Industry pack root does not exist: {root}")

        from service.industry_pack.loader import load_pack

        self._packs.clear()
        for pack_yaml in sorted(root.glob("*/pack.yaml")):
            pack = load_pack(pack_yaml.parent)
            self._packs[pack.id] = pack

        if not self._packs:
            raise IndustryPackNotFound(f"No industry pack found under: {root}")

    def has(self, pack_id: str) -> bool:
        return pack_id in self._packs

    def get(self, pack_id: str) -> IndustryPack:
        pack = self._packs.get(pack_id)
        if pack is None:
            raise IndustryPackNotFound(f"Industry pack not found: {pack_id}")
        return pack

    def list_ids(self) -> list[str]:
        return sorted(self._packs.keys())


_industry_pack_registry = IndustryPackRegistry()


def get_industry_pack_registry() -> IndustryPackRegistry:
    return _industry_pack_registry
