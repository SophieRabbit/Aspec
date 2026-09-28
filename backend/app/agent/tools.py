from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any

from ..knowledge.retriever import Retriever
from ..knowledge.region_hierarchy import (
    REGION_ALIASES,
    detect_requested_region,
    region_priority,
)


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
)


def safe_calculate(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError("表达式包含不支持的符号")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise ValueError("表达式仅支持数值")
    return eval(compile(tree, "<expression>", "eval"), {"__builtins__": {}}, {})


def extract_expression(query: str) -> str | None:
    normalized = query.replace("×", "*").replace("÷", "/").replace("＋", "+")
    normalized = normalized.replace("－", "-").replace("：", ":")
    candidates = re.findall(r"[0-9\s]+(?:[+\-*/()%][0-9\s()]+)+", normalized)
    if not candidates:
        return None
    return max(candidates, key=len).strip()


def format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{round(value):,.0f}"
    return f"{value:,.2f}"


def calculate_tool(query: str) -> dict[str, Any]:
    expression = extract_expression(query)
    if not expression:
        return {"expression": None, "result": None, "note": "本次问题未包含可计算的数值表达式"}
    try:
        result = safe_calculate(expression)
    except Exception as exc:
        return {"expression": expression, "result": None, "note": f"计算失败：{exc}"}
    return {
        "expression": expression,
        "result": format_number(result),
        "note": f"{expression} = {format_number(result)}",
    }


def retrieve_tool(
    query: str,
    retriever: Retriever,
    top_k: int = 5,
    requested_region: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    results = retriever.search(
        query,
        top_k=top_k,
        region_scope=requested_region,
    )
    if requested_region is None:
        results = [
            item
            for item in results
            if item["document"].get("region") == "全国"
        ]
    sources: list[dict[str, Any]] = []
    for rank, item in enumerate(results):
        source = retriever.to_source(item)
        source["retrieval_rank"] = rank
        sources.append(source)
    for source in sources:
        document = next(
            (doc for doc in retriever.knowledge_base.documents if doc.get("id") == source["doc_id"]),
            {},
        )
        source["region_priority"] = region_priority(document, requested_region)
    return sources


def compare_tool(
    query: str,
    retriever: Retriever,
    top_k: int = 4,
    requested_region: dict[str, Any] | None = None,
) -> dict[str, Any]:
    documents = retriever.knowledge_base.documents
    mentioned: list[dict[str, Any]] = []
    for document in documents:
        standard = document.get("standard", "")
        title = document.get("title", "")
        if standard and (standard in query or standard.split(" ")[0] in query):
            mentioned.append(document)
        elif title and title in query:
            mentioned.append(document)
    if len(mentioned) < 2:
        results = retriever.search(query, top_k=top_k * 2, region_scope=requested_region)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in results:
            standard = item["document"].get("standard", "未知")
            grouped.setdefault(standard, []).append(item)
        ordered = sorted(grouped.values(), key=len, reverse=True)[:2]
        groups: list[tuple[str, list[dict[str, Any]]]] = []
        for group in ordered:
            groups.append((group[0]["document"].get("standard", "未知"), group))
    else:
        groups = []
        for document in mentioned:
            standard = document.get("standard", "未知")
            groups.append(
                (
                    standard,
                    [
                        item
                        for item in retriever.search(query, top_k=top_k, region_scope=requested_region)
                        if item["document"].get("id") == document.get("id")
                    ],
                )
            )

    lines: list[str] = []
    for standard, items in groups:
        lines.append(f"- {standard}：")
        for item in items[:2]:
            snippet = item["snippet"].get("text", "")
            article = item["snippet"].get("article", "")
            page = item["snippet"].get("page")
            lines.append(f"  第{article}条（第{page}页）{snippet}")
    return {
        "standards": [standard for standard, _ in groups],
        "summary": "\n".join(lines) if lines else "未检索到可对比的规范条文",
    }


def compare_regional_tool(
    query: str,
    regions: list[str],
    retriever: Retriever,
    top_k_per_region: int = 4,
) -> dict[str, Any]:
    """Compare the same topic across multiple regions, grouped by region."""
    groups: list[dict[str, Any]] = []
    all_sources: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()

    for region_name in regions:
        region_scope = detect_requested_region(region_name, retriever.knowledge_base.documents)
        search_query = f"{region_name} {query}".strip()
        sources = retrieve_tool(
            search_query,
            retriever,
            top_k=top_k_per_region * 3,
            requested_region=region_scope,
        )
        local_sources = [
            source
            for source in sources
            if _source_belongs_to_region(source, region_name, region_scope)
        ]

        grouped: dict[str, list[dict[str, Any]]] = {}
        for source in local_sources:
            standard = source.get("standard") or source.get("title") or "未知规范"
            grouped.setdefault(standard, []).append(source)
            source_key = (
                f"{source.get('doc_id')}|{source.get('article')}|{source.get('page')}|{source.get('snippet')[:80]}"
            )
            if source_key not in seen_source_ids:
                seen_source_ids.add(source_key)
                all_sources.append(source)

        groups.append(
            {
                "region": region_name,
                "place": (region_scope or {}).get("place", region_name),
                "available": bool(local_sources),
                "total_sources": len(local_sources),
                "note": "" if local_sources else f"知识库未收录{region_name}相关规范",
                "standards": [
                    {
                        "standard": standard,
                        "count": len(items),
                        "sources": [
                            {
                                "standard": item.get("standard", ""),
                                "title": item.get("title", ""),
                                "chapter": item.get("chapter", ""),
                                "article": item.get("article", ""),
                                "page": item.get("page"),
                                "snippet": str(item.get("snippet", "")),
                            }
                            for item in items[:top_k_per_region]
                        ],
                    }
                    for standard, items in grouped.items()
                ],
            }
        )

    return {
        "query": query,
        "regions": [group["region"] for group in groups],
        "groups": groups,
        "available_region_count": sum(1 for group in groups if group["available"]),
        "sources": all_sources,
    }


def _source_belongs_to_region(
    source: dict[str, Any],
    region_name: str,
    region_scope: dict[str, Any] | None,
) -> bool:
    if source.get("region") == "全国":
        return False
    if source.get("region") == region_name:
        return True
    if region_scope and source.get("region") == region_scope.get("place"):
        return True
    if not region_scope:
        return False
    region = region_scope.get("region") or ""
    if region and source.get("region") in REGION_ALIASES.get(region, (region,)):
        return True
    return False


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def sqrt(value: float) -> float:
    return math.sqrt(value)
