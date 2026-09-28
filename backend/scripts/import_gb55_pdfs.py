from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import PRIORITY_STANDARDS_PATH  # noqa: E402
from app.knowledge.catalog import normalize_code  # noqa: E402
from app.knowledge.loader import KnowledgeBase  # noqa: E402

STD_PATTERN = re.compile(r"^(GB\s?5\d{4}-\d{4})\s*[-_·\s]*\s*(.+)$")
AUX_MARKERS = ("实施指南", "宣贯", "解读", "专家解答")
TITLE_HINTS = {
    "GB55030-2022": "防水",
    "GB55031-2022": "民用建筑",
    "GB55037-2022": "建筑防火通用规范",
}


def parse_gb55(path: Path) -> tuple[str, str] | None:
    stem = Path(path).stem.strip()
    match = STD_PATTERN.match(stem)
    if not match:
        return None
    code = match.group(1).replace(" ", "").strip()
    title = re.sub(r"\s+", " ", match.group(2)).strip(" -_·《》！？")
    return code, title


def select_canonical_files(files: list[Path]) -> tuple[list[Path], list[str]]:
    groups: dict[str, list[Path]] = {}
    for path in files:
        parsed = parse_gb55(path)
        if parsed:
            groups.setdefault(parsed[0], []).append(path)

    selected: list[Path] = []
    skipped: list[str] = []
    for code, paths in sorted(groups.items()):
        candidates = [
            path
            for path in paths
            if not any(marker in path.name for marker in AUX_MARKERS)
            and (code not in TITLE_HINTS or TITLE_HINTS[code] in path.name)
        ]
        if not candidates:
            skipped.extend(f"{path.name}（疑似重复/误命名/解读文件，已跳过）" for path in paths)
            continue
        best_by_title: dict[str, Path] = {}
        for path in candidates:
            code_part, _ = parse_gb55(path)
            title_key = re.sub(r"[\s.。!！?？《》]", "", Path(path).stem[len(code_part) :])
            if title_key not in best_by_title or path.stat().st_size > best_by_title[title_key].stat().st_size:
                best_by_title[title_key] = path
        selected.extend(best_by_title.values())
        for path in paths:
            if path not in best_by_title.values():
                skipped.append(f"{path.name}（重复文件，已跳过）")
    return selected, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Import canonical GB55 full-text PDFs")
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=Path(r"C:\Users\zhaof\Desktop\省标\通用规范"),
        help="directory containing GB55 PDFs",
    )
    parser.add_argument("--engine", choices=("pypdf", "pymupdf"), default="pymupdf")
    args = parser.parse_args()

    pdf_dir = args.pdf_dir
    if not pdf_dir.exists():
        print(f"未找到 PDF 目录：{pdf_dir}")
        return
    files = sorted(pdf_dir.glob("*.pdf"))
    selected, skipped = select_canonical_files(files)
    unmatched = [path for path in files if parse_gb55(path) is None]
    skipped.extend(f"{path.name}（未识别为单本 GB55 标准，已跳过）" for path in unmatched)

    manifest = json.loads(PRIORITY_STANDARDS_PATH.read_text(encoding="utf-8"))
    manifest_by_code = {
        normalize_code(item.get("code", "")): item
        for item in manifest
        if item.get("code")
    }

    knowledge_base = KnowledgeBase()
    imported: list[str] = []
    failed: list[str] = []
    for path in selected:
        parsed = parse_gb55(path)
        if not parsed:
            continue
        code, title = parsed
        category = manifest_by_code.get(normalize_code(code), {}).get("category", "通用规范")
        try:
            knowledge_base.ingest_pdf(
                path,
                title=title,
                standard=code,
                region="全国",
                document_type="国家标准",
                category=category,
                engine=args.engine,
                reload_after=False,
            )
            imported.append(code)
        except Exception as exc:
            failed.append(f"{path.name}: {exc}")

    knowledge_base.reload()
    print(f"导入 {len(imported)} 份，跳过 {len(skipped)} 份，失败 {len(failed)} 份")
    for code in imported:
        print(f"  + {code}")
    for item in skipped:
        print(f"  = {item}")
    for item in failed:
        print(f"  x {item}")


if __name__ == "__main__":
    main()
