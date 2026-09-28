from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import STANDARDS_DIR  # noqa: E402
from app.knowledge.text_cleaner import PREAMBLE_1, PREAMBLE_2, clean_kb_text  # noqa: E402


def main() -> int:
    cleaned = 0
    for path in sorted(STANDARDS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        documents = payload if isinstance(payload, list) else payload.get("documents", [])
        changed = False
        for document in documents:
            raw_title = document.get("title", "")
            cleaned_title = clean_kb_text(raw_title)
            if cleaned_title != raw_title:
                document["title"] = cleaned_title
                changed = True
            for snippet in document.get("snippets", []):
                raw = snippet.get("text", "")
                cleaned_text = clean_kb_text(raw)
                if "为适应国际技术法规与技术标准通行规则" in cleaned_text:
                    cleaned_text = PREAMBLE_1
                elif "项目建设水平或技术水平的高低程度" in cleaned_text:
                    cleaned_text = PREAMBLE_2
                if cleaned_text != raw:
                    snippet["text"] = cleaned_text
                    changed = True
        if changed:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            cleaned += 1
    print(f"已清洗 {cleaned} 份知识文档")
    return 0


if __name__ == "__main__":
    sys.exit(main())
