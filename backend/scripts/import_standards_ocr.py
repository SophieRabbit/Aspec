from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR, PDF_CHUNK_CHARS, STANDARDS_DIR  # noqa: E402
from app.knowledge.loader import clean_extracted_text  # noqa: E402
from app.knowledge.ocr import group_ocr_lines, ocr_image, split_ocr_cells  # noqa: E402
from app.knowledge.page_numbering import extract_trailing_book_page  # noqa: E402
from app.knowledge.priority_engine import (  # noqa: E402
    apply_priority,
    normalize_standard_code,
    parse_standard_filename,
)
from app.knowledge.text_cleaner import clean_kb_text  # noqa: E402


def _existing_codes() -> set[str]:
    codes: set[str] = set()
    for path in STANDARDS_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        documents = payload if isinstance(payload, list) else payload.get("documents", [])
        for document in documents:
            code = document.get("standard", "")
            if code:
                codes.add(normalize_standard_code(code))
    return codes


def _text_profile(path: Path) -> dict[str, int]:
    import pymupdf

    doc = pymupdf.open(str(path))
    pages = doc.page_count
    chars = 0
    for page in doc:
        chars += len((page.get_text("text") or "").strip())
    doc.close()
    return {"pages": pages, "chars": chars}


def _text_profile_key(parsed: Any, path: Path) -> tuple[float, int, int]:
    profile = _text_profile(path)
    ratio = profile["chars"] / max(1, profile["pages"])
    return ratio, profile["pages"], -path.stat().st_size


def _has_text_layer(path: Path, min_ratio: int = 30) -> bool:
    profile = _text_profile(path)
    return profile["pages"] > 0 and profile["chars"] / profile["pages"] >= min_ratio


def _make_doc_id(region: str, standard: str, title: str) -> str:
    slug = re.sub(
        r"[^0-9a-zA-Z\u4e00-\u9fff]+",
        "-",
        f"{region}-{standard or title}",
    ).strip("-").lower()
    return slug or "document"


def _chunk_text(text: str, size: int = PDF_CHUNK_CHARS) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    chunks: list[str] = []
    for index in range(0, len(text), size):
        chunk = text[index : index + size]
        if index + size < len(text):
            break_at = max(chunk.rfind("。"), chunk.rfind("；"), chunk.rfind(";"))
            if break_at > size // 2:
                chunk = chunk[: break_at + 1]
        if chunk.strip():
            chunks.append(chunk.strip())
    return chunks


def _ocr_page(page: Any, engine: Any, zoom: float) -> str:
    import pymupdf

    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        pix.save(str(temp_path))
        boxes = ocr_image(engine, temp_path)
    finally:
        temp_path.unlink(missing_ok=True)

    lines = group_ocr_lines(boxes)
    parts: list[str] = []
    for line in lines:
        cells = split_ocr_cells(line)
        parts.append(" | ".join(cells))
    return "\n".join(parts)


_WATERMARK_FRAGMENTS = (
    "住房城乡建设部信息公开浏览专用",
    "信息公开浏览专用",
    "文档来源于网络",
    "全咨之家",
    "仅供学习交流",
)


def _is_watermark_only(text: str) -> bool:
    cleaned = re.sub(r"[\s0-9\-—:：.。·、，,；;]+", "", text)
    if not cleaned:
        return False
    return any(
        cleaned.replace(fragment, "").strip() == ""
        for fragment in _WATERMARK_FRAGMENTS
        if fragment in cleaned
    )


def extract_pdf_snippets(
    path_str: str,
    *,
    zoom: float = 2.0,
    use_ocr: bool = True,
) -> list[dict[str, Any]]:
    import pymupdf

    doc = pymupdf.open(path_str)
    snippets: list[dict[str, Any]] = []
    ocr_engine = None
    try:
        for page_index, page in enumerate(doc, start=1):
            raw_text = page.get_text("text") or ""
            if len(raw_text.strip()) >= 30 and not _is_watermark_only(raw_text):
                text = raw_text
                book_page = None
            elif use_ocr:
                if ocr_engine is None:
                    from rapidocr_onnxruntime import RapidOCR

                    ocr_engine = RapidOCR(
                        intra_op_num_threads=int(
                            os.environ.get("RAPIDOCR_THREADS", "2")
                        ),
                        inter_op_num_threads=1,
                    )
                text = _ocr_page(page, ocr_engine, zoom)
                book_page = None
            else:
                continue

            if not text.strip():
                continue
            try:
                text = clean_kb_text(text)
            except Exception:
                pass
            book_page, text = extract_trailing_book_page(text)
            if book_page is not None and (
                book_page < 1 or book_page > doc.page_count + 5
            ):
                book_page = None
            if not text.strip():
                continue
            for chunk in _chunk_text(text):
                snippets.append(
                    {
                        "chapter": "原文",
                        "article": "",
                        "page": page_index,
                        "book_page": book_page,
                        "text": clean_extracted_text(chunk),
                    }
                )
    finally:
        doc.close()
    return snippets


def _build_document(
    *,
    standard: str,
    title: str,
    region: str,
    document_type: str,
    category: str,
    year: str,
    snippets: list[dict[str, Any]],
) -> dict[str, Any]:
    document = {
        "id": _make_doc_id(region, standard, title),
        "title": title,
        "standard": standard,
        "document_type": document_type,
        "region": region,
        "category": category,
        "year": int(year) if year.isdigit() else 0,
        "status": "待核实",
        "chapters": ["原文"],
        "snippets": snippets,
    }
    apply_priority(document)
    return document


def process_one(task: tuple[str, str, str, str, str, str, str, float, bool]) -> dict[str, Any]:
    (
        path_str,
        standard,
        title,
        region,
        document_type,
        category,
        year,
        zoom,
        use_ocr,
    ) = task
    try:
        snippets = extract_pdf_snippets(path_str, zoom=zoom, use_ocr=use_ocr)
        document = _build_document(
            standard=standard,
            title=title,
            region=region,
            document_type=document_type,
            category=category,
            year=year,
            snippets=snippets,
        )
        output = STANDARDS_DIR / f"{document['id']}.json"
        output.write_text(
            json.dumps({"documents": [document]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "path": path_str,
            "standard": standard,
            "title": title,
            "snippets": len(snippets),
            "error": "",
        }
    except Exception as exc:
        return {
            "path": path_str,
            "standard": standard,
            "title": title,
            "snippets": 0,
            "error": str(exc),
        }


def build_plan(
    pdf_dir: Path,
    *,
    skip_existing: bool,
) -> tuple[list[Path], list[str], list[str], dict[Path, Any]]:
    files = sorted(
        path
        for path in pdf_dir.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf"
    )
    existing = _existing_codes() if skip_existing else set()
    parsed_by_path: dict[Path, Any] = {}
    groups: dict[str, list[Path]] = {}
    for path in files:
        parsed = parse_standard_filename(path.name)
        parsed_by_path[path] = parsed
        if parsed.standard and parsed.standard != parsed.title:
            key = f"code:{normalize_standard_code(parsed.standard)}"
        else:
            key = f"title:{re.sub(r'\\W+', '', parsed.title.lower())}"
        groups.setdefault(key, []).append(path)

    chosen: list[Path] = []
    skipped_duplicates: list[str] = []
    skipped_existing: list[str] = []
    for key, paths in groups.items():
        parsed = parsed_by_path[paths[0]]
        if (
            key.startswith("code:")
            and normalize_standard_code(parsed.standard) in existing
        ):
            skipped_existing.extend(str(path) for path in paths)
            continue
        if len(paths) > 1:
            best = max(
                paths,
                key=lambda path: _text_profile_key(parsed_by_path[path], path),
            )
            skipped_duplicates.extend(
                str(path) for path in paths if path != best
            )
            chosen.append(best)
        else:
            chosen.append(paths[0])
    chosen.sort(key=lambda path: parsed_by_path[path].standard)
    return chosen, skipped_duplicates, skipped_existing, parsed_by_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="批量导入规范 PDF：文字层抽取 + 扫描页 OCR + 表格转正文 + 自动优先级"
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path(r"C:\Users\zhaof\Desktop\省标\城市规范"),
        help="PDF 所在目录",
    )
    parser.add_argument("--workers", type=int, default=4, help="并行进程数")
    parser.add_argument("--zoom", type=float, default=2.0, help="扫描页渲染倍率")
    parser.add_argument(
        "--ocr-threads",
        type=int,
        default=2,
        help="每个 OCR 进程使用的 CPU 线程数",
    )
    parser.add_argument("--no-ocr", action="store_true", help="扫描页不 OCR，直接跳过")
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="只导入有完整文字层的文件（扫描件跳过）",
    )
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 本（试点用）")
    parser.add_argument(
        "--report",
        type=Path,
        default=DATA_DIR / "import_city_report.json",
        help="导入报告输出路径",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="不跳过知识库已有的规范编号",
    )
    args = parser.parse_args()
    os.environ["RAPIDOCR_THREADS"] = str(args.ocr_threads)

    pdf_dir = args.pdf_dir.resolve()
    if not pdf_dir.exists():
        print(f"PDF 目录不存在：{pdf_dir}")
        return 1

    chosen, skipped_duplicates, skipped_existing, parsed_by_path = build_plan(
        pdf_dir,
        skip_existing=not args.no_skip_existing,
    )
    skipped_textless: list[str] = []
    if args.text_only:
        remaining: list[Path] = []
        for path in chosen:
            if _has_text_layer(path):
                remaining.append(path)
            else:
                skipped_textless.append(str(path))
        chosen = remaining
    if args.limit > 0:
        chosen = chosen[: args.limit]

    print(
        f"发现 {len(parsed_by_path)} 个 PDF，"
        f"重复跳过 {len(skipped_duplicates)}，"
        f"已在知识库跳过 {len(skipped_existing)}，"
        f"待导入 {len(chosen)}"
    )
    if not chosen:
        print("没有需要导入的文件")
        return 0

    tasks = []
    for path in chosen:
        parsed = parsed_by_path[path]
        tasks.append(
            (
                str(path),
                parsed.standard,
                parsed.title,
                parsed.region,
                parsed.standard_type,
                "城市规范",
                parsed.year,
                args.zoom,
                not args.no_ocr,
            )
        )

    results: list[dict[str, Any]] = []
    completed = 0
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(process_one, task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            completed += 1
            print(
                f"进度：{completed}/{len(tasks)} "
                f"{result.get('standard', '')} {result.get('title', '')} "
                f"error={result.get('error', '')}",
                flush=True,
            )

    imported = [item for item in results if not item["error"]]
    failed = [item for item in results if item["error"]]
    report = {
        "pdf_dir": str(pdf_dir),
        "total_pdfs": len(parsed_by_path),
        "skipped_duplicates": skipped_duplicates,
        "skipped_existing": skipped_existing,
        "skipped_textless": skipped_textless,
        "imported": imported,
        "failed": failed,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"导入完成：成功 {len(imported)}，失败 {len(failed)}")
    for item in imported:
        print(f"  + {item['standard']} {item['title']} ({item['snippets']} 片段)")
    for item in failed:
        print(f"  x {item['path']}: {item['error']}")
    print(f"报告：{args.report}")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
