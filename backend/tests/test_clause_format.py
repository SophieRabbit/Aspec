from __future__ import annotations

from app.knowledge.text_cleaner import (
    _format_standard_clauses,
    _remove_glued_x_noise,
    _repair_misordered_items,
    normalize_ocr_paragraphs,
)


def test_clause_number_and_numeric_content_are_separated() -> None:
    text = "4.3.33层及3层以上的旅馆应设乘客电梯。4.3.4其他内容。"
    output = _format_standard_clauses(text)
    assert "4.3.3 3层及3层以上" in output
    assert "\n4.3.4 " in output


def test_clause_format_is_idempotent() -> None:
    text = "2.2.3 民用建筑内容甲。2.2.4 室内装修内容乙 2.2.5 装配式内容丙"
    once = _format_standard_clauses(text)
    twice = _format_standard_clauses(once)
    assert once == twice


def test_clause_after_space_gets_newline() -> None:
    text = (
        "2.2.3 民用建筑应满足无障碍要求，且具有无障碍性能的设施 "
        "2.2.4 室内外装修不应影响建筑物结构的安全性 "
        "2.2.5 装配式建筑应采用集成化、模块化、标准化及通用化的"
    )
    output = _format_standard_clauses(text)
    assert "\n2.2.4 " in output
    assert "\n2.2.5 " in output


def test_parenthesized_items_get_newline() -> None:
    text = (
        "5 ) 横墙很少的砌体房屋内容。"
        "6 ) 砌体房屋有较大错层时内容。"
        "7 ) 建造砌体房屋内容。"
        "(2)检查内容。"
    )
    output = _format_standard_clauses(text)
    assert "\n6 ) " in output
    assert "\n7 ) " in output
    assert "\n(2) " in output


def test_table_page_artifacts_are_removed() -> None:
    text = (
        "5.5.1 公共厨房应符合食品卫生防疫安全和厨房工艺要求。\n"
        "5.5.2 厨房专间、备餐区等清洁操作区内不应设置排水明沟，12 |\n"
        "5.5 公共厨房 |"
    )
    output = _format_standard_clauses(text)
    assert "12 |" not in output
    assert "公共厨房 |" not in output
    assert "排水明沟" in output


def test_glued_x_noise_is_removed() -> None:
    text = "方便行动障碍者使用的带安全抓杆的洗手盆。Xaccessible urinal"
    output = _remove_glued_x_noise(text)
    assert "Xaccessible" not in output
    assert "accessible urinal" in output


def test_misordered_item_is_repaired() -> None:
    text = (
        "9.6.1 信息与标识的无障碍设计应符合下列规定："
        "等无障碍设施的位置，应设置无障碍标志，无障碍标志应符合本规范第3.16节的有关规定；"
        "2重要的展览性陈设，宜设置盲文解说牌。"
        "1主要出入口、无障碍通道、停车位、建筑出入口、厕所"
    )
    output = _repair_misordered_items(text)
    assert output.index("1主要出入口") < output.index("2重要的展览性陈设")
    assert "下列规定：1主要出入口" in output


def test_glued_clause_after_chinese_is_split() -> None:
    text = "5.3.4 开向公共走道的门开启时（常闭的管道井门除外），不得5.3.5设置无障碍出入口"
    output = _format_standard_clauses(text)
    assert "\n5.3.5 " in output
    assert "不得5.3.5" not in output


def test_numbered_items_are_split_without_breaking_quantities() -> None:
    text = (
        "电梯设置应符合下列规定：1十二层以下应设置至少1台电梯；"
        "2十二层及以上应设置至少2台电梯；4电梯载重量七层及以上不应"
        "小于800kg；3电梯厅应满足担架通行要求；5除无障碍电梯外普通电梯轿厢内宜设扶手。"
    )
    output = _format_standard_clauses(text)
    assert "\n2 " in output
    assert "\n3 " in output
    assert "\n4 " in output
    assert "\n5 " in output
    assert "1台电梯" in output
    assert "800kg" in output


def test_ocr_wrapped_prose_is_joined_without_breaking_tables() -> None:
    text = (
        "续表3\n"
        "| 楼梯类别 @colspan=2 | ~ | 最小宽度 | 最大高度 | 坡度 | 步距 |\n"
        "| 人员密集且竖向交通繁忙的建筑和大、中学校楼梯 @colspan=2 | "
        "~ | 0.28 | 0.165 | 30.51° | 0.61 |\n"
        "表3中人员密集且竖向交通繁忙的建筑主要指电影院、剧\n"
        "场、音乐厅、体育馆、商场、医院、旅馆、交通客运站、博物\n"
        "馆、展览建筑、公共图书馆、游乐园（场）这类建筑场所。\n"
        "超高层建筑中常由不同功能类型组合而成，由于其日常竖向\n"
        "交通主要依赖于乘客用电梯。\n"
        "6.8.11楼梯的每一梯段的踏步高度、宽度应一致。"
    )

    output = normalize_ocr_paragraphs(text)

    assert "电影院、剧场" in output
    assert "博物馆" in output
    assert "日常竖向交通" in output
    assert "剧\n场" not in output
    assert "博物\n馆" not in output
    assert "竖向\n交通" not in output
    assert "| 人员密集且竖向交通繁忙" in output
    assert "这类建筑场所。超高层建筑" in output
    assert "交通主要依赖于乘客用电梯。6.8.11楼梯" in output


def test_ocr_wrapped_clause_reference_list_is_joined() -> None:
    text = "第4.3.1、\n6.7.4、\n6.8.6、\n6.8.9条为强制性条文。"

    output = normalize_ocr_paragraphs(text)

    assert output == "第4.3.1、6.7.4、6.8.6、6.8.9条为强制性条文。"


def test_table_title_remains_separate_from_prose() -> None:
    text = (
        "6.8.10楼梯踏步的宽度和高度应符合表6.8.10的规定。"
        "表6.8.10楼梯踏步最小宽度和最大高度（m）\n"
        "| 楼梯类别 @colspan=2 | ~ | 最小宽度 | 最大高度 |"
    )

    output = normalize_ocr_paragraphs(text)

    assert (
        "6.8.10楼梯踏步的宽度和高度应符合表6.8.10的规定。\n"
        "表6.8.10楼梯踏步最小宽度和最大高度（m）"
    ) in output
    assert "\n| 楼梯类别 @colspan=2" in output


def test_ocr_spacing_and_unit_noise_are_normalized() -> None:
    text = (
        "1.6OXI.10=\n"
        "1.76 (m Z )。\n"
        "[ c」中间 走道 宽度按一半计：( 0.60+1.10+0.40 ) x 1.50/2=1.575(m²)。"
    )

    output = normalize_ocr_paragraphs(text)

    assert "1.60×1.10=1.76" in output
    assert "(m²)" in output
    assert "中间走道宽度按一半计：(0.60+1.10+0.40)×1.50/2=1.575(m²)" in output
