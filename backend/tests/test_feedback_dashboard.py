import base64
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.api import routes as api_routes
from app.main import app


client = TestClient(app)


def _basic_auth(username: str, password: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {encoded}"}


def test_feedback_dashboard_requires_authentication() -> None:
    missing = client.get("/api/admin/feedback/dashboard")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"].startswith("Basic")

    wrong = client.get(
        "/api/admin/feedback/dashboard",
        headers=_basic_auth(api_routes.FEEDBACK_DASHBOARD_USERNAME, "wrong-password"),
    )
    assert wrong.status_code == 401


def test_feedback_dashboard_aggregates_feedback(monkeypatch) -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    rows = [
        {
            "id": uuid.uuid4().hex[:12],
            "user_id": "user-a",
            "rating": "helpful",
            "reason_codes": [],
            "comment": "",
            "question_snapshot": "楼梯踏步宽度",
            "answer_snapshot": "应满足规范要求",
            "intent": "numeric",
            "intent_source": "rules",
            "trace_id": "trace-a",
            "kb_version": "kb@1",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": uuid.uuid4().hex[:12],
            "user_id": "user-a",
            "rating": "not_helpful",
            "reason_codes": ["incomplete", "source_mismatch"],
            "comment": "缺少条文",
            "question_snapshot": "防火分区面积",
            "answer_snapshot": "未给出明确出处",
            "intent": "numeric",
            "intent_source": "rules",
            "trace_id": "trace-b",
            "kb_version": "kb@1",
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": uuid.uuid4().hex[:12],
            "user_id": "user-b",
            "rating": "not_helpful",
            "reason_codes": ["incomplete"],
            "comment": "请补充地方规定",
            "question_snapshot": "住宅疏散距离",
            "answer_snapshot": "仅返回国家标准",
            "intent": "scenario",
            "intent_source": "rules",
            "trace_id": "trace-c",
            "kb_version": "kb@1",
            "created_at": now,
            "updated_at": now,
        },
    ]
    monkeypatch.setattr(api_routes.memory_store, "list_feedback", lambda: rows)

    response = client.get(
        "/api/admin/feedback/dashboard",
        headers=_basic_auth(
            api_routes.FEEDBACK_DASHBOARD_USERNAME,
            api_routes.FEEDBACK_DASHBOARD_PASSWORD,
        ),
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["summary"] == {
        "total": 3,
        "helpful": 1,
        "not_helpful": 2,
        "helpful_rate": 33.3,
        "users": 2,
    }
    assert len(payload["trend"]) == 14
    assert payload["reasons"][0] == {"name": "incomplete", "count": 2}
    assert payload["intents"][0] == {"name": "numeric", "count": 2}
    assert len(payload["recent"]) == 3
    assert payload["recent"][0]["question"] == "楼梯踏步宽度"
