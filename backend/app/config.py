from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STANDARDS_DIR = DATA_DIR / "standards"
MEMORY_DIR = DATA_DIR / "memory"
SAMPLE_KB_PATH = DATA_DIR / "sample_kb.json"

APP_NAME = "规宝"
API_PREFIX = "/api"

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "30"))
MEMORY_TOKEN_BUDGET = int(os.getenv("MEMORY_TOKEN_BUDGET", "1500"))
SHORT_TERM_KEEP = int(os.getenv("SHORT_TERM_KEEP", "10"))
PDF_CHUNK_CHARS = int(os.getenv("PDF_CHUNK_CHARS", "900"))
