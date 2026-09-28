from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "building_types.json"


@dataclass(frozen=True)
class BuildingTypeMatch:
    name: str
    matched_alias: str
    aliases: tuple[str, ...]
    primary_standards: tuple[str, ...]


@lru_cache(maxsize=1)
def _load_building_types() -> tuple[dict[str, object], ...]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return tuple(item for item in payload if isinstance(item, dict))


def get_building_type(name: str) -> BuildingTypeMatch | None:
    candidate = str(name).strip()
    if not candidate:
        return None
    for item in _load_building_types():
        aliases = tuple(
            str(alias)
            for alias in item.get("aliases", [])
            if str(alias).strip()
        )
        canonical = str(item.get("name", ""))
        if candidate not in (canonical, *aliases):
            continue
        return BuildingTypeMatch(
            name=canonical,
            matched_alias=candidate,
            aliases=aliases,
            primary_standards=tuple(
                str(code)
                for code in item.get("primary_standards", [])
                if str(code).strip()
            ),
        )
    return None


def detect_building_types(query: str) -> list[BuildingTypeMatch]:
    matches: list[BuildingTypeMatch] = []
    for item in _load_building_types():
        aliases = [
            str(alias)
            for alias in item.get("aliases", [])
            if str(alias).strip()
        ]
        matched = [alias for alias in aliases if alias in query]
        if not matched:
            continue
        matched_alias = max(matched, key=len)
        standards = tuple(
            str(code)
            for code in item.get("primary_standards", [])
            if str(code).strip()
        )
        matches.append(
            BuildingTypeMatch(
                name=str(item.get("name", "")),
                matched_alias=matched_alias,
                aliases=tuple(aliases),
                primary_standards=standards,
            )
        )
    return sorted(matches, key=lambda item: len(item.matched_alias), reverse=True)
