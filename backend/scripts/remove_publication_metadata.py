from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR, STANDARDS_DIR  # noqa: E402
from app.knowledge.text_cleaner import strip_publication_metadata  # noqa: E402


def clean_payload(payload: Any) -> dict[str, int]:
    documents = payload if isinstance(payload, list) else payload.get("documents", [])
    stats = {
        "snippets": 0,
        "removed": 0,
        "trimmed": 0,
    }
    for document in documents:
        cleaned_snippets: list[dict[str, Any]] = []
        for snippet in document.get("snippets", []):
            if not isinstance(snippet, dict) or not snippet.get("text"):
                continue
            original = str(snippet["text"])
            cleaned = strip_publication_metadata(original)
            stats["snippets"] += 1
            if not cleaned:
                stats["removed"] += 1
                continue
            if cleaned != original:
                stats["trimmed"] += 1
                snippet["text"] = cleaned
            cleaned_snippets.append(snippet)
        document["snippets"] = cleaned_snippets
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove publication/cover snippets from knowledge JSON files."
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    paths = sorted(STANDARDS_DIR.glob("*.json"))
    payloads: dict[Path, Any] = {}
    totals = {"files": 0, "snippets": 0, "removed": 0, "trimmed": 0}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        stats = clean_payload(payload)
        if stats["removed"] or stats["trimmed"]:
            payloads[path] = payload
            totals["files"] += 1
            for key in ("snippets", "removed", "trimmed"):
                totals[key] += stats[key]

    backup_dir: Path | None = None
    if args.write:
        backup_dir = DATA_DIR / "backups" / f"publication-clean-{datetime.now():%Y%m%d-%H%M%S}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        for path, payload in payloads.items():
            shutil.copy2(path, backup_dir / path.name)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    print(
        f"{'written' if args.write else 'preview'}: files={totals['files']}, "
        f"snippets={totals['snippets']}, removed={totals['removed']}, "
        f"trimmed={totals['trimmed']}, backup={backup_dir or '-'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
