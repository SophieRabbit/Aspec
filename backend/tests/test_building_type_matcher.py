from __future__ import annotations

from app.knowledge.loader import KnowledgeBase
from app.knowledge.keywords import extract_keywords
from app.knowledge.retriever import Retriever
from services.compound_intent import detect_compound_intent
from services.llm_type_matcher import detect_building_type_with_fallback


class FakeTypeLLM:
    enabled = True

    def __init__(self, result: str) -> None:
        self.result = result
        self.calls = 0

    def chat(self, messages, tools=None, *, tool_choice="auto") -> dict:
        self.calls += 1
        return {"content": self.result, "tool_calls": []}


def test_factory_office_and_cold_storage_match_by_rules() -> None:
    factory, factory_source = detect_building_type_with_fallback(
        "厂房内最远点的疏散距离是多少"
    )
    office, office_source = detect_building_type_with_fallback(
        "超高层办公楼疏散距离"
    )
    cold_storage, cold_storage_source = detect_building_type_with_fallback(
        "某冷库的防火分区面积"
    )

    assert [item.name for item in factory] == ["工业建筑"]
    assert factory_source == "rule"
    assert [item.name for item in office] == ["办公建筑"]
    assert office_source == "rule"
    assert [item.name for item in cold_storage] == ["工业建筑"]
    assert cold_storage_source == "rule"


def test_llm_is_only_used_when_rules_do_not_match() -> None:
    llm = FakeTypeLLM("工业建筑")
    rule_matches, rule_source = detect_building_type_with_fallback(
        "厂房内最远点疏散距离",
        llm,
    )
    assert rule_matches
    assert rule_source == "rule"
    assert llm.calls == 0

    matches, source = detect_building_type_with_fallback(
        "某特殊生产设施内的人员疏散距离",
        llm,
    )

    assert llm.calls == 1
    assert [item.name for item in matches] == ["工业建筑"]
    assert source == "llm"


def test_factory_retrieval_is_limited_to_industrial_scope() -> None:
    retriever = Retriever(KnowledgeBase())

    results = retriever.search(
        "厂房内最远点的疏散距离是多少",
        top_k=30,
    )

    standards = [item["document"].get("standard") for item in results]
    assert standards[0] == "GB50016-2014"
    assert "GB55037-2022" in standards
    assert set(standards) <= {"GB50016-2014", "GB55037-2022"}
    assert "3.7.4" in results[0]["text"]
    assert "甲" in results[0]["text"]
    assert "30" in results[0]["text"]
    assert any("7.1.3" in item["text"] for item in results)


def test_factory_distance_principles_remain_available_without_value_request() -> None:
    retriever = Retriever(KnowledgeBase())

    results = retriever.search(
        "厂房疏散距离有哪些要求",
        top_k=30,
    )

    assert results
    assert all(
        item["document"].get("region") == "全国"
        for item in results
    )
    assert {
        item["document"].get("standard")
        for item in results
    } == {"GB50016-2014", "GB55037-2022"}


def test_office_retrieval_is_limited_to_office_scope() -> None:
    retriever = Retriever(KnowledgeBase())

    results = retriever.search(
        "超高层办公楼疏散距离",
        top_k=30,
    )

    assert results
    assert all(
        item["document"].get("region") == "全国"
        for item in results
    )
    assert all(
        item["document"].get("standard") == "GB55037-2022"
        for item in results
    )


def test_cold_storage_retrieval_is_limited_to_industrial_scope() -> None:
    retriever = Retriever(KnowledgeBase())

    results = retriever.search(
        "某冷库的防火分区面积",
        top_k=30,
    )

    assert results
    assert all(
        item["document"].get("region") == "全国"
        for item in results
    )
    standards = {
        item["document"].get("standard")
        for item in results
    }
    assert standards <= {"GB50016-2014", "GB55037-2022"}
    assert "GB55037-2022" in standards


def test_compound_intent_uses_llm_type_for_filtering() -> None:
    llm = FakeTypeLLM("工业建筑")

    intent = detect_compound_intent(
        "某特殊生产设施的防火分区面积",
        llm,
    )

    assert intent.building_type == "工业建筑"
    assert intent.building_type_source == "llm"
    assert intent.attribute == "防火分区"
    assert intent.primary_standards[0] == "GB50016-2014"


def test_factory_distance_keywords_include_type_and_attribute() -> None:
    keywords = extract_keywords("厂房内最远点的疏散距离是多少")
    texts = [item["text"] for item in keywords]

    assert "工业建筑" in texts
    assert "厂房" in texts
    assert "疏散距离" in texts
