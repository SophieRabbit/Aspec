import json
from types import SimpleNamespace

from app.agent.planner import Planner


class FakeRetriever:
    def __init__(self) -> None:
        self.knowledge_base = SimpleNamespace(documents=[])

    def search(self, query: str, **kwargs) -> list:
        return []


class FakeLLM:
    enabled = True

    def __init__(
        self,
        *,
        first_tool_name: str = "retrieve_standards",
        first_tool_args: dict | None = None,
        raise_on_chat: bool = False,
    ) -> None:
        self.calls = 0
        self.messages: list[dict] = []
        self.tool_batches: list[list[str]] = []
        self.raise_on_chat = raise_on_chat
        self.first_tool_name = first_tool_name
        self.first_tool_args = first_tool_args or {"query": "住宅楼梯踏步宽度"}

    def chat(self, messages: list[dict], tools=None, *, tool_choice="auto") -> dict:
        self.messages = messages
        self.calls += 1
        self.tool_batches.append(
            [
                str(tool.get("function", {}).get("name", ""))
                for tool in (tools or [])
            ]
        )
        if self.raise_on_chat:
            raise RuntimeError("mock llm failure")
        if self.calls == 1:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": self.first_tool_name,
                            "arguments": json.dumps(self.first_tool_args),
                        },
                    }
                ],
            }
        return {"content": "最终答案：依据检索到的规范条文回答。", "tool_calls": []}


def test_function_calling_executes_tool_and_returns_final_answer() -> None:
    retriever = FakeRetriever()
    llm = FakeLLM()
    planner = Planner(retriever, llm_client=llm)

    result = planner.run(
        "住宅楼梯踏步宽度和高度有什么要求？",
        enable_function_calling=True,
    )

    assert "检索目标：楼梯宽度" in result["reply"]
    assert result["reply"].endswith("最终答案：依据检索到的规范条文回答。")
    assert result["steps"][0]["tool"] == "retrieve"
    assert result["sources"] == []
    assert result["follow_ups"]
    assert any(message["role"] == "assistant" and message.get("tool_calls") for message in llm.messages)
    assert any(message["role"] == "tool" for message in llm.messages)
    assert llm.calls == 2
    assert "web_search" not in llm.tool_batches[0]
    assert llm.tool_batches[1] == []


def test_function_calling_falls_back_to_rule_planner_on_error() -> None:
    retriever = FakeRetriever()
    llm = FakeLLM(raise_on_chat=True)
    planner = Planner(retriever, llm_client=llm)

    result = planner.run(
        "住宅楼梯踏步宽度和高度有什么要求？",
        enable_function_calling=True,
    )

    assert "暂未收录" in result["reply"]
    assert result["steps"]


def test_function_calling_exposes_web_search_only_when_explicitly_enabled() -> None:
    retriever = FakeRetriever()
    llm = FakeLLM()
    planner = Planner(retriever, llm_client=llm)

    planner.run(
        "住宅楼梯踏步宽度和高度有什么要求？",
        enable_function_calling=True,
        enable_web_search=True,
    )

    assert "web_search" in llm.tool_batches[0]


def test_function_calling_dispatches_calculation_tool() -> None:
    retriever = FakeRetriever()
    llm = FakeLLM(
        first_tool_name="calculate_expression",
        first_tool_args={"query": "3*4"},
    )
    planner = Planner(retriever, llm_client=llm)

    result = planner.run(
        "帮我算一下 3 乘 4",
        enable_function_calling=True,
    )

    assert result["steps"][0]["tool"] == "calculate"
    assert result["calculation"]["result"] == "12"


def test_function_calling_dispatches_regional_compare_tool() -> None:
    retriever = FakeRetriever()
    llm = FakeLLM(
        first_tool_name="compare_regional_standards",
        first_tool_args={
            "query": "防水规范",
            "regions": ["上海市", "北京市"],
        },
    )
    planner = Planner(retriever, llm_client=llm)

    result = planner.run(
        "对比上海和北京的防水规范",
        enable_function_calling=True,
    )

    assert result["steps"][0]["tool"] == "compare"
    assert result["comparison"]["regions"] == ["上海市", "北京市"]
