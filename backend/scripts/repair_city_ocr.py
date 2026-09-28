from __future__ import annotations

import concurrent.futures
import json
import pathlib
import re
import sys


backend = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend))
sys.path.insert(0, str(backend / "scripts"))

from rapidocr_onnxruntime import RapidOCR  # noqa: E402
import pymupdf  # noqa: E402

import import_standards_ocr  # noqa: E402
from app.knowledge.text_cleaner import clean_kb_text  # noqa: E402


_ENGINE: RapidOCR | None = None


def _init_worker() -> None:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = RapidOCR(
            intra_op_num_threads=1,
            inter_op_num_threads=1,
        )


_PUNCT = "\u3002\uff1b\uff1a;:"
_CLAUSE_RE = re.compile(
    "(?<=[" + _PUNCT + "])\\s*(?=\\d{1,2}(?:\\.\\d{1,2}){1,3}\\s)"
)
_ITEM_RE = re.compile(
    "(?<=[" + _PUNCT + "])\\s*(\\d{1,2})(?=\\s*[\\u4e00-\\u9fff（(])"
)


def _format_clauses(text: str) -> str:
    text = _CLAUSE_RE.sub("\n", text)
    text = _ITEM_RE.sub(lambda match: "\n" + match.group(1) + " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _process_page(task: tuple[str, int]) -> tuple[str, int, str]:
    pdf_path, page_no = task
    document = pymupdf.open(pdf_path)
    try:
        raw = import_standards_ocr._ocr_page(
            document[page_no - 1],
            _ENGINE,
            3.0,
        )
        cleaned = clean_kb_text(raw)
    finally:
        document.close()
    return pdf_path, page_no, _format_clauses(cleaned)


def _parse_jobs(plan_path: pathlib.Path) -> list[tuple[str, str, list[int], bool]]:
    jobs: list[tuple[str, str, list[int], bool]] = []
    seen_files: set[str] = set()
    for line in plan_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        file_name = line.split(" | ")[0]
        if file_name in seen_files:
            continue
        seen_files.add(file_name)
        pages_part = line.split("pages=", 1)[1].split(" | ", 1)[0]
        note = line.split("note=", 1)[1].split(" | ", 1)[0]
        pdf_path = line.split("path=", 1)[1].strip().replace("\ufeff", "")
        if note == "FULL_OCR_NO_SNIPPETS":
            document = pymupdf.open(pdf_path)
            pages = list(range(1, document.page_count + 1))
            document.close()
            full_ocr = True
        else:
            pages = [int(item) for item in pages_part.split(",") if item.strip()]
            full_ocr = False
        jobs.append((file_name, pdf_path, pages, full_ocr))
    return jobs


def main() -> int:
    project = backend.parent
    plan_path = project / "output" / "city_repair_plan.txt"
    cache_path = project / "output" / "city_ocr_cache.json"
    standards_dir = backend / "data" / "standards"
    jobs = _parse_jobs(plan_path)

    tasks = sorted(
        {
            (pdf_path, page_no)
            for _, pdf_path, pages, _ in jobs
            for page_no in pages
        }
    )
    cache: dict[str, str] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    missing = [task for task in tasks if f"{task[0]}|{task[1]}" not in cache]
    print(f"tasks={len(tasks)} cached={len(tasks) - len(missing)} missing={len(missing)}")

    if missing:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=8,
            initializer=_init_worker,
        ) as executor:
            futures = {
                executor.submit(_process_page, task): task for task in missing
            }
            done = 0
            for future in concurrent.futures.as_completed(futures):
                pdf_path, page_no, text = future.result()
                cache[f"{pdf_path}|{page_no}"] = text
                done += 1
                if done % 50 == 0:
                    cache_path.write_text(
                        json.dumps(cache, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    print(f"progress={done}/{len(missing)}")
        cache_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    updated_files = 0
    for file_name, pdf_path, pages, full_ocr in jobs:
        json_path = standards_dir / file_name
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        document = payload["documents"][0]
        if full_ocr:
            new_snippets: list[dict[str, object]] = []
            for page_no in sorted(pages):
                text = cache.get(f"{pdf_path}|{page_no}", "").strip()
                if text:
                    new_snippets.append(
                        {
                            "chapter": "原文",
                            "article": "",
                            "page": page_no,
                            "book_page": None,
                            "text": text,
                        }
                    )
            document["snippets"] = new_snippets
        else:
            snippets = document.get("snippets", [])
            for snippet in snippets:
                page_no = int(snippet.get("page", 0) or 0)
                if page_no in pages:
                    text = cache.get(f"{pdf_path}|{page_no}", "").strip()
                    if text:
                        snippet["text"] = text
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        updated_files += 1

    print(f"updated_files={updated_files}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
