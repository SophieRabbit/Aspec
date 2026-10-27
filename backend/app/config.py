from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STANDARDS_DIR = DATA_DIR / "standards"
STANDARD_STATUS_PATH = DATA_DIR / "standard_status.json"
MEMORY_DIR = DATA_DIR / "memory"
PRIORITY_STANDARDS_PATH = DATA_DIR / "priority_standards.json"
PRIORITY_PDFS_DIR = DATA_DIR / "priority_pdfs"
PRIORITY_STANDARD_BOOST = float(os.getenv("PRIORITY_STANDARD_BOOST", "80"))
PRIORITY_TIER_STEP = float(os.getenv("PRIORITY_TIER_STEP", "20"))
MEMORY_DB_PATH = DATA_DIR / "memory" / "memory.db"
MEMORY_DATABASE_URL = os.getenv(
    "MEMORY_DATABASE_URL",
    f"sqlite:///{MEMORY_DB_PATH.as_posix()}",
)
MEMORY_IMPORT_JSON = os.getenv("MEMORY_IMPORT_JSON", "1") == "1"

REDIS_URL = os.getenv("REDIS_URL", "")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(24 * 60 * 60)))
SESSION_KEEP = int(os.getenv("SESSION_KEEP", "20"))

APP_NAME = "规宝"
API_PREFIX = "/api"

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "30"))
MEMORY_TOKEN_BUDGET = int(os.getenv("MEMORY_TOKEN_BUDGET", "1500"))
SHORT_TERM_KEEP = int(os.getenv("SHORT_TERM_KEEP", "10"))
MEMORY_CONTEXT_FACTS = int(os.getenv("MEMORY_CONTEXT_FACTS", "10"))
PDF_CHUNK_CHARS = int(os.getenv("PDF_CHUNK_CHARS", "900"))

LLM_API_BASE = os.getenv("LLM_API_BASE", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

AGENT_FUNCTION_CALLING_ENABLED = os.getenv("AGENT_FUNCTION_CALLING_ENABLED", "1") == "1"
AGENT_MAX_TOOL_TURNS = int(os.getenv("AGENT_MAX_TOOL_TURNS", "2"))
AGENT_LLM_TIMEOUT_SECONDS = float(os.getenv("AGENT_LLM_TIMEOUT_SECONDS", "20"))
AGENT_TOOL_RESULT_CHARS = int(os.getenv("AGENT_TOOL_RESULT_CHARS", "8000"))
AGENT_LLM_MAX_TOKENS = int(os.getenv("AGENT_LLM_MAX_TOKENS", "1200"))
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "0") == "1"

MEMORY_LLM_ENABLED = os.getenv("MEMORY_LLM_ENABLED", "0") == "1"
MEMORY_LLM_TIMEOUT_SECONDS = float(os.getenv("MEMORY_LLM_TIMEOUT_SECONDS", "20"))
MEMORY_MAX_FACTS_PER_TURN = int(os.getenv("MEMORY_MAX_FACTS_PER_TURN", "12"))
MEMORY_MAX_ITEMS_PER_USER = int(os.getenv("MEMORY_MAX_ITEMS_PER_USER", "500"))

FEEDBACK_ADMIN_TOKEN = os.getenv("FEEDBACK_ADMIN_TOKEN", "")
FEEDBACK_DASHBOARD_USERNAME = os.getenv("FEEDBACK_DASHBOARD_USERNAME", "zwszff")
FEEDBACK_DASHBOARD_PASSWORD = os.getenv("FEEDBACK_DASHBOARD_PASSWORD", "zwszff")
