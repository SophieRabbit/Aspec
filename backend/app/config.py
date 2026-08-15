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

EVAL_DATA_DIR = DATA_DIR / "eval"
EVAL_DB_PATH = EVAL_DATA_DIR / "eval.db"
EVAL_REPORTS_DIR = EVAL_DATA_DIR / "reports"
EVAL_DATASET_DIR = BASE_DIR / "tests" / "datasets"
EVAL_USE_INTERNAL_CHAT = os.getenv("EVAL_USE_INTERNAL_CHAT", "1") == "1"
EVAL_CHAT_URL = os.getenv("EVAL_CHAT_URL", "http://127.0.0.1:8000/api/chat")

LLM_API_BASE = os.getenv("LLM_API_BASE", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

EVAL_THRESHOLDS = {
    "retrieval": float(os.getenv("EVAL_THRESHOLD_RETRIEVAL", "0.5")),
    "keyword": float(os.getenv("EVAL_THRESHOLD_KEYWORD", "0.7")),
    "source": float(os.getenv("EVAL_THRESHOLD_SOURCE", "0.5")),
    "completeness": float(os.getenv("EVAL_THRESHOLD_COMPLETENESS", "3.0")),
}
