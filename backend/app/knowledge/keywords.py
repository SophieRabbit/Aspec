from __future__ import annotations

import re
from typing import Any

from .retriever import STOP_TOKENS, tokenize

MEANINGFUL_TERMS = (
    "民用建筑",
    "公共建筑",
    "商业建筑",
    "住宅",
    "日照",
    "踏步",
    "楼梯",
    "宽度",
    "高度",
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

    matched: list[str] = []
    for term in MEANINGFUL_TERMS:
        if term in cleaned and term not in matched:
            matched.append(term)

    if not matched:
        tokens = [token for token in tokenize(cleaned) if len(token) >= 2 and token not in STOP_TOKENS]
        for token in sorted(set(tokens), key=len, reverse=True):
            if any(token in existing for existing in matched):
                continue
            matched.append(token)
            if len(matched) >= 6:
                break

    for term in matched[:6]:
        keywords.append({"text": term, "kind": "domain"})
    return keywords
