from __future__ import annotations

from typing import Any


def _combined_source_text(sources: list[dict[str, Any]]) -> str:
    return " ".join(
        f"{source.get('standard', '')} {source.get('title', '')} {source.get('snippet', '')}"
        for source in sources
    )


def score_case(
    record: dict[str, Any],
    reply: str,
    sources: list[dict[str, Any]],
    latency_ms: float,
    thresholds: dict[str, float],
    completeness_score: float,
) -> dict[str, Any]:
    expected_source = record.get("expected_source") or []
    expected_keywords = record.get("expected_keywords") or []
    expected_pages = record.get("expected_pages") or []
    source_text = _combined_source_text(sources)

    retrieval_hits = [
        expected
        for expected in expected_source
        if expected
        and any(
            expected in source.get("standard", "") or expected in source.get("title", "")
            for source in sources
        )
    ]
    retrieval = len(retrieval_hits) / len(expected_source) if expected_source else 1.0

    keyword_hits = [
        keyword for keyword in expected_keywords if keyword and (keyword in reply or keyword in source_text)
    ]
    keyword = len(keyword_hits) / len(expected_keywords) if expected_keywords else 1.0

    page_hits = [
        page for page in expected_pages if any(source.get("page") == page for source in sources)
    ]
    source_accuracy = len(page_hits) / len(expected_pages) if expected_pages else 1.0

    failed: list[str] = []
    if expected_source and retrieval < thresholds.get("retrieval", 0.5):
        failed.append("retrieval")
    if expected_keywords and keyword < thresholds.get("keyword", 0.7):
        failed.append("keyword")
    if expected_pages and source_accuracy < thresholds.get("source", 0.5):
        failed.append("source")
    if completeness_score < thresholds.get("completeness", 3.0):
        failed.append("completeness")

    return {
        "retrieval": round(retrieval, 3),
        "keyword": round(keyword, 3),
        "source": round(source_accuracy, 3),
        "completeness": round(completeness_score, 3),
        "latency_ms": round(latency_ms, 1),
        "failed_dimensions": failed,
        "is_bad_case": bool(failed),
    }
