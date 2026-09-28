from __future__ import annotations

from app.agent.planner import Planner
from app.knowledge.keywords import extract_keywords
from app.knowledge.loader import KnowledgeBase
from app.knowledge.retriever import Retriever
from services.compound_intent import detect_compound_intent
from services.synonym_expander import expand_query


def test_roof_garden_aliases_are_expanded() -> None:
    terms = expand_query("空中花园")

    assert terms[0] == "空中花园"
    assert "屋顶花园" in terms
    assert "屋顶绿化" in terms
    assert "种植屋面" in terms
    assert "空中庭院" in terms
    assert "建筑立体绿化" in terms
    assert "生态阳台" in terms
    assert "空中共享平台" in terms


def test_query_recognizes_multiple_concept_groups() -> None:
    query = "成都四代住宅的相关规范，对空中花园有啥要求"
    intent = detect_compound_intent(query)

    assert intent.building_type == "住宅建筑"
    assert intent.concept_group == "roof_garden"
    assert intent.concept_label == "屋顶花园"
    assert intent.attribute == "绿化要求"
    assert [concept.concept_id for concept in intent.concepts] == [
        "roof_garden",
        "fourth_gen_housing",
    ]


def test_multi_route_retrieval_finds_roof_greening_standards() -> None:
    retriever = Retriever(KnowledgeBase())
    query = "成都四代住宅的相关规范，对空中花园有啥要求"
    intent = detect_compound_intent(query)

    results = retriever.search(
        query,
        top_k=30,
        region_scope=intent.region_scope,
    )

    standards = {
        item["document"].get("standard", "")
        for item in results
    }
    assert "GB55030-2022" in standards
    roof_terms = (
        "空中花园",
        "屋顶花园",
        "屋顶绿化",
        "种植屋面",
        "露台绿化",
        "阳台绿化",
        "建筑立体绿化",
        "生态阳台",
        "空中共享平台",
    )
    assert all(
        any(term in item["text"] for term in roof_terms)
        for item in results
    )
    assert (
        results[0]["document"].get("title")
        == "四川天府新区直管区公园城市规划管理创新规定(2024)"
    )
    assert any(
        "空中花园" in item["text"]
        or "屋顶绿化" in item["text"]
        or "种植屋面" in item["text"]
        for item in results
    )


def test_header_displays_synonym_concepts_and_target() -> None:
    reply = Planner._with_compound_intent_header(
        "成都四代住宅的相关规范，对空中花园有啥要求",
        "依据规范回答。",
        requested_region={"place": "成都市"},
    )

    assert "相关概念：屋顶花园" in reply
    assert "空中花园" in reply
    assert "相关概念：庭院式住宅" in reply
    assert "四代住宅" in reply
    assert "检索目标：绿化要求" in reply


def test_synonym_concepts_are_exposed_as_keywords() -> None:
    keywords = extract_keywords(
        "成都四代住宅的相关规范，对空中花园有啥要求",
        {"place": "成都市"},
    )
    texts = [item["text"] for item in keywords]

    assert "屋顶花园" in texts
    assert "空中花园" in texts
    assert "屋顶绿化" in texts
    assert "种植屋面" in texts
    assert "生态阳台" in texts
    assert "空中共享平台" in texts
    assert "庭院式住宅" in texts
    assert "四代住宅" in texts


def test_detail_highlight_terms_include_synonyms() -> None:
    terms = Planner._highlight_terms(
        "成都四代住宅的相关规范，对空中花园有啥要求"
    )

    assert "空中花园" in terms
    assert "屋顶绿化" in terms
    assert "种植屋面" in terms
    assert "生态阳台" in terms
    assert "空中共享平台" in terms


def test_concept_detail_returns_only_highlighted_concept_text() -> None:
    planner = Planner(Retriever(KnowledgeBase()))
    query = "成都四代住宅的相关规范，对空中花园有啥要求"

    result = planner.format_spec_detail(
        "四川省-蒲江县规划管理技术规定第三-第四章",
        query,
    )

    assert result is not None
    assert result["matched"] is True
    assert result["snippets"]
    assert all(
        "<mark>空中花园</mark>" in item["text"]
        for item in result["snippets"]
    )
