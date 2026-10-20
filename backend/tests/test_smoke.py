from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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
