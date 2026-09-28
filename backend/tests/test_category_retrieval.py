from __future__ import annotations

from app.knowledge.loader import KnowledgeBase
from app.knowledge.keywords import extract_keywords
from app.knowledge.region_hierarchy import detect_requested_region
from app.knowledge.retriever import (
    EVACUATION_TERMS,
    WIDTH_TERMS,
    Retriever,
    _has_nearby_terms,
)
from app.agent.planner import Planner
from services.compound_intent import detect_compound_intent


def test_commercial_building_evacuation_retrieval_hits_category() -> None:
    retriever = Retriever(KnowledgeBase())

    results = retriever.search(
        "商业建筑疏散宽度怎么计算",
        top_k=20,
    )

    assert results
    texts = [item["text"] for item in results]
    titles = [item["document"].get("title", "") for item in results]
    assert any("商店" in text or "营业厅" in text for text in texts)
    assert any("商店建筑" in title for title in titles)
    assert len({item["document"].get("standard", "") for item in results}) <= 6
    assert results[0]["document"].get("title") == "商店建筑设计规范"
    standards = {item["document"].get("standard", "") for item in results}
    assert "GB55037-2022" in standards
    assert "GB50016-2006" not in standards
    assert "JGJ/T67-2019" not in standards


def test_chengdu_query_keeps_national_results_when_local_missing() -> None:
    retriever = Retriever(KnowledgeBase())
    query = "成都商业建筑疏散宽度怎么计算"
    intent = detect_compound_intent(query)

    results = retriever.search(
        query,
        top_k=20,
        region_scope=intent.region_scope,
    )

    assert results
    standards = {item["document"].get("standard", "") for item in results}
    assert "JGJ48-2014" in standards
    assert "GB50016-2006" not in standards
    assert "GB55037-2022" in standards
    assert any(
        item["document"].get("region") == "四川省"
        for item in results
    )


def test_width_without_nearby_evacuation_is_not_relevant() -> None:
    unrelated = "过道宽度不应小于1.20m。" + "其他说明。" * 80 + "疏散出口数量应符合规定。"
    related = "疏散楼梯的净宽度不应小于1.10m。"

    assert not _has_nearby_terms(
        unrelated,
        EVACUATION_TERMS,
        WIDTH_TERMS,
    )
    assert _has_nearby_terms(
        related,
        EVACUATION_TERMS,
        WIDTH_TERMS,
    )


def test_commercial_stair_dimension_prioritizes_jgj48_and_filters_obsolete() -> None:
    retriever = Retriever(KnowledgeBase())

    results = retriever.search(
        "商业建筑疏散楼梯的尺寸",
        top_k=20,
    )

    assert results
    assert results[0]["document"].get("standard") == "JGJ48-2014"
    standards = [item["document"].get("standard", "") for item in results]
    assert "GB50016-2006" not in standards
    assert (
        standards.index("JGJ48-2014")
        < standards.index("GB55031-2022")
        < standards.index("GB55037-2022")
    )


def test_standard_list_prioritizes_jgj48_and_hides_obsolete() -> None:
    planner = Planner(Retriever(KnowledgeBase()))

    payload = planner.format_search_list("商业建筑疏散楼梯的尺寸")
    items = payload["items"]

    assert items
    assert items[0]["standard"] == "JGJ48-2014"
    assert any(item["standard"] == "GB55031-2022" for item in items)
    assert all(item["standard"] != "GB50016-2006" for item in items)


def test_jinan_local_word_is_retrieved_first() -> None:
    knowledge_base = KnowledgeBase()
    retriever = Retriever(knowledge_base)
    query = "济南商品住宅品质提升有什么要求"
    region_scope = detect_requested_region(query, knowledge_base.documents)

    results = retriever.search(
        query,
        top_k=10,
        region_scope=region_scope,
    )

    assert results
    assert results[0]["document"].get("region") == "济南市"
    assert (
        results[0]["document"].get("title")
        == "济南市商品住宅品质提升指引2026"
    )


def test_tianfu_official_docx_is_retrievable() -> None:
    knowledge_base = KnowledgeBase()
    retriever = Retriever(knowledge_base)
    query = "天府新区公园城市空中花园有什么要求"
    region_scope = detect_requested_region(query, knowledge_base.documents)

    results = retriever.search(
        query,
        top_k=20,
        region_scope=region_scope,
    )

    assert region_scope is not None
    assert region_scope["place"] == "成都市"
    assert any(
        item["document"].get("title")
        == "四川天府新区直管区公园城市规划管理创新规定(2024)"
        for item in results
    )


def test_office_floor_height_uses_clear_height_synonym() -> None:
    planner = Planner(Retriever(KnowledgeBase()))
    query = "\u529e\u516c\u697c\u5c42\u9ad8\u6700\u5927\u80fd\u505a\u5230\u591a\u5c11"

    results = planner.retriever.search(query, top_k=10)

    assert results
    assert results[0]["document"].get("standard") == "JGJ/T67-2019"
    assert "\u529e\u516c\u5efa\u7b51\u7684\u51c0\u9ad8\u5e94\u7b26\u5408" in results[0]["text"]

    items = planner.format_search_list(query)["items"]
    assert any(item["standard"] == "JGJ/T67-2019" for item in items)


def test_garage_ramp_two_lane_width_keeps_specific_terms() -> None:
    retriever = Retriever(KnowledgeBase())
    query = "\u5730\u4e0b\u8f66\u5e93\u6c7d\u8f66\u5761\u9053\uff0c\u53cc\u8f66\u9053\u5bbd\u5ea6\u662f\u591a\u5c11"

    keywords = extract_keywords(query)
    keyword_texts = [item["text"] for item in keywords]
    assert "\u6c7d\u8f66\u5761\u9053" in keyword_texts
    assert "\u53cc\u8f66\u9053" in keyword_texts
    assert "\u5761\u9053" not in keyword_texts

    slope_keywords = extract_keywords(
        "\u5730\u4e0b\u8f66\u5e93\u6c7d\u8f66\u5761\u9053\u53cc\u8f66\u9053\u5761\u5ea6\u548c\u5bbd\u5ea6"
    )
    assert "\u5761\u5ea6" in [item["text"] for item in slope_keywords]

    results = retriever.search(query, top_k=20)
    assert results
    assert results[0]["document"].get("standard") == "JGJ100-2015"
    assert "\u88684.2.10- 1" in results[0]["text"]
    assert "5.5" in results[0]["text"]
    assert "7.0" in results[0]["text"]
    assert all("\u53cc\u8f66\u9053" in item["text"] for item in results)

    planner = Planner(retriever)
    detail = planner.format_spec_detail(
        "\u5168\u56fd-gb55031-2022",
        query,
    )
    assert detail is not None
    assert detail["matched"] is False
    assert detail["snippets"] == []


def test_residential_spacing_query_requires_spacing_context() -> None:
    retriever = Retriever(KnowledgeBase())
    query = "\u4f4f\u5b85\u697c\u95f4\u8ddd\u6700\u5c0f\u662f\u591a\u5c11"

    keyword_texts = [
        item["text"]
        for item in extract_keywords(query)
    ]
    assert "\u697c\u95f4\u8ddd" in keyword_texts

    results = retriever.search(query, top_k=20)

    assert results
    assert len(results) <= 5
    assert all("\u95f4\u8ddd" in item["text"] for item in results)
    assert all("\u4f4f\u5b85" in item["text"] for item in results)
