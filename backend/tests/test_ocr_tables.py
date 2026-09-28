from __future__ import annotations

from app.knowledge.ocr import repair_ocr_table_fragments


def test_step_distance_table_rows_are_repaired() -> None:
    text = "\n".join(
        [
            "表3楼梯坡度及步距（m）",
            "| 楼梯类别 @colspan=2 | ~ | 最小宽度 | 最大高度 | 坡度 |",
            "| 住宅楼梯 @rowspan=2 | 住宅公共楼梯 | 0.26 | 0.175 | 33.94° |",
            "| ~ | 住宅套内楼梯 | 0.22 | 0.20 | 42.27° |",
            "| ~ | 小学宿舍楼梯 | 0.26 | 0.15 | 29.98° |",
            "步距",
            "0.61",
            "0.62",
            "| 宿舍楼梯其他宿舍楼梯 | 0.27 | 0.165 | 31.43° | 0.600.56 |",
        ]
    )

    repaired = repair_ocr_table_fragments(text)

    assert "| 步距 |" in repaired
    assert "| 33.94° | 0.61 |" in repaired
    assert "| 42.27° | 0.62 |" in repaired
    assert "| 29.98° | 0.56 |" in repaired
    assert "| 宿舍楼梯 @rowspan=2 | 小学宿舍楼梯" in repaired
    assert "| ~ | 其他宿舍楼梯" in repaired
    assert "| 31.43° | 0.60 |" in repaired
    assert "0.600.56" not in repaired
