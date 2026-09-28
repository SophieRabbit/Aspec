from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping)


class SqlMemoryStore:
    """SQL storage for raw conversations and the structured memory library."""

    def __init__(self, database_url: str, echo: bool = False) -> None:
        self.database_url = database_url
        connect_args: dict[str, Any] = {}
        pool_kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            if database_url == "sqlite:///:memory:":
                pool_kwargs["poolclass"] = StaticPool
        self.engine = create_engine(
            database_url,
            echo=echo,
            connect_args=connect_args,
            **pool_kwargs,
        )
        self.metadata = MetaData()
        self.conversations = Table(
            "conversations",
            self.metadata,
            Column("conversation_id", String(64), primary_key=True),
            Column("user_id", String(128), primary_key=True),
            Column("title", String(128), nullable=False),
            Column("created_at", String(40), nullable=False),
            Column("updated_at", String(40), nullable=False),
            Column("message_count", Integer, nullable=False, default=0),
            Column("deleted_at", String(40), nullable=True),
        )
        self.messages = Table(
            "messages",
            self.metadata,
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("conversation_id", String(64), nullable=False),
            Column("user_id", String(128), nullable=False),
            Column("role", String(16), nullable=False),
            Column("content", Text, nullable=False),
            Column("trace_id", String(64), nullable=False, default=""),
            Column("metadata_json", Text, nullable=False, default="{}"),
            Column("created_at", String(40), nullable=False),
            Index("ix_messages_conversation", "conversation_id", "created_at"),
            Index("ix_messages_user", "user_id", "created_at"),
        )
        self.memory_items = Table(
            "memory_items",
            self.metadata,
            Column("id", String(32), primary_key=True),
            Column("user_id", String(128), nullable=False),
            Column("source_conversation_id", String(64), nullable=False),
            Column("source_message_id", String(32), nullable=True),
            Column("text", Text, nullable=False),
            Column("normalized_text", Text, nullable=False),
            Column("category", String(32), nullable=False),
            Column("importance", Integer, nullable=False),
            Column("occurrences", Integer, nullable=False, default=1),
            Column("status", String(16), nullable=False, default="active"),
            Column("created_at", String(40), nullable=False),
            Column("last_seen_at", String(40), nullable=False),
            UniqueConstraint("user_id", "normalized_text", name="uq_memory_user_text"),
            Index("ix_memory_user_score", "user_id", "status", "importance"),
        )
        self.memory_jobs = Table(
            "memory_jobs",
            self.metadata,
            Column("id", String(32), primary_key=True),
            Column("conversation_id", String(64), nullable=False),
            Column("user_id", String(128), nullable=False),
            Column("source_message_id", String(32), nullable=True),
            Column("status", String(16), nullable=False, default="pending"),
            Column("attempts", Integer, nullable=False, default=0),
            Column("result_json", Text, nullable=True),
            Column("error", Text, nullable=True),
            Column("created_at", String(40), nullable=False),
            Column("updated_at", String(40), nullable=False),
            Index("ix_memory_jobs_user_status", "user_id", "status", "created_at"),
        )
        self.init_schema()

    def init_schema(self) -> None:
        self.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    def import_json_files(self, directory: Path, user_id: str = "default") -> int:
        if not directory.exists():
            return 0
        imported = 0
        for path in sorted(directory.glob("*.json")):
            try:
                with path.open(encoding="utf-8") as handle:
                    data = json.load(handle)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("skip malformed memory json %s: %s", path, exc)
                continue
            conversation_id = str(data.get("conversation_id", path.stem))
            if self.exists(conversation_id, user_id):
                continue
            self.create_conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                title=str(data.get("title", "新对话"))[:128],
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
                message_count=int(data.get("message_count", 0)),
            )
            for message in data.get("messages", []):
                metadata = {
                    key: value
                    for key, value in message.items()
                    if key not in {"id", "role", "content", "created_at", "conversation_id"}
                }
                self.add_message(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role=str(message.get("role", "")),
                    content=str(message.get("content", "")),
                    metadata=metadata,
                    created_at=message.get("created_at"),
                    update_count=False,
                )
            for fact in data.get("facts", []):
                self.upsert_memory_item(
                    user_id=user_id,
                    source_conversation_id=conversation_id,
                    source_message_id=None,
                    text=str(fact.get("text", "")),
                    category=str(fact.get("category", "项目信息")),
                    importance=int(fact.get("importance", 2)),
                )
            imported += 1
        if imported:
            logger.info("imported %s legacy json conversations for user %s", imported, user_id)
        return imported

    def create_conversation(
        self,
        *,
        conversation_id: str | None = None,
        user_id: str = "default",
        title: str = "新对话",
        created_at: str | None = None,
        updated_at: str | None = None,
        message_count: int = 0,
    ) -> dict[str, Any]:
        conversation_id = conversation_id or uuid.uuid4().hex[:12]
        timestamp = _now()
        values = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "title": title[:128],
            "created_at": created_at or timestamp,
            "updated_at": updated_at or timestamp,
            "message_count": message_count,
            "deleted_at": None,
        }
        with self.engine.begin() as connection:
            connection.execute(self.conversations.insert().values(**values))
        return values

    def exists(self, conversation_id: str, user_id: str = "default") -> bool:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(self.conversations.c.conversation_id).where(
                    self.conversations.c.conversation_id == conversation_id,
                    self.conversations.c.user_id == user_id,
                    self.conversations.c.deleted_at.is_(None),
                )
            ).first()
        return row is not None

    def list_conversations(self, user_id: str = "default") -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(self.conversations)
                .where(
                    self.conversations.c.user_id == user_id,
                    self.conversations.c.deleted_at.is_(None),
                )
                .order_by(self.conversations.c.updated_at.desc())
            ).fetchall()
        return [_row_dict(row) for row in rows]

    def get_conversation(self, conversation_id: str, user_id: str = "default") -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(self.conversations).where(
                    self.conversations.c.conversation_id == conversation_id,
                    self.conversations.c.user_id == user_id,
                    self.conversations.c.deleted_at.is_(None),
                )
            ).first()
        return _row_dict(row) if row else None

    def delete_conversation(self, conversation_id: str, user_id: str = "default") -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(
                self.conversations.update()
                .where(
                    self.conversations.c.conversation_id == conversation_id,
                    self.conversations.c.user_id == user_id,
                    self.conversations.c.deleted_at.is_(None),
                )
                .values(deleted_at=_now(), updated_at=_now())
            )
            connection.execute(
                self.messages.delete().where(
                    self.messages.c.conversation_id == conversation_id,
                    self.messages.c.user_id == user_id,
                )
            )
        return result.rowcount > 0

    def add_message(
        self,
        *,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        trace_id: str = "",
        created_at: str | None = None,
        update_count: bool = True,
    ) -> dict[str, Any]:
        timestamp = created_at or _now()
        values = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": role,
            "content": content[:4000],
            "trace_id": trace_id[:64],
            "metadata_json": json.dumps(metadata or {}, ensure_ascii=False, default=str),
            "created_at": timestamp,
        }
        with self.engine.begin() as connection:
            result = connection.execute(self.messages.insert().values(**values))
            message_id = result.inserted_primary_key[0]
            if update_count:
                conversation = connection.execute(
                    select(self.conversations).where(
                        self.conversations.c.conversation_id == conversation_id,
                        self.conversations.c.user_id == user_id,
                    )
                ).first()
                if conversation:
                    conversation = _row_dict(conversation)
                    title = conversation["title"]
                    if role == "user" and title in ("新对话", ""):
                        title = content.strip()[:24] or title
                    connection.execute(
                        self.conversations.update()
                        .where(
                            self.conversations.c.conversation_id == conversation_id,
                            self.conversations.c.user_id == user_id,
                        )
                        .values(
                            title=title,
                            message_count=self.conversations.c.message_count + 1,
                            updated_at=_now(),
                        )
                    )
        return {
            "id": str(message_id),
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "trace_id": trace_id,
            "created_at": timestamp,
        }

    def get_messages(self, conversation_id: str, user_id: str = "default") -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(self.messages)
                .where(
                    self.messages.c.conversation_id == conversation_id,
                    self.messages.c.user_id == user_id,
                )
                .order_by(self.messages.c.id.asc())
            ).fetchall()
        messages: list[dict[str, Any]] = []
        for row in rows:
            row = _row_dict(row)
            item = {
                "id": row["id"],
                "conversation_id": row["conversation_id"],
                "role": row["role"],
                "content": row["content"],
                "trace_id": row["trace_id"],
                "created_at": row["created_at"],
            }
            metadata = json.loads(row["metadata_json"] or "{}")
            item.update(metadata)
            messages.append(item)
        return messages

    def get_message(self, message_id: str, user_id: str = "default") -> dict[str, Any] | None:
        try:
            numeric_id = int(message_id)
        except (TypeError, ValueError):
            return None
        with self.engine.connect() as connection:
            row = connection.execute(
                select(self.messages).where(
                    self.messages.c.id == numeric_id,
                    self.messages.c.user_id == user_id,
                )
            ).first()
        if not row:
            return None
        row = _row_dict(row)
        item = {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "role": row["role"],
            "content": row["content"],
            "trace_id": row["trace_id"],
            "created_at": row["created_at"],
        }
        metadata = json.loads(row["metadata_json"] or "{}")
        item.update(metadata)
        return item

    def upsert_memory_item(
        self,
        *,
        user_id: str,
        source_conversation_id: str,
        source_message_id: str | None,
        text: str,
        category: str,
        importance: int,
    ) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("memory item text cannot be empty")
        normalized = _normalize_text(text)
        timestamp = _now()
        importance = max(1, min(5, importance))
        with self.engine.begin() as connection:
            row = connection.execute(
                select(self.memory_items).where(
                    self.memory_items.c.user_id == user_id,
                    self.memory_items.c.normalized_text == normalized,
                )
            ).first()
            if row:
                existing = _row_dict(row)
                connection.execute(
                    self.memory_items.update()
                    .where(self.memory_items.c.id == existing["id"])
                    .values(
                        text=text,
                        category=category,
                        importance=min(5, max(existing["importance"] + 1, importance)),
                        occurrences=existing["occurrences"] + 1,
                        status="active",
                        source_conversation_id=source_conversation_id,
                        source_message_id=source_message_id,
                        last_seen_at=timestamp,
                    )
                )
                item = {**existing, "importance": min(5, max(existing["importance"] + 1, importance))}
                item["occurrences"] = existing["occurrences"] + 1
                item["last_seen_at"] = timestamp
                return item
            item = {
                "id": uuid.uuid4().hex[:12],
                "user_id": user_id,
                "source_conversation_id": source_conversation_id,
                "source_message_id": source_message_id,
                "text": text,
                "normalized_text": normalized,
                "category": category,
                "importance": importance,
                "occurrences": 1,
                "status": "active",
                "created_at": timestamp,
                "last_seen_at": timestamp,
            }
            connection.execute(self.memory_items.insert().values(**item))
            return item

    def list_memory_items(
        self,
        user_id: str = "default",
        *,
        category: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        statement = select(self.memory_items).where(
            self.memory_items.c.user_id == user_id,
            self.memory_items.c.status == "active",
        )
        if category:
            statement = statement.where(self.memory_items.c.category == category)
        statement = statement.order_by(
            (self.memory_items.c.importance * (self.memory_items.c.occurrences + 1)).desc(),
            self.memory_items.c.last_seen_at.desc(),
        ).limit(limit)
        with self.engine.connect() as connection:
            rows = connection.execute(statement).fetchall()
        return [_row_dict(row) for row in rows]

    def delete_memory_item(self, item_id: str, user_id: str = "default") -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(
                self.memory_items.update()
                .where(
                    self.memory_items.c.id == item_id,
                    self.memory_items.c.user_id == user_id,
                )
                .values(status="archived", last_seen_at=_now())
            )
        return result.rowcount > 0

    def trim_memory_items(self, user_id: str, max_items: int) -> None:
        if max_items <= 0:
            return
        with self.engine.begin() as connection:
            rows = connection.execute(
                select(self.memory_items)
                .where(
                    self.memory_items.c.user_id == user_id,
                    self.memory_items.c.status == "active",
                )
                .order_by(
                    (self.memory_items.c.importance * (self.memory_items.c.occurrences + 1)).desc(),
                    self.memory_items.c.last_seen_at.desc(),
                )
            ).fetchall()
            for row in rows[max_items:]:
                connection.execute(
                    self.memory_items.update()
                    .where(self.memory_items.c.id == _row_dict(row)["id"])
                    .values(status="archived", last_seen_at=_now())
                )

    def create_distill_job(
        self,
        *,
        conversation_id: str,
        user_id: str,
        source_message_id: str | None,
    ) -> str:
        job_id = uuid.uuid4().hex[:12]
        timestamp = _now()
        with self.engine.begin() as connection:
            connection.execute(
                self.memory_jobs.insert().values(
                    id=job_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    source_message_id=source_message_id,
                    status="pending",
                    attempts=0,
                    result_json=None,
                    error=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
        return job_id

    def mark_distill_job(
        self,
        job_id: str,
        *,
        status: str,
        result: list[dict[str, Any]] | None = None,
        error: str | None = None,
        attempts: int | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": status,
            "error": error,
            "updated_at": _now(),
        }
        if result is not None:
            values["result_json"] = json.dumps(result, ensure_ascii=False, default=str)
        if attempts is not None:
            values["attempts"] = attempts
        with self.engine.begin() as connection:
            connection.execute(
                self.memory_jobs.update().where(self.memory_jobs.c.id == job_id).values(**values)
            )

    def get_distill_job(self, job_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(self.memory_jobs).where(self.memory_jobs.c.id == job_id)
            ).first()
        return _row_dict(row) if row else None

    def list_distill_jobs(self, user_id: str = "default", limit: int = 50) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(self.memory_jobs)
                .where(self.memory_jobs.c.user_id == user_id)
                .order_by(self.memory_jobs.c.created_at.desc())
                .limit(limit)
            ).fetchall()
        return [_row_dict(row) for row in rows]

    def list_distill_jobs_for_retry(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(self.memory_jobs)
                .where(
                    self.memory_jobs.c.status.in_(("pending", "failed")),
                    self.memory_jobs.c.attempts < 2,
                )
                .order_by(self.memory_jobs.c.created_at.asc())
                .limit(limit)
            ).fetchall()
        return [_row_dict(row) for row in rows]
