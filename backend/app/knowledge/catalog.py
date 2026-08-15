from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..config import DATA_DIR

CATEGORY_KEYWORDS = [
    ("建筑设计", "建筑设计"),
    ("建筑施工", "建筑施工"),
    ("建筑结构", "建筑结构"),
    ("给水排水", "给水排水"),
    ("给排水", "给水排水"),
    ("门窗玻璃", "门窗玻璃"),
    ("节能保温", "节能保温"),
    ("建筑材料", "建筑材料"),
    ("暖通", "暖通"),
    ("电气", "电气"),
    ("电力", "电力"),
    ("消防", "消防"),
    ("水利", "水利"),
    ("铁道交通", "铁道交通"),
    ("交通路桥", "交通路桥"),
    ("城建市政", "城建市政"),
    ("混凝土", "混凝土"),
    ("涂料防水", "涂料防水"),
    ("安全管理", "安全管理"),
    ("人防", "人防"),
    ("城市道路", "城市道路"),
    ("综合管廊", "综合管廊"),
    ("图集", "图集"),
]

CODE_PATTERN = re.compile(
    r"^([A-Z]{1,8}(?:[∕/_]?T)?[∕/_]?\s*\d{1,6}(?:\.\d+)?(?:[-—]\s*\d{4})?)",
    re.IGNORECASE,
)


def normalize_code(code: str) -> str:
    return re.sub(r"[\s/∕_\-—]", "", code).lower()


def code_series(code: str) -> str:
    match = re.match(r"([a-z]{1,8})(\d+)", normalize_code(code))
    if match:
        return match.group(1) + match.group(2)[:2]
    return ""


def _extract_code(filename: str) -> str:
    stem = Path(filename).stem.strip()
    match = CODE_PATTERN.match(stem)
    if match:
        return re.sub(r"\s+", "", match.group(1)).replace("∕", "/")
    return ""


def _extract_title(filename: str, code: str) -> str:
    stem = Path(filename).stem.strip()
    if not code:
        return stem
    return stem[len(code) :].lstrip(" -_—·：:：")


def _classify(folder: str, filename: str, code: str) -> str:
    raw = re.search(r"\u300a([^\u300b]+)\u300b", folder)
    text = raw.group(1) if raw else f"{folder} {filename}"
    for keyword, category in CATEGORY_KEYWORDS:
        if keyword in text:
            return category

    prefix = normalize_code(code)[:4]
    prefix_map = {
        "dlt": "电力",
        "tb": "铁道交通",
        "jtg": "交通路桥",
        "sl": "水利",
        "cjj": "城建市政",
        "cjt": "城建市政",
    }
    for prefix_key, category in prefix_map.items():
        if prefix.startswith(prefix_key):
            return category
    return "其他"


def parse_catalog(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        parts = line.rsplit("/,", 1)
        if len(parts) != 2:
            continue
        folder, filename = parts
        filename = filename.strip()
        if not filename.lower().endswith(".pdf"):
            continue
        code = _extract_code(filename)
        title = _extract_title(filename, code)
        category = _classify(folder, filename, code)
        if not title:
            title = filename
        entries.append(
            {
                "code": code,
                "title": title,
                "category": category,
                "path": f"{folder}/,{filename}",
            }
        )
    return entries


def _bigrams(text: str) -> set[str]:
    parts = re.findall(r"[\u4e00-\u9fff]+", text)
    grams: set[str] = set()
    for part in parts:
        if len(part) == 1:
            grams.add(part)
            continue
        for index in range(len(part) - 1):
            grams.add(part[index : index + 2])
    return grams


class Catalog:
    EXCLUDED_CATEGORIES = {"建筑设计", "图集"}

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        matches = sorted((DATA_DIR / "pdfs").glob("目录搜索*.txt"))
        if not matches:
            self.entries = []
            return
        self.entries = parse_catalog(matches[0])

    def recommend(
        self,
        query: str,
        exclude_codes: set[str] | None = None,
        limit_per_category: int = 3,
        max_total: int = 12,
    ) -> list[dict[str, Any]]:
        exclude_codes = exclude_codes or set()
        query_code = _extract_code(query) or ""
        series = code_series(query_code)
        query_grams = _bigrams(query)
        candidates: list[dict[str, Any]] = []

        for entry in self.entries:
            if entry["category"] in self.EXCLUDED_CATEGORIES:
                continue
            code = normalize_code(entry["code"])
            if not code or code in exclude_codes:
                continue
            score = 0.0
            if series and code_series(entry["code"]) == series:
                score += 20
            common = len(query_grams & _bigrams(entry["title"]))
            score += common * 3
            if score > 0:
                item = dict(entry)
                item["score"] = score
                candidates.append(item)

        candidates.sort(key=lambda item: item["score"], reverse=True)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in candidates:
            grouped.setdefault(item["category"], []).append(item)

        categories: list[dict[str, Any]] = []
        total = 0
        for category in sorted(grouped, key=lambda key: max(item["score"] for item in grouped[key]), reverse=True):
            items = [
                {"code": item["code"], "title": item["title"], "category": item["category"], "path": item["path"]}
                for item in grouped[category][:limit_per_category]
            ]
            categories.append({"category": category, "items": items})
            total += len(items)
            if total >= max_total:
                break
        return categories


def save_catalog_cache(path: Path, entries: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
