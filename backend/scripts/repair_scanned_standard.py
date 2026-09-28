from __future__ import annotations

import argparse
import gc
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402
from rapidocr_onnxruntime import RapidOCR  # noqa: E402

from app.config import PDF_CHUNK_CHARS, STANDARDS_DIR  # noqa: E402
from app.knowledge.ocr import ocr_page_text, repair_ocr_table_fragments  # noqa: E402
from app.knowledge.page_numbering import extract_trailing_book_page  # noqa: E402
from app.knowledge.text_cleaner import normalize_ocr_paragraphs  # noqa: E402


_ENGINE: RapidOCR | None = None
CACHE_PATH = Path(__file__).resolve().parents[1] / "tmp" / "standards_ocr_cache.json"


def _init_worker() -> None:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = RapidOCR(
            intra_op_num_threads=1,
            inter_op_num_threads=1,
        )


def _normalize_code(code: str) -> str:
    return re.sub(r"[\s_\-—]+", "", code).lower()


def _find_pdf(code: str) -> Path | None:
    normalized = _normalize_code(code)
    candidates: list[Path] = []
    for folder in (Path.home() / "Desktop").iterdir():
        if not folder.is_dir():
            continue
        for path in folder.rglob("*.pdf"):
            if normalized in _normalize_code(path.stem):
                candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_size)


def _find_json(code: str) -> Path | None:
    normalized = _normalize_code(code)
    for path in STANDARDS_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        documents = payload if isinstance(payload, list) else payload.get("documents", [])
        for document in documents:
            if _normalize_code(str(document.get("standard", ""))) == normalized:
                return path
    return None


def _chunk_lines(text: str, size: int = PDF_CHUNK_CHARS) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if current and sum(len(item) + 1 for item in current) + len(line) > size:
            chunks.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _ocr_page(task: tuple[str, int, float, bool]) -> str:
    pdf_path, page_no, zoom, force_ocr = task
    document = pymupdf.open(pdf_path)
    try:
        page = document[page_no - 1]
        raw = page.get_text("text") or ""
        if not force_ocr and len(raw.strip()) >= 30:
            return raw.strip()
        try:
            return ocr_page_text(page, _ENGINE, zoom=zoom)
        except MemoryError:
            gc.collect()
            return ocr_page_text(page, _ENGINE, zoom=min(zoom, 2.0))
    finally:
        document.close()


def repair(
    pdf_path: Path,
    json_path: Path,
    workers: int,
    *,
    force_ocr: bool,
    pages: list[int] | None,
) -> int:
    document = pymupdf.open(str(pdf_path))
    page_count = document.page_count
    document.close()
    selected_pages = (
        sorted({page for page in pages if 1 <= page <= page_count})
        if pages
        else list(range(1, page_count + 1))
    )

    cache: dict[str, str] = {}
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = {}

    zoom = 3.0
    tasks = [
        (str(pdf_path), page_no, zoom, force_ocr)
        for page_no in selected_pages
        if f"{pdf_path}|{page_no}|{zoom}|{int(force_ocr)}" not in cache
    ]
    page_text: dict[int, str] = {
        page_no: cache[f"{pdf_path}|{page_no}|{zoom}|{int(force_ocr)}"]
        for page_no in selected_pages
        if f"{pdf_path}|{page_no}|{zoom}|{int(force_ocr)}" in cache
    }
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as executor:
        futures = {executor.submit(_ocr_page, task): task for task in tasks}
        for future in as_completed(futures):
            pdf, page_no, task_zoom, task_force_ocr = futures[future]
            text = repair_ocr_table_fragments(future.result())
            page_text[page_no] = text
            cache[
                f"{pdf}|{page_no}|{task_zoom}|{int(task_force_ocr)}"
            ] = text
            if len(page_text) % 10 == 0 or len(page_text) == page_count:
                CACHE_PATH.write_text(
                    json.dumps(cache, ensure_ascii=False),
                    encoding="utf-8",
                )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    document = payload if isinstance(payload, list) else payload.get("documents", [])
    if not document:
        raise RuntimeError(f"no document in {json_path}")
    target = document[0]
    replaced_pages = set(selected_pages)
    snippets: list[dict[str, Any]] = [
        snippet
        for snippet in target.get("snippets", [])
        if int(snippet.get("page", 0) or 0) not in replaced_pages
    ]
    for page_no in sorted(replaced_pages):
        if page_no not in page_text:
            continue
        text = normalize_ocr_paragraphs(
            repair_ocr_table_fragments(page_text[page_no]).strip()
        )
        if not text:
            continue
        book_page, text = extract_trailing_book_page(text)
        for chunk in _chunk_lines(text):
            snippets.append(
                {
                    "chapter": "原文",
                    "article": "",
                    "page": page_no,
                    "book_page": book_page,
                    "text": chunk,
                }
            )
    target["snippets"] = snippets
    output = [target] if isinstance(payload, list) else {"documents": [target]}
    json_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return len(snippets)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-OCR a scanned standard PDF and update its knowledge JSON."
    )
    parser.add_argument("--code", required=True, help="standard code, e.g. GB55031-2022")
    parser.add_argument("--pdf", type=Path, help="source PDF path (optional)")
    parser.add_argument("--json", type=Path, help="knowledge JSON path (optional)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="ignore an existing text layer and OCR rendered page images",
    )
    parser.add_argument(
        "--pages",
        default="",
        help="comma-separated page numbers; omit to process the whole PDF",
    )
    args = parser.parse_args()

    pdf_path = args.pdf or _find_pdf(args.code)
    if pdf_path is None:
        print(f"pdf not found for {args.code}")
        return 1
    json_path = args.json or _find_json(args.code)
    if json_path is None:
        print(f"knowledge json not found for {args.code}")
        return 1
    count = repair(
        pdf_path,
        json_path,
        args.workers,
        force_ocr=args.force_ocr,
        pages=[
            int(item)
            for item in re.split(r"[\s,]+", args.pages)
            if item.strip().isdigit()
        ],
    )
    print(f"updated {json_path}: {count} snippets from {pdf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
