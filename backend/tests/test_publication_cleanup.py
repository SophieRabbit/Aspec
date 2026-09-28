from __future__ import annotations

from app.knowledge.text_cleaner import strip_publication_metadata


def test_publication_metadata_is_removed() -> None:
    text = (
        "10.00元统一书号：15112·23962版权所有翻印必究"
        "本社网址：http://www.cabp.com.cn"
    )

    assert strip_publication_metadata(text) == ""


def test_normative_tail_is_preserved() -> None:
    text = (
        "10.00元统一书号：15112·23962版权所有翻印必究"
        "1 总则1.0.1 为使商店建筑设计满足安全卫生要求，制定本规范。"
    )

    cleaned = strip_publication_metadata(text)

    assert cleaned.startswith("1.0.1 为使商店建筑设计")
    assert "统一书号" not in cleaned
