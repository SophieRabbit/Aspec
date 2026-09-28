from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "building_components.json"


@dataclass(frozen=True)
class BuildingComponentMatch:
    name: str
    matched_alias: str
    aliases: tuple[str, ...]


@lru_cache(maxsize=1)
def _load_components() -> dict[str, tuple[str, ...]]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return {
        str(name): tuple(
            str(alias)
            for alias in aliases
            if str(alias).strip()
        )
        for name, aliases in payload.items()
    }


def detect_building_component(query: str) -> BuildingComponentMatch | None:
    matches: list[tuple[tuple[int, int, int], str, str]] = []
    for index, (name, aliases) in enumerate(_load_components().items()):
        for alias in aliases:
            if alias not in query:
                continue
            score = (
                int(alias == name),
                len(alias),
                -index,
            )
            matches.append((score, name, alias))
    if not matches:
        return None
    _, name, matched_alias = max(matches, key=lambda item: item[0])
    return BuildingComponentMatch(
        name=name,
        matched_alias=matched_alias,
        aliases=_load_components()[name],
    )
