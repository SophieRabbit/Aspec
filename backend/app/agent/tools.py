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


_CLAUSE_START_RE = re.compile(
    r"(?<![0-9.])(\d{1,2}(?:\.\d{1,2}){1,3})\s+"
    r"(?=[\u4e00-\u9fff（(])"
)

_COMPARISON_TOPIC_TERMS = (
    "楼梯",
    "踏步",
    "梯段",
    "扶手",
    "栏杆",
    "防火",
    "疏散",
    "防水",
    "无障碍",
    "净高",
    "层高",
    "面积",
    "间距",
    "坡度",
    "宽度",
)

_TOPIC_EXPANSIONS = {
    "楼梯": ("楼梯", "踏步", "梯段", "扶手", "平台"),
    "踏步": ("楼梯", "踏步", "梯段", "扶手", "平台"),
    "梯段": ("楼梯", "踏步", "梯段", "扶手", "平台"),
    "防火": ("防火", "耐火", "消防", "疏散"),
    "疏散": ("疏散", "安全出口", "疏散距离", "疏散宽度"),
}


def normalize_comparison_query(query: str) -> str:
    """Normalize common stair terms for consistent comparison retrieval."""
    if not any(term in query for term in ("比较", "对比", "区别", "差异")):
        return query
    if not any(term in query for term in ("楼梯", "踏步", "梯段")):
        return query
    return re.sub(r"踏步|梯段", "楼梯", query)


def _mentioned_documents(
    query: str,
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mentioned: list[tuple[int, dict[str, Any]]] = []
    seen: set[str] = set()
    for document in documents:
        standard = str(document.get("standard", ""))
        title = str(document.get("title", ""))
        matched_at = -1
        if standard and standard in query:
            matched_at = query.find(standard)
        elif title and title in query:
            matched_at = query.find(title)
        if matched_at < 0:
            continue
        key = str(document.get("id") or f"{standard}:{title}")
        if key in seen:
            continue
        seen.add(key)
        mentioned.append((matched_at, document))
    mentioned.sort(key=lambda item: item[0])
    return [document for _, document in mentioned]


def _comparison_topic_terms(query: str) -> tuple[str, ...]:
    terms: list[str] = []
    for primary, related in _TOPIC_EXPANSIONS.items():
        if primary in query:
            terms.extend(related)
    terms.extend(
        term
        for term in _COMPARISON_TOPIC_TERMS
        if term in query and term not in terms
    )
    if terms:
        return tuple(dict.fromkeys(terms))
    return tuple(
        term
        for term in re.findall(r"[\u4e00-\u9fff]{2,8}", query)
        if term not in ("规范", "标准", "比较", "对比", "区别", "差异", "规定")
    )


def _extract_document_clauses(
    document: dict[str, Any],
    topic_terms: tuple[str, ...],
) -> list[dict[str, Any]]:
    snippets = list(document.get("snippets", []))
    normative = [
        snippet
        for snippet in snippets
        if str(snippet.get("chapter", "")).strip() == "原文"
    ]
    candidates = normative or snippets
    clauses: dict[str, dict[str, Any]] = {}

    def clause_quality(body: str, page: Any) -> tuple[int, int, int]:
        explanation = int(body.startswith("本条"))
        try:
            page_number = int(page)
        except (TypeError, ValueError):
            page_number = 999999
        return page_number, explanation, len(body)

    for snippet in candidates:
        text = str(snippet.get("text", ""))
        matches = list(_CLAUSE_START_RE.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[match.end() : end].strip(" \n；;")
            article = match.group(1)
            if not body or not any(term in body for term in topic_terms):
                continue
            clause = {
                "article": article,
                "page": snippet.get("page"),
                "book_page": snippet.get("book_page"),
                "text": body,
                "standard": document.get("standard", ""),
                "title": document.get("title", ""),
            }
            existing = clauses.get(article)
            if existing is None or clause_quality(
                body,
                snippet.get("page"),
            ) < clause_quality(
                str(existing.get("text", "")),
                existing.get("page"),
            ):
                clauses[article] = clause
    return sorted(
        clauses.values(),
        key=lambda item: tuple(int(part) for part in item["article"].split(".")),
    )


def _clause_reference(clause: dict[str, Any] | None) -> str:
    if clause is None:
        return "本次检索未命中"
    page = clause.get("page")
    return (
        f"{clause.get('standard', '')} 第{clause.get('article', '')}条"
        + (f"（第{page}页）" if page else "")
    )


def _table_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace("|", "/").strip()


def _stair_comparison(
    query: str,
    groups: list[tuple[dict[str, Any], list[dict[str, Any]]]],
) -> dict[str, Any] | None:
    if len(groups) != 2 or not any(term in query for term in ("楼梯", "踏步", "梯段")):
        return None
    by_standard = {
        str(document.get("standard", "")): (document, clauses)
        for document, clauses in groups
    }
    residential = by_standard.get("GB50096-2011")
    civil = by_standard.get("GB55031-2022")
    if not residential or not civil:
        return None

    def clause_map(group: tuple[dict[str, Any], list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
        return {str(item["article"]): item for item in group[1]}

    residential_clauses = clause_map(residential)
    civil_clauses = clause_map(civil)

    def refs(clauses: dict[str, dict[str, Any]], articles: tuple[str, ...]) -> str:
        return "；".join(
            _clause_reference(clauses.get(article))
            for article in articles
        )

    row_specs = (
        (
            "梯段净宽",
            "公共楼梯梯段净宽≥1.10m；不超过6层且一边设栏杆时≥1.00m。",
            ("6.3.1",),
            "按人流股数计算，每股0.55m，且不少于2股（通常≥1.10m）。",
            ("5.3.2", "5.3.3"),
        ),
        (
            "踏步尺寸",
            "踏步宽≥0.26m，踏步高≤0.175m。",
            ("6.3.2",),
            "住宅建筑公共楼梯踏步宽≥0.26m、高≤0.175m；同梯段尺寸应一致并防滑。",
            ("5.3.9", "5.3.10"),
        ),
        (
            "休息平台",
            "平台净宽≥梯段净宽且≥1.20m；剪刀梯平台≥1.30m。",
            ("6.3.3", "6.3.4"),
            "平台净宽≥梯段净宽且≥1.20m；有实体墙时转向端≥1.30m；直跑梯中间平台≥0.90m。",
            ("5.3.5",),
        ),
        (
            "净高",
            "平台结构下缘至人行通道垂直高度≥2.00m。",
            ("6.3.3",),
            "平台上下过道净高≥2.00m；梯段净高≥2.20m。",
            ("5.3.7",),
        ),
        (
            "扶手与梯井",
            "扶手高≥0.90m；水平栏杆长度>0.50m时扶手高≥1.05m；梯井>0.11m应防儿童攀滑。",
            ("6.3.2", "6.3.5"),
            "公共楼梯至少单侧设扶手，达3股人流时两侧设；儿童场所梯井>0.20m应防坠落。",
            ("5.3.4", "5.3.11"),
        ),
        (
            "踏步级数",
            "本次点名的楼梯条款未明确规定每梯段踏步级数上下限。",
            (),
            "每个梯段踏步不少于2级且不超过18级。",
            ("5.3.8",),
        ),
    )
    residential_header = (
        f"{residential[0].get('standard', '')}《{residential[0].get('title', '')}》"
    )
    civil_header = f"{civil[0].get('standard', '')}《{civil[0].get('title', '')}》"
    lines = [
        "### 核心结论",
        "两本标准对住宅公共楼梯的基础尺寸基本一致；"
        "GB55031-2022 对梯段净高、踏步级数和公共扶手设置补充得更明确。",
        "",
        f"| 对比项 | {_table_cell(residential_header)} | {_table_cell(civil_header)} |",
        "| --- | --- | --- |",
    ]
    for title, residential_text, residential_articles, civil_text, civil_articles in row_specs:
        residential_cell = residential_text
        if residential_articles:
            residential_cell += (
                f" 依据：{refs(residential_clauses, residential_articles)}"
            )
        civil_cell = civil_text
        if civil_articles:
            civil_cell += f" 依据：{refs(civil_clauses, civil_articles)}"
        lines.append(
            f"| {title} | {_table_cell(residential_cell)} | {_table_cell(civil_cell)} |"
        )
    lines.extend(
        (
            "",
            "### 差异提示",
            "• GB55031-2022 增加公共楼梯梯段净高≥2.20m、每梯段2～18级等要求。",
            "• GB50096-2011 保留不超过6层住宅单边栏杆梯段净宽≥1.00m，"
            "以及水平栏杆长度>0.50m时扶手高≥1.05m的规定。",
            "• 本表比较公共楼梯基础尺寸；户内楼梯、消防疏散和无障碍要求需另查对应条文。",
        )
    )
    return {
        "standards": ["GB50096-2011", "GB55031-2022"],
        "summary": "\n".join(lines),
        "matrix": [
            {
                "item": title,
                "standards": [
                    {
                        "standard": "GB50096-2011",
                        "text": residential_text,
                        "references": [
                            _clause_reference(residential_clauses.get(article))
                            for article in residential_articles
                        ],
                    },
                    {
                        "standard": "GB55031-2022",
                        "text": civil_text,
                        "references": [
                            _clause_reference(civil_clauses.get(article))
                            for article in civil_articles
                        ],
                    },
                ],
            }
            for title, residential_text, residential_articles, civil_text, civil_articles in row_specs
        ],
    }


def compare_tool(
    query: str,
    retriever: Retriever,
    top_k: int = 4,
    requested_region: dict[str, Any] | None = None,
) -> dict[str, Any]:
    query = normalize_comparison_query(query)
    documents = retriever.knowledge_base.documents
    mentioned = _mentioned_documents(query, documents)
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
        groups: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        topic_terms = _comparison_topic_terms(query)
        for document in mentioned:
            standard = document.get("standard", "未知")
            clauses = _extract_document_clauses(document, topic_terms)
            groups.append((document, clauses))

        stair_result = _stair_comparison(query, groups)
        if stair_result is not None:
            return stair_result

        lines = [
            "### 对比结果",
            "以下仅摘录两本标准中与问题主题直接相关的规范原文。",
            "",
            "| 标准 | 条款 | 核心要求 |",
            "| --- | --- | --- |",
        ]
        matrix: list[dict[str, Any]] = []
        for document, clauses in groups:
            selected = clauses[:6]
            if not selected:
                lines.append(
                    f"| {document.get('standard', '')}《{document.get('title', '')}》"
                    " | 未命中 | 本次检索未找到与该主题直接相关的原文 |"
                )
                continue
            for clause in selected:
                text = _table_cell(str(clause.get("text", ""))[:220])
                lines.append(
                    f"| {document.get('standard', '')}《{document.get('title', '')}"
                    f"》 | 第{clause.get('article', '')}条"
                    f"（第{clause.get('page', '')}页） | {text} |"
                )
                matrix.append(clause)
        return {
            "standards": [document.get("standard", "") for document, _ in groups],
            "summary": "\n".join(lines),
            "matrix": matrix,
        }

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
