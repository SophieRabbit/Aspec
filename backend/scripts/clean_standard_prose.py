from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR  # noqa: E402
from app.knowledge.text_cleaner import clean_kb_text, normalize_ocr_paragraphs  # noqa: E402


def _table_lines(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line.strip().startswith("|")
    ]


def clean_snippet_prose(text: str) -> str:
    output: list[str] = []
    prose: list[str] = []

    def flush_prose() -> None:
        if prose:
            cleaned = normalize_ocr_paragraphs(
                clean_kb_text("\n".join(prose))
            ).strip()
            if cleaned:
                output.append(cleaned)
            prose.clear()

    for line in text.splitlines():
        if line.strip().startswith("|"):
            flush_prose()
            output.append(line)
        else:
            prose.append(line)
    flush_prose()
    return "\n".join(output)


def _resolve_paths(paths: list[Path], report_path: Path | None) -> list[Path]:
    resolved: list[Path] = []
    if report_path and report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for item in report.get("results", []):
            target = item.get("target")
            if target:
                resolved.append(Path(target))
    for path in paths:
        if path.is_dir():
            resolved.extend(sorted(path.glob("*.json")))
        elif path.suffix.lower() == ".json":
            resolved.append(path)
    return sorted(set(resolved))


def clean_files(paths: list[Path], *, write: bool) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    payloads: dict[Path, Any] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        documents = payload if isinstance(payload, list) else payload.get("documents", [])
        stats = {
            "file": str(path),
            "snippets": 0,
            "changed": 0,
            "lines_before": 0,
            "lines_after": 0,
        }
        for document in documents:
            for snippet in document.get("snippets", []):
                text = str(snippet.get("text", ""))
                cleaned = clean_snippet_prose(text)
                if _table_lines(text) != _table_lines(cleaned):
                    raise RuntimeError(f"table rows changed in {path}")
                stats["snippets"] += 1
                stats["lines_before"] += len(text.splitlines())
                stats["lines_after"] += len(cleaned.splitlines())
                if cleaned != text:
                    snippet["text"] = cleaned
                    stats["changed"] += 1
        payloads[path] = payload
        results.append(stats)

    backup_dir: Path | None = None
    if write and payloads:
        backup_dir = DATA_DIR / "backups" / f"prose-clean-{datetime.now():%Y%m%d-%H%M%S}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        for path, payload in payloads.items():
            shutil.copy2(path, backup_dir / path.name)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    return {
        "files": len(results),
        "changed_snippets": sum(item["changed"] for item in results),
        "lines_before": sum(item["lines_before"] for item in results),
        "lines_after": sum(item["lines_after"] for item in results),
        "backup_dir": str(backup_dir) if backup_dir else "",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean prose whitespace and OCR line wrapping while leaving tables untouched."
    )
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--output-report",
        type=Path,
        default=DATA_DIR / "clean_standard_prose_report.json",
    )
    args = parser.parse_args()

    paths = _resolve_paths(args.paths, args.report)
    if not paths:
        print("no JSON files selected")
        return 1
    report = clean_files(paths, write=args.write)
    args.output_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"{'written' if args.write else 'preview'}: files={report['files']}, "
        f"changed_snippets={report['changed_snippets']}, "
        f"lines={report['lines_before']}->{report['lines_after']}, "
        f"backup={report['backup_dir'] or '-'}"
    )
    print(f"report: {args.output_report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
