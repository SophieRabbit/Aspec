from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from docx import Document  # noqa: E402
from docx.oxml.table import CT_Tbl  # noqa: E402
from docx.oxml.text.paragraph import CT_P  # noqa: E402
from docx.table import Table, _Cell  # noqa: E402
from docx.text.paragraph import Paragraph  # noqa: E402

from app.config import DATA_DIR, STANDARDS_DIR  # noqa: E402
from app.knowledge.region_hierarchy import ALIASES, KNOWN_HIERARCHY  # noqa: E402
from app.knowledge.priority_engine import (  # noqa: E402
    normalize_standard_code,
    parse_standard_filename,
)
from app.knowledge.text_cleaner import normalize_ocr_paragraphs  # noqa: E402

NOISE_MARKERS = (
    "www.bzfxw.com",
    "标准分享网",
    "文档来源于网络",
    "全咨之家",
)
ARTICLE_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,3})")


def _clean_text(value: str) -> str:
    text = value.replace("\u3000", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff]) (?=[\u4e00-\u9fff])", "", text)
    return text.strip()


def _is_noise(text: str) -> bool:
    return any(marker in text for marker in NOISE_MARKERS)


def _iter_block_items(document: Any) -> Iterator[Paragraph | Table]:
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _paragraph_ends_section(paragraph: Paragraph) -> bool:
    return "w:sectPr" in paragraph._p.xml


def _cell_text(cell: _Cell) -> str:
    return _clean_text(cell.text)


def _render_table(table: Table) -> str:
    rendered_rows: list[list[dict[str, Any]]] = []
    active_merges: dict[int, dict[str, Any]] = {}

    for row in table.rows:
        rendered_cells: list[dict[str, Any]] = []
        column_index = 0
        for cell_xml in row._tr.tc_lst:
            cell = _Cell(cell_xml, table)
            text = _cell_text(cell)
            merge_value = str(cell_xml.vMerge or "").lower()
            colspan = max(1, int(cell_xml.grid_span or 1))
            if cell_xml.vMerge is not None and merge_value in ("", "continue"):
                anchor = next(
                    (
                        active_merges[index]
                        for index in range(column_index, column_index + colspan)
                        if index in active_merges
                    ),
                    None,
                )
                if anchor is not None:
                    anchor["rowspan"] += 1
                    for index in range(column_index, column_index + colspan):
                        active_merges[index] = anchor
                rendered_cells.append({"skip": True})
            else:
                rendered_cell = {
                    "text": text,
                    "rowspan": 1,
                    "colspan": colspan,
                    "skip": False,
                }
                rendered_cells.append(rendered_cell)
                for index in range(column_index, column_index + colspan):
                    if merge_value == "restart":
                        active_merges[index] = rendered_cell
                    else:
                        active_merges.pop(index, None)
            column_index += colspan
        rendered_rows.append(rendered_cells)

    if not any(
        not cell.get("skip") and str(cell.get("text", "")).strip()
        for row in rendered_rows
        for cell in row
    ):
        return ""

    lines: list[str] = []
    for row in rendered_rows:
        cells: list[str] = []
        for cell in row:
            if cell.get("skip"):
                continue
            text = str(cell.get("text", "")).strip() or " "
            if cell["rowspan"] > 1:
                text = f"{text} @rowspan={cell['rowspan']}".strip()
            if cell["colspan"] > 1:
                text = f"{text} @colspan={cell['colspan']}".strip()
            cells.append(text)
        if cells:
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def extract_docx_snippets(
    path: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    document = Document(path)
    snippets: list[dict[str, Any]] = []
    page_blocks: list[str] = []
    page_number = 1
    table_count = 0
    paragraph_count = 0

    def flush_page() -> None:
        nonlocal page_number
        text = normalize_ocr_paragraphs("\n".join(page_blocks)).strip()
        if text:
            article_match = ARTICLE_RE.match(text)
            snippets.append(
                {
                    "chapter": "原文",
                    "article": article_match.group(1) if article_match else "",
                    "page": page_number,
                    "book_page": None,
                    "text": text,
                }
            )
        page_blocks.clear()
        page_number += 1

    for block in _iter_block_items(document):
        if isinstance(block, Paragraph):
            text = _clean_text(block.text)
            if text and not _is_noise(text):
                page_blocks.append(text)
                paragraph_count += 1
            if _paragraph_ends_section(block):
                flush_page()
            continue

        table = _render_table(block).strip()
        if table:
            page_blocks.append(table)
            table_count += 1

    flush_page()
    return snippets, {
        "paragraphs": paragraph_count,
        "tables": table_count,
        "pages": page_number - 1,
        "snippets": len(snippets),
        "characters": sum(len(item["text"]) for item in snippets),
    }


def _normalize_match_text(value: str) -> str:
    value = re.sub(r"(?i)\.(docx|pdf)$", "", value)
    value = re.sub(
        r"[\s_\-—－()（）【】\[\]《》〈〉“”\"'·、，,。.]+",
        "",
        value,
    )
    return value.lower()


def _normalize_region_text(value: str) -> str:
    value = _normalize_match_text(value)
    return re.sub(
        r"(特别行政区|维吾尔自治区|壮族自治区|回族自治区|自治区|省|市|区|县)$",
        "",
        value,
    )


def _load_standard_index() -> tuple[
    dict[str, tuple[Path, dict[str, Any], dict[str, Any]]],
    list[tuple[Path, dict[str, Any], dict[str, Any]]],
]:
    index: dict[str, tuple[Path, dict[str, Any], dict[str, Any]]] = {}
    records: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    for path in sorted(STANDARDS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        documents = payload if isinstance(payload, list) else payload.get("documents", [])
        for document in documents:
            code = normalize_standard_code(str(document.get("standard", "")))
            if code:
                index[code] = (path, payload, document)
            records.append((path, payload, document))
    return index, records


def _region_matches(path: Path, document: dict[str, Any]) -> bool:
    path_regions = {
        _normalize_region_text(part)
        for part in path.parts[:-1]
        if part and part not in (path.anchor, "Desktop", "省标", "地方规范")
    }
    document_regions = {
        _normalize_region_text(str(document.get(key, "")))
        for key in ("region", "province", "city", "district")
        if document.get(key)
    }
    return bool(path_regions & document_regions)


def _known_path_regions(path: Path) -> set[str]:
    known = {
        _normalize_region_text(name)
        for name in set(KNOWN_HIERARCHY) | set(ALIASES.values())
    }
    path_regions = {
        _normalize_region_text(part)
        for part in path.parts[:-1]
        if part and part not in (path.anchor, "Desktop", "省标", "地方规范")
    }
    return path_regions & known


def _match_by_title(
    path: Path,
    records: list[tuple[Path, dict[str, Any], dict[str, Any]]],
) -> tuple[float, Path, dict[str, Any], dict[str, Any]] | None:
    source_key = _normalize_match_text(path.stem)
    source_regions = _known_path_regions(path)
    candidates: list[tuple[float, Path, dict[str, Any], dict[str, Any]]] = []
    for target_path, payload, document in records:
        title_key = _normalize_match_text(str(document.get("title", "")))
        if not source_key or not title_key:
            continue
        document_regions = {
            _normalize_region_text(str(document.get(key, "")))
            for key in ("region", "province", "city", "district")
            if document.get(key)
        }
        if (
            source_regions
            and document_regions
            and not source_regions & document_regions
        ):
            continue
        if source_key == title_key:
            score = 1.0
        elif source_key in title_key or title_key in source_key:
            score = 0.82 + 0.12 * (
                min(len(source_key), len(title_key))
                / max(len(source_key), len(title_key))
            )
        else:
            score = difflib.SequenceMatcher(
                None,
                source_key,
                title_key,
            ).ratio()
        if _region_matches(path, document):
            score += 0.08
        if score >= 0.78:
            candidates.append((score, target_path, payload, document))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0]


def _backup_targets(paths: list[Path]) -> Path:
    backup_dir = DATA_DIR / "backups" / f"docx-import-{datetime.now():%Y%m%d-%H%M%S}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for path in sorted(set(paths)):
        shutil.copy2(path, backup_dir / path.name)
    return backup_dir


def import_docx_standards(
    docx_dir: Path,
    *,
    write: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    docx_paths = sorted(docx_dir.rglob("*.docx"))
    index, records = _load_standard_index()
    target_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    duplicates: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    target_paths: list[Path] = []
    payloads: dict[Path, dict[str, Any]] = {}

    for path in docx_paths:
        parsed = parse_standard_filename(path.name)
        target = index.get(normalize_standard_code(parsed.standard))
        if target is None:
            title_match = _match_by_title(path, records)
            if title_match is not None:
                _, target_path, payload, document = title_match
                target = (target_path, payload, document)
        if target is None:
            results.append(
                {
                    "source": str(path),
                    "standard": parsed.standard,
                    "title": parsed.title,
                    "status": "unmatched",
                }
            )
            continue
        target_path, payload, document = target
        target_groups.setdefault(
            (str(target_path), str(document.get("id", ""))),
            [],
        ).append(
            {
                "source": path,
                "target_path": target_path,
                "payload": payload,
                "document": document,
                "parsed": parsed,
            }
        )

    selected: list[dict[str, Any]] = []
    for items in target_groups.values():
        chosen = max(items, key=lambda item: item["source"].stat().st_size)
        selected.append(chosen)
        if len(items) > 1:
            duplicates.append(
                {
                    "standard": chosen["document"].get("standard", ""),
                    "selected": chosen["source"].name,
                    "candidates": [
                        str(item["source"])
                        for item in items
                    ],
                }
            )

    for item in selected:
        path = item["source"]
        parsed = item["parsed"]
        target_path = item["target_path"]
        payload = item["payload"]
        document = item["document"]
        snippets, stats = extract_docx_snippets(path)
        if not snippets:
            results.append(
                {
                    "source": str(path),
                    "standard": parsed.standard,
                    "title": document.get("title", parsed.title),
                    "status": "empty",
                    **stats,
                }
            )
            continue

        document["snippets"] = snippets
        payloads[target_path] = payload
        target_paths.append(target_path)
        results.append(
            {
                "source": str(path),
                "target": str(target_path),
                "standard": document.get("standard", parsed.standard),
                "title": document.get("title", parsed.title),
                "status": "ready",
                **stats,
            }
        )

    backup_dir: Path | None = None
    if write and payloads:
        backup_dir = _backup_targets(target_paths)
        for path, payload in payloads.items():
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        for result in results:
            if result.get("status") == "ready":
                result["status"] = "written"

    report = {
        "docx_files": len(docx_paths),
        "selected_docx": len(selected),
        "matched": sum(1 for item in results if item["status"] != "unmatched"),
        "written": sum(1 for item in results if item["status"] == "written"),
        "backup_dir": str(backup_dir) if backup_dir else "",
        "duplicates": duplicates,
        "results": results,
    }
    return report, results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import Word standards and replace matching PDF/OCR knowledge JSON."
    )
    parser.add_argument("docx_dir", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--report",
        type=Path,
        default=DATA_DIR / "import_docx_report.json",
    )
    args = parser.parse_args()

    report, _ = import_docx_standards(args.docx_dir, write=args.write)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    mode = "written" if args.write else "preview"
    print(
        f"{mode}: docx={report['docx_files']}, selected={report['selected_docx']}, "
        f"matched={report['matched']}, written={report['written']}, "
        f"backup={report['backup_dir'] or '-'}"
    )
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
