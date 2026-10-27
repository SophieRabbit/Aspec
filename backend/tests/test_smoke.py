import uuid

from fastapi.testclient import TestClient

from app.api import routes as api_routes
from app.main import app
from app.schemas import ChatRequest


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_web_search_is_disabled_by_default() -> None:
    request = ChatRequest(message="住宅楼梯踏步宽度有什么要求？")
    assert request.disable_web_search is True


def test_knowledge_status() -> None:
    response = client.get("/api/knowledge/status")
    assert response.status_code == 200
    assert response.json()["document_count"] >= 8


def test_chat_returns_sources() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "住宅楼梯踏步宽度和高度有什么要求？"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"]
    assert len(payload["sources"]) >= 1
    assert payload["reasoning"]
    assert payload["follow_ups"]
    assert payload["keywords"]


def test_chitchat_does_not_return_standards() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "你好啊"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "chitchat"
    assert payload["sources"] == []
    assert payload["recommendations"] == []
    assert payload["keywords"] == []
    assert "你好" in payload["reply"]

    search = client.get("/api/search", params={"q": "你好啊"})
    assert search.status_code == 200
    assert search.json()["items"] == []


def test_uncovered_question_does_not_offer_human_support() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "你知道12星座啊"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "fallback"
    assert payload["intent_label"] == "未覆盖问题"
    assert payload["sources"] == []
    assert "人工" not in payload["reply"]
    assert "工程建设规范" in payload["reply"]


def test_zodiac_question_is_directly_refused_without_zodiac_content() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "你还知道生肖吗"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "fallback"
    assert payload["intent_label"] == "未覆盖问题"
    assert payload["sources"] == []
    assert payload["follow_ups"] == []
    assert payload["reply"] == api_routes.OUT_OF_SCOPE_REPLY
    for unrelated_content in ("十二生肖", "属相", "鼠", "牛", "虎", "兔"):
        assert unrelated_content not in payload["reply"]


def test_hong_kong_request_returns_mainland_scope_notice_without_retrieval(
    monkeypatch,
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("knowledge retrieval must not run outside mainland China")

    monkeypatch.setattr(api_routes.planner, "run", fail_if_called)
    monkeypatch.setattr(api_routes.planner, "format_search_list", fail_if_called)

    response = client.post(
        "/api/chat",
        json={"message": "给我找找香港的踏步规范"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "outside_region"
    assert payload["intent_label"] == "中国大陆以外"
    assert payload["sources"] == []
    assert payload["recommendations"] == []
    assert payload["keywords"] == []
    assert payload["web_results"] == []
    assert payload["follow_ups"] == []
    assert "仅限中国大陆地区" in payload["reply"]
    assert "香港不属于该范围" in payload["reply"]
    assert "未检索知识库" in payload["reply"]
    assert "GB55031" not in payload["reply"]

    search = client.get("/api/search", params={"q": "香港的踏步规范"})
    assert search.status_code == 200
    assert search.json()["items"] == []


def test_tokyo_request_returns_mainland_scope_notice() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "帮我查查东京的建筑规范"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "outside_region"
    assert payload["sources"] == []
    assert payload["recommendations"] == []
    assert "东京不属于该范围" in payload["reply"]


def test_feedback_round_trip_and_update() -> None:
    user_id = f"feedback-{uuid.uuid4().hex[:8]}"
    headers = {"X-User-Id": user_id}
    chat = client.post(
        "/api/chat",
        headers=headers,
        json={
            "message": "住宅楼梯踏步宽度有什么要求？",
            "disable_web_search": True,
        },
    ).json()
    assert chat["message_id"]

    feedback_payload = {
        "conversation_id": chat["conversation_id"],
        "message_id": chat["message_id"],
        "trace_id": chat["trace_id"],
        "rating": "not_helpful",
        "reason_codes": ["incomplete"],
        "comment": "希望补充条文出处",
    }
    first = client.post("/api/feedback", headers=headers, json=feedback_payload)
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["rating"] == "not_helpful"
    assert first_payload["reason_codes"] == ["incomplete"]

    second = client.post(
        "/api/feedback",
        headers=headers,
        json={**feedback_payload, "reason_codes": ["wrong_clause", "incomplete"]},
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["id"] == first_payload["id"]
    assert second_payload["reason_codes"] == ["wrong_clause", "incomplete"]

    messages = client.get(
        f"/api/conversations/{chat['conversation_id']}/messages",
        headers=headers,
    ).json()
    assistant = next(item for item in messages if item["role"] == "assistant")
    assert assistant["id"] == chat["message_id"]
    assert assistant["feedback"]["id"] == first_payload["id"]


def test_feedback_rejects_another_users_message() -> None:
    owner = f"feedback-owner-{uuid.uuid4().hex[:8]}"
    other = f"feedback-other-{uuid.uuid4().hex[:8]}"
    chat = client.post(
        "/api/chat",
        headers={"X-User-Id": owner},
        json={"message": "你好", "disable_web_search": True},
    ).json()
    response = client.post(
        "/api/feedback",
        headers={"X-User-Id": other},
        json={
            "conversation_id": chat["conversation_id"],
            "message_id": chat["message_id"],
            "rating": "helpful",
        },
    )
    assert response.status_code == 404


def test_feedback_export_requires_admin_token(monkeypatch) -> None:
    monkeypatch.setattr(api_routes, "FEEDBACK_ADMIN_TOKEN", "test-feedback-token")
    denied = client.get("/api/feedback/export")
    assert denied.status_code == 403

    exported = client.get(
        "/api/feedback/export",
        headers={"X-Feedback-Admin-Token": "test-feedback-token"},
    )
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    assert "rating" in exported.text


def test_document_context() -> None:
    chat = client.post(
        "/api/chat",
        json={"message": "住宅楼梯踏步宽度和高度有什么要求？"},
    ).json()
    doc_id = chat["sources"][0]["doc_id"]
    response = client.get(
        f"/api/knowledge/documents/{doc_id}/context",
        params={"query": "楼梯踏步宽度"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["matches"]
    assert payload["query_terms"]


def test_region_scope_only_returns_national_for_unknown_local() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "昆山市住宅楼梯踏步宽度和高度有什么要求？"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"]
    allowed_regions = {"全国", "江苏省", "华东地区"}
    assert all(source["region"] in allowed_regions for source in payload["sources"])
    assert "未找到" not in payload["reply"]
    assert "暂未收录" in payload["reply"]


def test_province_without_local_topic_keeps_notice_in_reply() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "帮我查一下河北省的踏步相关规范。"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"]
    assert "河北省" in payload["reply"]
    assert "踏步" in payload["reply"]
    assert "未收录" in payload["reply"]


def test_follow_up_inherits_previous_topic() -> None:
    first = client.post(
        "/api/chat",
        json={"message": "住宅项目规范对楼梯踏步有什么要求？"},
    ).json()
    second = client.post(
        "/api/chat",
        json={
            "conversation_id": first["conversation_id"],
            "message": "这条规定在民用建筑通用规范中有没有更严格的要求？",
        },
    ).json()
    assert any(keyword["text"] == "踏步" for keyword in second["keywords"])
    assert second["reply"] != first["reply"]
