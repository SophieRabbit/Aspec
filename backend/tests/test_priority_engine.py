from __future__ import annotations

from app.knowledge.priority_engine import (
    apply_priority,
    evaluate,
    parse_standard_filename,
)


def test_parse_common_standard_filenames() -> None:
    cases = [
        (
            "GB 50016-2014 建筑设计防火规范.pdf",
            "GB50016-2014",
            "建筑设计防火规范",
            "国家标准",
            "GB",
            "全国",
        ),
        (
            "GBT50010-2010混凝土结构设计标准.pdf",
            "GB/T50010-2010",
            "混凝土结构设计标准",
            "国家标准",
            "GB/T",
            "全国",
        ),
        (
            "GB-T51439-2021城市步行和自行车交通系统规划标准.pdf",
            "GB/T51439-2021",
            "城市步行和自行车交通系统规划标准",
            "国家标准",
            "GB/T",
            "全国",
        ),
        (
            "DBJ04T467-2023建筑防烟排烟系统技术标准.pdf",
            "DBJ04/T467-2023",
            "建筑防烟排烟系统技术标准",
            "地方标准",
            "DB/T",
            "山西省",
        ),
        (
            "DBJ51-001 四川省住宅设计标准.pdf",
            "DBJ51-001",
            "四川省住宅设计标准",
            "地方标准",
            "DB",
            "四川省",
        ),
        (
            "人民防空地下室设计规范GB 50038-2005.pdf",
            "GB50038-2005",
            "人民防空地下室设计规范",
            "国家标准",
            "GB",
            "全国",
        ),
        (
            "26-《城市消防站建设标准》（建标152-2017）.pdf",
            "建标152-2017",
            "城市消防站建设标准",
            "行业标准",
            "建标",
            "全国",
        ),
        (
            "09-《城市停车规划规范》（GBT51149-2016）.pdf",
            "GB/T51149-2016",
            "城市停车规划规范",
            "国家标准",
            "GB/T",
            "全国",
        ),
        (
            "JGJT67-2019.pdf",
            "JGJ/T67-2019",
            "",
            "行业标准",
            "JGJ/T",
            "全国",
        ),
        (
            "CJJT15-2011城市道路公共交通站、场、厂工程设计规范.pdf",
            "CJJ/T15-2011",
            "城市道路公共交通站、场、厂工程设计规范",
            "行业标准",
            "CJJ/T",
            "全国",
        ),
        (
            "TDT1062-2021社区生活圈规划技术指南2021.pdf",
            "TD/T1062-2021",
            "社区生活圈规划技术指南2021",
            "行业标准",
            "TD/T",
            "全国",
        ),
    ]
    for filename, standard, title, doc_type, type_key, region in cases:
        parsed = parse_standard_filename(filename)
        assert parsed.standard == standard
        assert parsed.standard_type == doc_type
        assert parsed.standard_type_key == type_key
        assert parsed.region == region
        if title:
            assert parsed.title == title


def test_priority_scoring() -> None:
    assert evaluate("GB55019-2021", "建筑与市政工程无障碍通用规范")["priority"] == 100
    assert evaluate("GB50016-2014", "建筑设计防火规范")["priority"] == 100
    assert evaluate("GB/T50011-2010", "建筑抗震设计标准")["priority"] == 75
    assert evaluate("JGJ/T67-2019", "办公建筑设计标准")["priority"] == 40
    assert evaluate("DBJ51-001", "四川省住宅设计标准")["priority"] == 70
    assert evaluate("T/CECS123-2021", "某团体标准")["priority"] == 30


def test_apply_priority_backfills_missing_fields() -> None:
    document = {
        "standard": "GB50016-2014",
        "title": "建筑设计防火规范",
    }
    apply_priority(document)
    assert document["priority"] == 100
    assert document["tier"] == "核心规范"
    assert document["standard_type"] == "国家标准"


def test_apply_priority_keeps_existing_value() -> None:
    document = {
        "standard": "GB50016-2014",
        "title": "建筑设计防火规范",
        "priority": 88,
    }
    apply_priority(document)
    assert document["priority"] == 88
