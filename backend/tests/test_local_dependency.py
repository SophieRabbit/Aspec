from __future__ import annotations

from types import SimpleNamespace

from app.agent.planner import Planner
from app.knowledge.loader import KnowledgeBase
from app.knowledge.retriever import Retriever
from services.local_dependency import detect_local_dependency


class EmptyRetriever:
    def __init__(self) -> None:
        self.documents: list[dict] = []
        self.knowledge_base = SimpleNamespace(documents=self.documents)

    def search(self, query: str, top_k: int = 5, **kwargs):
        return []

    @staticmethod
    def to_source(item):
        return item


def test_detect_office_floor_height_as_planning_dependency() -> None:
    result = detect_local_dependency(
        "\u529e\u516c\u697c\u5c42\u9ad8\u6700\u5927\u80fd\u505a\u5230\u591a\u5c11"
    )

    assert result is not None
    assert result["category"] == "\u89c4\u5212\u6307\u6807"
    assert "\u5c42\u9ad8" in result["matched_keywords"]["\u89c4\u5212\u6307\u6807"]


def test_office_floor_height_appends_planning_prompt() -> None:
    planner = Planner(Retriever(KnowledgeBase()))
    result = planner.run(
        "\u529e\u516c\u697c\u5c42\u9ad8\u6700\u5927\u80fd\u505a\u5230\u591a\u5c11",
        enable_function_calling=False,
        enable_web_search=False,
    )

    assert "\u8be5\u95ee\u9898\u9700\u7ed3\u5408\u5730\u65b9\u89c4\u8303" in result["reply"]
    assert "**__\U0001f4a1 \u8be5\u95ee\u9898\u9700\u7ed3\u5408\u5730\u65b9\u89c4\u8303" in result["reply"]
    assert (
        "\u8be5\u95ee\u9898\u6d89\u53ca\u5730\u65b9\u89c4\u5212\u6307\u6807"
        in result["reply"]
    )


def test_missing_chengdu_local_regulation_gets_city_prompt() -> None:
    planner = Planner(EmptyRetriever())
    result = planner.run(
        "\u6210\u90fd\u4f4f\u5b85\u9633\u53f0\u9762\u79ef\u600e\u4e48\u7b97",
        enable_function_calling=False,
        enable_web_search=False,
    )

    assert (
        "\u6210\u90fd\u5e02\u5730\u65b9\u89c4\u8303\u6682\u672a\u6536\u5f55"
        in result["reply"]
    )
    assert (
        "\u5efa\u8bae\u67e5\u9605\u6210\u90fd\u5e02\u4f4f\u5efa\u5c40\u5b98\u7f51"
        in result["reply"]
    )


def test_fire_compartment_area_does_not_trigger_local_dependency() -> None:
    planner = Planner(Retriever(KnowledgeBase()))
    result = planner.run(
        "\u9632\u706b\u5206\u533a\u6700\u5927\u9762\u79ef\u662f\u591a\u5c11",
        enable_function_calling=False,
        enable_web_search=False,
    )

    assert "\u8be5\u95ee\u9898\u9700\u7ed3\u5408\u5730\u65b9\u89c4\u8303" not in result["reply"]
    assert "\u5730\u65b9\u89c4\u8303\u6682\u672a\u6536\u5f55" not in result["reply"]


def test_building_spacing_appends_sunlight_prompt_once() -> None:
    planner = Planner(Retriever(KnowledgeBase()))
    result = planner.run(
        "\u697c\u95f4\u8ddd\u6700\u5c0f\u662f\u591a\u5c11",
        enable_function_calling=False,
        enable_web_search=False,
    )

    assert (
        "\u8be5\u95ee\u9898\u6d89\u53ca\u5730\u65b9\u95f4\u8ddd\u4e0e\u65e5\u7167\u6807\u51c6"
        in result["reply"]
    )
    assert result["reply"].count("\U0001f4a1") == 1

    repeated = planner._with_local_dependency_notice(result, "\u697c\u95f4\u8ddd")
    assert repeated["reply"] == result["reply"]
