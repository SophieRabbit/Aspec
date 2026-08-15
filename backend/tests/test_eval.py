from pathlib import Path

from app.eval.scoring import score_case
from app.eval.store import EvalStore
from app.eval.advice import generate_advice


def test_score_case_deterministic_metrics() -> None:
    record = {
        "expected_source": ["GB 50096-2011"],
        "expected_keywords": ["净高", "2.40m"],
        "expected_pages": [42],
    }
    reply = "住宅室内净高不应低于2.40m。"
    sources = [
        {
            "standard": "GB 50096-2011",
            "title": "住宅设计规范",
            "page": 42,
            "snippet": "净高不应低于2.40m",
        }
    ]
    metrics = score_case(
        record,
        reply,
        sources,
        123.4,
        {"retrieval": 0.5, "keyword": 0.7, "source": 0.5, "completeness": 3.0},
        4.0,
    )
    assert metrics["retrieval"] == 1.0
    assert metrics["keyword"] == 1.0
    assert metrics["source"] == 1.0
    assert metrics["latency_ms"] == 123.4
    assert metrics["is_bad_case"] is False


def test_store_bad_case(tmp_path: Path) -> None:
    store = EvalStore(tmp_path / "eval.db")
    run_id = store.create_run("qa_test_suite")
    store.finish_run(run_id, {"bad_case_count": 1}, "report.html", {})
    bad_case_id = store.add_bad_case(
        question="测试问题",
        actual_reply="回答",
        failed_dimensions=["retrieval"],
        source="user_feedback",
        run_id=run_id,
    )
    assert bad_case_id
    assert store.list_bad_cases()[0]["question"] == "测试问题"
    assert store.list_runs()[0]["run_id"] == run_id


def test_advice_generation_for_bad_case() -> None:
    advice = generate_advice(
        [
            {
                "is_bad_case": True,
                "failed_dimensions": ["retrieval"],
                "question": "无障碍厕所最小尺寸是多少？",
            }
        ]
    )
    assert advice
    assert advice[0]["dimension"] == "retrieval"
    assert advice[0]["suggestions"]
    assert "chunk_size" in " ".join(advice[0]["suggestions"])
