from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import PRIORITY_PDFS_DIR, PRIORITY_STANDARDS_PATH
from app.knowledge.catalog import normalize_code
from app.knowledge.loader import KnowledgeBase


def find_pdf_for_standard(item: dict, files: list[Path]) -> Path | None:
    code = normalize_code(item.get("code", ""))
    title = re.sub(r"[\s、，。]", "", item.get("title", ""))
    for path in files:
        stem = Path(path).stem
        normalized_stem = normalize_code(stem)
        if code and (normalized_stem.startswith(code) or code in normalized_stem):
            return path
        if title and title in stem:
            return path
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legal PDFs for priority standards")
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=PRIORITY_PDFS_DIR,
        help="directory containing priority standard PDFs",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PRIORITY_STANDARDS_PATH,
        help="priority standards manifest JSON",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    pdf_dir = args.pdf_dir
    if not pdf_dir.exists():
        print(f"未找到 PDF 目录：{pdf_dir}")
        return
    files = sorted(pdf_dir.rglob("*.pdf"))

    knowledge_base = KnowledgeBase()
    imported: list[str] = []
    missing: list[dict[str, str]] = []

    for item in manifest:
        pdf_path = find_pdf_for_standard(item, files)
        if not pdf_path:
            missing.append({"code": item["code"], "title": item["title"]})
            continue
        document_type = "行业标准" if str(item["code"]).startswith(("JGJ", "CJJ")) else "国家标准"
        knowledge_base.ingest_pdf(
            pdf_path,
            title=item["title"],
            standard=item["code"],
            document_type=document_type,
        )
        imported.append(item["code"])

    print(f"导入 {len(imported)} 项，缺失 {len(missing)} 项")
    if missing:
        print("缺失清单：")
        for item in missing:
            print(f"- {item['code']} {item['title']}")


if __name__ == "__main__":
    main()
