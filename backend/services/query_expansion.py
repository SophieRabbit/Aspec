from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import (
    QUERY_EXPANSION_CACHE_DAYS,
    QUERY_EXPANSION_MAX_TOKENS,
)

logger = logging.getLogger(__name__)
PROMPT_VERSION = "v1"

_GENERIC_TERMS = {
    "建筑",
    "工程",
    "规范",
    "标准",
    "规程",
    "规定",
    "要求",
    "设计",
    "问题",
    "相关",
    "如何",
    "怎么",
}


@dataclass(frozen=True)
class ExpandedQuery:
    canonical_topic: str
    synonyms: tuple[str, ...]
    search_queries: tuple[str, ...]
    attributes: tuple[str, ...]
    cache_hit: bool = False

    @property
    def terms(self) -> tuple[str, ...]:
        values = (
            self.canonical_topic,
            *self.synonyms,
            *self.search_queries,
            *self.attributes,
        )
        return tuple(dict.fromkeys(value for value in values if value))

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_topic": self.canonical_topic,
            "synonyms": list(self.synonyms),
            "search_queries": list(self.search_queries),
            "attributes": list(self.attributes),
        }


class QueryExpansionService:
    """Expands unknown construction vocabulary without generating answers."""

    def __init__(
        self,
        llm_client: Any,
        *,
        cache: Any | None = None,
        max_tokens: int = QUERY_EXPANSION_MAX_TOKENS,
        cache_days: int = QUERY_EXPANSION_CACHE_DAYS,
    ) -> None:
        self.llm_client = llm_client
        self.cache = cache
        self.max_tokens = max_tokens
        self.cache_days = max(1, cache_days)
        self._memory_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}

    @staticmethod
    def _normalized_query(query: str) -> str:
        return re.sub(r"\s+", "", query).strip()

    def _cache_key(self, query: str) -> str:
        model = str(getattr(self.llm_client, "model", ""))
        raw = f"{PROMPT_VERSION}|{model}|{self._normalized_query(query)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_recent(timestamp: Any, days: int) -> bool:
        try:
            created = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except ValueError:
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return created >= datetime.now(timezone.utc) - timedelta(days=days)

    def _get_cached(self, key: str) -> dict[str, Any] | None:
        if self.cache is not None:
            try:
                row = self.cache.get_query_expansion(key)
                if row and self._is_recent(row.get("created_at"), self.cache_days):
                    return json.loads(row.get("expansion_json") or "{}")
            except Exception as exc:
                logger.warning("query expansion cache read failed: %s", exc)
            return None
        cached = self._memory_cache.get(key)
        if cached and cached[0] >= datetime.now(timezone.utc) - timedelta(days=self.cache_days):
            return cached[1]
        return None

    def _save_cached(self, key: str, query: str, expansion: dict[str, Any]) -> None:
        if self.cache is not None:
            try:
                self.cache.save_query_expansion(
                    cache_key=key,
                    query_text=query,
                    model=str(getattr(self.llm_client, "model", "")),
                    prompt_version=PROMPT_VERSION,
                    expansion=expansion,
                )
            except Exception as exc:
                logger.warning("query expansion cache write failed: %s", exc)
            return
        self._memory_cache[key] = (datetime.now(timezone.utc), expansion)

    @staticmethod
    def _clean_terms(values: Any, *, limit: int) -> tuple[str, ...]:
        if not isinstance(values, list):
            return ()
        terms: list[str] = []
        for value in values:
            text = re.sub(r"\s+", " ", str(value)).strip()
            if len(text) < 2 or len(text) > 40 or text in _GENERIC_TERMS:
                continue
            if text not in terms:
                terms.append(text)
            if len(terms) >= limit:
                break
        return tuple(terms)

    def _validated(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        canonical = re.sub(r"\s+", " ", str(payload.get("canonical_topic", ""))).strip()
        if canonical in _GENERIC_TERMS:
            canonical = ""
        synonyms = self._clean_terms(payload.get("synonyms"), limit=8)
        search_queries = self._clean_terms(payload.get("search_queries"), limit=5)
        attributes = self._clean_terms(payload.get("attributes"), limit=5)
        if not canonical and not search_queries:
            return None
        return {
            "canonical_topic": canonical[:40],
            "synonyms": list(synonyms),
            "search_queries": list(search_queries),
            "attributes": list(attributes),
        }

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return {}
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}
        return payload if isinstance(payload, dict) else {}

    def expand(self, query: str) -> ExpandedQuery | None:
        if not query.strip() or not getattr(self.llm_client, "enabled", False):
            return None
        cache_key = self._cache_key(query)
        cached = self._get_cached(cache_key)
        if cached:
            validated = self._validated(cached)
            if validated:
                return ExpandedQuery(
                    canonical_topic=validated["canonical_topic"],
                    synonyms=tuple(validated["synonyms"]),
                    search_queries=tuple(validated["search_queries"]),
                    attributes=tuple(validated["attributes"]),
                    cache_hit=True,
                )

        system = (
            "你是工程建设规范检索的术语归一化器。只输出 JSON，不要回答问题。"
            "目标是把用户俗称、简称或口语改写成可用于本地全文检索的专业术语。"
            "输出格式：{\"canonical_topic\":\"\",\"synonyms\":[],"
            "\"search_queries\":[],\"attributes\":[]}。"
            "synonyms最多8个，search_queries最多5个，attributes最多5个。"
            "只保留与问题语义等价或直接相关的技术术语，不得加入规范结论、"
            "数值、标准编号或无关主题。如果无法确定，返回空数组。"
        )
        try:
            response = self.llm_client.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": query},
                ],
                None,
                tool_choice="none",
                max_tokens=self.max_tokens,
            )
            validated = self._validated(
                self._parse_json(str(response.get("content") or ""))
            )
        except Exception as exc:
            logger.warning("query expansion failed, using local fallback: %s", exc)
            return None
        if not validated:
            return None
        self._save_cached(cache_key, query, validated)
        return ExpandedQuery(
            canonical_topic=validated["canonical_topic"],
            synonyms=tuple(validated["synonyms"]),
            search_queries=tuple(validated["search_queries"]),
            attributes=tuple(validated["attributes"]),
        )
