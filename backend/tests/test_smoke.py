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
    assert len(payload["sources"]) >= 8
    assert payload["reasoning"]
    assert payload["follow_ups"]
    assert payload["keywords"]


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
    assert "未找到【昆山市】" in payload["reply"]


def test_standard_recommendations() -> None:
    response = client.get(
        "/api/standards/recommend",
        params={"query": "GB 50016-2014 建筑设计防火规范"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] > 0
    categories = [group["category"] for group in payload["categories"]]
    assert "建筑设计" not in categories


def test_required_domain_term_filters_sunlight() -> None:
    response = client.post(
        "/api/chat",
        json={"message": "帮我查查山西省的日照标准"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"]
    assert any("日照" in source["title"] for source in payload["sources"])
    assert not any("太阳能" in source["title"] for source in payload["sources"][:5])
    assert any(item["level"] == "华北地区" for item in payload["region_path"])


def test_follow_up_inherits_previous_region_and_topic() -> None:
    first = client.post(
        "/api/chat",
        json={"message": "帮我查查山西省的日照标准"},
    ).json()
    second = client.post(
        "/api/chat",
        json={
            "conversation_id": first["conversation_id"],
            "message": "这条规定在地方标准中有没有更严格的要求？",
        },
    ).json()
    assert any(item["level"] == "山西省" for item in second["region_path"])
    assert any(keyword["text"] == "日照" for keyword in second["keywords"])
    assert "地方标准" in second["reply"] or "更严格" in second["reply"]
    assert second["reply"] != first["reply"]
