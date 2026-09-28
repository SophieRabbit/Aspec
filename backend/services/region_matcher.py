from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "regions.json"
REGION_GROUPS = {
    "四川省": "西南地区",
    "北京市": "华北地区",
    "上海市": "华东地区",
    "广东省": "华南地区",
}
MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}


@dataclass(frozen=True)
class Region:
    name: str
    aliases: tuple[str, ...]
    region_code: str
    local_standards: tuple[str, ...]
    parent: str = ""
    path: tuple[str, ...] = ()

    def to_scope(self) -> dict[str, str]:
        province = ""
        city = ""
        district = ""
        region = ""
        for item in self.path:
            if item in ("华北地区", "华东地区", "华中地区", "华南地区", "西南地区", "西北地区", "东北地区"):
                region = item
            elif item.endswith(("省", "自治区")) or item in MUNICIPALITIES:
                province = item
            elif item.endswith("市"):
                if self.name == item:
                    city = item
                else:
                    city = item
            elif item.endswith(("区", "县", "旗")):
                district = item
        if self.name.endswith(("区", "县", "旗")) and self.name not in MUNICIPALITIES:
            district = self.name
        elif self.name.endswith("市"):
            if self.name in MUNICIPALITIES:
                province = self.name
            else:
                city = self.name
        elif self.name.endswith(("省", "自治区", "直辖市")):
            province = self.name
        else:
            region = self.name
        scope = "district" if district else "city" if city else "province" if province else "region"
        return {
            "place": self.name,
            "province": province,
            "city": city,
            "district": district,
            "region": region,
            "scope": scope,
        }


@lru_cache(maxsize=1)
def _load_regions() -> dict[str, dict[str, object]]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return {
        str(name): item
        for name, item in payload.items()
        if isinstance(item, dict)
    }


def _build_region(name: str) -> Region | None:
    item = _load_regions().get(name)
    if item is None:
        return None
    path: list[str] = [name]
    parent = str(item.get("parent", "") or "")
    visited = {name}
    while parent and parent not in visited:
        visited.add(parent)
        parent_item = _load_regions().get(parent)
        if parent_item is None:
            path.append(parent)
            break
        path.append(parent)
        parent = str(parent_item.get("parent", "") or "")
    if parent and parent not in path:
        path.append(parent)
    return Region(
        name=name,
        aliases=tuple(
            str(alias)
            for alias in item.get("aliases", [])
            if str(alias).strip()
        ),
        region_code=str(item.get("region_code", "")),
        local_standards=tuple(
            str(title)
            for title in item.get("local_standards", [])
            if str(title).strip()
        ),
        parent=str(item.get("parent", "") or ""),
        path=tuple(path),
    )


def detect_region(query: str) -> Region | None:
    matches: list[tuple[int, int, int, str]] = []
    for name, item in _load_regions().items():
        for alias in item.get("aliases", []):
            text = str(alias).strip()
            start = query.find(text)
            if not text or start < 0:
                continue
            if name.endswith(("区", "县", "旗")):
                specificity = 4
            elif name.endswith("市"):
                specificity = 3
            elif name.endswith(("省", "自治区")):
                specificity = 2
            else:
                specificity = 1
            matches.append((-specificity, start, -len(text), name))
    if not matches:
        return None
    _, _, _, name = min(matches)
    return _build_region(name)


def local_standard_titles(region: Region | None) -> tuple[str, ...]:
    if region is None:
        return ()
    titles: list[str] = []
    for name in reversed(region.path):
        item = _load_regions().get(name, {})
        for title in item.get("local_standards", []):
            text = str(title).strip()
            if text and text not in titles:
                titles.append(text)
    for title in region.local_standards:
        if title not in titles:
            titles.append(title)
    return tuple(titles)
