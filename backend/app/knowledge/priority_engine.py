from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_ZWSP_CHARS = "\u200b\u200c\u200d\ufeff"

_CODE_RE = re.compile(
    r"(?i)(?P<prefix>"
    r"GB\s*/?\s*[-_－—]?\s*T|GBT|GBJ|GB|"
    r"JGJ\s*/?\s*[-_－—]?\s*T|JGJT|JGJ|"
    r"CJJ\s*/?\s*[-_－—]?\s*T|CJJT|CJJ|"
    r"DBJ?\s*\d+\s*/?\s*[-_－—]?\s*T|DB\s*\d+\s*/?\s*[-_－—]?\s*T|DBJ?\s*\d+|DB\s*\d+|"
    r"T\s*/\s*CECS|CECS|TDT|TD\s*/?\s*[-_－—]?\s*T|TD|"
    r"JTG\s*/?\s*[-_－—]?\s*T|JTG|"
    r"DL\s*/?\s*[-_－—]?\s*T|DL|"
    r"JG\s*/?\s*[-_－—]?\s*T|JG|CJ\s*/?\s*[-_－—]?\s*T|CJ|"
    r"建标"
    r")"
    r"\s*[-_－—/／]?\s*(?P<number>\d{1,6})"
    r"(?:\.(?P<sub>\d{1,4}))?"
    r"(?:\s*[-_－—]\s*(?P<year>(?:19|20)\d{2}))?"
)

_TYPE_BASE = {
    "GB55": 100,
    "GB": 80,
    "GB/T": 60,
    "JGJ": 50,
    "JGJ/T": 40,
    "CJJ": 50,
    "CJJ/T": 40,
    "JG": 40,
    "JG/T": 35,
    "CJ": 40,
    "CJ/T": 35,
    "JTG": 50,
    "JTG/T": 40,
    "DL": 40,
    "DL/T": 35,
    "TD": 45,
    "TD/T": 40,
    "建标": 50,
    "DB": 60,
    "DB/T": 55,
    "T/CECS": 30,
}

_KEYWORD_BONUSES: list[tuple[tuple[str, ...], int]] = [
    (("防火",), 20),
    (("无障碍", "适老"), 15),
    (("抗震", "荷载"), 15),
    (("住宅", "居住"), 10),
    (("节能",), 10),
    (("制图", "表达"), 5),
    (("验收", "施工质量"), 5),
]

_DB_PROVINCES = {
    "11": "北京市",
    "12": "天津市",
    "13": "河北省",
    "14": "山西省",
    "15": "内蒙古自治区",
    "21": "辽宁省",
    "22": "吉林省",
    "23": "黑龙江省",
    "31": "上海市",
    "32": "江苏省",
    "33": "浙江省",
    "34": "安徽省",
    "35": "福建省",
    "36": "江西省",
    "37": "山东省",
    "41": "河南省",
    "42": "湖北省",
    "43": "湖南省",
    "44": "广东省",
    "45": "广西壮族自治区",
    "46": "海南省",
    "50": "重庆市",
    "51": "四川省",
    "52": "贵州省",
    "53": "云南省",
    "54": "西藏自治区",
    "61": "陕西省",
    "62": "甘肃省",
    "63": "青海省",
    "64": "宁夏回族自治区",
    "65": "新疆维吾尔自治区",
}

_DBJ_PROVINCES = {
    "04": "山西省",
    "50": "重庆市",
    "51": "四川省",
    "52": "贵州省",
    "53": "云南省",
    "61": "陕西省",
    "62": "甘肃省",
    "63": "青海省",
    "64": "宁夏回族自治区",
    "65": "新疆维吾尔自治区",
}


@dataclass
class ParsedStandard:
    raw: str
    standard: str
    title: str
    year: str = ""
    number: str = ""
    prefix: str = ""
    standard_type: str = "国家标准"
    standard_type_key: str = "其他"
    is_recommended: bool = False
    is_local: bool = False
    region: str = "全国"


def _clean_filename(filename: str) -> str:
    stem = filename
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    for ch in _ZWSP_CHARS:
        stem = stem.replace(ch, "")
    stem = re.sub(r"^\d{1,3}[-_－—\s]+", "", stem)
    return stem.strip()


def _normalize_standard(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"\s+", "", text)
    text = text.replace("／", "/")
    text = text.replace("－", "-").replace("—", "-")
    text = re.sub(r"^GBT", "GB/T", text, flags=re.IGNORECASE)
    text = re.sub(r"^JGJT", "JGJ/T", text, flags=re.IGNORECASE)
    text = re.sub(r"^CJJT", "CJJ/T", text, flags=re.IGNORECASE)
    text = re.sub(r"^TDT", "TD/T", text, flags=re.IGNORECASE)
    text = re.sub(r"^([A-Z]+)-T", r"\1/T", text, flags=re.IGNORECASE)
    text = re.sub(
        r"^(DBJ?\d+|DB\d+)T(?=\d|$)",
        r"\1/T",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^CECS", "T/CECS", text, flags=re.IGNORECASE)
    return text


def _extract_title(stem: str, match: re.Match[str]) -> str:
    start, end = match.span()
    title = (stem[:start] + stem[end:]).strip()
    title = re.sub(r"[《》「」『』]", "", title)
    title = re.sub(r"[（(]\s*[）)]", "", title)
    title = re.sub(r"【\s*】", "", title)
    title = re.sub(r"[（(][^（()）]*(?:带书签|条文说明)[^（()）]*[）)]", "", title)
    title = re.sub(
        r"(带书签\+条文说明|带书签|条文说明|正式实施版|实施版|批注)$",
        "",
        title,
    )
    title = re.sub(r"[\s_\-－—.]+", " ", title).strip(" -_·.。，,")
    return title or stem


def _prefix_key(prefix_raw: str) -> str:
    prefix = _normalize_standard(prefix_raw)
    if prefix.startswith("DB"):
        is_recommended = bool(re.search(r"/T", prefix))
        return "DB/T" if is_recommended else "DB"
    if prefix.startswith("T/CECS"):
        return "T/CECS"
    if prefix == "GB" or prefix == "GB/T":
        return prefix
    return prefix


def _classify(
    prefix_key: str,
    prefix_raw: str,
    number: str,
) -> tuple[str, str, bool, bool, str]:
    if prefix_key == "GB55":
        return "国家标准", "GB55", False, False, "全国"
    if prefix_key == "GB":
        return "国家标准", "GB", False, False, "全国"
    if prefix_key == "GB/T":
        return "国家标准", "GB/T", True, False, "全国"
    if prefix_key.startswith("DB"):
        region = _local_region(prefix_raw)
        return "地方标准", prefix_key, "/T" in prefix_key, True, region
    if prefix_key == "T/CECS":
        return "团体标准", "T/CECS", False, False, "全国"
    if prefix_key in _TYPE_BASE:
        recommended = bool(re.search(r"/T$", prefix_key))
        return "行业标准", prefix_key, recommended, False, "全国"
    return "规范", "其他", False, False, "全国"


def _local_region(prefix_key: str) -> str:
    match = re.search(r"DBJ\s*(\d{2})", prefix_key)
    if match:
        return _DBJ_PROVINCES.get(match.group(1), "全国")
    match = re.search(r"DB\s*(\d{2})", prefix_key)
    if match:
        return _DB_PROVINCES.get(match.group(1), "全国")
    return "全国"


def parse_standard_filename(filename: str) -> ParsedStandard:
    stem = _clean_filename(filename)
    match = _CODE_RE.search(stem)
    if not match:
        return ParsedStandard(
            raw=stem,
            standard=stem,
            title=stem,
            standard_type="规范",
            standard_type_key="其他",
        )

    raw = match.group(0)
    standard = _normalize_standard(raw)
    number = match.group("number") or ""
    year = match.group("year") or ""
    prefix_raw = match.group("prefix") or ""
    prefix_key = _prefix_key(prefix_raw)
    if prefix_key == "GB" and number.startswith("55"):
        prefix_key = "GB55"
    document_type, type_key, is_recommended, is_local, region = _classify(
        prefix_key, prefix_raw, number
    )
    return ParsedStandard(
        raw=stem,
        standard=standard,
        title=_extract_title(stem, match),
        year=year,
        number=number,
        prefix=prefix_key,
        standard_type=document_type,
        standard_type_key=type_key,
        is_recommended=is_recommended,
        is_local=is_local,
        region=region,
    )


def evaluate(standard: str, title: str) -> dict[str, object]:
    parsed = parse_standard_filename(f"{standard} {title}".strip())
    score = _TYPE_BASE.get(parsed.standard_type_key, 20)
    text = f"{standard} {title}"
    for keywords, bonus in _KEYWORD_BONUSES:
        if any(keyword in text for keyword in keywords):
            score += bonus
    score = min(100, score)
    if score >= 90:
        tier = "核心规范"
    elif score >= 70:
        tier = "基础规范"
    elif score >= 50:
        tier = "专项规范"
    else:
        tier = "参考规范"
    return {
        "priority": score,
        "tier": tier,
        "standard_type": parsed.standard_type,
        "standard_type_key": parsed.standard_type_key,
    }


def apply_priority(document: dict[str, object]) -> dict[str, object]:
    info = evaluate(
        str(document.get("standard", "")),
        str(document.get("title", "")),
    )
    document.setdefault("priority", info["priority"])
    document.setdefault("tier", info["tier"])
    document.setdefault("standard_type", info["standard_type"])
    return document


def normalize_standard_code(code: str) -> str:
    return re.sub(r"[\s/\-－—]", "", code).lower()
