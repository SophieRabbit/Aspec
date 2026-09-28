from __future__ import annotations

import logging
from typing import Any

from .building_type_matcher import (
    BuildingTypeMatch,
    detect_building_types,
    get_building_type,
)


logger = logging.getLogger(__name__)

BUILDING_TYPE_OPTIONS = (
    "住宅建筑",
    "商业建筑",
    "办公建筑",
    "旅馆建筑",
    "医疗建筑",
    "学校建筑",
    "文化建筑",
    "体育建筑",
    "交通建筑",
    "餐饮建筑",
    "娱乐建筑",
    "工业建筑",
    "车库建筑",
    "老年人建筑",
)

TYPE_ALIASES = {
    "教育建筑": "学校建筑",
    "办公类建筑": "办公建筑",
    "工业厂房": "工业建筑",
}


def llm_detect_building_type(
    query: str,
    llm_client: Any | None = None,
) -> str | None:
    if llm_client is None or not getattr(llm_client, "enabled", False):
        return None
    prompt = (
        "请判断以下建筑查询属于哪类建筑，只返回类型名称，不要解释：\n\n"
        f"可选类型：{'、'.join(BUILDING_TYPE_OPTIONS)}\n\n"
        f"查询：{query}"
    )
    try:
        response = llm_client.chat(
            [{"role": "user", "content": prompt}],
            tool_choice="none",
        )
    except Exception as exc:
        logger.warning("LLM building type detection failed: %s", exc)
        return None

    content = str(response.get("content") or "").strip()
    if not content:
        return None
    for option in BUILDING_TYPE_OPTIONS:
        if option in content:
            return option
    for alias, canonical in TYPE_ALIASES.items():
        if alias in content:
            return canonical
    return None


def detect_building_type_with_fallback(
    query: str,
    llm_client: Any | None = None,
) -> tuple[list[BuildingTypeMatch], str]:
    matches = detect_building_types(query)
    if matches:
        return matches, "rule"

    llm_type = llm_detect_building_type(query, llm_client)
    match = get_building_type(llm_type or "")
    if match is not None:
        return [match], "llm"
    return [], "fallback"
