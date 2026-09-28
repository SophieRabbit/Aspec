from __future__ import annotations

from app.agent.planner import Planner


def test_keyword_clause_is_underlined() -> None:
    text = (
        "7历史建筑 7.1保护重点 7.1.1不同时期、不同类型的历史建筑均应进行保护，应加强 "
        "7.1.2历史建筑加建、改建和添加设施应与历史建筑的传统形 "
        "7.1.3在不影响历史文化价值的前提下，应结合实际使用需求式、色彩、材质等相协调。"
        "保护修和日常保养维护，维护历史建筑的主要特征，不应破坏或遮挡体现历史建筑核心价值"
        "的外观、结构和构件。有效提升历史建筑在消防安全、无障碍、节能等方面的性能。"
        "7.2活化利用 7.2.1历史建筑应优先延续原有使用功能"
    )
    planner = Planner.__new__(Planner)
    output = planner._highlight_clause_html(text, ["无障碍"])
    assert '7.1.1不同时期' in output
    assert '7.1.1不同时期' not in output.split('<u class="clause-hit">')[1]
    assert '<u class="clause-hit">7.1.3在不影响' in output
    assert "<mark>无障碍</mark>" in output
    assert "clause-hit" in output.split("<mark>无障碍</mark>")[0]


def test_highlight_terms_use_natural_keywords() -> None:
    planner = Planner.__new__(Planner)
    terms = planner._highlight_terms("成都无障碍设施相关规范有啥")
    assert terms == ["无障碍"]
    assert not any("碍设施" in term for term in terms)


def test_standard_index_snippet_is_detected() -> None:
    planner = Planner.__new__(Planner)
    index_text = (
        "序号编号规范名称 14 GB55014-2021 园林绿化工程项目规范 "
        "15 GB55015-2021 建筑节能与可再生能源利用通用规范 "
        "16 GB55016-2021 建筑环境通用规范"
    )
    normal_text = "2.2.3 民用建筑应满足无障碍要求。"
    toc_text = (
        "3.3 公共浴室和更衣室············12 "
        "3.4 无障碍客房和无障碍住房、居室············12 "
        "3.5 轮椅席位············13"
    )
    assert planner._looks_like_standard_index(index_text) is True
    assert planner._looks_like_standard_index(normal_text) is False
    assert planner._looks_like_standard_index(toc_text) is True


def test_cross_page_clause_is_merged() -> None:
    planner = Planner.__new__(Planner)
    snippets = [
        {
            "chapter": "OCR",
            "page": 10,
            "book_page": 8,
            "text": "5.5.1 公共厨房应符合食品卫生防疫安全要求，不应设置排水明沟",
        },
        {
            "chapter": "OCR",
            "page": 11,
            "book_page": 9,
            "text": "并应采取排烟措施。5.5.2 其他内容。",
        },
    ]
    units = planner._build_clause_units(snippets)
    first = units[0]
    second = units[1]
    first_text = "".join(part[2] for part in first["parts"])
    assert first["parts"][0][0] == 10
    assert first["parts"][1][0] == 11
    assert "排烟措施" in first_text
    assert second["parts"][0][0] == 11


def test_formula_numbers_are_not_treated_as_clause_numbers() -> None:
    planner = Planner.__new__(Planner)
    text = (
        "基本面积=3.24(m²); 内部走道宽度按一半计："
        "1.50×1.10/2=0.99(m²)。"
    )

    fragments = planner._split_snippet_clause_fragments(text)

    assert fragments == [(False, text)]


def test_clause_range_after_sentence_starts_new_fragment() -> None:
    planner = Planner.__new__(Planner)
    text = (
        "7.1.5 这两条规定了最小净宽度和最小净高度等基本要求。"
        "7.1.6、7.1.7 这两条规定了疏散指示标志的要求。"
    )

    fragments = planner._split_snippet_clause_fragments(text)
    starts = [fragment for starts, fragment in fragments if starts]

    assert len(starts) == 3
    assert starts[0].startswith("7.1.5 这两条")
    assert starts[1].startswith("7.1.6、")
    assert starts[2].startswith("7.1.7 ")


def test_out_of_order_pages_are_stitched_to_adjacent_page() -> None:
    planner = Planner.__new__(Planner)
    snippets = [
        {
            "chapter": "原文",
            "page": 141,
            "book_page": 131,
            "text": (
                "8.4.15燃煤住宅应设置竖向烟道，依据国家标准《城镇燃气设计规"
            ),
        },
        {
            "chapter": "原文",
            "page": 109,
            "book_page": 99,
            "text": "平台0.30m平台≥2.00m表3楼梯坡度及步距",
        },
        {
            "chapter": "原文",
            "page": 142,
            "book_page": 132,
            "text": "范》GB50028-2006第10.7.2条第1款。竖向烟道能避免烟气低空污染。",
        },
    ]

    units = planner._build_clause_units(snippets)
    target = next(
        unit
        for unit in units
        if "8.4.15燃煤住宅" in "".join(part[2] for part in unit["parts"])
    )
    text = "".join(part[2] for part in target["parts"])

    assert "《城镇燃气设计规范》GB50028-2006第10.7.2条" in text
    assert [part[0] for part in target["parts"]] == [141, 142]
    assert "平台0.30m" not in text


def test_only_entry_with_keyword_is_underlined() -> None:
    planner = Planner.__new__(Planner)
    text = (
        "5.5.1 本条规定多层砌体房屋的高度和层数控制要求。\n"
        "6 ) 砌体房屋有较大错层时，其层数应按2倍计算，还要注意符合无障碍设计的相关强制性要求。\n"
        "7 ) 建造砌体房屋时，不应为追求近期经济效益而超高。"
    )
    output = planner._highlight_clause_html(text, ["无障碍"])
    assert '<u class="clause-hit">6 )' in output
    assert "5.5.1 本条规定" not in output.split("<u")[1]
    assert output.count('<u class="clause-hit">') == 1


def test_table_rows_are_highlighted_without_breaking_markdown() -> None:
    planner = Planner.__new__(Planner)
    text = (
        "| 楼梯类别 @rowspan=2 | 最小宽度 |\n"
        "| 商店楼梯 | 0.28 |\n"
        "5.3.1 商店营业厅的疏散通道应符合规定。"
    )

    output = planner._highlight_clause_html(text, ["商店"])
    lines = output.splitlines()

    assert lines[0].startswith("| ")
    assert "<mark>商店</mark>" in lines[1]
    assert "<u" not in lines[0]
    assert "<u" not in lines[1]
    assert "<u" in lines[2]


def test_table_prefix_is_preserved_when_clause_starts_mid_row() -> None:
    planner = Planner.__new__(Planner)
    text = (
        "| @rowspan=7 | 8.6 \u6d88\u9632\u5e94\u6025\u7167\u660e "
        "@rowspan=3 | 1. \u5e94\u6025\u7167\u660e |\n"
        "| 2. \u5e94\u6025\u7167\u660e |"
    )

    fragments = planner._split_snippet_clause_fragments(text)
    starts = [fragment for starts, fragment in fragments if starts]

    assert len(starts) == 1
    assert starts[0].startswith("| @rowspan=7 | 8.6 ")
