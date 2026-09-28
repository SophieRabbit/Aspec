from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import pymupdf

from .ocr import ocr_image

_PAGE_TOKEN_RE = re.compile(r"[\s·•—–\-—]*\d{1,4}[\s·•—–\-—]*$")


def _looks_like_book_page(value: int) -> bool:
    return 0 < value < 10000 and not (1900 <= value <= 2099)


def extract_trailing_book_page(text: str) -> tuple[int | None, str]:
    """Detect and remove a standalone printed page number at the end of text."""
    stripped = text.rstrip()
    match = _PAGE_TOKEN_RE.search(stripped)
    if not match:
        return None, text
    numbers = re.findall(r"\d{1,4}", match.group(0))
    if not numbers:
        return None, text
    value = int(numbers[-1])
    if not _looks_like_book_page(value):
        return None, text
    cleaned = stripped[: match.start()].rstrip()
    return value, cleaned


def strip_book_page_token(text: str, book_page: int | None) -> str:
    if book_page is None:
        return text
    pattern = re.compile(r"[\s·•—–\-—]*" + str(book_page) + r"[\s·•—–\-—]*$")
    return pattern.sub("", text.rstrip()).rstrip()


def book_page_from_page_image(
    page: Any,
    engine: Any,
    zoom: float = 4.0,
    bottom_ratio: float = 0.18,
    top_ratio: float = 0.12,
) -> int | None:
    """Find the printed page number by OCR-ing the page footer/header bands."""
    width = page.rect.width
    height = page.rect.height
    bands = [
        (pymupdf.Rect(0, height * (1 - bottom_ratio), width, height), "bottom"),
        (pymupdf.Rect(0, 0, width, height * top_ratio), "top"),
    ]
    for rect, _ in bands:
        pix = page.get_pixmap(clip=rect, matrix=pymupdf.Matrix(zoom, zoom))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            pix.save(str(temp_path))
            boxes = ocr_image(engine, temp_path)
        finally:
            temp_path.unlink(missing_ok=True)
        candidates: list[tuple[float, int]] = []
        for box in boxes:
            text = box.get("text", "").strip()
            if len(text) > 6:
                continue
            numbers = re.findall(r"\d{1,4}", text)
            if not numbers:
                continue
            value = int(numbers[-1])
            if _looks_like_book_page(value):
                candidates.append((box.get("y0", 0.0), value))
        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1]
    return None
