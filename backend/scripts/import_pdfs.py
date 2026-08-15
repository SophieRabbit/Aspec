from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR, STANDARDS_DIR  # noqa: E402
from app.knowledge.loader import KnowledgeBase  # noqa: E402

PDFS_DIR = DATA_DIR / "pdfs"

STD_PATTERN = re.compile(r"^([A-Z/]{1,5}\s*\d[\d.\-A-Za-z（()）]*)\s*[-_·\s]*\s*(.+)$")
SCOPE_FOLDERS = ("国家标准", "地方标准", "国家图集", "地方图集")

PROVINCE_MAP = {
    "江苏": "江苏省",
    "上海": "上海市",
    "北京": "北京市",
    "重庆": "重庆市",
    "云南": "云南省",
    "贵州": "贵州省",
    "陕西": "陕西省",
    "山西": "山西省",
    "浙江": "浙江省",
    "广东": "广东省",
    "河北": "河北省",
    "四川": "四川省",
    "新疆": "新疆维吾尔自治区",
    "海南": "海南省",
}

REGION_FOLDER_NAMES = {
    "中国南部标准": "中南地区",
    "华东地区": "华东地区",
    "华北地区": "华北地区",
    "西南标准": "西南地区",
}


def parse_filename(filename: str) -> tuple[str, str]:
    stem = Path(filename).stem
    match = STD_PATTERN.match(stem.strip())
    if match:
        standard = re.sub(r"\s+", " ", match.group(1)).strip()
        if standard.startswith("GBT"):
            standard = "GB/T" + standard[3:]
        title = re.sub(r"\s+", " ", match.group(2)).strip()
        return standard, title
    return stem.strip(), stem.strip()


def detect_metadata(relative_parts: list[str]) -> tuple[str, str, str]:
    parents = relative_parts[:-1] if relative_parts else []
    is_province_set = any("省标" in part or part in REGION_FOLDER_NAMES for part in parents)
    scope = "地方" if (any("地方" in part for part in parents) or is_province_set) else "国家"
    kind = "图集" if any("图集" in part for part in parents) else "规范"
    if kind == "图集":
        document_type = "国家图集" if scope == "国家" else "地方图集"
    else:
        document_type = "国家标准" if scope == "国家" else "地方标准"
    category = "建筑设计" if any("建筑设计" in part for part in parents) else ""

    region = "全国"
    if scope == "地方" and parents:
        candidates = [
            part
            for part in parents
            if part not in SCOPE_FOLDERS
            and "图集" not in part
            and "系列" not in part
            and "合订" not in part
            and "G101" not in part
        ]
        if is_province_set:
            candidates = [part for part in candidates if part != "省标"]
        else:
            candidates = [part for part in candidates if "标准" not in part]
        if candidates:
            region = resolve_region_name(candidates[-1])
    return region, document_type, category


def resolve_region_name(folder: str) -> str:
    cleaned = re.sub(r"^\d+", "", folder)
    if cleaned in REGION_FOLDER_NAMES:
        return REGION_FOLDER_NAMES[cleaned]
    if "省标" in cleaned:
        cleaned = cleaned.replace("省标", "")
    if cleaned in PROVINCE_MAP:
        return PROVINCE_MAP[cleaned]
    return folder


def make_doc_id(region: str, standard: str, title: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", f"{region}-{standard or title}").strip("-").lower()
    return slug or "document"


def ingest_one(task: tuple[str, str, str, str, str, str, bool, str]) -> tuple[str, str]:
    path_str, standard, title, region, document_type, category, delete_after, engine = task
    path = Path(path_str)
    try:
        knowledge_base = KnowledgeBase()
        knowledge_base.ingest_pdf(
            path,
            title=title,
            standard=standard,
            region=region,
            document_type=document_type,
            category=category,
            engine=engine,
        )
        if delete_after:
            path.unlink()
        return path.name, ""
    except Exception as exc:
        return path.name, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="把 PDF 规范导入为可检索知识库")
    parser.add_argument(
        "--pdf-dir",
        default=str(PDFS_DIR),
        help="PDF 所在目录，默认 data/pdfs；支持外部硬盘或服务器目录",
    )
    parser.add_argument(
        "--delete-after",
        action="store_true",
        help="导入成功后删除原 PDF（请确认备份后再使用）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="并行导入进程数，默认 4",
    )
    parser.add_argument(
        "--engine",
        choices=("pypdf", "pymupdf"),
        default="pypdf",
        help="PDF 文本提取引擎，pymupdf 效果通常更好但需要安装",
    )
    args = parser.parse_args()

    pdfs_dir = Path(args.pdf_dir).resolve()
    pdfs_dir.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(pdfs_dir.rglob("*.pdf"))
    if not pdf_files:
        print(f"目录中没有 PDF：{pdfs_dir}")
        print("请把规范 PDF 放进来后重新运行。")
        return 1

    imported: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    seen_ids: set[str] = set()
    tasks: list[tuple[str, str, str, str, str, str, bool, str]] = []

    for path in pdf_files:
        standard, title = parse_filename(path.name)
        relative_parts = [part for part in path.relative_to(pdfs_dir).parts if part != "."]
        region, document_type, category = detect_metadata(relative_parts)
        doc_id = make_doc_id(region, standard, title)
        if (STANDARDS_DIR / f"{doc_id}.json").exists() or doc_id in seen_ids:
            skipped.append(path.name)
            continue
        seen_ids.add(doc_id)
        tasks.append((str(path), standard, title, region, document_type, category, args.delete_after, args.engine))

    print(f"待导入 {len(tasks)} 份，已存在/重复跳过 {len(skipped)} 份，使用 {args.workers} 个进程")
    if not tasks:
        print("没有需要导入的文件")
        return 0

    completed = 0
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(ingest_one, task) for task in tasks]
        for future in as_completed(futures):
            name, error = future.result()
            completed += 1
            if error:
                failed.append(f"{name}: {error}")
            else:
                imported.append(name)
            if completed % 20 == 0 or completed == len(tasks):
                print(f"进度：{completed}/{len(tasks)}")

    print(f"导入完成：新增 {len(imported)} 份，跳过 {len(skipped)} 份，失败 {len(failed)} 份")
    if args.delete_after:
        print("已按 --delete-after 删除导入成功的原 PDF。")
    else:
        print("原 PDF 未删除；如需释放空间，请确认索引可用后运行：python scripts/import_pdfs.py --delete-after")
    for name in imported:
        print(f"  + {name}")
    for name in skipped:
        print(f"  = {name}")
    for item in failed:
        print(f"  x {item}")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
