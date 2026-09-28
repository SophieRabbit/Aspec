import json
from pathlib import Path

from app.agent.intent_router import (
    INTENT_COLLOQUIAL,
    INTENT_COMPARISON,
    INTENT_FALLBACK,
    INTENT_MATERIAL,
    INTENT_NAME,
    INTENT_NUMBER,
    INTENT_NUMERIC,
    INTENT_SCENARIO,
    INTENT_TERM,
    INTENT_VERSION,
    IntentType,
    IntentRouter,
)


def test_all_intent_dataset_cases_route_correctly() -> None:
    router = IntentRouter()
    cases_path = Path(__file__).resolve().parent / "datasets" / "intent_router_cases.jsonl"
    cases = []
    for line in cases_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        cases.append((item["question"], item["intent"]))
    assert len(cases) >= 50
    for query, expected in cases:
        result = router.classify(query, use_llm=False)
        assert result.intent == expected, f"{query}: {result.intent} != {expected}"
        assert result.confidence > 0


def test_low_confidence_uses_fallback() -> None:
    router = IntentRouter()
    result = router.classify("随便看看", use_llm=False)
    assert result.intent in {INTENT_SCENARIO, INTENT_COLLOQUIAL}
    assert result.source in {"rules", "fallback"}


def test_llm_second_layer_overrides_low_confidence_rules() -> None:
    class FakeLLM:
        enabled = True

        def chat(self, messages: list[dict], tools=None, *, tool_choice="auto") -> dict:
            assert messages[0]["role"] == "system"
            assert "意图分类器" in messages[0]["content"]
            return {"content": '{"intent": "numeric", "confidence": 0.9, "reason": "指标查询"}', "tool_calls": []}

    router = IntentRouter(FakeLLM())
    result = router.classify("楼梯踏板", use_llm=True)
    assert result.intent == INTENT_NUMERIC
    assert result.source == "llm"


def test_llm_not_used_when_rule_is_confident() -> None:
    class FakeLLM:
        enabled = True

        def chat(self, messages: list[dict], tools=None, *, tool_choice="auto") -> dict:
            raise AssertionError("LLM should not be called for high-confidence rules")

    router = IntentRouter(FakeLLM())
    result = router.classify("GB50016第5.3.1条", use_llm=True)
    assert result.intent == INTENT_NUMBER
    assert result.source == "rules"


def test_route_alias_and_intent_type_are_available() -> None:
    router = IntentRouter()
    result = router.route("住宅设计规范", use_llm=False)
    assert result.intent == INTENT_NAME
    assert IntentType(result.intent) == IntentType.STANDARD_NAME
