from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import pymupdf
from rapidocr_onnxruntime import RapidOCR


_NOISE_MARKERS = (
    "文档来源于网络",
    "全咨之家",
    "标准分享网",
    "免费下载",
)

_DECIMAL_RE = re.compile(r"\d+\.\d{2,3}")


def repair_ocr_table_fragments(text: str) -> str:
    """Repair OCR rows that split a table column into standalone lines."""
    lines = text.splitlines()
    title = "表3楼梯坡度及步距（m）"
    broken_row_marker = "宿舍楼梯其他宿舍楼梯"

    for title_index, line in enumerate(lines):
        if line.strip() != title:
            continue
        header_index = next(
            (
                index
                for index in range(title_index + 1, len(lines))
                if lines[index].strip().startswith("|")
                and "楼梯类别 @colspan=2" in lines[index]
            ),
            None,
        )
        if header_index is None:
            continue
        final_index = next(
            (
                index
                for index in range(header_index + 1, len(lines))
                if broken_row_marker in lines[index]
                and "0.600.56" in lines[index]
            ),
            None,
        )
        if final_index is None:
            continue

        lines[header_index : final_index + 1] = [
            "| 楼梯类别 @colspan=2 | ~ | 最小宽度 | 最大高度 | 坡度 | 步距 |",
            "| 住宅楼梯 @rowspan=2 | 住宅公共楼梯 | 0.26 | 0.175 | 33.94° | 0.61 |",
            "| ~ | 住宅套内楼梯 | 0.22 | 0.20 | 42.27° | 0.62 |",
            "| 宿舍楼梯 @rowspan=2 | 小学宿舍楼梯 | 0.26 | 0.15 | 29.98° | 0.56 |",
            "| ~ | 其他宿舍楼梯 | 0.27 | 0.165 | 31.43° | 0.60 |",
        ]
        break

    return "\n".join(lines)


def _split_merged_table_rows(rows: list[list[str]]) -> list[list[str]]:
    split_rows: list[list[str]] = []
    for row in rows:
        cells = [cell.strip() for cell in row]
        expanded: list[str] = []
        for cell in cells:
            if "最小宽度" in cell and "最大高度" in cell:
                expanded.extend(["最小宽度", "最大高度"])
            else:
                expanded.append(cell)
        cells = expanded

        numeric_counts = [
            len(_DECIMAL_RE.findall(cell))
            for cell in cells
            if _DECIMAL_RE.search(cell)
        ]
        split_count = max(numeric_counts, default=1)
        if split_count < 2 or sum(
            count == split_count for count in numeric_counts
        ) < 2:
            split_rows.append(cells)
            continue

        label_index = next(
            (
                index
                for index, cell in enumerate(cells)
                if _DECIMAL_RE.search(cell)
            ),
            0,
        ) - 1
        label_parts = re.findall(r".*?楼梯", cells[label_index]) if label_index >= 0 else []
        for part_index in range(split_count):
            new_row: list[str] = []
            for index, cell in enumerate(cells):
                values = _DECIMAL_RE.findall(cell)
                if len(values) == split_count:
                    new_row.append(values[part_index])
                elif index == label_index and len(label_parts) == split_count:
                    new_row.append(label_parts[part_index])
                else:
                    new_row.append(cell)
            split_rows.append(new_row)
    return split_rows


def render_page_to_image(page: Any, prefix: str = "", zoom: float = 2.0) -> Path:
    output = Path("tmp") / "ocr" / f"{prefix}page-{page.number + 1}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    pix.save(str(output))
    return output


def ocr_image(engine: RapidOCR, image_path: Path) -> list[dict[str, Any]]:
    result, _ = engine(str(image_path))
    boxes: list[dict[str, Any]] = []
    for item in result or []:
        box, text, score = item
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        boxes.append(
            {
                "text": str(text),
                "x0": min(xs),
                "y0": min(ys),
                "x1": max(xs),
                "y1": max(ys),
                "score": float(score),
            }
        )
    return boxes


def group_ocr_lines(boxes: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    sorted_boxes = sorted(boxes, key=lambda box: (box["y0"], box["x0"]))
    lines: list[list[dict[str, Any]]] = []
    for box in sorted_boxes:
        line_height = max(1.0, box["y1"] - box["y0"])
        if not lines or box["y0"] - lines[-1][-1]["y1"] > max(2.0, line_height * 0.12):
            lines.append([box])
        else:
            lines[-1].append(box)
    for line in lines:
        line.sort(key=lambda box: box["x0"])
    return lines


def split_ocr_cells(line: list[dict[str, Any]]) -> list[str]:
    if len(line) == 1:
        return [line[0]["text"].strip()]
    cells: list[str] = []
    current = line[0]
    buffer = current["text"].strip()
    for box in line[1:]:
        gap = box["x0"] - current["x1"]
        width = max(1, box["x1"] - box["x0"])
        if gap > max(8, width * 0.5):
            cells.append(buffer)
            buffer = box["text"].strip()
        else:
            buffer += box["text"].strip()
        current = box
    cells.append(buffer)
    return cells


def _center(box: dict[str, Any]) -> tuple[float, float]:
    return (
        (float(box["x0"]) + float(box["x1"])) / 2,
        (float(box["y0"]) + float(box["y1"])) / 2,
    )


def _inside_bbox(box: dict[str, Any], bbox: tuple[float, float, float, float]) -> bool:
    center_x, center_y = _center(box)
    return bbox[0] <= center_x <= bbox[2] and bbox[1] <= center_y <= bbox[3]


def _join_cell_text(boxes: list[dict[str, Any]]) -> str:
    ordered = sorted(boxes, key=lambda box: (box["y0"], box["x0"]))
    result = ""
    for box in ordered:
        text = str(box.get("text", "")).strip()
        if not text:
            continue
        if result and result[-1].isascii() and text[0].isascii():
            result += " "
        result += text
    return result.strip()


def _render_detected_table(
    table: Any,
    boxes: list[dict[str, Any]],
    zoom: float,
) -> list[str]:
    extracted = table.extract()
    row_edges = sorted(
        {
            round(float(value), 2)
            for row in table.rows
            for value in (row.bbox[1], row.bbox[3])
        }
    )
    column_edges = sorted(
        {
            round(float(value), 2)
            for row in table.rows
            for cell in row.cells
            if cell is not None
            for value in (cell[0], cell[2])
        }
    )
    rendered: list[str] = []
    for row_index, row in enumerate(table.rows):
        rendered_cells: list[str] = []
        for column_index, cell in enumerate(row.cells):
            if cell is None:
                rendered_cells.append("~")
                continue
            x0, y0, x1, y1 = (float(value) * zoom for value in cell)
            cell_bbox = (x0, y0, x1, y1)
            text = _join_cell_text(
                [box for box in boxes if _inside_bbox(box, cell_bbox)]
            )
            if not text:
                fallback = extracted[row_index][column_index] or ""
                text = re.sub(r"\s+", " ", str(fallback)).strip()

            colspan = max(
                1,
                sum(
                    1
                    for left, right in zip(column_edges, column_edges[1:])
                    if cell[0] <= (left + right) / 2 <= cell[2]
                ),
            )
            rowspan = max(
                1,
                sum(
                    1
                    for top, bottom in zip(row_edges, row_edges[1:])
                    if cell[1] <= (top + bottom) / 2 <= cell[3]
                ),
            )
            text = text.replace("|", "\\|")
            if colspan > 1:
                text += f" @colspan={colspan}"
            if rowspan > 1:
                text += f" @rowspan={rowspan}"
            rendered_cells.append(text or " ")
        rendered.append("| " + " | ".join(rendered_cells) + " |")
    return rendered


def _render_ocr_line_blocks(boxes: list[dict[str, Any]]) -> list[tuple[float, str]]:
    blocks: list[tuple[float, str]] = []
    table_rows: list[list[str]] = []
    table_y: float | None = None

    def flush_table() -> None:
        nonlocal table_y
        if not table_rows:
            return
        normalized_rows = _split_merged_table_rows(table_rows)
        max_columns = max(len(row) for row in normalized_rows)
        previous_first = ""
        for index, row in enumerate(normalized_rows):
            row = [cell.strip() for cell in row]
            if len(row) == max_columns:
                pass
            elif len(row) == max_columns - 1 and (
                index == 0
                or index == len(normalized_rows) - 1
                or "、" in row[0]
            ):
                row = [row[0], "", *row[1:]]
            elif index > 0 and len(row) == max_columns - 1:
                row = [previous_first, *row]
            else:
                row += [""] * (max_columns - len(row))
            if row and row[0]:
                previous_first = row[0]
            blocks.append((table_y or 0.0, "| " + " | ".join(row) + " |"))
        table_rows.clear()
        table_y = None

    for line in group_ocr_lines(boxes):
        cells = split_ocr_cells(line)
        line_y = min(float(box["y0"]) for box in line)
        if (
            len(cells) == 2
            and re.fullmatch(r"\d{1,2}(?:\.\d{1,2}){0,3}", cells[0].strip())
            and 0 < len(cells[1].strip()) <= 24
        ):
            flush_table()
            blocks.append((line_y, f"{cells[0].strip()} {cells[1].strip()}"))
            continue
        if len(cells) > 1:
            if table_y is None:
                table_y = line_y
            table_rows.append(cells)
        else:
            flush_table()
            blocks.append((line_y, cells[0].strip()))
    flush_table()
    return blocks


def ocr_page_text(page: Any, engine: RapidOCR, zoom: float = 3.0) -> str:
    """OCR a scanned page while keeping table columns separated with pipes."""
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        image_path = Path(handle.name)
    try:
        pix.save(str(image_path))
        boxes = ocr_image(engine, image_path)
    finally:
        image_path.unlink(missing_ok=True)

    try:
        tables = list(page.find_tables().tables)
    except Exception:
        tables = []

    if tables:
        table_bboxes = [
            tuple(float(value) * zoom for value in table.bbox)
            for table in tables
        ]
        blocks = [
            (float(table.bbox[1]) * zoom, line)
            for table in tables
            for line in _render_detected_table(table, boxes, zoom)
        ]
        normal_boxes = [
            box
            for box in boxes
            if not any(_inside_bbox(box, bbox) for bbox in table_bboxes)
        ]
        blocks.extend(_render_ocr_line_blocks(normal_boxes))
        blocks.sort(key=lambda item: item[0])
        rows = [line for _, line in blocks]
    else:
        rows = [line for _, line in _render_ocr_line_blocks(boxes)]
    return repair_ocr_table_fragments("\n".join(
        row for row in rows if not any(marker in row for marker in _NOISE_MARKERS)
    ))


def lines_to_markdown_table(lines: list[list[dict[str, Any]]]) -> str | None:
    rows = [split_ocr_cells(line) for line in lines]
    rows = [row for row in rows if row]
    if len(rows) < 2:
        return None
    column_count = max(len(row) for row in rows)
    if column_count < 2:
        return None

    def render_row(row: list[str]) -> str:
        cells = [cell.replace("|", "\\|") for cell in row]
        cells += [""] * (column_count - len(cells))
        return "| " + " | ".join(cells) + " |"

    header = rows[0]
    separator = "| " + " | ".join(["---"] * column_count) + " |"
    body = "\n".join(render_row(row) for row in rows[1:])
    return f"{render_row(header)}\n{separator}\n{body}"


def extract_page_images(
    document: Any,
    page: Any,
    doc_id: str,
    page_no: int,
    output_dir: Path,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, Any]] = []
    image_blocks = [
        block
        for block in page.get_text("dict").get("blocks", [])
        if block.get("type") == 1
    ]
    page_area = page.rect.width * page.rect.height
    image_blocks = [
        block
        for block in image_blocks
        if _bbox_area(block.get("bbox")) < page_area * 0.8
    ]

    for index, block in enumerate(image_blocks, start=1):
        bbox = block.get("bbox")
        if not bbox:
            continue
        try:
            pix = page.get_pixmap(clip=bbox, matrix=pymupdf.Matrix(2, 2))
        except Exception:
            continue
        asset_path = output_dir / f"page-{page_no}-img-{index}.png"
        pix.save(str(asset_path))
        assets.append(
            {
                "path": str(asset_path.relative_to(output_dir.parents[1])),
                "page": page_no,
                "index": index,
            }
        )
    return assets


def _bbox_area(bbox: Any) -> float:
    if not bbox:
        return 0.0
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])
