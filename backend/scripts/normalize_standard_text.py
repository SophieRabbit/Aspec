from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.knowledge.text_cleaner import normalize_ocr_paragraphs  # noqa: E402


def _table_lines(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line.strip().startswith("|")
    ]


def normalize_payload(payload: Any) -> dict[str, int]:
    documents = payload if isinstance(payload, list) else payload.get("documents", [])
    stats = {
        "documents": len(documents),
        "snippets": 0,
        "changed_snippets": 0,
        "lines_before": 0,
        "lines_after": 0,
        "table_lines": 0,
    }
    for document in documents:
        for snippet in document.get("snippets", []):
            if not isinstance(snippet, dict) or not snippet.get("text"):
                continue
            original = str(snippet["text"])
            normalized = normalize_ocr_paragraphs(original)
            if _table_lines(original) != _table_lines(normalized):
                raise RuntimeError("table rows changed during prose normalization")
            stats["snippets"] += 1
            stats["lines_before"] += len(original.splitlines())
            stats["lines_after"] += len(normalized.splitlines())
            stats["table_lines"] += len(_table_lines(original))
            if normalized != original:
                snippet["text"] = normalized
                stats["changed_snippets"] += 1
    return stats


def _expand_paths(paths: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(path.glob("*.json")))
        elif path.suffix.lower() == ".json":
            expanded.append(path)
    return expanded


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Join OCR-wrapped prose lines while preserving table rows."
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--write",
        action="store_true",
        help="write normalized JSON; without this flag only report changes",
    )
    args = parser.parse_args()

    paths = _expand_paths(args.paths)
    if not paths:
        print("no JSON files found")
        return 1

    total_removed = 0
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        stats = normalize_payload(payload)
        removed = stats["lines_before"] - stats["lines_after"]
        total_removed += removed
        if args.write:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        mode = "updated" if args.write else "preview"
        print(
            f"{mode} {path}: snippets={stats['snippets']}, "
            f"changed={stats['changed_snippets']}, "
            f"lines={stats['lines_before']}->{stats['lines_after']}, "
            f"removed={removed}, table_lines={stats['table_lines']}"
        )
    print(f"total removed lines: {total_removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
