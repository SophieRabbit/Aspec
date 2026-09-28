from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


DATA_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "local_dependency_keywords.json"
)


@lru_cache(maxsize=1)
def _load_keyword_groups() -> dict[str, dict[str, Any]]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return {
        str(category): value
        for category, value in payload.items()
        if isinstance(value, dict)
    }


def detect_local_dependency(query: str) -> dict[str, Any] | None:
    """Return matched local-regulation categories for a user query."""
    if not query.strip():
        return None

    matches: list[dict[str, Any]] = []
    for category, config in _load_keyword_groups().items():
        keywords = [
            str(keyword)
            for keyword in config.get("keywords", [])
            if str(keyword).strip()
        ]
        matched_keywords = [
            keyword
            for keyword in keywords
            if keyword in query
        ]
        if (
            category == "消防地方细则"
            and "防火分区" in matched_keywords
            and "面积" in query
            and len(matched_keywords) == 1
        ):
            matched_keywords = []
        if not matched_keywords:
            continue
        matches.append(
            {
                "category": category,
                "prompt": str(config.get("prompt", "")).strip(),
                "matched_keywords": matched_keywords,
            }
        )

    if not matches:
        return None

    prompts = list(
        dict.fromkeys(
            match["prompt"]
            for match in matches
            if match["prompt"]
        )
    )
    return {
        "category": matches[0]["category"] if len(matches) == 1 else "",
        "categories": [match["category"] for match in matches],
        "prompt": " ".join(prompts),
        "prompts": prompts,
        "matched_keywords": {
            match["category"]: match["matched_keywords"]
            for match in matches
        },
    }
