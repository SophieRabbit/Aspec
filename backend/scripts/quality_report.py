from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import STANDARDS_DIR  # noqa: E402


def document_quality(document: dict) -> dict:
    text = "".join(snippet.get("text", "") for snippet in document.get("snippets", []))
    total = max(1, len(text))
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    spaces = text.count(" ")
    suspicious = sum(text.count(char) for char in ("□", "�", "囗"))
    chinese_ratio = chinese / total
    score = (1 - chinese_ratio) * 60 + (spaces / total) * 20 + suspicious * 3
    return {
        "title": document.get("title", ""),
        "standard": document.get("standard", ""),
        "total": total,
        "chinese_ratio": round(chinese_ratio, 3),
        "space_ratio": round(spaces / total, 3),
        "suspicious": suspicious,
        "score": round(score, 2),
    }


def main() -> int:
    rows: list[dict] = []
    for path in sorted(STANDARDS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        documents = payload if isinstance(payload, list) else payload.get("documents", [])
        rows.extend(document_quality(document) for document in documents)
    rows.sort(key=lambda row: row["score"], reverse=True)
    print("最可能需要 OCR/重新提取的 30 份文档：")
    for row in rows[:30]:
        print(
            f"{row['score']:.1f}  中文占比 {row['chinese_ratio']:.1%}  "
            f"空格占比 {row['space_ratio']:.1%}  {row['standard']} {row['title']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
