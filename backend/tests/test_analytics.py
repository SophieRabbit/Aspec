from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.api import routes as api_routes
from app.main import app
from app.memory.sql_store import SqlMemoryStore
from services.analytics_dashboard import build_analytics_dashboard


client = TestClient(app)


def test_analytics_events_persist_anonymous_identity() -> None:
    store = SqlMemoryStore("sqlite:///:memory:")
    try:
        accepted = store.add_analytics_events(
            [
                {
                    "event_name": "page_view",
                    "visitor_id": "visitor-a",
                    "session_id": "session-a",
                    "user_id": "visitor-a",
                    "path": "/",
                    "properties": {"page_name": "规范问答"},
                },
                {
                    "event_name": "question_submit",
                    "visitor_id": "visitor-a",
                    "session_id": "session-a",
                    "user_id": "visitor-a",
                    "path": "/",
                    "properties": {"question": "楼梯宽度"},
                },
            ]
        )

        assert accepted == 2
        events = store.list_analytics_events()
        assert len(events) == 2
        assert events[0]["visitor_id"] == "visitor-a"
        page_view = next(event for event in events if event["event_name"] == "page_view")
        assert page_view["properties"]["page_name"] == "规范问答"
    finally:
        store.close()


def test_analytics_dashboard_calculates_pv_uv_and_funnel() -> None:
    now = datetime(2026, 10, 28, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    events = [
        {
            "event_name": "page_view",
            "visitor_id": "visitor-a",
            "session_id": "session-a",
            "created_at": now.isoformat(),
            "properties": {},
        },
        {
            "event_name": "page_view",
            "visitor_id": "visitor-b",
            "session_id": "session-b",
            "created_at": now.isoformat(),
            "properties": {},
        },
        {
            "event_name": "question_submit",
            "visitor_id": "visitor-a",
            "session_id": "session-a",
            "created_at": now.isoformat(),
            "properties": {"question": "楼梯宽度", "request_id": "request-1"},
        },
        {
            "event_name": "answer_complete",
            "visitor_id": "visitor-a",
            "session_id": "session-a",
            "created_at": now.isoformat(),
            "properties": {
                "request_id": "request-1",
                "intent": "numeric",
                "source_count": 3,
                "latency_ms": 120,
            },
        },
        {
            "event_name": "source_open",
            "visitor_id": "visitor-a",
            "session_id": "session-a",
            "created_at": now.isoformat(),
            "properties": {},
        },
        {
            "event_name": "feedback_submit",
            "visitor_id": "visitor-a",
            "session_id": "session-a",
            "created_at": now.isoformat(),
            "properties": {"rating": "helpful"},
        },
    ]

    payload = build_analytics_dashboard(events, now=now)

    assert payload["summary"] == {
        "pv": 2,
        "uv": 2,
        "sessions": 2,
        "questions": 1,
        "answers": 1,
        "answer_errors": 0,
        "source_opens": 1,
        "feedback_submits": 1,
        "answer_rate": 100.0,
        "feedback_rate": 100.0,
    }
    assert payload["trend"][-1]["pv"] == 2
    assert payload["trend"][-1]["uv"] == 2
    assert payload["recent_questions"][0] == {
        "question": "楼梯宽度",
        "intent": "numeric",
        "source_count": 3,
        "latency_ms": 120,
        "status": "answered",
        "created_at": now.isoformat(),
    }


def test_analytics_collection_endpoint_accepts_batch(monkeypatch) -> None:
    captured: list[dict] = []

    def capture(events):
        captured.extend(events)
        return len(events)

    monkeypatch.setattr(api_routes.memory_store, "add_analytics_events", capture)
    response = client.post(
        "/api/analytics/events",
        headers={
            "X-User-Id": "visitor-a",
            "X-Visitor-Id": "visitor-a",
            "X-Session-Id": "session-a",
        },
        json={
            "events": [
                {
                    "name": "question_submit",
                    "path": "/",
                    "conversation_id": "conversation-a",
                    "properties": {
                        "question": "住宅楼梯宽度",
                        "request_id": "request-a",
                    },
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": 1}
    assert captured[0]["visitor_id"] == "visitor-a"
    assert captured[0]["session_id"] == "session-a"
    assert captured[0]["event_name"] == "question_submit"
