from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import STANDARDS_DIR  # noqa: E402
from app.knowledge.loader import clean_extracted_text  # noqa: E402


def main() -> int:
    cleaned = 0
    for path in sorted(STANDARDS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        documents = payload if isinstance(payload, list) else payload.get("documents", [])
        changed = False
        for document in documents:
            for snippet in document.get("snippets", []):
                raw = snippet.get("text", "")
                cleaned_text = clean_extracted_text(raw)
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
