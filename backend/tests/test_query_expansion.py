import json
from pathlib import Path

from app.knowledge.loader import KnowledgeBase
from app.knowledge.retriever import Retriever
from app.memory.store import MemoryStore
from services.query_expansion import ExpandedQuery, QueryExpansionService


class FakeExpansionLLM:
    enabled = True
    model = "test-expansion-model"

    def __init__(self) -> None:
        self.calls = 0

    def chat(
        self,
        messages,
        tools=None,
        *,
        tool_choice="auto",
        max_tokens=None,
    ):
        self.calls += 1
        assert max_tokens == 180
        return {
            "content": json.dumps(
                {
                    "canonical_topic": "消防车登高操作场地",
                    "synonyms": ["消防登高场地", "登高救援场地"],
                    "search_queries": ["消防车登高操作场地 长度 宽度"],
                    "attributes": ["尺寸", "距离", "坡度"],
                },
                ensure_ascii=False,
            ),
            "tool_calls": [],
        }


def test_query_expansion_is_short_json_and_cached() -> None:
    llm = FakeExpansionLLM()
    service = QueryExpansionService(llm, max_tokens=180)

    first = service.expand("登高救援用硬化场地尺寸")
    second = service.expand("登高救援用硬化场地尺寸")

    assert first is not None
    assert first.canonical_topic == "消防车登高操作场地"
    assert first.cache_hit is False
    assert second is not None
    assert second.cache_hit is True
    assert llm.calls == 1


def test_query_expansion_cache_persists_across_service_instances(
    tmp_path: Path,
) -> None:
    llm = FakeExpansionLLM()
    cache = MemoryStore(
        database_url=f"sqlite:///{tmp_path / 'query-cache.db'}",
        redis_url="",
        import_json=False,
    )
    first = QueryExpansionService(llm, cache=cache, max_tokens=180).expand(
        "登高救援用硬化场地尺寸"
    )
    second = QueryExpansionService(llm, cache=cache, max_tokens=180).expand(
        "登高救援用硬化场地尺寸"
    )

    assert first is not None
    assert second is not None
    assert second.cache_hit is True
    assert llm.calls == 1


def test_retriever_uses_expanded_terms_before_local_retrieval() -> None:
    retriever = Retriever(KnowledgeBase())

    class Expander:
        def expand(self, query):
            return ExpandedQuery(
                canonical_topic="消防车登高操作场地",
                synonyms=("消防登高场地",),
                search_queries=("消防车登高操作场地 长度 宽度",),
                attributes=("尺寸", "距离"),
            )

    retriever.query_expander = Expander()
    results = retriever.search("登高救援用硬化场地尺寸", top_k=5)

    assert results
    assert results[0]["document"]["standard"] == "GB50016-2014"
    assert results[0]["snippet"]["article"] == "7.2.2"


def test_known_topics_do_not_call_query_expansion() -> None:
    retriever = Retriever(KnowledgeBase())

    class ExpanderMustNotBeCalled:
        def expand(self, query):
            raise AssertionError("known topic should not use LLM expansion")

    retriever.query_expander = ExpanderMustNotBeCalled()
    assert retriever.search("住宅楼梯踏步宽度")[0]["document"]["standard"] == "GB50096-2011"
