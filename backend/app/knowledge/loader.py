from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from ..config import PDF_CHUNK_CHARS, SAMPLE_KB_PATH, STANDARDS_DIR
from .region_hierarchy import apply_region_hierarchy


def _slugify(text: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", text).strip("-").lower()
    return slug or "document"


def clean_extracted_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    return text.strip()


class KnowledgeBase:
    """Loads JSON knowledge documents and optional PDF ingestion."""

    def __init__(self) -> None:
        self.documents: list[dict[str, Any]] = []
        self.loaded_at: float = 0.0
        self.knowledge_base = "预构建规范知识库"
        self.reload()

    def reload(self) -> None:
        STANDARDS_DIR.mkdir(parents=True, exist_ok=True)
        documents: list[dict[str, Any]] = []
        for path in [SAMPLE_KB_PATH, *sorted(STANDARDS_DIR.glob("*.json"))]:
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            raw_documents = payload if isinstance(payload, list) else payload.get("documents", [])
            documents.extend(self._normalize_document(item) for item in raw_documents)
        self.documents = documents
        self.loaded_at = time.time()

    @staticmethod
    def _normalize_document(document: dict[str, Any]) -> dict[str, Any]:
        document.setdefault("title", document.get("standard", "未命名规范"))
        document.setdefault("document_type", "规范")
        document.setdefault("region", "全国")
        document.setdefault("year", 0)
        document.setdefault("status", "现行")
        document.setdefault("chapters", [])
        document.setdefault("snippets", [])
        return apply_region_hierarchy(document)

    def ingest_pdf(
        self,
        path: Path,
        title: str,
        standard: str,
        region: str = "全国",
        document_type: str = "国家标准",
        category: str = "",
        engine: str = "pypdf",
    ) -> dict[str, Any]:
        """Extract text from a PDF and save it as a JSON knowledge document."""
        if engine == "pymupdf":
            try:
                import fitz
            except ImportError as exc:
                raise RuntimeError("缺少 PyMuPDF，请安装 pymupdf") from exc
            document = fitz.open(str(path))
            pages = [page.get_text() for page in document]
            document.close()
        else:
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise RuntimeError("缺少 pypdf 依赖，无法解析 PDF") from exc
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]

        snippets: list[dict[str, Any]] = []
        for page_index, page_text in enumerate(pages, start=1):
            text = clean_extracted_text(page_text or "")
            if not text:
                continue
            for chunk in self._chunk_text(text):
                snippets.append(
                    {
                        "chapter": "原文",
                        "article": "",
                        "page": page_index,
                        "text": chunk,
                    }
                )

        document = {
            "id": _slugify(f"{region}-{standard or title}"),
            "title": title,
            "standard": standard,
            "document_type": document_type,
            "region": region,
            "category": category,
            "year": 0,
            "status": "待确认",
            "chapters": ["原文"],
            "snippets": snippets,
        }
        output = STANDARDS_DIR / f"{document['id']}.json"
        output.write_text(
            json.dumps({"documents": [document]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.reload()
        return document

    @staticmethod
    def _chunk_text(text: str, size: int = PDF_CHUNK_CHARS) -> list[str]:
        text = clean_extracted_text(text)
        chunks: list[str] = []
        for index in range(0, len(text), size):
            chunk = text[index : index + size]
            if index + size < len(text):
                break_at = max(chunk.rfind("。"), chunk.rfind("；"), chunk.rfind(";"))
                if break_at > size // 2:
                    chunk = chunk[: break_at + 1]
            if chunk.strip():
                chunks.append(chunk.strip())
        return chunks

    def stats(self) -> dict[str, Any]:
        standards = sorted({doc.get("standard", "") for doc in self.documents if doc.get("standard")})
        snippet_count = sum(len(doc.get("snippets", [])) for doc in self.documents)
        return {
            "document_count": len(self.documents),
            "snippet_count": snippet_count,
            "standards": standards,
            "knowledge_base": self.knowledge_base,
        }
