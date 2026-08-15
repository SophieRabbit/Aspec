from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import EVAL_DB_PATH


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvalStore:
    def __init__(self, db_path: Path = EVAL_DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        return connection

    def init(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS eval_runs (
                    run_id TEXT PRIMARY KEY,
                    dataset_id TEXT,
                    status TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    metrics_json TEXT,
                    report_path TEXT,
                    regressions_json TEXT
                );
                CREATE TABLE IF NOT EXISTS eval_results (
                    run_id TEXT,
                    case_id TEXT,
                    question TEXT,
                    category TEXT,
                    expected_json TEXT,
                    actual_reply TEXT,
                    sources_json TEXT,
                    metrics_json TEXT,
                    is_bad_case INTEGER,
                    failed_dimensions_json TEXT
                );
                CREATE TABLE IF NOT EXISTS bad_cases (
                    id TEXT PRIMARY KEY,
                    run_id TEXT,
                    trace_id TEXT,
                    question TEXT,
                    actual_reply TEXT,
                    expected_reply TEXT,
                    failed_dimensions_json TEXT,
                    source TEXT,
                    user_note TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    request_json TEXT,
                    response_json TEXT,
                    sources_json TEXT,
                    reasoning_json TEXT,
                    memory_json TEXT,
                    web_results_json TEXT,
                    latency_ms REAL,
                    created_at TEXT
                );
                """
            )
            columns = [row[1] for row in connection.execute("PRAGMA table_info(eval_runs)").fetchall()]
            if "advice_json" not in columns:
                connection.execute("ALTER TABLE eval_runs ADD COLUMN advice_json TEXT")

    def save_trace(
        self,
        trace_id: str,
        request: dict[str, Any],
        response: dict[str, Any],
        latency_ms: float,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO traces (
                    trace_id, request_json, response_json, sources_json,
                    reasoning_json, memory_json, web_results_json, latency_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    json.dumps(request, ensure_ascii=False, default=str),
                    json.dumps(response, ensure_ascii=False, default=str),
                    json.dumps(response.get("sources", []), ensure_ascii=False, default=str),
                    json.dumps(response.get("reasoning", []), ensure_ascii=False, default=str),
                    json.dumps(response.get("memory"), ensure_ascii=False, default=str),
                    json.dumps(response.get("web_results", []), ensure_ascii=False, default=str),
                    latency_ms,
                    _now(),
                ),
            )

    def add_bad_case(
        self,
        *,
        question: str,
        actual_reply: str,
        expected_reply: str = "",
        failed_dimensions: list[str],
        source: str,
        trace_id: str = "",
        run_id: str = "",
        user_note: str = "",
    ) -> str:
        bad_case_id = uuid.uuid4().hex[:12]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO bad_cases (
                    id, run_id, trace_id, question, actual_reply, expected_reply,
                    failed_dimensions_json, source, user_note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bad_case_id,
                    run_id,
                    trace_id,
                    question,
                    actual_reply,
                    expected_reply,
                    json.dumps(failed_dimensions, ensure_ascii=False),
                    source,
                    user_note,
                    _now(),
                ),
            )
        return bad_case_id

    def create_run(self, dataset_id: str) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO eval_runs (run_id, dataset_id, status, started_at) VALUES (?, ?, ?, ?)",
                (run_id, dataset_id, "running", _now()),
            )
        return run_id

    def finish_run(
        self,
        run_id: str,
        metrics: dict[str, Any],
        report_path: str,
        regressions: dict[str, float],
        advice: list[dict[str, Any]] | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE eval_runs
                SET status = ?, finished_at = ?, metrics_json = ?, report_path = ?, regressions_json = ?, advice_json = ?
                WHERE run_id = ?
                """,
                (
                    "finished",
                    _now(),
                    json.dumps(metrics, ensure_ascii=False),
                    report_path,
                    json.dumps(regressions, ensure_ascii=False),
                    json.dumps(advice or [], ensure_ascii=False),
                    run_id,
                ),
            )

    def save_result(
        self,
        run_id: str,
        result: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO eval_results (
                    run_id, case_id, question, category, expected_json,
                    actual_reply, sources_json, metrics_json, is_bad_case, failed_dimensions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    result["case_id"],
                    result["question"],
                    result["category"],
                    json.dumps(
                        {
                            "source": result.get("expected_source", []),
                            "keywords": result.get("expected_keywords", []),
                            "pages": result.get("expected_pages", []),
                        },
                        ensure_ascii=False,
                    ),
                    result.get("actual_reply", ""),
                    json.dumps(result.get("sources", []), ensure_ascii=False),
                    json.dumps(result.get("metrics", {}), ensure_ascii=False),
                    1 if result.get("is_bad_case") else 0,
                    json.dumps(result.get("failed_dimensions", []), ensure_ascii=False),
                ),
            )

    def list_runs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM eval_runs ORDER BY started_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM eval_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_results(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM eval_results WHERE run_id = ? ORDER BY rowid",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def previous_metrics(self, dataset_id: str, exclude_run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT metrics_json FROM eval_runs
                WHERE dataset_id = ? AND run_id != ? AND status = 'finished' AND metrics_json IS NOT NULL
                ORDER BY started_at DESC LIMIT 1
                """,
                (dataset_id, exclude_run_id),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["metrics_json"])

    def list_bad_cases(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM bad_cases ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def list_user_feedback_cases(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT question, actual_reply, user_note, trace_id
                FROM bad_cases
                WHERE source = 'user_feedback'
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]
