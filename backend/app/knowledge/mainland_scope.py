from __future__ import annotations

import re
from typing import Any

OUTSIDE_MAINLAND_INTENT = "outside_region"

_SPECIAL_REGIONS = {
    "香港": ("香港", "香港特别行政区"),
    "澳门": ("澳门", "澳門", "澳门特别行政区", "澳門特別行政區"),
    "台湾": ("台湾", "臺灣", "台湾地区", "臺灣地區"),
}

_FOREIGN_PLACES = (
    "海外",
    "境外",
    "外国",
    "日本",
    "韩国",
    "朝鲜",
    "蒙古",
    "新加坡",
    "马来西亚",
    "泰国",
    "越南",
    "老挝",
    "柬埔寨",
    "缅甸",
    "菲律宾",
    "印度尼西亚",
    "印度",
    "巴基斯坦",
    "孟加拉国",
    "斯里兰卡",
    "尼泊尔",
    "马尔代夫",
    "哈萨克斯坦",
    "乌兹别克斯坦",
    "吉尔吉斯斯坦",
    "塔吉克斯坦",
    "土库曼斯坦",
    "阿富汗",
    "伊朗",
    "伊拉克",
    "以色列",
    "约旦",
    "黎巴嫩",
    "沙特阿拉伯",
    "阿联酋",
    "卡塔尔",
    "科威特",
    "土耳其",
    "俄罗斯",
    "乌克兰",
    "白俄罗斯",
    "波兰",
    "德国",
    "法国",
    "英国",
    "爱尔兰",
    "荷兰",
    "比利时",
    "瑞士",
    "奥地利",
    "意大利",
    "西班牙",
    "葡萄牙",
    "希腊",
    "瑞典",
    "挪威",
    "丹麦",
    "芬兰",
    "冰岛",
    "捷克",
    "斯洛伐克",
    "匈牙利",
    "罗马尼亚",
    "保加利亚",
    "塞尔维亚",
    "克罗地亚",
    "埃及",
    "南非",
    "尼日利亚",
    "阿尔及利亚",
    "摩洛哥",
    "突尼斯",
    "肯尼亚",
    "埃塞俄比亚",
    "美国",
    "加拿大",
    "墨西哥",
    "巴西",
    "阿根廷",
    "智利",
    "秘鲁",
    "哥伦比亚",
    "委内瑞拉",
    "澳大利亚",
    "新西兰",
)

_FOREIGN_CITIES = (
    "东京",
    "大阪",
    "京都",
    "横滨",
    "名古屋",
    "札幌",
    "福冈",
    "神户",
    "广岛",
    "冲绳",
    "首尔",
    "釜山",
    "仁川",
    "济州",
    "新加坡市",
    "迪拜",
    "阿布扎比",
    "多哈",
    "利雅得",
    "纽约",
    "洛杉矶",
    "旧金山",
    "芝加哥",
    "华盛顿",
    "波士顿",
    "西雅图",
    "休斯敦",
    "拉斯维加斯",
    "迈阿密",
    "多伦多",
    "温哥华",
    "蒙特利尔",
    "渥太华",
    "卡尔加里",
    "伦敦",
    "曼彻斯特",
    "伯明翰",
    "爱丁堡",
    "利物浦",
    "剑桥",
    "牛津",
    "巴黎",
    "里昂",
    "马赛",
    "尼斯",
    "柏林",
    "慕尼黑",
    "法兰克福",
    "汉堡",
    "科隆",
    "斯图加特",
    "罗马",
    "米兰",
    "威尼斯",
    "佛罗伦萨",
    "那不勒斯",
    "马德里",
    "巴塞罗那",
    "瓦伦西亚",
    "塞维利亚",
    "莫斯科",
    "圣彼得堡",
    "海参崴",
    "悉尼",
    "墨尔本",
    "布里斯班",
    "珀斯",
    "阿德莱德",
    "堪培拉",
    "奥克兰",
    "惠灵顿",
    "基督城",
)

_LATIN_PLACES = (
    (re.compile(r"\bhong\s*kong\b", re.IGNORECASE), "香港"),
    (re.compile(r"\bhksar\b", re.IGNORECASE), "香港"),
    (re.compile(r"\bmacau\b|\bmacao\b", re.IGNORECASE), "澳门"),
    (re.compile(r"\btaiwan\b", re.IGNORECASE), "台湾"),
    (re.compile(r"\boverseas?\b", re.IGNORECASE), "境外"),
)


def detect_outside_mainland_place(query: str) -> str | None:
    text = query.strip()
    if not text:
        return None
    for place, aliases in _SPECIAL_REGIONS.items():
        if any(alias in text for alias in aliases):
            return place
    for place in (*_FOREIGN_PLACES, *_FOREIGN_CITIES):
        if place in text:
            return place
    for pattern, place in _LATIN_PLACES:
        if pattern.search(text):
            return place
    return None


def outside_mainland_result(query: str, place: str) -> dict[str, Any]:
    return {
        "reply": (
            f"当前规范检索范围仅限中国大陆地区。{place}不属于该范围，"
            "因此无法查询相关规范，也未检索知识库。"
            "请提供中国大陆地区的项目地址或规范查询内容。"
        ),
        "sources": [],
        "steps": [
            {
                "tool": "region_scope",
                "title": "地域范围限制",
                "detail": f"识别到{place}，未查询知识库",
                "duration_ms": 0,
            }
        ],
        "follow_ups": [],
        "calculation": None,
        "comparison": None,
        "region_path": [],
        "requested_region": None,
        "web_results": [],
        "web_note": "",
        "effective_query": query,
        "memory_used": False,
    }
