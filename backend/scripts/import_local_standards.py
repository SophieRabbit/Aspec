from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

os.environ.setdefault("OMP_NUM_THREADS", "1")

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from app.config import DATA_DIR, STANDARDS_DIR  # noqa: E402
from app.knowledge.region_hierarchy import (  # noqa: E402
    ALIASES,
    KNOWN_HIERARCHY,
)
from app.knowledge.priority_engine import (  # noqa: E402
    apply_priority,
    normalize_standard_code,
    parse_standard_filename,
)
from import_standards_ocr import (  # noqa: E402
    extract_pdf_snippets,
    _text_profile,
)

_EXTRA_REGIONS = {
    "广西省": "广西壮族自治区",
    "广西": "广西壮族自治区",
    "新疆省": "新疆维吾尔自治区",
    "湖北省": "湖北省",
    "河南省": "河南省",
    "福建省": "福建省",
    "河北省": "河北省",
    "山西省": "山西省",
    "陕西省": "陕西省",
}


def _canonical_region(parts: list[str]) -> str:
    for raw in reversed(parts):
        name = raw.strip()
        if name in KNOWN_HIERARCHY:
            return name
        if name in ALIASES:
            return ALIASES[name]
        if name in ALIASES.values():
            return name
        if name in _EXTRA_REGIONS:
            return _EXTRA_REGIONS[name]
        stripped = name[:-1] if name.endswith("省") else name
        if stripped in ALIASES:
            return ALIASES[stripped]
    return "全国"


def _clean_fallback_title(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"^\d+[-_\s]+", "", stem)
    stem = re.sub(r"[《》「」『』]", "", stem).strip()
    return stem


def _infer_version_year(filename: str) -> str:
    match = re.search(r"(?:19|20)\d{2}", filename)
    if match:
        return match.group(0)
    match = re.search(r"(?<!\d)(\d{2})\s*版", filename)
    if match:
        year_two = int(match.group(1))
        if year_two <= 39:
            return f"20{year_two:02d}"
        return f"19{year_two:02d}"
    return ""


def _local_meta(path: Path, pdf_dir: Path) -> dict[str, str]:
    relative_parts = list(path.relative_to(pdf_dir).parts)
    parsed = parse_standard_filename(path.name)
    region = _canonical_region(relative_parts[:-1])
    for alias in sorted(ALIASES, key=len, reverse=True):
        if alias in path.name:
            canonical = ALIASES[alias]
            if canonical in KNOWN_HIERARCHY and len(canonical) > len(region):
                region = canonical
    standard = ""
    title = _clean_fallback_title(path.name)
    year = ""
    if parsed.standard and parsed.standard != parsed.title:
        standard = parsed.standard
        title = parsed.title
        year = parsed.year
    if not year:
        year = _infer_version_year(path.name)
    guide_parents = [
        part for part in relative_parts[:-1] if part.endswith("导则")
    ]
    if guide_parents and "成都" not in title:
        title = f"{guide_parents[-1]}-{title}"
    document_type = parsed.standard_type
    if not standard:
        document_type = "地方文件"
    return {
        "region": region,
        "standard": standard,
        "title": title,
        "year": year,
        "document_type": document_type,
    }


def _existing_keys() -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    for path in STANDARDS_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        documents = (
            payload if isinstance(payload, list) else payload.get("documents", [])
        )
        for document in documents:
            keys.add(
                (
                    document.get("region", ""),
                    normalize_standard_code(document.get("standard", "")),
                    document.get("title", ""),
                )
            )
    return keys


def _make_doc_id(region: str, standard: str, title: str) -> str:
    slug = re.sub(
        r"[^0-9a-zA-Z\u4e00-\u9fff]+",
        "-",
        f"{region}-{standard or title}",
    ).strip("-").lower()
    return slug or "document"


def _build_document(
    *,
    region: str,
    standard: str,
    title: str,
    year: str,
    document_type: str,
    snippets: list[dict[str, Any]],
) -> dict[str, Any]:
    document = {
        "id": _make_doc_id(region, standard, title),
        "title": title,
        "standard": standard,
        "document_type": document_type,
        "region": region,
        "category": "地方规范",
        "year": int(year) if year.isdigit() else 0,
        "status": "待核实",
        "chapters": ["原文"],
        "snippets": snippets,
    }
    apply_priority(document)
    return document


def process_one(task: tuple[str, str, str, str, str, float, bool]) -> dict[str, Any]:
    path_str, region, standard, title, year, document_type, zoom, use_ocr = (
        *task[:6],
        task[6],
        task[7],
    )
    try:
        snippets = extract_pdf_snippets(
            path_str,
            zoom=zoom,
            use_ocr=use_ocr,
        )
        document = _build_document(
            region=region,
            standard=standard,
            title=title,
            year=year,
            document_type=document_type,
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
            "region": region,
            "snippets": len(snippets),
            "error": "",
        }
    except Exception as exc:
        return {
            "path": path_str,
            "standard": standard,
            "title": title,
            "region": region,
            "snippets": 0,
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="批量导入地方规范：按省/市目录识别地区，无编号文件按标题入库"
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path(r"C:\Users\zhaof\Desktop\省标\地方规范"),
    )
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--zoom", type=float, default=2.0)
    parser.add_argument("--ocr-threads", type=int, default=2)
    parser.add_argument("--text-only", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--report",
        type=Path,
        default=DATA_DIR / "import_local_report.json",
    )
    args = parser.parse_args()
    os.environ["RAPIDOCR_THREADS"] = str(args.ocr_threads)

    pdf_dir = args.pdf_dir.resolve()
    if not pdf_dir.exists():
        print(f"PDF 目录不存在：{pdf_dir}")
        return 1
    files = sorted(
        {
            path
            for path in pdf_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == ".pdf"
        }
    )
    existing = _existing_keys()
    groups: dict[tuple[str, str], list[Path]] = {}
    meta_by_path: dict[Path, dict[str, str]] = {}
    for path in files:
        meta = _local_meta(path, pdf_dir)
        meta_by_path[path] = meta
        code_key = normalize_standard_code(meta["standard"]) if meta["standard"] else ""
        title_key = re.sub(r"\W+", "", meta["title"].lower())
        group_key = (
            f"code:{code_key}" if code_key else f"title:{title_key}"
        )
        groups.setdefault((meta["region"], group_key), []).append(path)

    chosen: list[Path] = []
    skipped_existing: list[str] = []
    skipped_duplicates: list[str] = []
    for (region, key), paths in groups.items():
        meta = meta_by_path[paths[0]]
        exists = False
        if meta["standard"]:
            code_norm = normalize_standard_code(meta["standard"])
            exists = (region, code_norm, "") in existing or any(
                item[1] == code_norm for item in existing if item[0] == region
            )
        elif (region, "", meta["title"]) in existing:
            exists = True
        if exists:
            skipped_existing.extend(str(path) for path in paths)
            continue
        if len(paths) > 1:
            best = max(
                paths,
                key=lambda path: (
                    _text_profile(path)["chars"]
                    / max(1, _text_profile(path)["pages"]),
                    _text_profile(path)["pages"],
                    -path.stat().st_size,
                ),
            )
            skipped_duplicates.extend(
                str(path) for path in paths if path != best
            )
            chosen.append(best)
        else:
            chosen.append(paths[0])

    if args.text_only:
        chosen = [
            path
            for path in chosen
            if _text_profile(path)["chars"] / max(1, _text_profile(path)["pages"])
            >= 30
        ]
    if args.limit > 0:
        chosen = chosen[: args.limit]

    print(
        f"发现 {len(files)} 个 PDF，重复 {len(skipped_duplicates)}，"
        f"已在库 {len(skipped_existing)}，待导入 {len(chosen)}"
    )
    if not chosen:
        print("没有需要导入的文件")
        return 0

    tasks = []
    for path in chosen:
        meta = meta_by_path[path]
        tasks.append(
            (
                str(path),
                meta["region"],
                meta["standard"],
                meta["title"],
                meta["year"],
                meta["document_type"],
                args.zoom,
                not args.text_only,
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
                f"{result.get('standard', '') or result.get('title', '')} "
                f"error={result.get('error', '')}",
                flush=True,
            )

    imported = [item for item in results if not item["error"]]
    failed = [item for item in results if item["error"]]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(
            {
                "pdf_dir": str(pdf_dir),
                "imported": imported,
                "failed": failed,
                "skipped_existing": skipped_existing,
                "skipped_duplicates": skipped_duplicates,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"导入完成：成功 {len(imported)}，失败 {len(failed)}")
    for item in imported:
        print(
            f"  + {item['region']} {item['standard'] or item['title']} "
            f"({item['snippets']} 片段)"
        )
    for item in failed:
        print(f"  x {item['path']}: {item['error']}")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
