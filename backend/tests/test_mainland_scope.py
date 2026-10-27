from types import SimpleNamespace

import pytest

from app.agent.planner import Planner
from app.knowledge.mainland_scope import detect_outside_mainland_place


class FailingRetriever:
    def __init__(self) -> None:
        self.knowledge_base = SimpleNamespace(documents=[])

    def search(self, query: str, **kwargs) -> list:
        raise AssertionError("knowledge retrieval must not run outside mainland China")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("香港的踏步规范", "香港"),
        ("中国香港住宅防火要求", "香港"),
        ("Hong Kong building code", "香港"),
        ("澳门的疏散规范", "澳门"),
        ("台湾的建筑标准", "台湾"),
        ("日本楼梯规范", "日本"),
        ("帮我查查东京的建筑规范", "东京"),
        ("纽约建筑防火要求", "纽约"),
        ("境外项目踏步尺寸", "境外"),
    ],
)
def test_outside_mainland_places_are_detected(query: str, expected: str) -> None:
    assert detect_outside_mainland_place(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "中国大陆住宅楼梯踏步要求",
        "海南省建筑防火规范",
        "港口工程消防要求",
    ],
)
def test_mainland_queries_are_not_misclassified(query: str) -> None:
    assert detect_outside_mainland_place(query) is None


def test_planner_returns_region_notice_without_retrieval() -> None:
    planner = Planner(FailingRetriever())

    result = planner.run("给我找找香港的踏步规范")

    assert result["sources"] == []
    assert result["web_results"] == []
    assert result["steps"][0]["tool"] == "region_scope"
    assert "仅限中国大陆地区" in result["reply"]
    assert "香港不属于该范围" in result["reply"]
