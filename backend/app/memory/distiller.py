from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from ..config import (
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_MODEL,
    MEMORY_LLM_ENABLED,
    MEMORY_LLM_TIMEOUT_SECONDS,
    MEMORY_MAX_FACTS_PER_TURN,
)

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = ("项目信息", "用户偏好", "约束条件", "上下文")
DEFAULT_CATEGORY = "项目信息"

_RULE_PATTERNS = [
    re.compile(
        r"(项目(?:名称|类型|地点|地区|位置|性质|用途|规模))[:：\s]*([^，。；\n]{1,40})"
    ),
    re.compile(
        r"(建筑面积|套内面积|建筑高度|总高度|层高|层数|耐火等级|建筑类别|防火分区面积)"
        r"[:：]?\s*([^，。；\n]{1,40})"
    ),
    re.compile(
        r"((?:本项目|这个项目|该建筑|住宅|办公楼|医院|学校|厂房|商业建筑)"
        r"(?:是|为|位于|在|属于|采用|使用|建筑面积|建筑高度|层数|耐火等级)"
        r"[^，。；\n]{1,34})"
    ),
    re.compile(r"(用户(?:更)?(?:偏好|倾向|希望|要求)(?:使用|采用|遵循|按)?[^，。；\n]{1,40})"),
    re.compile(r"(项目所在地|项目地址|建设地点|项目区域)[:：\s]*([^，。；\n]{1,40})"),
]


class MemoryDistiller:
    """Extracts durable, structured memory from a conversation turn."""

    def __init__(
        self,
        *,
        api_base: str = LLM_API_BASE,
        api_key: str = LLM_API_KEY,
        model: str = LLM_MODEL,
        enabled: bool = MEMORY_LLM_ENABLED,
        timeout_seconds: float = MEMORY_LLM_TIMEOUT_SECONDS,
        max_facts_per_turn: int = MEMORY_MAX_FACTS_PER_TURN,
    ) -> None:
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.max_facts_per_turn = max_facts_per_turn

    @property
    def _can_use_llm(self) -> bool:
        return bool(self.enabled and self.api_base and self.api_key)

    def extract(
        self,
        user_message: str,
        assistant_message: str,
    ) -> list[dict[str, Any]]:
        if self._can_use_llm:
            try:
                return self._extract_with_llm(user_message, assistant_message)
            except Exception as exc:
                logger.warning("LLM memory distillation failed, using rules: %s", exc)
        return self._extract_with_rules(user_message)

    def _extract_with_llm(self, user_message: str, assistant_message: str) -> list[dict[str, Any]]:
        base = self.api_base.rstrip("/")
        if base.endswith("/chat/completions"):
            url = base
        else:
            url = f"{base}/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是工程规范咨询平台的结构化记忆提炼器。"
                        "从用户与助手的对话中提炼值得长期保留的事实，用于后续多轮对话。"
                        "只输出 JSON，格式为 {\"facts\":[{\"text\":\"事实文本\","
                        "\"category\":\"项目信息|用户偏好|约束条件|上下文\","
                        "\"importance\":1到5的整数}]}。"
                        "不要提取临时提问本身；只提取项目名称、地点、建筑类型、规模、层数、"
                        "耐火等级、当地标准、用户偏好等。每条事实独立、短小、可直接阅读。"
                        "最多 12 条，不要编造对话中不存在的细节。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"用户消息：\n{user_message}\n\n助手回复：\n{assistant_message}",
                },
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        return self._parse_facts(content)

    def _parse_facts(self, content: str) -> list[dict[str, Any]]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)
        if isinstance(data, dict):
            raw_items = data.get("facts", [])
        elif isinstance(data, list):
            raw_items = data
        else:
            return []

        facts: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in raw_items[: self.max_facts_per_turn]:
            if not isinstance(raw, dict):
                continue
            text = str(raw.get("text") or raw.get("fact") or "").strip()
            if not text or len(text) < 4:
                continue
            category = str(raw.get("category", DEFAULT_CATEGORY)).strip()
            if category not in ALLOWED_CATEGORIES:
                category = DEFAULT_CATEGORY
            try:
                importance = int(raw.get("importance", 2))
            except (TypeError, ValueError):
                importance = 2
            normalized = re.sub(r"\s+", "", text).lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            facts.append(
                {
                    "text": text[:120],
                    "category": category,
                    "importance": max(1, min(5, importance)),
                }
            )
        return facts

    @staticmethod
    def _extract_with_rules(user_message: str) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        seen: set[str] = set()
        for pattern in _RULE_PATTERNS:
            for match in pattern.finditer(user_message):
                label = match.group(1)
                value = match.group(2) if match.lastindex and match.lastindex >= 2 else label
                text = f"{label}：{value}" if value != label else label
                if len(text) < 6:
                    continue
                normalized = re.sub(r"\s+", "", text).lower()
                if normalized in seen:
                    continue
                seen.add(normalized)
                facts.append(
                    {
                        "text": text[:120],
                        "category": DEFAULT_CATEGORY,
                        "importance": 2,
                    }
                )
        return facts[:MEMORY_MAX_FACTS_PER_TURN]
