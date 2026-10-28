from app.agent.planner import Planner
from app.knowledge.loader import KnowledgeBase
from app.knowledge.retriever import Retriever


class LLMMustNotBeCalled:
    enabled = True

    def chat(self, messages, tools=None, *, tool_choice="auto"):
        raise AssertionError("stable answer mode must not call the LLM")


def test_stable_mode_returns_identical_answers_with_or_without_llm() -> None:
    cloud_planner = Planner(
        Retriever(KnowledgeBase()),
        llm_client=LLMMustNotBeCalled(),
    )
    local_planner = Planner(Retriever(KnowledgeBase()))
    queries = (
        "住宅设计规范",
        "楼梯踏步最小宽度",
        "高层住宅的消防疏散要求",
        "比较住宅设计规范和民用建筑通用规范的楼梯规定",
    )

    for query in queries:
        cloud_result = cloud_planner.run(
            query,
            enable_function_calling=True,
            enable_web_search=False,
        )
        local_result = local_planner.run(
            query,
            enable_function_calling=True,
            enable_web_search=False,
        )
        assert cloud_result["reply"] == local_result["reply"], query
        assert cloud_result["sources"] == local_result["sources"], query
        assert cloud_result["follow_ups"] == local_result["follow_ups"], query


def test_stable_mode_uses_deterministic_standard_listing() -> None:
    cloud_planner = Planner(
        Retriever(KnowledgeBase()),
        llm_client=LLMMustNotBeCalled(),
    )
    local_planner = Planner(Retriever(KnowledgeBase()))
    query = "住宅楼梯踏步相关规范有哪些"

    assert cloud_planner.format_search_list(query) == local_planner.format_search_list(query)
