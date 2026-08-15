from __future__ import annotations

import re
from typing import Any

KNOWN_HIERARCHY: dict[str, tuple[str | None, str | None, str | None]] = {
    "江苏省": ("江苏省", None, None),
    "苏州市": ("江苏省", "苏州市", None),
    "昆山市": ("江苏省", "苏州市", "昆山市"),
    "四川省": ("四川省", None, None),
    "成都市": ("四川省", "成都市", None),
    "蒲江县": ("四川省", "成都市", "蒲江县"),
    "内江市": ("四川省", "内江市", None),
    "广安市": ("四川省", "广安市", None),
    "德阳市": ("四川省", "德阳市", None),
    "眉山市": ("四川省", "眉山市", None),
    "达州市": ("四川省", "达州市", None),
    "雅安市": ("四川省", "雅安市", None),
    "河北省": ("河北省", None, None),
    "保定市": ("河北省", "保定市", None),
    "云南省": ("云南省", None, None),
    "昆明市": ("云南省", "昆明市", None),
    "贵州省": ("贵州省", None, None),
    "贵阳市": ("贵州省", "贵阳市", None),
    "重庆市": ("重庆市", None, None),
    "陕西省": ("陕西省", None, None),
    "西安市": ("陕西省", "西安市", None),
    "新疆维吾尔自治区": ("新疆维吾尔自治区", None, None),
    "乌鲁木齐市": ("新疆维吾尔自治区", "乌鲁木齐市", None),
    "山西省": ("山西省", None, None),
    "太原市": ("山西省", "太原市", None),
    "广东省": ("广东省", None, None),
    "河北省": ("河北省", None, None),
    "浙江省": ("浙江省", None, None),
    "陕西省": ("陕西省", None, None),
    "海南省": ("海南省", None, None),
    "北京市": ("北京市", None, None),
    "上海市": ("上海市", None, None),
    "新疆维吾尔自治区": ("新疆维吾尔自治区", None, None),
    "华北地区": ("", "", ""),
    "北方地区": ("", "", ""),
    "华东地区": ("", "", ""),
    "华中地区": ("", "", ""),
    "华南地区": ("", "", ""),
    "西南地区": ("", "", ""),
    "西北地区": ("", "", ""),
    "东北地区": ("", "", ""),
    "中南地区": ("", "", ""),
}

PROVINCE_REGION = {
    "北京市": "华北地区",
    "天津市": "华北地区",
    "河北省": "华北地区",
    "山西省": "华北地区",
    "内蒙古自治区": "华北地区",
    "上海市": "华东地区",
    "江苏省": "华东地区",
    "浙江省": "华东地区",
    "安徽省": "华东地区",
    "福建省": "华东地区",
    "江西省": "华东地区",
    "山东省": "华东地区",
    "河南省": "华中地区",
    "湖北省": "华中地区",
    "湖南省": "华中地区",
    "广东省": "华南地区",
    "广西壮族自治区": "华南地区",
    "海南省": "华南地区",
    "重庆市": "西南地区",
    "四川省": "西南地区",
    "贵州省": "西南地区",
    "云南省": "西南地区",
    "西藏自治区": "西南地区",
    "陕西省": "西北地区",
    "甘肃省": "西北地区",
    "青海省": "西北地区",
    "宁夏回族自治区": "西北地区",
    "新疆维吾尔自治区": "西北地区",
    "辽宁省": "东北地区",
    "吉林省": "东北地区",
    "黑龙江省": "东北地区",
}

REGION_ALIASES = {
    "华北地区": ("华北地区", "北方地区"),
    "北方地区": ("华北地区", "东北地区", "西北地区", "北方地区"),
    "华东地区": ("华东地区",),
    "华中地区": ("华中地区",),
    "华南地区": ("华南地区", "中南地区"),
    "西南地区": ("西南地区",),
    "西北地区": ("西北地区",),
    "东北地区": ("东北地区",),
    "中南地区": ("中南地区", "华南地区"),
}

ALIASES = {
    "昆山": "昆山市",
    "苏州": "苏州市",
    "成都": "成都市",
    "蒲江": "蒲江县",
    "内江": "内江市",
    "广安": "广安市",
    "德阳": "德阳市",
    "眉山": "眉山市",
    "达州": "达州市",
    "雅安": "雅安市",
    "保定": "保定市",
    "昆明": "昆明市",
    "贵阳": "贵阳市",
    "西安": "西安市",
    "太原": "太原市",
    "乌鲁木齐": "乌鲁木齐市",
}


def apply_region_hierarchy(document: dict[str, Any]) -> dict[str, Any]:
    region = document.get("region", "")
    hierarchy = KNOWN_HIERARCHY.get(region)
    if hierarchy:
        document["province"], document["city"], document["district"] = hierarchy
    else:
        document.setdefault("province", "")
        document.setdefault("city", "")
        document.setdefault("district", "")
    return document


def detect_requested_region(query: str, documents: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: dict[str, tuple[str | None, str | None, str | None]] = dict(KNOWN_HIERARCHY)
    for document in documents:
        for key in ("district", "city", "province", "region"):
            value = document.get(key)
            if value and value not in candidates:
                candidates[value] = (
                    document.get("province") or "",
                    document.get("city") or "",
                    document.get("district") or "",
                )

    resolved_names = {
        alias: canonical
        for alias, canonical in ALIASES.items()
        if alias in query and canonical in candidates
    }
    for alias, canonical in resolved_names.items():
        query = query.replace(alias, canonical)

    for name in sorted(candidates, key=len, reverse=True):
        if len(name) >= 2 and name in query:
            province, city, district = candidates[name]
            region = PROVINCE_REGION.get(province or "", "")
            if not region and name in REGION_ALIASES:
                region = name
            if region and not province and not city and not district:
                scope = "region"
            else:
                scope = "district" if district else "city" if city else "province"
            return {
                "place": name,
                "province": province or "",
                "city": city or "",
                "district": district or "",
                "region": region,
                "scope": scope,
            }

    match = re.search(r"([\u4e00-\u9fff]{2,12}?(?:省|市|自治州|地区|盟|区|县|旗))", query)
    if match:
        return {
            "place": match.group(1),
            "province": "",
            "city": "",
            "district": "",
            "region": "",
            "scope": "unknown",
        }
    return None


def document_in_scope(document: dict[str, Any], requested: dict[str, Any] | None) -> bool:
    if not requested:
        return True
    region = document.get("region", "")
    if region == "全国":
        return True
    if requested.get("place") and region == requested["place"]:
        return True

    requested_region = requested.get("region") or ""
    if requested_region and region in REGION_ALIASES.get(requested_region, (requested_region,)):
        return True

    province = requested.get("province") or ""
    city = requested.get("city") or ""
    district = requested.get("district") or ""
    doc_province = document.get("province") or ""
    doc_city = document.get("city") or ""
    doc_district = document.get("district") or ""

    if province and doc_province and doc_province != province:
        return False
    if city and doc_city and doc_city != city:
        return False
    if district and doc_district and doc_district != district:
        return False
    return bool(doc_province or doc_city or doc_district)


def region_priority(document: dict[str, Any], requested: dict[str, Any] | None) -> int:
    if not requested:
        return 0
    if document.get("region") == "全国":
        return 0

    requested_region = requested.get("region") or ""
    document_region = document.get("region", "")
    if requested_region and document_region in REGION_ALIASES.get(requested_region, (requested_region,)):
        return 20

    province = requested.get("province") or ""
    city = requested.get("city") or ""
    district = requested.get("district") or ""
    doc_province = document.get("province") or ""
    doc_city = document.get("city") or ""
    doc_district = document.get("district") or ""

    if district and doc_district == district:
        return 80
    if city and doc_city == city:
        return 60
    if province and doc_province == province:
        return 40
    return 0


def region_alias_match(document_region: str, requested: dict[str, Any] | None) -> bool:
    if not requested:
        return False
    requested_region = requested.get("region") or ""
    return bool(
        requested_region
        and document_region in REGION_ALIASES.get(requested_region, (requested_region,))
    )


def build_region_notice(requested: dict[str, Any] | None, documents: list[dict[str, Any]]) -> str:
    if not requested:
        return ""

    counts = {"national": 0, "region": 0, "province": 0, "city": 0, "district": 0}
    for document in documents:
        if document.get("region") == "全国":
            counts["national"] += 1
            continue
        if not document_in_scope(document, requested):
            continue
        if requested.get("district") and document.get("district") == requested["district"]:
            counts["district"] += 1
        elif requested.get("city") and document.get("city") == requested["city"]:
            counts["city"] += 1
        elif requested.get("province") and document.get("province") == requested["province"]:
            counts["province"] += 1
        elif requested.get("region") and document.get("region") in REGION_ALIASES.get(
            requested["region"], (requested["region"],)
        ):
            counts["region"] += 1
        else:
            counts["province"] += 1

    place = requested.get("place", "")
    region = requested.get("region") or place
    province = requested.get("province") or place
    city = requested.get("city") or place
    district = requested.get("district") or place
    levels: list[str] = []
    if counts["national"]:
        levels.append(f"国家级规范 {counts['national']} 部")
    if requested.get("region") and counts["region"]:
        levels.append(f"{region}规范 {counts['region']} 部")
    if requested.get("province") and counts["province"]:
        levels.append(f"{province}规范 {counts['province']} 部")
    if requested.get("city") and counts["city"]:
        levels.append(f"{city}规范 {counts['city']} 部")
    if requested.get("district") and counts["district"]:
        levels.append(f"{district}规范 {counts['district']} 部")

    if counts["district"] == 0 and counts["city"] == 0 and counts["province"] == 0 and counts["region"] == 0:
        return (
            f"未找到【{place}】相关规范，本次仅展示国家级规范；"
            f"当前知识库未收录{region}、{province}、{city}、{district}的相关规范。"
        )
    if requested.get("district") and counts["district"] == 0:
        return f"未找到【{place}】相关规范，已为你展示：{'、'.join(levels)}。"
    if requested.get("city") and counts["city"] == 0:
        return f"未找到【{place}】本级规范，已为你展示：{'、'.join(levels)}。"
    if requested.get("province") and counts["province"] == 0:
        return f"未找到【{place}】相关规范，已为你展示：{'、'.join(levels)}。"
    if requested.get("region") and counts["region"] == 0:
        return f"未找到【{place}】相关规范，已为你展示：{'、'.join(levels)}。"
    return f"已为你展示【{place}】及上级相关规范：{'、'.join(levels)}。"


def build_region_path(requested: dict[str, Any] | None, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not requested:
        return []

    counts = {"national": 0, "region": 0, "province": 0, "city": 0, "district": 0}
    for document in documents:
        if document.get("region") == "全国":
            counts["national"] += 1
            continue
        if not document_in_scope(document, requested):
            continue
        if requested.get("district") and document.get("district") == requested["district"]:
            counts["district"] += 1
        elif requested.get("city") and document.get("city") == requested["city"]:
            counts["city"] += 1
        elif requested.get("province") and document.get("province") == requested["province"]:
            counts["province"] += 1
        elif requested.get("region") and document.get("region") in REGION_ALIASES.get(
            requested["region"], (requested["region"],)
        ):
            counts["region"] += 1
        else:
            counts["province"] += 1

    path: list[dict[str, Any]] = [
        {"level": "国家级", "count": counts["national"], "available": counts["national"] > 0}
    ]
    if requested.get("region"):
        path.append(
            {
                "level": requested["region"],
                "count": counts["region"],
                "available": counts["region"] > 0,
            }
        )
    if requested.get("province"):
        path.append(
            {
                "level": requested["province"],
                "count": counts["province"],
                "available": counts["province"] > 0,
            }
        )
    if requested.get("city"):
        path.append(
            {
                "level": requested["city"],
                "count": counts["city"],
                "available": counts["city"] > 0,
            }
        )
    if requested.get("district"):
        path.append(
            {
                "level": requested["district"],
                "count": counts["district"],
                "available": counts["district"] > 0,
            }
        )
    return path
