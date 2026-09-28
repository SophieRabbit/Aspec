from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .building_component_matcher import detect_building_component
from .llm_type_matcher import detect_building_type_with_fallback
from .region_matcher import detect_region, local_standard_titles
from .synonym_expander import SynonymGroupMatch, expand_query_details


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "query_attributes.json"
COMPONENT_ATTRIBUTES = {"尺寸", "宽度", "高度", "坡度"}
FUNCTION_TERMS = ("疏散", "防火", "消防", "无障碍")


@dataclass(frozen=True)
class CompoundIntent:
    query: str
    region: str = ""
    building_type: str = ""
    component: str = ""
    attribute: str = ""
    topic: str = ""
    region_scope: dict[str, str] = field(default_factory=dict)
    region_standards: tuple[str, ...] = ()
    primary_standards: tuple[str, ...] = ()
    building_aliases: tuple[str, ...] = ()
    component_keywords: tuple[str, ...] = ()
    attribute_keywords: tuple[str, ...] = ()
    concepts: tuple[SynonymGroupMatch, ...] = ()
    concept_group: str = ""
    concept_label: str = ""
    concept_synonyms: tuple[str, ...] = ()
    related_standards: tuple[str, ...] = ()
    related_attributes: tuple[str, ...] = ()
    building_type_source: str = "fallback"
    is_compound: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "region": self.region,
            "building_type": self.building_type,
            "component": self.component,
            "attribute": self.attribute,
            "topic": self.topic,
            "concept_group": self.concept_group,
            "concept_label": self.concept_label,
            "concept_synonyms": list(self.concept_synonyms),
            "building_type_source": self.building_type_source,
            "is_compound": self.is_compound,
        }


@lru_cache(maxsize=1)
def _load_attributes() -> dict[str, tuple[str, ...]]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return {
        str(attribute): tuple(
            str(keyword)
            for keyword in keywords
            if str(keyword).strip()
        )
        for attribute, keywords in payload.items()
    }


def _concept_attribute(
    query: str,
    concepts: tuple[SynonymGroupMatch, ...],
) -> tuple[str, tuple[str, ...]]:
    if not concepts:
        return "", ()
    request_terms = ("要求", "规定", "标准", "怎么做", "如何")
    if not any(term in query for term in request_terms):
        return "", ()

    request_positions = [
        query.find(term)
        for term in request_terms
        if query.find(term) >= 0
    ]

    def matched_distance(match: SynonymGroupMatch) -> int:
        if not request_positions:
            return len(query)
        positions = [
            query.find(term)
            for term in match.matched_terms
            if query.find(term) >= 0
        ]
        return min(
            abs(position - request_position)
            for position in positions
            for request_position in request_positions
        )

    matches = min(concepts, key=matched_distance)
    explicit = [
        attribute
        for attribute in matches.related_attributes
        if attribute in query
    ]
    implied = [
        attribute
        for attribute in matches.related_attributes
        if any(attribute in synonym for synonym in matches.synonyms)
    ]
    attribute = next(iter(explicit or implied), "")
    if not attribute:
        return matches.canonical, (matches.canonical,)
    suffix = "要求" if "要求" in query else ""
    return f"{attribute}{suffix}", (attribute, suffix) if suffix else (attribute,)


def _primary_concept(
    query: str,
    concepts: tuple[SynonymGroupMatch, ...],
) -> SynonymGroupMatch | None:
    if not concepts:
        return None
    request_positions = [
        query.find(term)
        for term in ("要求", "规定", "标准", "怎么做", "如何")
        if query.find(term) >= 0
    ]
    if not request_positions:
        return concepts[0]

    def distance(match: SynonymGroupMatch) -> int:
        positions = [
            query.find(term)
            for term in match.matched_terms
            if query.find(term) >= 0
        ]
        return min(
            abs(position - request_position)
            for position in positions
            for request_position in request_positions
        )

    return min(concepts, key=distance)


def detect_compound_intent(
    query: str,
    llm_client: Any | None = None,
) -> CompoundIntent:
    building_matches, building_type_source = detect_building_type_with_fallback(
        query,
        llm_client,
    )
    component = detect_building_component(query)
    expansion = expand_query_details(query)
    region = detect_region(query)
    if not building_matches and not expansion.matches:
        return CompoundIntent(
            query=query,
            region=region.name if region else "",
            component=component.name if component else "",
            component_keywords=component.aliases if component else (),
            building_type_source=building_type_source,
        )

    building = building_matches[0] if building_matches else None
    matched_attributes: list[tuple[int, str, tuple[str, ...]]] = []
    for attribute, keywords in _load_attributes().items():
        matched = [keyword for keyword in keywords if keyword in query]
        if matched:
            matched_attributes.append(
                (max(len(keyword) for keyword in matched), attribute, keywords)
            )
    if not matched_attributes and component is None and not expansion.matches:
        return CompoundIntent(
            query=query,
            region=region.name if region else "",
        )

    concept_attribute, concept_keywords = _concept_attribute(
        query,
        expansion.matches,
    )
    component_attributes = [
        item for item in matched_attributes if item[1] in COMPONENT_ATTRIBUTES
    ]
    if component is not None and component_attributes:
        _, attribute, keywords = max(
            component_attributes,
            key=lambda item: item[0],
        )
    elif concept_attribute:
        attribute, keywords = concept_attribute, concept_keywords
    elif matched_attributes:
        _, attribute, keywords = max(matched_attributes, key=lambda item: item[0])
    else:
        attribute, keywords = "", ()

    function_terms = [
        term for term in FUNCTION_TERMS if term in query
    ]
    topic = "".join(
        (
            building.name if building else "",
            *function_terms,
            component.name if component else "",
            "、".join(concept.canonical for concept in expansion.matches),
        )
    )
    primary_standards: list[str] = []
    seen_standard_keys: set[str] = set()
    for standard in (
        *(building.primary_standards if building else ()),
        *expansion.related_standards,
    ):
        key = re.sub(r"[\s/\-－—]", "", standard).lower()
        if key and key not in seen_standard_keys:
            seen_standard_keys.add(key)
            primary_standards.append(standard)
    concept = _primary_concept(query, expansion.matches)
    return CompoundIntent(
        query=query,
        region=region.name if region else "",
        building_type=building.name if building else "",
        component=component.name if component else "",
        attribute=attribute,
        topic=topic,
        region_scope=region.to_scope() if region else {},
        region_standards=local_standard_titles(region) if region else (),
        primary_standards=tuple(primary_standards),
        building_aliases=building.aliases if building else (),
        component_keywords=component.aliases if component else (),
        attribute_keywords=keywords,
        concepts=expansion.matches,
        concept_group=concept.concept_id if concept else "",
        concept_label=concept.canonical if concept else "",
        concept_synonyms=expansion.terms,
        related_standards=expansion.related_standards,
        related_attributes=expansion.related_attributes,
        building_type_source=building_type_source,
        is_compound=True,
    )
