from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "synonym_groups.json"


@dataclass(frozen=True)
class SynonymGroupMatch:
    concept_id: str
    canonical: str
    synonyms: tuple[str, ...]
    matched_terms: tuple[str, ...]
    related_standards: tuple[str, ...]
    related_attributes: tuple[str, ...]


@dataclass(frozen=True)
class QueryExpansion:
    query: str
    matches: tuple[SynonymGroupMatch, ...]
    terms: tuple[str, ...]
    related_standards: tuple[str, ...]
    related_attributes: tuple[str, ...]


@lru_cache(maxsize=1)
def _load_groups() -> tuple[dict[str, object], ...]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return tuple(item for item in payload if isinstance(item, dict))


def match_synonym_groups(query: str) -> tuple[SynonymGroupMatch, ...]:
    matches: list[SynonymGroupMatch] = []
    for item in _load_groups():
        synonyms = tuple(
            str(term)
            for term in item.get("synonyms", [])
            if str(term).strip()
        )
        matched_terms = tuple(term for term in synonyms if term in query)
        if not matched_terms:
            continue
        matches.append(
            SynonymGroupMatch(
                concept_id=str(item.get("concept_id", "")),
                canonical=str(item.get("canonical", "")),
                synonyms=synonyms,
                matched_terms=matched_terms,
                related_standards=tuple(
                    str(code)
                    for code in item.get("related_standards", [])
                    if str(code).strip()
                ),
                related_attributes=tuple(
                    str(attribute)
                    for attribute in item.get("related_attributes", [])
                    if str(attribute).strip()
                ),
            )
        )
    return tuple(matches)


def expand_query_details(query: str) -> QueryExpansion:
    matches = match_synonym_groups(query)
    terms: list[str] = []
    related_standards: list[str] = []
    related_attributes: list[str] = []
    for match in matches:
        for term in match.synonyms:
            if term not in terms:
                terms.append(term)
        for code in match.related_standards:
            if code not in related_standards:
                related_standards.append(code)
        for attribute in match.related_attributes:
            if attribute not in related_attributes:
                related_attributes.append(attribute)
    return QueryExpansion(
        query=query,
        matches=matches,
        terms=tuple(terms),
        related_standards=tuple(related_standards),
        related_attributes=tuple(related_attributes),
    )


def expand_query(query: str) -> list[str]:
    return list(expand_query_details(query).terms)
