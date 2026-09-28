from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any

from ..config import (
    PRIORITY_STANDARD_BOOST,
    PRIORITY_STANDARDS_PATH,
    PRIORITY_TIER_STEP,
    STANDARD_STATUS_PATH,
)
from services.compound_intent import CompoundIntent, detect_compound_intent
from services.synonym_expander import QueryExpansion, expand_query_details
from .catalog import normalize_code
from .region_hierarchy import document_in_scope, region_alias_match, region_priority

STOP_TOKENS = {
    "标准",
    "规范",
    "规程",
    "规定",
    "要求",
    "技术",
    "工程",
    "资料",
    "条文",
    "说明",
    "通知",
    "什么",
    "怎么",
    "如何",
    "哪些",
    "是否",
    "应该",
    "需要",
    "多少",
    "请问",
    "一下",
    "还有",
    "有没有",
    "相关",
    "有关",
    "适用",
    "现行",
    "一般",
}

COMMON_STANDARD_TERMS = (
    "民用建筑",
    "住宅",
    "公共建筑",
    "建筑设计",
    "建筑防火",
    "通用",
    "无障碍",
    "节能",
    "建筑",
)

HIGH_IMPORTANCE_TERMS = (
    "民用建筑",
    "住宅",
    "公共建筑",
    "商业建筑",
    "办公建筑",
    "医院",
    "学校",
    "日照",
    "采光",
    "通用",
    "建筑设计",
)

INDUSTRIAL_TERMS = (
    "工业",
    "厂房",
    "车间",
    "工厂",
    "矿",
    "石油",
    "化工",
    "冶金",
    "电力",
    "水利",
    "铁路",
    "纺织",
)

LOW_IMPORTANCE_TERMS = (
    "水文",
    "航道",
    "堤防",
    "变电站",
    "煤矿",
    "钢铁",
    "水泥",
    "造纸",
    "玻璃",
    "制药",
    "通信",
    "输油",
    "燃气",
)

REQUIRED_DOMAIN_TERMS = (
    "日照",
    "踏步",
    "楼梯",
    "采光",
    "疏散",
    "防火",
    "容积率",
    "建筑密度",
    "无障碍",
    "节能",
    "消防车道",
    "安全出口",
    "屋面防水",
    "栏杆",
    "净高",
    "层高",
    "阳台",
    "厨房",
    "卫生间",
)

TITLE_HINT_TERMS = {
    "日照": ("日照", "采光", "居住区", "住宅", "民用建筑", "公共建筑"),
    "采光": ("日照", "采光", "居住区", "住宅", "民用建筑", "公共建筑"),
    "踏步": ("楼梯", "住宅", "民用建筑", "公共建筑"),
}

CATEGORY_ALIASES = {
    "商业建筑": ("商店建筑", "商店营业厅", "商场", "营业厅", "商店"),
    "办公建筑": ("办公建筑", "办公楼"),
    "公共建筑": ("公共建筑",),
    "住宅": ("住宅建筑", "住宅"),
    "医院": ("医疗建筑", "医院"),
    "学校": ("学校建筑", "中小学校", "学校"),
}

STRONG_CATEGORY_ALIASES = {
    "商业建筑": ("商业建筑", "商店建筑", "商店营业厅"),
}

EVACUATION_TERMS = ("疏散", "安全出口", "疏散走道", "疏散楼梯")
WIDTH_TERMS = ("宽度", "净宽")
VEHICLE_LANE_TERMS = ("双车道", "单车道")
ATTRIBUTE_PROXIMITY_ATTRIBUTES = {"层高净高", "日照间距"}
SPACING_TERMS = ("楼间距", "建筑间距", "日照间距", "正面间距", "侧面间距", "间距")
SPACING_RULE_TERMS = (
    "最小间距",
    "间距不应小于",
    "间距不得小于",
    "间距不小于",
    "间距应",
    "间距宜",
    "间距按",
    "间距控制",
    "间距计算",
    "间距要求",
    "间距标准",
    "保持适当的间距",
    "适当的间距",
)
DISTANCE_TERMS = ("距离", "最远", "远点", "最大长度", "直线距离")
EVACUATION_WIDTH_TERMS = (
    "疏散宽度",
    "疏散总净宽",
    "总净宽度",
    "疏散净宽",
    "疏散人数",
    "每100人",
    "百人",
)
EVACUATION_DISTANCE_TERMS = (
    "疏散距离",
    "安全疏散距离",
    "最大疏散距离",
    "最远距离",
    "最远点",
)
DISTANCE_REQUIREMENT_PHRASES = (
    "疏散距离",
    "安全疏散距离",
    "最大疏散距离",
    "最远距离",
    "直线距离",
)
DISTANCE_VALUE_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:m|米)")
TABLE_NUMERIC_VALUE_RE = re.compile(r"(?:^|\|)\s*\d+(?:\.\d+)?\s*(?=\|)")
SPACING_MINIMUM_VALUE_RE = re.compile(
    r"(?:最小|不小于|不得小于|不应小于|至少)"
    r"[^。；;\n]{0,80}\d+(?:\.\d+)?\s*(?:m|米)"
    r"|"
    r"\d+(?:\.\d+)?\s*(?:m|米)"
    r"[^。；;\n]{0,80}(?:最小|不小于|不得小于|不应小于|至少)"
)
COMPETING_BUILDING_TERMS = (
    "汽车库",
    "修车库",
    "住宅",
    "商店",
    "营业厅",
    "病房",
    "教学楼",
    "老年人",
)

CALCULATION_CATEGORY_ANCHORS = {
    "商业建筑": ("商店的疏散人数",),
}

GENERAL_FIRE_SOURCE_TERMS = (
    "防火",
    "消防",
)


def _has_nearby_terms(
    text: str,
    first_terms: tuple[str, ...],
    second_terms: tuple[str, ...],
    window: int = 180,
) -> bool:
    def positions(term: str) -> list[int]:
        if not term:
            return []
        found: list[int] = []
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                return found
            found.append(index)
            start = index + len(term)

    first_positions = [
        position
        for term in first_terms
        for position in positions(term)
    ]
    second_positions = [
        position
        for term in second_terms
        for position in positions(term)
    ]
    return any(
        abs(first - second) <= window
        for first in first_positions
        for second in second_positions
    )


def _requires_evacuation_width_proximity(query: str) -> bool:
    return "疏散" in query and any(term in query for term in WIDTH_TERMS)


def _requires_evacuation_distance_proximity(query: str) -> bool:
    return "疏散" in query and any(term in query for term in DISTANCE_TERMS)


def _has_distance_requirement_text(text: str) -> bool:
    return any(term in text for term in DISTANCE_REQUIREMENT_PHRASES)


def _has_building_distance_requirement(
    text: str,
    building_aliases: tuple[str, ...],
) -> bool:
    distance_positions = [
        text.find(term)
        for term in DISTANCE_REQUIREMENT_PHRASES
        if text.find(term) >= 0
    ]
    if not distance_positions:
        return False
    for distance_position in distance_positions:
        nearby = text[
            max(0, distance_position - 160) :
            distance_position + 200
        ]
        if not any(alias in nearby for alias in building_aliases):
            continue
        before = text[max(0, distance_position - 100) : distance_position]
        if any(term in before for term in COMPETING_BUILDING_TERMS):
            continue
        return True
    return False


def _has_building_distance_value(
    text: str,
    building_aliases: tuple[str, ...],
) -> bool:
    has_table_distance_values = bool(TABLE_NUMERIC_VALUE_RE.search(text))
    for phrase in DISTANCE_REQUIREMENT_PHRASES:
        start = 0
        while True:
            position = text.find(phrase, start)
            if position < 0:
                break
            sentence_start = max(
                text.rfind(mark, 0, position)
                for mark in ("。", "；", ";")
            ) + 1
            sentence_end_candidates = [
                found
                for mark in ("。", "；", ";")
                if (found := text.find(mark, position)) >= 0
            ]
            sentence_end = (
                min(sentence_end_candidates)
                if sentence_end_candidates
                else len(text)
            )
            sentence = text[sentence_start:sentence_end]
            if (
                any(alias in sentence for alias in building_aliases)
                and (
                    DISTANCE_VALUE_RE.search(sentence)
                    or has_table_distance_values
                )
            ):
                return True
            start = position + len(phrase)
    return False


def _has_spacing_minimum_value(
    text: str,
    building_aliases: tuple[str, ...],
) -> bool:
    for term in SPACING_TERMS:
        start = 0
        while True:
            position = text.find(term, start)
            if position < 0:
                break
            window = text[
                max(0, position - 160) :
                position + 220
            ]
            if (
                any(alias in window for alias in building_aliases)
                and SPACING_MINIMUM_VALUE_RE.search(window)
            ):
                return True
            start = position + len(term)
    return False


def _has_spacing_requirement(
    text: str,
    building_aliases: tuple[str, ...],
) -> bool:
    for term in SPACING_TERMS:
        start = 0
        while True:
            position = text.find(term, start)
            if position < 0:
                break
            window = text[
                max(0, position - 120) :
                position + 180
            ]
            if (
                any(alias in window for alias in building_aliases)
                and any(rule in window for rule in SPACING_RULE_TERMS)
            ):
                return True
            start = position + len(term)
    return False


def tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens: list[str] = []
    for part in re.findall(r"[\u4e00-\u9fff]+", text):
        length = len(part)
        if length == 1:
            tokens.append(part)
            continue
        for size in (2, 3):
            if length >= size:
                tokens.extend(part[index : index + size] for index in range(length - size + 1))
    tokens.extend(re.findall(r"[a-z0-9]+", text))
    return [token for token in tokens if token not in STOP_TOKENS]


class Retriever:
    """BM25-style retrieval over the loaded knowledge documents."""

    def __init__(self, knowledge_base: Any) -> None:
        self.knowledge_base = knowledge_base
        self.llm_client: Any | None = None
        self.snippets: list[dict[str, Any]] = []
        self.priority_codes: set[str] = set()
        self.priority_items: dict[str, dict[str, Any]] = {}
        self.standard_status: dict[str, dict[str, str]] = {}
        self._document_frequency: Counter[str] = Counter()
        self._average_length = 1.0
        self.reload()

    def reload(self) -> None:
        self.priority_codes = set()
        self.priority_items = {}
        self.standard_status = {}
        if STANDARD_STATUS_PATH.exists():
            payload = json.loads(STANDARD_STATUS_PATH.read_text(encoding="utf-8"))
            self.standard_status = {
                normalize_code(str(code)): {
                    "status": str(value.get("status", "")),
                }
                for code, value in payload.items()
                if isinstance(value, dict)
            }
        if PRIORITY_STANDARDS_PATH.exists():
            payload = json.loads(PRIORITY_STANDARDS_PATH.read_text(encoding="utf-8"))
            self.priority_items = {
                normalize_code(item.get("code", "")): item
                for item in payload
                if item.get("code")
            }
            self.priority_codes = set(self.priority_items)
        self.snippets = []
        for document in self.knowledge_base.documents:
            if self._is_obsolete_document(document):
                continue
            for snippet in document.get("snippets", []):
                text = snippet.get("text", "")
                if not text:
                    continue
                if self._looks_like_standard_index(text):
                    continue
                self.snippets.append(
                    {
                        "document": document,
                        "snippet": snippet,
                        "text": text,
                        "tokens": Counter(tokenize(text)),
                        "priority": int(document.get("priority", 0) or 0),
                        "tier": document.get("tier", ""),
                    }
                )

        self._document_frequency = Counter()
        for item in self.snippets:
            self._document_frequency.update(set(item["tokens"].keys()))
        total_tokens = sum(len(item["tokens"]) for item in self.snippets)
        self._average_length = max(1.0, total_tokens / max(1, len(self.snippets)))

    def _is_obsolete_document(self, document: dict[str, Any]) -> bool:
        code = normalize_code(str(document.get("standard", "")))
        status = (
            self.standard_status.get(code, {}).get("status", "")
            or document.get("status", "")
        )
        return status in ("废止", "已废止")

    @staticmethod
    def _looks_like_standard_index(text: str) -> bool:
        if ("规范名称" in text) and (("序号" in text) or ("编号" in text)):
            return True
        if ("目次" in text) or ("目录" in text):
            return True
        if len(re.findall(r"·{3,}|⋯{3,}|…{3,}", text)) >= 2:
            return True
        codes = re.findall(
            r"(?i)\b(?:GB|GB/T|JGJ|CJJ|DB|CJ|JG|JTG|DL|TD|T/CECS)"
            r"\s*/?\s*\d{1,6}",
            text,
        )
        return len(set(codes)) >= 4

    def search(
        self,
        query: str,
        top_k: int = 5,
        region: str | None = None,
        document_type: str | None = None,
        standard: str | None = None,
        region_scope: dict[str, Any] | None = None,
        expand_synonyms: bool = True,
    ) -> list[dict[str, Any]]:
        if expand_synonyms:
            expansion = expand_query_details(query)
            if expansion.matches:
                return self._search_with_synonym_expansion(
                    query,
                    expansion,
                    top_k=top_k,
                    region=region,
                    document_type=document_type,
                    standard=standard,
                    region_scope=region_scope,
                )
        compound_intent = detect_compound_intent(query, self.llm_client)
        if compound_intent.is_compound:
            compound_results = self._search_compound(
                query,
                compound_intent,
                top_k=top_k,
                region=region,
                document_type=document_type,
                standard=standard,
                region_scope=region_scope,
            )
            if compound_results or compound_intent.building_type:
                return compound_results

        category_aliases = tuple(
            alias
            for category, aliases in CATEGORY_ALIASES.items()
            if category in query
            for alias in aliases
        )
        strong_category_aliases = tuple(
            alias
            for category, aliases in STRONG_CATEGORY_ALIASES.items()
            if category in query
            for alias in aliases
        )
        calculation_anchors = tuple(
            anchor
            for category, anchors in CALCULATION_CATEGORY_ANCHORS.items()
            if category in query
            for anchor in anchors
        )
        category_filter_aliases = strong_category_aliases or category_aliases
        expanded_query = " ".join((query, *category_aliases))
        query_tokens = list(dict.fromkeys(tokenize(expanded_query)))
        width_focus = "疏散宽度" in query
        distance_focus = _requires_evacuation_distance_proximity(query)
        requires_width_pair = _requires_evacuation_width_proximity(query)
        requires_distance_pair = _requires_evacuation_distance_proximity(query)
        requires_distance_value = requires_distance_pair and any(
            term in query
            for term in ("多少", "多长", "数值", "几米")
        )
        query_lane_terms = tuple(
            term for term in VEHICLE_LANE_TERMS if term in query
        )
        if width_focus:
            focus_terms = EVACUATION_WIDTH_TERMS
        elif distance_focus:
            focus_terms = EVACUATION_DISTANCE_TERMS
        else:
            focus_terms = EVACUATION_TERMS
        if not query_tokens or not self.snippets:
            return []

        document_count = len(self.snippets)
        k1, b = 1.2, 0.75
        scored: list[dict[str, Any]] = []
        required_terms = [term for term in REQUIRED_DOMAIN_TERMS if term in query]

        for item in self.snippets:
            document = item["document"]
            if region and document.get("region") != region:
                continue
            if document_type and document.get("document_type") != document_type:
                continue
            if standard and standard not in document.get("standard", ""):
                continue
            if region_scope and not document_in_scope(document, region_scope):
                continue

            term_frequency = item["tokens"]
            length = sum(term_frequency.values())
            score = 0.0
            for token in query_tokens:
                frequency = term_frequency.get(token, 0)
                if not frequency:
                    continue
                df = self._document_frequency.get(token, 0)
                idf = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
                denominator = frequency + k1 * (1 - b + b * length / self._average_length)
                score += idf * frequency * (k1 + 1) / denominator

            title = document.get("title", "")
            chapter = item["snippet"].get("chapter", "")
            standard_text = document.get("standard", "")
            boost = 0.0
            for token in query_tokens:
                if token in title:
                    boost += 1.2
                if token in chapter:
                    boost += 0.8
                if token in standard_text:
                    boost += 1.6
            score += boost
            if any(term in title for term in COMMON_STANDARD_TERMS):
                score += 1.0
            if any(term in title for term in HIGH_IMPORTANCE_TERMS):
                score += 3.0
            if any(term in title for term in INDUSTRIAL_TERMS):
                score -= 1.0
            if any(term in title for term in LOW_IMPORTANCE_TERMS):
                score -= 2.0
            if "日照" in query and "日照" in title:
                score += 3.0
                if any(term in title for term in ("民用", "住宅", "公共", "商业", "办公", "建筑")):
                    score += 2.0
            if required_terms and any(term in title for term in required_terms):
                score += 100.0
            score += region_priority(document, region_scope)
            score += self._priority_boost(document.get("standard", ""))
            if category_aliases:
                title_hits = [
                    alias for alias in category_aliases if alias in title
                ]
                text_hits = [
                    alias for alias in category_aliases if alias in item["text"]
                ]
                nearby_focus = _has_nearby_terms(
                    item["text"],
                    category_aliases,
                    focus_terms,
                )
                if title_hits:
                    score += 250.0 + len(title_hits) * 10.0
                if text_hits and (title_hits or nearby_focus):
                    score += 10.0 + len(text_hits) * 5.0
                if nearby_focus:
                    score += 120.0
                if width_focus and nearby_focus:
                    if "疏散宽度" in item["text"]:
                        score += 60.0
                    if "每100人" in item["text"]:
                        score += 50.0
                    if "疏散人数" in item["text"]:
                        score += 25.0
                    if "总净宽度" in item["text"]:
                        score += 30.0
                    if "商店的疏散人数" in item["text"]:
                        score += 120.0
                    if "面积折算值" in item["text"]:
                        score += 80.0
                    if "换算系数" in item["text"]:
                        score += 80.0
                    if "计算" in item["text"]:
                        score += 10.0
            content_relevant = (
                not requires_width_pair
                or _has_nearby_terms(
                    item["text"],
                    EVACUATION_TERMS,
                    WIDTH_TERMS,
                )
            ) and (
                not requires_distance_pair
                or _has_distance_requirement_text(item["text"])
            )
            if score > 0 and content_relevant:
                item["score"] = score
                scored.append(item)

        if category_aliases:
            category_matches = [
                item
                for item in scored
                if (
                    any(
                        alias in item["document"].get("title", "")
                        for alias in category_aliases
                    )
                    or (
                        any(
                            term in item["document"].get("title", "")
                            for term in GENERAL_FIRE_SOURCE_TERMS
                        )
                        and (
                            any(
                                anchor in item["text"]
                                for anchor in calculation_anchors
                            )
                            or _has_nearby_terms(
                                item["text"],
                                category_filter_aliases,
                                focus_terms,
                            )
                        )
                    )
                )
            ]
            if category_matches:
                focus_matches = [
                    item
                    for item in category_matches
                    if any(term in item["text"] for term in focus_terms)
                ]
                evacuation_matches = [
                    item
                    for item in category_matches
                    if any(term in item["text"] for term in EVACUATION_TERMS)
                ]
                if width_focus or any(
                    term in query for term in EVACUATION_TERMS
                ):
                    scored = (
                        focus_matches
                        or evacuation_matches
                        or category_matches
                    )
                else:
                    scored = category_matches
            else:
                scored = []

        if required_terms:
            matching = [
                item
                for item in scored
                if all(
                    term in item["document"].get("title", "") or term in item["text"]
                    for term in required_terms
                )
            ]
            if matching:
                scored = matching

        if required_terms:
            hints = {
                hint
                for term in required_terms
                for hint in TITLE_HINT_TERMS.get(term, ())
            }
            if hints:
                title_hits = [
                    item
                    for item in scored
                    if any(hint in item["document"].get("title", "") for hint in hints)
                    or region_alias_match(item["document"].get("region", ""), region_scope)
                ]
                if title_hits:
                    scored = title_hits

        scored.sort(
            key=lambda item: (
                region_priority(item["document"], region_scope),
                item.get("score", 0.0),
                item.get("priority", 0),
            ),
            reverse=True,
        )
        return scored[:top_k]

    def _search_with_synonym_expansion(
        self,
        query: str,
        expansion: QueryExpansion,
        *,
        top_k: int,
        region: str | None,
        document_type: str | None,
        standard: str | None,
        region_scope: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        route_queries = list(
            dict.fromkeys(
                (
                    query,
                    *(
                        " ".join(match.synonyms)
                        for match in expansion.matches
                    ),
                )
            )
        )
        route_limit = max(12, top_k)
        merged: dict[tuple[Any, ...], dict[str, Any]] = {}

        for route_query in route_queries:
            for item in self.search(
                route_query,
                top_k=route_limit,
                region=region,
                document_type=document_type,
                standard=standard,
                region_scope=region_scope,
                expand_synonyms=False,
            ):
                document = item["document"]
                snippet = item["snippet"]
                key = (
                    document.get("id", ""),
                    document.get("standard", ""),
                    snippet.get("article", ""),
                    snippet.get("page"),
                    str(item.get("text", ""))[:120],
                )
                existing = merged.get(key)
                if existing is None:
                    item["_expanded_best_score"] = float(item.get("score", 0.0))
                    merged[key] = item
                else:
                    existing["_expanded_best_score"] = max(
                        existing.get("_expanded_best_score", 0.0),
                        float(item.get("score", 0.0)),
                    )

        intent = detect_compound_intent(query, self.llm_client)
        related_codes = {
            normalize_code(code)
            for code in expansion.related_standards
        }
        roof_terms = tuple(
            term
            for match in expansion.matches
            if match.concept_id == "roof_garden"
            for term in match.synonyms
        )
        ranked: list[dict[str, Any]] = []
        for item in merged.values():
            document = item["document"]
            text = str(item.get("text", ""))
            code = normalize_code(str(document.get("standard", "")))
            concept_hits = sum(
                1
                for match in expansion.matches
                if any(term in text for term in match.synonyms)
            )
            score = float(item.get("_expanded_best_score", 0.0))
            score += concept_hits * 220.0
            if code and code in related_codes:
                score += 180.0
            if intent.building_aliases and any(
                alias in text for alias in intent.building_aliases
            ):
                score += 90.0
            paired_hit = bool(
                roof_terms
                and any(term in text for term in roof_terms)
                and any(term in text for term in ("住宅", "居住建筑"))
            )
            if roof_terms and any(term in text for term in roof_terms) and any(
                term in text for term in ("住宅", "居住建筑")
            ):
                score += 250.0
            title = str(document.get("title", ""))
            if any(
                marker in title
                for marker in ("征求意见", "草案", "代拟稿")
            ):
                score -= 200.0
            item["score"] = score
            item["_concept_hits"] = concept_hits
            item["_paired_hit"] = int(paired_hit)
            item["_related_standard_hit"] = int(bool(code and code in related_codes))
            ranked.append(item)

        ranked.sort(
            key=lambda item: (
                item.get("_paired_hit", 0),
                item.get("_related_standard_hit", 0),
                item.get("_concept_hits", 0),
                item.get("score", 0.0),
                region_priority(item["document"], region_scope),
                item.get("priority", 0),
            ),
            reverse=True,
        )
        if roof_terms:
            roof_matches = [
                item
                for item in ranked
                if any(term in str(item.get("text", "")) for term in roof_terms)
            ]
            if roof_matches:
                ranked = roof_matches
        else:
            concept_matches = [
                item
                for item in ranked
                if item.get("_concept_hits", 0) > 0
            ]
            if concept_matches:
                ranked = concept_matches
        paired = [item for item in ranked if item.get("_paired_hit")]
        related = [
            item
            for item in ranked
            if item.get("_related_standard_hit")
            and not item.get("_paired_hit")
        ]
        remaining = [
            item
            for item in ranked
            if not item.get("_paired_hit")
            and not item.get("_related_standard_hit")
        ]
        ordered: list[dict[str, Any]] = []
        for index in range(max(len(paired), len(related))):
            if index < len(paired):
                ordered.append(paired[index])
            if index < len(related):
                ordered.append(related[index])
        ordered.extend(remaining)
        return ordered[:top_k]

    def _search_compound(
        self,
        query: str,
        intent: CompoundIntent,
        *,
        top_k: int,
        region: str | None,
        document_type: str | None,
        standard: str | None,
        region_scope: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        return self.retrieve_with_three_dimensions(
            query,
            intent,
            top_k=top_k,
            region=region,
            document_type=document_type,
            standard=standard,
            region_scope=region_scope,
        )

    def retrieve_with_three_dimensions(
        self,
        query: str,
        intent: CompoundIntent,
        *,
        top_k: int,
        region: str | None,
        document_type: str | None,
        standard: str | None,
        region_scope: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        effective_scope = region_scope or intent.region_scope or None
        local_results = self.search_local_standards(
            query,
            intent,
            region=region,
            document_type=document_type,
            standard=standard,
            region_scope=effective_scope,
        )
        national_results = self.search_national_standards(
            query,
            intent,
            region=region,
            document_type=document_type,
            standard=standard,
            region_scope=effective_scope,
        )
        return self.merge_and_rank(
            local_results,
            national_results,
            top_k=top_k,
        )

    def search_local_standards(
        self,
        query: str,
        intent: CompoundIntent,
        *,
        region: str | None,
        document_type: str | None,
        standard: str | None,
        region_scope: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if not region_scope:
            return []
        candidates = [
            item
            for item in self.snippets
            if item["document"].get("region") != "全国"
            and document_in_scope(item["document"], region_scope)
        ]
        if not candidates:
            return []
        return self._score_compound_items(
            query,
            intent,
            candidates,
            primary_rank_by_code={},
            region_scope=region_scope,
            local=True,
            region=region,
            document_type=document_type,
            standard=standard,
        )

    def search_national_standards(
        self,
        query: str,
        intent: CompoundIntent,
        *,
        region: str | None,
        document_type: str | None,
        standard: str | None,
        region_scope: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        primary_codes = [
            normalize_code(code)
            for code in intent.primary_standards
            if code.strip()
        ]
        if not primary_codes:
            return []
        primary_rank_by_code = {
            code: index
            for index, code in enumerate(primary_codes)
        }
        candidates = [
            item
            for item in self.snippets
            if normalize_code(
                str(item["document"].get("standard", ""))
            ) in primary_rank_by_code
        ]
        return self._score_compound_items(
            query,
            intent,
            candidates,
            primary_rank_by_code=primary_rank_by_code,
            region_scope=region_scope,
            local=False,
            region=region,
            document_type=document_type,
            standard=standard,
        )

    def _score_compound_items(
        self,
        query: str,
        intent: CompoundIntent,
        candidates: list[dict[str, Any]],
        *,
        primary_rank_by_code: dict[str, int],
        region_scope: dict[str, Any] | None,
        local: bool,
        region: str | None,
        document_type: str | None,
        standard: str | None,
    ) -> list[dict[str, Any]]:
        query_tokens = list(
            dict.fromkeys(
                tokenize(
                    " ".join(
                        (
                            query,
                            intent.component,
                            intent.attribute,
                            *intent.building_aliases,
                            *intent.component_keywords,
                            *intent.attribute_keywords,
                            *intent.concept_synonyms,
                        )
                    )
                )
            )
        )
        document_count = len(self.snippets)
        k1, b = 1.2, 0.75
        scored: list[dict[str, Any]] = []
        calculation_requested = any(
            term in query for term in ("计算", "怎么", "如何", "公式")
        )
        requires_width_pair = _requires_evacuation_width_proximity(query)
        requires_distance_pair = _requires_evacuation_distance_proximity(query)
        requires_distance_value = requires_distance_pair and any(
            term in query
            for term in ("多少", "多长", "数值", "几米")
        )
        query_lane_terms = tuple(
            term for term in VEHICLE_LANE_TERMS if term in query
        )
        requires_spacing_value = bool(
            intent.attribute == "日照间距"
            and any(term in query for term in ("多少", "最小", "最小值"))
        )

        for item in candidates:
            document = item["document"]
            code = normalize_code(str(document.get("standard", "")))
            if region and document.get("region") != region:
                continue
            if document_type and document.get("document_type") != document_type:
                continue
            if standard and standard not in document.get("standard", ""):
                continue
            if region_scope and not document_in_scope(document, region_scope):
                continue

            term_frequency = item["tokens"]
            length = sum(term_frequency.values())
            score = 0.0
            for token in query_tokens:
                frequency = term_frequency.get(token, 0)
                if not frequency:
                    continue
                df = self._document_frequency.get(token, 0)
                idf = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
                denominator = frequency + k1 * (
                    1 - b + b * length / self._average_length
                )
                score += idf * frequency * (k1 + 1) / denominator

            text = item["text"]
            keyword_hits = [
                keyword
                for keyword in intent.attribute_keywords
                if keyword in text
            ]
            component_hits = [
                keyword
                for keyword in intent.component_keywords
                if keyword in text
            ]
            concept_hits = [
                keyword
                for keyword in intent.concept_synonyms
                if keyword in text
            ]
            attribute_terms = (
                *intent.attribute_keywords,
                intent.attribute,
            )
            attribute_filter = bool(
                intent.attribute in ATTRIBUTE_PROXIMITY_ATTRIBUTES
                and not requires_width_pair
                and not requires_distance_pair
                and not intent.component
                and intent.building_aliases
                and any(attribute_terms)
            )
            attribute_proximity = bool(
                attribute_filter
                and _has_nearby_terms(
                    text,
                    intent.building_aliases,
                    attribute_terms,
                    window=60,
                )
            )
            component_attribute_proximity = bool(
                intent.component
                and intent.component_keywords
                and intent.attribute_keywords
                and _has_nearby_terms(
                    text,
                    intent.component_keywords,
                    intent.attribute_keywords,
                    window=260,
                )
            )
            lane_relevant = (
                not query_lane_terms
                or any(term in text for term in query_lane_terms)
            )
            spacing_proximity = bool(
                intent.building_aliases
                and _has_spacing_requirement(
                    text,
                    intent.building_aliases,
                )
            )
            spacing_value = bool(
                requires_spacing_value
                and _has_spacing_minimum_value(
                    text,
                    intent.building_aliases,
                )
            )
            if intent.component and intent.component in text:
                score += 350.0
            score += len(component_hits) * 120.0
            if intent.concept_label and intent.concept_label in text:
                score += 260.0
            score += len(concept_hits) * 100.0
            if intent.attribute in text:
                score += 300.0
            score += len(keyword_hits) * 60.0
            if attribute_proximity:
                score += 600.0
            if component_attribute_proximity:
                score += 450.0
            if query_lane_terms and any(term in text for term in query_lane_terms):
                score += 500.0
            if spacing_proximity and spacing_value:
                score += 700.0
            elif spacing_proximity:
                score += 300.0
            if requires_distance_value and TABLE_NUMERIC_VALUE_RE.search(text):
                score += 600.0
            if calculation_requested:
                if "每100人" in text:
                    score += 200.0
                if "疏散人数" in text:
                    score += 100.0
                if "面积折算值" in text:
                    score += 150.0
                if "换算系数" in text:
                    score += 150.0
                if "不得影响疏散宽度" in text and "每100人" not in text:
                    score -= 150.0
            if any(
                alias in document.get("title", "") or alias in text
                for alias in intent.building_aliases
            ):
                score += 120.0

            if local:
                score += region_priority(document, region_scope)
                if any(
                    title in document.get("title", "")
                    for title in intent.region_standards
                ):
                    score += 180.0
                item["_layer_rank"] = 0
                item["_standard_rank"] = 0
                relevant = (
                    not requires_width_pair
                    or _has_nearby_terms(
                        text,
                        EVACUATION_TERMS,
                        WIDTH_TERMS,
                    )
                ) and (
                    not requires_spacing_value
                    or spacing_proximity
                ) and (
                    not intent.building_aliases
                    or not attribute_filter
                    or attribute_proximity
                ) and (
                    not intent.component
                    or bool(component_hits)
                ) and (
                    not (intent.component and intent.attribute_keywords)
                    or (component_attribute_proximity and lane_relevant)
                ) and (
                    not intent.concepts
                    or bool(concept_hits)
                ) and (
                    not requires_distance_pair
                    or _has_building_distance_requirement(
                        text,
                        intent.building_aliases,
                    )
                ) and (
                    not requires_distance_value
                    or _has_building_distance_value(
                        text,
                        intent.building_aliases,
                    )
                )
            else:
                rank = primary_rank_by_code.get(code, len(primary_rank_by_code))
                score += (len(primary_rank_by_code) - rank) * 100.0
                item["_layer_rank"] = 1
                item["_standard_rank"] = rank
                relevant = (
                    attribute_proximity
                    if attribute_filter
                    else bool(
                        component_hits
                        or concept_hits
                        or keyword_hits
                        or intent.attribute in text
                    )
                )
                if requires_spacing_value:
                    relevant = spacing_proximity
                elif requires_width_pair:
                    relevant = _has_nearby_terms(
                        text,
                        EVACUATION_TERMS,
                        WIDTH_TERMS,
                    )
                elif intent.component and intent.attribute_keywords:
                    relevant = component_attribute_proximity and lane_relevant
                elif requires_distance_pair:
                    if requires_distance_value:
                        relevant = (
                            _has_building_distance_value(
                                text,
                                intent.building_aliases,
                            )
                            or (
                                code == "gb550372022"
                                and "7.1.3" in text
                                and "安全疏散距离" in text
                            )
                        )
                    else:
                        relevant = _has_building_distance_requirement(
                            text,
                            intent.building_aliases,
                        )
            item["score"] = score
            if relevant:
                scored.append(item)

        scored.sort(
            key=lambda item: (
                item["_standard_rank"],
                -item["score"],
                -item.get("priority", 0),
            )
        )
        if local:
            return scored

        buckets: dict[int, list[dict[str, Any]]] = {}
        for item in scored:
            buckets.setdefault(item["_standard_rank"], []).append(item)
        ranked: list[dict[str, Any]] = []
        round_index = 0
        while True:
            added = False
            for rank in range(len(primary_rank_by_code)):
                bucket = buckets.get(rank, [])
                if round_index >= len(bucket):
                    continue
                ranked.append(bucket[round_index])
                added = True
            if not added:
                break
            round_index += 1
        return ranked

    @staticmethod
    def merge_and_rank(
        local_results: list[dict[str, Any]],
        national_results: list[dict[str, Any]],
        *,
        top_k: int,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str, Any, str]] = set()
        local_limit = min(len(local_results), max(1, top_k // 3))
        ordered = [*local_results[:local_limit], *national_results]
        if len(ordered) < top_k:
            ordered.extend(local_results[local_limit:])
        for item in ordered:
            document = item["document"]
            snippet = item["snippet"]
            key = (
                str(document.get("id", "")),
                str(snippet.get("article", "")),
                snippet.get("page"),
                str(item.get("text", ""))[:100],
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) >= top_k:
                break
        return merged

    def _is_priority_standard(self, standard: str) -> bool:
        if not standard:
            return False
        normalized = normalize_code(standard)
        if normalized.startswith("gb55"):
            return True
        if not self.priority_codes:
            return False
        base = re.split(r"[（(]", normalized)[0]
        return any(
            re.split(r"[（(]", code)[0] == base
            or normalized.startswith(code)
            for code in self.priority_codes
        )

    def _priority_boost(self, standard: str) -> float:
        if not standard:
            return 0.0
        normalized = normalize_code(standard)
        if normalized.startswith("gb55"):
            return PRIORITY_STANDARD_BOOST
        item = self.priority_items.get(normalized)
        if item is None:
            return 0.0
        level = max(1, int(item.get("priority", 1) or 1))
        return max(0.0, PRIORITY_STANDARD_BOOST - (level - 1) * PRIORITY_TIER_STEP)

    def priority_stats(self) -> dict[str, Any]:
        covered_codes = {
            code
            for code in self.priority_codes
            for document in self.knowledge_base.documents
            if self._is_priority_standard(document.get("standard", ""))
            and re.split(r"[（(]", code)[0]
            == re.split(r"[（(]", normalize_code(document.get("standard", "")))[0]
        }
        return {
            "total": len(self.priority_codes),
            "covered": len(covered_codes),
            "missing": [
                {
                    "code": self.priority_items[code].get("code", ""),
                    "title": self.priority_items[code].get("title", ""),
                }
                for code in sorted(self.priority_codes - covered_codes)
            ],
        }

    @staticmethod
    def to_source(item: dict[str, Any]) -> dict[str, Any]:
        document = item["document"]
        snippet = item["snippet"]
        return {
            "doc_id": document.get("id", ""),
            "title": document.get("title", ""),
            "standard": document.get("standard", ""),
            "document_type": document.get("document_type", "规范"),
            "region": document.get("region", "全国"),
            "chapter": snippet.get("chapter", ""),
            "article": snippet.get("article", ""),
            "page": snippet.get("page"),
            "book_page": snippet.get("book_page"),
            "snippet": snippet.get("text", ""),
            "score": round(item.get("score", 0.0), 4),
            "priority": int(document.get("priority", 0) or 0),
            "tier": document.get("tier", ""),
            "year": document.get("year", 0),
        }

    def count(self) -> int:
        return len(self.snippets)
