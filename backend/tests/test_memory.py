import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.memory.distiller import MemoryDistiller
from app.memory.session_store import LocalSessionStore
from app.memory.sql_store import SqlMemoryStore
from app.memory.store import MemoryStore


client = TestClient(app)


def test_sql_store_persists_raw_messages_and_memory_items(tmp_path: Path) -> None:
    store = SqlMemoryStore(f"sqlite:///{tmp_path / 'memory.db'}")
    conversation = store.create_conversation(user_id="user-a")
    store.add_message(
        conversation_id=conversation["conversation_id"],
        user_id="user-a",
        role="user",
        content="项目地点：昆山市",
        metadata={"custom": "keep-me"},
        trace_id="trace-1",
    )
    store.add_message(
        conversation_id=conversation["conversation_id"],
        user_id="user-a",
        role="assistant",
        content="已记录。",
        trace_id="trace-1",
    )

    messages = store.get_messages(conversation["conversation_id"], "user-a")
    assert len(messages) == 2
    assert messages[0]["content"] == "项目地点：昆山市"
    assert messages[0]["custom"] == "keep-me"
    assert messages[1]["role"] == "assistant"

    first = store.upsert_memory_item(
        user_id="user-a",
        source_conversation_id=conversation["conversation_id"],
        source_message_id=messages[0]["id"],
        text="项目地点：昆山市",
        category="项目信息",
        importance=2,
    )
    second = store.upsert_memory_item(
        user_id="user-a",
        source_conversation_id=conversation["conversation_id"],
        source_message_id=messages[0]["id"],
        text="项目地点：昆山市",
        category="项目信息",
        importance=2,
    )
    assert first["id"] == second["id"]
    assert second["occurrences"] == 2
    assert second["importance"] == 3
    assert store.list_memory_items("user-a")[0]["text"] == "项目地点：昆山市"


def test_memory_store_builds_context_after_distillation(tmp_path: Path) -> None:
    store = MemoryStore(
        database_url=f"sqlite:///{tmp_path / 'memory.db'}",
        redis_url="",
        import_json=False,
    )
    conversation = store.create_conversation(user_id="user-a")
    user_message = store.add_message(
        conversation["conversation_id"],
        "user",
        "项目地点：昆山市，建筑类型：住宅",
        user_id="user-a",
    )
    store.add_message(
        conversation["conversation_id"],
        "assistant",
        "已记录。",
        user_id="user-a",
    )
    store.distill(
        conversation_id=conversation["conversation_id"],
        user_id="user-a",
        user_message_id=user_message["id"],
        user_content="项目地点：昆山市，建筑类型：住宅",
        assistant_content="已记录。",
    )

    memory = store.build_context(conversation["conversation_id"], user_id="user-a")
    assert memory["recent_messages"] == 2
    assert any("昆山" in fact["text"] for fact in memory["facts"])
    assert store.list_distill_jobs("user-a")[0]["status"] == "done"


def test_rule_distiller_extracts_project_facts() -> None:
    facts = MemoryDistiller(enabled=False).extract(
        "本项目是昆山市的商业办公楼，地上18层，耐火等级一级。",
        "",
    )
    assert any("昆山" in fact["text"] for fact in facts)
    assert all(1 <= fact["importance"] <= 5 for fact in facts)


def test_local_session_store_keeps_only_recent_window() -> None:
    store = LocalSessionStore(ttl_seconds=60, keep=3)
    for index in range(5):
        store.push_message("c1", "user-a", {"role": "user", "content": str(index)})
    recent = store.get_recent_messages("c1", "user-a")
    assert [item["content"] for item in recent] == ["2", "3", "4"]
    assert store.delete("c1", "user-a") is True
    assert store.get_recent_messages("c1", "user-a") is None


def test_memory_api_isolates_conversations_by_user() -> None:
    user_a = f"api-a-{uuid.uuid4().hex[:8]}"
    user_b = f"api-b-{uuid.uuid4().hex[:8]}"
    conversation_a = client.post(
        "/api/conversations",
        headers={"X-User-Id": user_a},
    ).json()
    conversation_b = client.post(
        "/api/conversations",
        headers={"X-User-Id": user_b},
    ).json()

    list_a = client.get("/api/conversations", headers={"X-User-Id": user_a}).json()
    assert any(item["conversation_id"] == conversation_a["conversation_id"] for item in list_a)
    assert all(item["user_id"] == user_a for item in list_a)
    assert not any(item["conversation_id"] == conversation_b["conversation_id"] for item in list_a)

    wrong_user_delete = client.delete(
        f"/api/conversations/{conversation_a['conversation_id']}",
        headers={"X-User-Id": user_b},
    ).json()
    assert wrong_user_delete["deleted"] is False

    correct_delete = client.delete(
        f"/api/conversations/{conversation_a['conversation_id']}",
        headers={"X-User-Id": user_a},
    ).json()
    assert correct_delete["deleted"] is True
