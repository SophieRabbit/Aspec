from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

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
        self.snippets: list[dict[str, Any]] = []
        self._document_frequency: Counter[str] = Counter()
        self._average_length = 1.0
        self.reload()

    def reload(self) -> None:
        self.snippets = []
        for document in self.knowledge_base.documents:
            for snippet in document.get("snippets", []):
                text = snippet.get("text", "")
                if not text:
                    continue
                self.snippets.append(
                    {
                        "document": document,
                        "snippet": snippet,
                        "text": text,
                        "tokens": Counter(tokenize(text)),
                    }
                )

        self._document_frequency = Counter()
        for item in self.snippets:
            self._document_frequency.update(set(item["tokens"].keys()))
        total_tokens = sum(len(item["tokens"]) for item in self.snippets)
        self._average_length = max(1.0, total_tokens / max(1, len(self.snippets)))

    def search(
        self,
        query: str,
        top_k: int = 5,
        region: str | None = None,
        document_type: str | None = None,
        standard: str | None = None,
        region_scope: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        query_tokens = tokenize(query)
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
                score += 20.0
            score += region_priority(document, region_scope)
            if score > 0:
                item["score"] = score
                scored.append(item)

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

        scored.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        return scored[:top_k]

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
            "snippet": snippet.get("text", ""),
            "score": round(item.get("score", 0.0), 4),
        }

    def count(self) -> int:
        return len(self.snippets)
