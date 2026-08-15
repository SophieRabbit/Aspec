from __future__ import annotations

import json
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

from ..agent.planner import Planner
from ..config import (
    EVAL_DATASET_DIR,
    EVAL_REPORTS_DIR,
    EVAL_THRESHOLDS,
)
from ..knowledge.loader import KnowledgeBase
from ..knowledge.retriever import Retriever
from .advice import generate_advice
from .judge import completeness_score
from .reporter import generate_report
from .scoring import score_case
from .store import EvalStore


def load_dataset(dataset_id: str) -> list[dict[str, Any]]:
    path = EVAL_DATASET_DIR / f"{dataset_id}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"评测集不存在：{path}")
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def run_evaluation(
    dataset_id: str,
    limit: int | None = None,
    thresholds: dict[str, float] | None = None,
    include_user_feedback: bool = True,
) -> dict[str, Any]:
    store = EvalStore()
    run_id = store.create_run(dataset_id)
    records = load_dataset(dataset_id)
    if limit:
        records = records[:limit]
    if include_user_feedback:
        for feedback in store.list_user_feedback_cases():
            records.append(
                {
                    "id": f"user-{feedback['trace_id'][:8]}",
                    "category": "用户反馈",
                    "question": feedback["question"],
                    "expected_source": [],
                    "expected_keywords": [],
                    "expected_pages": [],
                    "notes": feedback.get("user_note", ""),
                }
            )

    thresholds = {**EVAL_THRESHOLDS, **(thresholds or {})}
    knowledge_base = KnowledgeBase()
    retriever = Retriever(knowledge_base)
    planner = Planner(retriever)
    results: list[dict[str, Any]] = []
    latencies: list[float] = []

    for record in records:
        question = record["question"]
        trace_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        result = planner.run(question, enable_web_search=False)
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)

        metrics = score_case(
            record,
            result["reply"],
            result["sources"],
            latency_ms,
            thresholds,
            completeness_score(question, result["reply"], record.get("expected_keywords", [])),
        )
        result_item = {
            "case_id": record.get("id", ""),
            "category": record.get("category", ""),
            "question": question,
            "expected_source": record.get("expected_source", []),
            "expected_keywords": record.get("expected_keywords", []),
            "expected_pages": record.get("expected_pages", []),
            "actual_reply": result["reply"],
            "sources": result["sources"],
            "metrics": metrics,
            "is_bad_case": metrics["is_bad_case"],
            "failed_dimensions": metrics["failed_dimensions"],
            "trace_id": trace_id,
        }
        store.save_result(run_id, result_item)
        store.save_trace(
            trace_id,
            {"message": question, "eval_run": run_id},
            {"reply": result["reply"], "sources": result["sources"]},
            latency_ms,
        )
        if metrics["is_bad_case"]:
            store.add_bad_case(
                question=question,
                actual_reply=result["reply"],
                expected_reply="",
                failed_dimensions=metrics["failed_dimensions"],
                source="eval",
                trace_id=trace_id,
                run_id=run_id,
            )
        results.append(result_item)

    metrics = {
        "retrieval_hit_rate": _mean(results, "retrieval"),
        "keyword_coverage": _mean(results, "keyword"),
        "source_accuracy": _mean(results, "source"),
        "avg_completeness": _mean(results, "completeness"),
        "latency_p50": round(statistics.median(latencies), 1) if latencies else 0,
        "latency_p95": _percentile(latencies, 95),
        "bad_case_count": sum(1 for result in results if result["is_bad_case"]),
    }

    previous = store.previous_metrics(dataset_id, run_id)
    regressions: dict[str, float] = {}
    if previous:
        for key in ("retrieval_hit_rate", "keyword_coverage", "source_accuracy", "avg_completeness"):
            if key in previous and key in metrics:
                delta = metrics[key] - previous[key]
                if delta < -0.05:
                    regressions[key] = round(delta, 3)

    advice = generate_advice(results)
    report_path = generate_report(
        run_id,
        dataset_id,
        metrics,
        results,
        regressions,
        EVAL_REPORTS_DIR / f"run_{run_id}.html",
        advice,
    )
    store.finish_run(run_id, metrics, report_path, regressions, advice)
    return {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "status": "finished",
        "metrics": metrics,
        "bad_case_count": metrics["bad_case_count"],
        "report_path": report_path,
        "regressions": regressions,
        "advice": advice,
    }


def _mean(results: list[dict[str, Any]], key: str) -> float:
    if not results:
        return 0.0
    values = [result["metrics"][key] for result in results]
    return round(sum(values) / len(values), 3)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * percentile / 100))
    return round(ordered[index], 1)
