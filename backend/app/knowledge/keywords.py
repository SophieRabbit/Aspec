from __future__ import annotations

import re
from typing import Any

from services.building_type_matcher import detect_building_types
from services.compound_intent import detect_compound_intent
from services.synonym_expander import match_synonym_groups

from .retriever import STOP_TOKENS, tokenize

MEANINGFUL_TERMS = (
    "民用建筑",
    "公共建筑",
    "商业建筑",
    "工业建筑",
    "厂房",
    "工厂",
    "车间",
    "冷库",
    "住宅",
    "日照",
    "踏步",
    "楼梯",
    "宽度",
    "高度",
    "距离",
    "疏散距离",
    "建筑密度",
    "容积率",
    "建筑高度",
    "采光",
    "疏散",
    "防火",
    "净高",
    "面积",
    "层高",
    "无障碍",
    "节能",
    "消防车道",
    "安全出口",
    "屋面防水",
    "栏杆",
    "阳台",
    "厨房",
    "卫生间",
)


EXTRA_QUERY_TERMS = (
    "汽车坡道",
    "地下坡道",
    "坡道",
    "双车道",
    "单车道",
    "坡度",
    "楼间距",
    "建筑间距",
    "日照间距",
)


def extract_keywords(query: str, requested_region: dict[str, Any] | None = None) -> list[dict[str, str]]:
    keywords: list[dict[str, str]] = []
    cleaned = query

    if requested_region and requested_region.get("place"):
        place = requested_region["place"]
        keywords.append({"text": place, "kind": "region"})
        cleaned = cleaned.replace(place, "")

    code_match = re.search(
        r"([A-Z]{1,8}(?:[∕/_]?T)?[∕/_]?\s*\d{1,6}(?:\.\d+)?(?:[-—]\s*\d{4})?)",
        cleaned,
        re.IGNORECASE,
    )
    if code_match:
        keywords.append({"text": code_match.group(1).strip(), "kind": "code"})

    for match in detect_building_types(query):
        for term in (match.name, match.matched_alias):
            if term and not any(item["text"] == term for item in keywords):
                keywords.append({"text": term, "kind": "building"})

    for match in match_synonym_groups(query):
        concept_terms = [match.canonical, *match.synonyms]
        for term in concept_terms:
            if term and not any(item["text"] == term for item in keywords):
                keywords.append({"text": term, "kind": "concept"})

    matched_candidates: list[str] = []
    for term in MEANINGFUL_TERMS:
        if term in cleaned and term not in matched_candidates:
            matched_candidates.append(term)
    for term in EXTRA_QUERY_TERMS:
        if term in cleaned and term not in matched_candidates:
            matched_candidates.append(term)

    intent = detect_compound_intent(query)
    for term in (
        intent.component,
        *intent.component_keywords,
        intent.attribute,
        *intent.attribute_keywords,
    ):
        if term and term in cleaned and term not in matched_candidates:
            matched_candidates.append(term)

    matched: list[str] = []
    for term in sorted(matched_candidates, key=len, reverse=True):
        if any(term in existing and term != existing for existing in matched):
            continue
        matched.append(term)

    if not matched:
        tokens = [token for token in tokenize(cleaned) if len(token) >= 2 and token not in STOP_TOKENS]
        for token in sorted(set(tokens), key=len, reverse=True):
            if any(token in existing for existing in matched):
                continue
            matched.append(token)
            if len(matched) >= 6:
                break

    for term in matched[:8]:
        if any(item["text"] == term for item in keywords):
            continue
        keywords.append({"text": term, "kind": "domain"})
    return keywords[:24]
