from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo


def _event_time(event: dict[str, Any]) -> datetime | None:
    text = str(event.get("created_at", "")).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _properties(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("properties")
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_analytics_dashboard(
    events: list[dict[str, Any]],
    *,
    days: int = 14,
    now: datetime | None = None,
) -> dict[str, Any]:
    shanghai = ZoneInfo("Asia/Shanghai")
    generated_at = (now or datetime.now(shanghai)).astimezone(shanghai)
    day_count = max(1, days)
    daily: dict[str, dict[str, Any]] = {}
    daily_visitors: dict[str, set[str]] = {}
    for offset in range(day_count - 1, -1, -1):
        day = (generated_at - timedelta(days=offset)).date()
        key = day.isoformat()
        daily[key] = {
            "date": day.strftime("%m-%d"),
            "pv": 0,
            "uv": 0,
            "questions": 0,
            "answers": 0,
        }
        daily_visitors[key] = set()

    visitors: set[str] = set()
    sessions: set[str] = set()
    question_events: list[dict[str, Any]] = []
    answers_by_request: dict[str, dict[str, Any]] = {}
    intent_counts: Counter[str] = Counter()
    counts = Counter()

    for event in events:
        name = str(event.get("event_name", ""))
        visitor_id = str(event.get("visitor_id", "")).strip()
        session_id = str(event.get("session_id", "")).strip()
        if visitor_id:
            visitors.add(visitor_id)
        if session_id:
            sessions.add(session_id)
        counts[name] += 1
        if name == "question_submit":
            question_events.append(event)
        if name == "answer_complete":
            properties = _properties(event)
            request_id = str(properties.get("request_id", "")).strip()
            if request_id:
                answers_by_request[request_id] = event
            intent = str(properties.get("intent", "")).strip()
            if intent:
                intent_counts[intent] += 1

        event_time = _event_time(event)
        if event_time is None:
            continue
        day_key = event_time.astimezone(shanghai).date().isoformat()
        if day_key not in daily:
            continue
        point = daily[day_key]
        if visitor_id:
            daily_visitors[day_key].add(visitor_id)
        if name == "page_view":
            point["pv"] += 1
        elif name == "question_submit":
            point["questions"] += 1
        elif name == "answer_complete":
            point["answers"] += 1

    for day_key, point in daily.items():
        point["uv"] = len(daily_visitors[day_key])

    questions = counts["question_submit"]
    answers = counts["answer_complete"]
    feedback_submits = counts["feedback_submit"]
    recent_questions: list[dict[str, Any]] = []
    question_events.sort(
        key=lambda item: _event_time(item) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    for event in question_events[:20]:
        properties = _properties(event)
        request_id = str(properties.get("request_id", "")).strip()
        answer = answers_by_request.get(request_id, {})
        answer_properties = _properties(answer)
        recent_questions.append(
            {
                "question": str(properties.get("question", ""))[:500],
                "intent": str(answer_properties.get("intent", "")),
                "source_count": _safe_int(answer_properties.get("source_count")),
                "latency_ms": _safe_int(answer_properties.get("latency_ms")),
                "status": "answered" if answer else "submitted",
                "created_at": str(event.get("created_at", "")),
            }
        )

    return {
        "generated_at": generated_at.isoformat(),
        "summary": {
            "pv": counts["page_view"],
            "uv": len(visitors),
            "sessions": len(sessions),
            "questions": questions,
            "answers": answers,
            "answer_errors": counts["answer_error"],
            "source_opens": counts["source_open"],
            "feedback_submits": feedback_submits,
            "answer_rate": round(answers / questions * 100, 1) if questions else 0.0,
            "feedback_rate": round(feedback_submits / answers * 100, 1) if answers else 0.0,
        },
        "trend": list(daily.values()),
        "intents": [
            {"name": name, "count": count}
            for name, count in intent_counts.most_common(10)
        ],
        "recent_questions": recent_questions,
    }
