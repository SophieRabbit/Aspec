import json
from pathlib import Path


DATASET = Path(__file__).parent / "datasets" / "qa_test_suite.jsonl"


def test_dataset_count_and_schema() -> None:
    lines = [line for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert 30 <= len(lines) <= 50
    for line in lines:
        record = json.loads(line)
        assert record["id"]
        assert record["question"]
        assert record["category"] in ("规范检索", "地区差异", "材质对比", "边界极端")
        assert isinstance(record["expected_source"], list)
        assert isinstance(record["expected_keywords"], list)
        assert isinstance(record["expected_pages"], list)
