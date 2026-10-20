from __future__ import annotations

from app.agent.planner import Planner
from app.knowledge.loader import KnowledgeBase
from app.knowledge.region_hierarchy import detect_requested_region
from app.knowledge.retriever import Retriever
from services.compound_intent import detect_compound_intent
from services.region_matcher import detect_region


def test_detect_commercial_evacuation_width_intent() -> None:
    intent = detect_compound_intent("商业建筑疏散宽度怎么计算")

    assert intent.is_compound is True
    assert intent.building_type == "商业建筑"
    assert intent.attribute == "疏散宽度"
    assert intent.primary_standards[:4] == (
        "JGJ48-2014",
        "GB55031-2022",
        "GB50016-2006",
        "GB55037-2022",
    )


def test_detect_commercial_stair_dimension_intent() -> None:
    intent = detect_compound_intent("商业建筑疏散楼梯的尺寸")

    assert intent.is_compound is True
    assert intent.building_type == "商业建筑"
    assert intent.component == "楼梯"
    assert intent.attribute == "尺寸"
    assert intent.topic == "商业建筑疏散楼梯"
    assert intent.primary_standards[0] == "JGJ48-2014"
    assert "GB55031-2022" in intent.primary_standards


def test_non_compound_query_falls_back() -> None:
    intent = detect_compound_intent("防火分区面积怎么确定")

    assert intent.is_compound is False


def test_unrelated_memory_does_not_override_current_constraints() -> None:
    planner = Planner(Retriever(KnowledgeBase()))
    query = "帮我查下踏步规范"
    result = planner.run(
        query,
        memory_facts=[
            {
                "text": "住宅楼梯踏步宽度和高度有什么要求？",
                "category": "项目信息",
            }
        ],
        enable_web_search=False,
    )

    assert result["effective_query"] == query
    assert result["memory_used"] is False
    assert "识别到的约束" not in result["reply"]


def test_explicit_project_query_can_use_memory_background() -> None:
    planner = Planner(Retriever(KnowledgeBase()))
    result = planner.run(
        "本项目踏步规范",
        memory_facts=[
            {
                "text": "项目信息：建筑类型住宅",
                "category": "项目信息",
            }
        ],
        enable_web_search=False,
    )

    assert result["memory_used"] is True
    assert "项目背景" in result["effective_query"]
    assert "识别到的约束" not in result["reply"]


def test_chengdu_region_is_independent_dimension() -> None:
    region = detect_region("成都商业建筑疏散宽度怎么计算")
    intent = detect_compound_intent("成都商业建筑疏散宽度怎么计算")

    assert region is not None
    assert region.name == "成都市"
    assert region.path == ("成都市", "四川省", "西南地区")
    assert intent.region == "成都市"
    assert intent.region_scope["province"] == "四川省"
    assert intent.region_scope["city"] == "成都市"
    assert intent.building_type == "商业建筑"
    assert intent.attribute == "疏散宽度"


def test_beijing_region_does_not_change_other_dimensions() -> None:
    intent = detect_compound_intent("北京商业建筑疏散宽度怎么计算")

    assert intent.region == "北京市"
    assert intent.region_scope["province"] == "北京市"
    assert intent.building_type == "商业建筑"
    assert intent.attribute == "疏散宽度"


def test_hangzhou_first_city_is_not_overridden_by_chengdu() -> None:
    region = detect_region("杭州成都商业建筑疏散宽度怎么计算")
    intent = detect_compound_intent("杭州成都商业建筑疏散宽度怎么计算")

    assert region is not None
    assert region.name == "杭州市"
    assert intent.region == "杭州市"


def test_compound_header_contains_only_intent_dimensions() -> None:
    reply = Planner._with_compound_intent_header(
        "成都商业建筑疏散宽度怎么计算",
        "依据国家标准计算。",
    )

    assert "地域：成都市" in reply
    assert "建筑类型：商业建筑" in reply
    assert "检索目标：疏散宽度" in reply
    assert "【国家标准（参考对照）】" not in reply


def test_compound_header_uses_requested_region_override() -> None:
    reply = Planner._with_compound_intent_header(
        "杭州成都商业建筑疏散宽度怎么计算",
        "依据国家标准计算。",
        requested_region={"place": "杭州市"},
    )

    assert "地域：杭州市" in reply
    assert "地域：成都市" not in reply


def test_compound_header_shows_component_dimension_target() -> None:
    reply = Planner._with_compound_intent_header(
        "商业建筑疏散楼梯的尺寸",
        "依据规范查询。",
    )

    assert "建筑类型：商业建筑" in reply
    assert "检索目标：楼梯尺寸" in reply
    assert "检索目标：疏散宽度" not in reply


def test_local_notice_uses_full_component_topic() -> None:
    planner = Planner.__new__(Planner)
    query = "杭州商业建筑疏散楼梯的尺寸"
    requested_region = detect_requested_region(query, [])
    sources = [
        {
            "doc_id": "jgj48",
            "standard": "JGJ48-2014",
            "title": "商店建筑设计规范",
            "region": "全国",
            "snippet": "楼梯尺寸",
            "score": 10,
        },
        {
            "doc_id": "gb55037",
            "standard": "GB55037-2022",
            "title": "建筑防火通用规范",
            "region": "全国",
            "snippet": "楼梯尺寸",
            "score": 9,
        },
        {
            "doc_id": "gb50352",
            "standard": "GB50352-2019",
            "title": "民用建筑设计统一标准",
            "region": "全国",
            "snippet": "楼梯尺寸",
            "score": 8,
        },
    ]

    reply = planner._compose_answer(
        query,
        sources,
        None,
        None,
        requested_region=requested_region,
    )

    assert "杭州市地方商业建筑疏散楼梯规范暂未收录" in reply
