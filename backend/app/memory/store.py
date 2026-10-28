from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config import (
    MEMORY_CONTEXT_FACTS,
    MEMORY_DATABASE_URL,
    MEMORY_DIR,
    MEMORY_IMPORT_JSON,
    MEMORY_MAX_ITEMS_PER_USER,
    MEMORY_TOKEN_BUDGET,
    REDIS_URL,
    SESSION_KEEP,
    SESSION_TTL_SECONDS,
)
from .distiller import MemoryDistiller
from .session_store import create_session_store
from .sql_store import SqlMemoryStore

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    other_chars = len(text) - chinese_chars
    return chinese_chars + int(other_chars / 3) + 1


class MemoryStore:
    """
    Production memory facade.

    SQL is the source of truth for raw chat records and structured memory.
    Redis holds only the current-session hot window, and LLM distillation runs
    as a background job so it never blocks the chat response.
    """

    def __init__(
        self,
        database_url: str = MEMORY_DATABASE_URL,
        *,
        redis_url: str = REDIS_URL,
        session_ttl_seconds: int = SESSION_TTL_SECONDS,
        session_keep: int = SESSION_KEEP,
        import_json: bool = MEMORY_IMPORT_JSON,
        json_dir: Path = MEMORY_DIR,
        distiller: MemoryDistiller | None = None,
    ) -> None:
        self.sql = SqlMemoryStore(database_url)
        self.session = create_session_store(redis_url, session_ttl_seconds, session_keep)
        self.distiller = distiller or MemoryDistiller()
        if import_json:
            self.sql.import_json_files(json_dir)

    def create_conversation(self, user_id: str = "default", title: str = "新对话") -> dict[str, Any]:
        conversation = self.sql.create_conversation(user_id=user_id, title=title)
        self.session.set_recent_messages(conversation["conversation_id"], user_id, [])
        return conversation

    def exists(self, conversation_id: str, user_id: str = "default") -> bool:
        return self.sql.exists(conversation_id, user_id)

    def list_conversations(self, user_id: str = "default") -> list[dict[str, Any]]:
        return self.sql.list_conversations(user_id)

    def delete_conversation(self, conversation_id: str, user_id: str = "default") -> bool:
        deleted = self.sql.delete_conversation(conversation_id, user_id)
        self.session.delete(conversation_id, user_id)
        return deleted

    def get_messages(self, conversation_id: str, user_id: str = "default") -> list[dict[str, Any]]:
        return self.sql.get_messages(conversation_id, user_id)

    def get_message(self, message_id: str, user_id: str = "default") -> dict[str, Any] | None:
        return self.sql.get_message(message_id, user_id)

    def save_feedback(self, **values: Any) -> dict[str, Any]:
        return self.sql.upsert_feedback(**values)

    def list_feedback(self, *, limit: int = 10000) -> list[dict[str, Any]]:
        return self.sql.list_feedback(limit=limit)

    def add_analytics_events(self, events: list[dict[str, Any]]) -> int:
        return self.sql.add_analytics_events(events)

    def list_analytics_events(
        self,
        *,
        since: str | None = None,
        limit: int = 200000,
    ) -> list[dict[str, Any]]:
        return self.sql.list_analytics_events(since=since, limit=limit)

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        user_id: str = "default",
        metadata: dict[str, Any] | None = None,
        trace_id: str = "",
    ) -> dict[str, Any]:
        message = self.sql.add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            metadata=metadata,
            trace_id=trace_id,
        )
        self.session.push_message(
            conversation_id,
            user_id,
            {
                "role": role,
                "content": content[:300],
                "created_at": message["created_at"],
                "trace_id": trace_id,
            },
        )
        return message

    def get_recent_messages(
        self,
        conversation_id: str,
        user_id: str = "default",
        limit: int = SESSION_KEEP,
    ) -> list[dict[str, Any]]:
        cached = self.session.get_recent_messages(conversation_id, user_id)
        if cached is not None:
            return cached[-limit:] if limit else cached
        messages = self.sql.get_messages(conversation_id, user_id)
        recent = messages[-limit:] if limit else messages
        self.session.set_recent_messages(conversation_id, user_id, recent)
        return recent

    def build_context(
        self,
        conversation_id: str,
        *,
        user_id: str = "default",
        max_tokens: int = MEMORY_TOKEN_BUDGET,
        max_facts: int = MEMORY_CONTEXT_FACTS,
        recent_limit: int = SESSION_KEEP,
    ) -> dict[str, Any]:
        facts = self.sql.list_memory_items(user_id, limit=max_facts)
        recent = self.get_recent_messages(conversation_id, user_id, limit=recent_limit)

        lines: list[str] = []
        if facts:
            lines.append("长期记忆：")
            lines.extend(f"- {fact['text']}" for fact in facts)
        if recent:
            lines.append("近期对话：")
            for message in recent:
                role = "用户" if message["role"] == "user" else "助手"
                content = str(message.get("content", ""))[:300]
                lines.append(f"{role}：{content}")

        context_text = "\n".join(lines)
        while context_text and _estimate_tokens(context_text) > max_tokens and len(lines) > 1:
            lines.pop()
            context_text = "\n".join(lines)
        return {
            "context": context_text,
            "facts": facts,
            "recent_messages": len(recent),
            "token_estimate": _estimate_tokens(context_text),
            "budget": max_tokens,
            "strategy": "Redis 会话缓存 + SQL 原始记录 + LLM 结构化记忆库",
        }

    def list_facts(self, user_id: str = "default", limit: int = 200) -> list[dict[str, Any]]:
        return self.sql.list_memory_items(user_id, limit=limit)

    def forget_fact(self, item_id: str, user_id: str = "default") -> bool:
        return self.sql.delete_memory_item(item_id, user_id)

    def distill(
        self,
        *,
        conversation_id: str,
        user_id: str,
        user_message_id: str | None,
        user_content: str,
        assistant_content: str,
    ) -> None:
        if not user_content.strip():
            return
        job_id = self.sql.create_distill_job(
            conversation_id=conversation_id,
            user_id=user_id,
            source_message_id=user_message_id,
        )
        self._process_distill_job(
            job_id=job_id,
            conversation_id=conversation_id,
            user_id=user_id,
            user_message_id=user_message_id,
            user_content=user_content,
            assistant_content=assistant_content,
        )

    def _process_distill_job(
        self,
        *,
        job_id: str,
        conversation_id: str,
        user_id: str,
        user_message_id: str | None,
        user_content: str,
        assistant_content: str,
    ) -> None:
        job = self.sql.get_distill_job(job_id)
        attempts = int(job.get("attempts", 0)) if job else 0
        last_error: Exception | None = None
        while attempts < 2:
            attempts += 1
            try:
                facts = self.distiller.extract(user_content, assistant_content)
                for fact in facts:
                    self.sql.upsert_memory_item(
                        user_id=user_id,
                        source_conversation_id=conversation_id,
                        source_message_id=user_message_id,
                        text=fact["text"],
                        category=fact["category"],
                        importance=fact["importance"],
                    )
                self.sql.trim_memory_items(user_id, MEMORY_MAX_ITEMS_PER_USER)
                self.sql.mark_distill_job(
                    job_id,
                    status="done",
                    result=facts,
                    attempts=attempts,
                )
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "memory distillation attempt %s failed for job %s: %s",
                    attempts,
                    job_id,
                    exc,
                )
        self.sql.mark_distill_job(
            job_id,
            status="failed",
            error=str(last_error),
            attempts=attempts,
        )

    def retry_distill_jobs(self, limit: int = 20) -> int:
        retried = 0
        for job in self.sql.list_distill_jobs_for_retry(limit):
            user_message = (
                self.sql.get_message(job["source_message_id"], job["user_id"])
                if job.get("source_message_id")
                else None
            )
            if not user_message:
                self.sql.mark_distill_job(
                    job["id"],
                    status="failed",
                    error="source message not found",
                    attempts=job["attempts"],
                )
                continue
            messages = self.sql.get_messages(job["conversation_id"], job["user_id"])
            assistant_content = ""
            found_user = False
            for message in messages:
                if str(message.get("id")) == job.get("source_message_id"):
                    found_user = True
                    continue
                if found_user and message.get("role") == "assistant":
                    assistant_content = message.get("content", "")
                    break
            self._process_distill_job(
                job_id=job["id"],
                conversation_id=job["conversation_id"],
                user_id=job["user_id"],
                user_message_id=job["source_message_id"],
                user_content=user_message["content"],
                assistant_content=assistant_content,
            )
            retried += 1
        return retried

    def list_distill_jobs(self, user_id: str = "default", limit: int = 50) -> list[dict[str, Any]]:
        return self.sql.list_distill_jobs(user_id, limit=limit)

    def close(self) -> None:
        self.sql.close()
