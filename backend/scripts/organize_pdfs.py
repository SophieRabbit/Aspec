from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "data" / "pdfs"
ROOT = BASE.resolve()

REGION_MAP = {
    "1-国标": "国家标准",
    "2-成都": "地方标准/四川省/成都市",
    "3-四川": "地方标准/四川省",
    "4-河北": "地方标准/河北省",
    "5-云南": "地方标准/云南省/昆明市",
    "6-贵州": "地方标准/贵州省/贵阳市",
    "7-重庆": "地方标准/重庆市",
    "8-西安": "地方标准/陕西省/西安市",
    "9-新疆": "地方标准/新疆维吾尔自治区",
    "10-山西": "地方标准/山西省",
    "建筑资料集": "参考资料",
}

NON_PDF_LABEL = {
    "1-国标": "国家标准",
    "2-成都": "成都市",
    "3-四川": "四川省",
    "4-河北": "河北省",
    "5-云南": "云南省",
    "6-贵州": "贵州省",
    "7-重庆": "重庆市",
    "8-西安": "西安市",
    "9-新疆": "新疆维吾尔自治区",
    "10-山西": "山西省",
    "建筑资料集": "参考资料",
}

CITY_SUBFOLDERS = {"内江", "广安", "德阳", "眉山", "达州", "雅安", "保定"}
CITY_NAMES = {
    "内江": "内江市",
    "广安": "广安市",
    "德阳": "德阳市",
    "眉山": "眉山市",
    "达州": "达州市",
    "雅安": "雅安市",
    "保定": "保定市",
    "太原": "太原市",
}

SPECIAL = {
    "1-国标/1-国标/12J926 无障碍设计.pdf": "图集/国家标准图集/12J926 无障碍设计.pdf",
    "1-国标/1-国标/13J811-1改《建筑设计防火规范》图示（2015年修改版）-OCR版带书签.pdf": (
        "图集/国家标准图集/13J811-1 建筑设计防火规范图示（2015年修改版）.pdf"
    ),
    "1-国标/1-国标/GBT50353-2013 建筑工程建筑面积计算规范.pdf": (
        "国家标准/GBT 50353-2013 建筑工程建筑面积计算规范.pdf"
    ),
    "1-国标/1-国标/城市居住区规划设计标准（2018版）.pdf": (
        "国家标准/GB 50180-2018 城市居住区规划设计标准.pdf"
    ),
    "1-国标/1-国标/建筑设计防火规范.pdf": (
        "国家标准/GB 50016-2014（2018年版）建筑设计防火规范.pdf"
    ),
    "1-国标/1-国标/民用建筑通用规范.pdf": (
        "国家标准/GB 55031-2022 民用建筑通用规范.pdf"
    ),
    "2-成都/2-成都/蒲江/蒲江县规划管理技术规定《第三、第四章》.pdf": (
        "地方标准/四川省/成都市/蒲江县/蒲江县规划管理技术规定（第三、四章）.pdf"
    ),
    "2-成都/2-成都/2017VS2024红皮书 -0507 - ok +++.pdf": (
        "地方标准/四川省/成都市/成都市城市规划管理技术规定2017版与2024版对比.pdf"
    ),
    "8-西安/8-西安/03-2 城市一般控制区-10(1)(1).pdf": (
        "地方标准/陕西省/西安市/图则/西安市城市一般控制区图则.pdf"
    ),
    "8-西安/8-西安/03-7 重要发展区-10 (1)(1).pdf": (
        "地方标准/陕西省/西安市/图则/西安市重要发展区图则.pdf"
    ),
}


def clean_name(name: str) -> str:
    stem = Path(name).stem.strip()
    suffix = Path(name).suffix.lower()
    stem = re.sub(r"(?:[\[(][1-9][)\]]|\([1-9]\))+$", "", stem)
    stem = re.sub(r"\[1\]\(1\)$", "", stem)
    stem = re.sub(r"\s*\+{2,}\s*", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return f"{stem}{suffix}"


def unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    index = 2
    while True:
        candidate = dest.with_name(f"{dest.stem}-{index}{dest.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def destination_for(path: Path, parts: list[str]) -> Path:
    rel_key = "/".join(parts)
    if rel_key in SPECIAL:
        return ROOT / SPECIAL[rel_key]

    top = parts[0]
    if path.suffix.lower() == ".pdf":
        if top == "3-四川":
            city = next((part for part in parts[1:-1] if part in CITY_SUBFOLDERS), None)
            if city:
                dest = ROOT / f"地方标准/四川省/{CITY_NAMES[city]}"
            else:
                dest = ROOT / REGION_MAP[top]
        elif top == "4-河北" and any(part in CITY_SUBFOLDERS for part in parts[1:-1]):
            dest = ROOT / "地方标准/河北省/保定市"
        elif top == "10-山西" and any(part == "太原" for part in parts[1:-1]):
            dest = ROOT / "地方标准/山西省/太原市"
        elif top == "9-新疆" and "乌鲁木齐" in path.name:
            dest = ROOT / "地方标准/新疆维吾尔自治区/乌鲁木齐市"
        elif top == "2-成都" and any(part.startswith("公服规范") for part in parts[1:-1]):
            dest = ROOT / "地方标准/四川省/成都市/公建配套设施导则"
        elif top == "2-成都" and any(part == "蒲江" for part in parts[1:-1]):
            dest = ROOT / "地方标准/四川省/成都市/蒲江县"
        else:
            dest = ROOT / REGION_MAP.get(top, "未分类")
        return unique_dest(dest / clean_name(path.name))

    label = NON_PDF_LABEL.get(top, top)
    subdirs = [part for part in parts[1:-1] if not re.fullmatch(r"\d+-.*", part)]
    dest = ROOT / "其他资料" / label
    if subdirs:
        dest = dest.joinpath(*subdirs)
    return unique_dest(dest / clean_name(path.name))


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    moved = 0
    for path in sorted(BASE.rglob("*")):
        if not path.is_file() or path.name == "README.md":
            continue
        parts = [part for part in path.relative_to(BASE).parts if part != "."]
        dest = destination_for(path, parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        action = "计划移动" if dry_run else "移动"
        print(f"{action}: {path.relative_to(ROOT)} -> {dest.relative_to(ROOT)}")
        if not dry_run:
            try:
                shutil.move(str(path), str(dest))
                moved += 1
            except OSError as exc:
                print(f"失败: {path.name}: {exc}")

    if not dry_run:
        for directory in sorted(
            (item for item in BASE.rglob("*") if item.is_dir()),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
    print(f"\n{'计划整理' if dry_run else '整理完成'}：{moved if dry_run else moved} 个文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
