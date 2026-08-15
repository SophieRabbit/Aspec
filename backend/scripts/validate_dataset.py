from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.knowledge.loader import KnowledgeBase  # noqa: E402

DATASET = Path(__file__).resolve().parents[1] / "tests" / "datasets" / "qa_test_suite.jsonl"


def main() -> int:
    knowledge_base = KnowledgeBase()
    document_texts = [
        f"{doc.get('standard', '')} {doc.get('title', '')} "
        + " ".join(snippet.get("text", "") for snippet in doc.get("snippets", []))
        for doc in knowledge_base.documents
    ]
    combined = "\n".join(document_texts)

    issues: list[str] = []
    categories: dict[str, int] = {}
    total = 0
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        total += 1
        categories[record["category"]] = categories.get(record["category"], 0) + 1

        for source in record.get("expected_source", []):
            if source and not any(source in text for text in document_texts):
                issues.append(f"{record['id']}: expected_source 不存在 -> {source}")

        if record["category"] in ("规范检索", "地区差异"):
            for keyword in record.get("expected_keywords", []):
                if keyword and keyword not in combined:
                    issues.append(f"{record['id']}: expected_keyword 不存在 -> {keyword}")

    print(f"数据集共 {total} 条：{categories}")
    if issues:
        print("发现以下问题：")
        for issue in issues:
            print("  -", issue)
        return 1
    print("校验通过：期望来源与关键词均可在当前知识库中找到。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
