import json
from pathlib import Path

from app.agent.intent_router import (
    INTENT_CHITCHAT,
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


def test_chitchat_is_detected_without_knowledge_retrieval() -> None:
    router = IntentRouter()
    for query in ("你好啊", "您好！", "你是谁？", "谢谢啦", "在吗"):
        result = router.classify(query, use_llm=False)
        assert result.intent == INTENT_CHITCHAT, query
        assert result.confidence >= 0.9


def test_known_synonym_term_is_not_rejected_as_fallback() -> None:
    router = IntentRouter()
    result = router.classify("消防登高面", use_llm=False)

    assert result.intent == INTENT_TERM
    assert result.source == "rules"


def test_explicit_out_of_scope_question_skips_llm_classification() -> None:
    class FakeLLM:
        enabled = True

        def chat(self, messages: list[dict], tools=None, *, tool_choice="auto") -> dict:
            raise AssertionError("LLM should not classify an explicit out-of-scope question")

    router = IntentRouter(FakeLLM())
    result = router.classify("你还知道生肖吗", use_llm=True)
    assert result.intent == INTENT_FALLBACK
    assert result.source == "rules"
    assert result.confidence >= router.low_confidence_threshold


def test_greeting_prefix_does_not_hide_a_real_standard_query() -> None:
    router = IntentRouter()
    result = router.classify("你好，请问住宅楼梯宽度有什么要求？", use_llm=False)
    assert result.intent != INTENT_CHITCHAT


def test_action_prefixed_standard_query_keeps_standard_intent() -> None:
    router = IntentRouter()
    result = router.classify("帮我查下踏步规范", use_llm=False)
    assert result.intent == INTENT_NAME
    assert result.confidence > 0


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
