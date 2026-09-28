from __future__ import annotations

from app.agent.planner import Planner


def test_tool_source_keeps_complete_formula_text() -> None:
    snippet = (
        "3.24(m²); 内部走道宽度(即办公桌与对面办公桌)按一半计："
        "1.50×1.10/2=0.99(m²)。辅助面积：中间走道宽度按一半计："
        "1.80×1.50/2=1.35(m²); 合计：6.35m²。"
    )

    source = Planner._tool_source(
        {
            "doc_id": "全国-jgj-t67-2019",
            "standard": "JGJ/T67-2019",
            "title": "办公建筑设计标准",
            "snippet": snippet,
        }
    )

    assert source["snippet"] == snippet
    assert source["snippet"].endswith("6.35m²。")
