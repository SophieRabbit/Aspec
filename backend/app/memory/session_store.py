from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    import redis as redis_lib
except ImportError:  # pragma: no cover - redis is optional for local development
    redis_lib = None  # type: ignore[assignment]


class RedisSessionStore:
    """Redis-backed hot cache for the current conversation window."""

    def __init__(self, redis_url: str, ttl_seconds: int, keep: int) -> None:
        if redis_lib is None:
            raise RuntimeError("redis package is not installed")
        self.client = redis_lib.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        self.client.ping()
        self.ttl_seconds = ttl_seconds
        self.keep = keep

    def _key(self, user_id: str, conversation_id: str) -> str:
        return f"memory:session:{user_id}:{conversation_id}"

    def _call(self, operation: Any, default: Any = None) -> Any:
        try:
            return operation()
        except Exception as exc:  # Redis can be temporarily unavailable; SQL is authoritative.
            logger.warning("redis session operation failed: %s", exc)
            return default

    def get_recent_messages(
        self,
        conversation_id: str,
        user_id: str = "default",
    ) -> list[dict[str, Any]] | None:
        raw = self._call(lambda: self.client.get(self._key(user_id, conversation_id)))
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            messages = payload.get("recent_messages", [])
            return messages[-self.keep :] if self.keep else messages
        except (json.JSONDecodeError, TypeError):
            self._call(lambda: self.client.delete(self._key(user_id, conversation_id)))
            return None

    def set_recent_messages(
        self,
        conversation_id: str,
        user_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        payload = {"recent_messages": messages[-self.keep :] if self.keep else messages}
        self._call(
            lambda: self.client.setex(
                self._key(user_id, conversation_id),
                self.ttl_seconds,
                json.dumps(payload, ensure_ascii=False, default=str),
            )
        )

    def push_message(
        self,
        conversation_id: str,
        user_id: str,
        message: dict[str, Any],
    ) -> list[dict[str, Any]]:
        messages = self.get_recent_messages(conversation_id, user_id) or []
        messages.append(message)
        self.set_recent_messages(conversation_id, user_id, messages)
        return messages[-self.keep :] if self.keep else messages

    def delete(self, conversation_id: str, user_id: str = "default") -> bool:
        return bool(self._call(lambda: self.client.delete(self._key(user_id, conversation_id)), False))


class LocalSessionStore:
    """In-memory fallback used when Redis is not configured or unavailable."""

    def __init__(self, ttl_seconds: int, keep: int) -> None:
        self._data: dict[str, list[dict[str, Any]]] = {}
        self.ttl_seconds = ttl_seconds
        self.keep = keep

    def _key(self, user_id: str, conversation_id: str) -> str:
        return f"{user_id}:{conversation_id}"

    def get_recent_messages(
        self,
        conversation_id: str,
        user_id: str = "default",
    ) -> list[dict[str, Any]] | None:
        messages = self._data.get(self._key(user_id, conversation_id))
        if messages is None:
            return None
        return messages[-self.keep :] if self.keep else messages

    def set_recent_messages(
        self,
        conversation_id: str,
        user_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        self._data[self._key(user_id, conversation_id)] = (
            messages[-self.keep :] if self.keep else messages
        )

    def push_message(
        self,
        conversation_id: str,
        user_id: str,
        message: dict[str, Any],
    ) -> list[dict[str, Any]]:
        messages = self.get_recent_messages(conversation_id, user_id) or []
        messages.append(message)
        self.set_recent_messages(conversation_id, user_id, messages)
        return messages[-self.keep :] if self.keep else messages

    def delete(self, conversation_id: str, user_id: str = "default") -> bool:
        return self._data.pop(self._key(user_id, conversation_id), None) is not None


def create_session_store(
    redis_url: str,
    ttl_seconds: int,
    keep: int,
) -> RedisSessionStore | LocalSessionStore:
    if not redis_url:
        logger.info("REDIS_URL not configured; using in-memory local session store")
        return LocalSessionStore(ttl_seconds, keep)
    try:
        store = RedisSessionStore(redis_url, ttl_seconds, keep)
        logger.info("Redis session store ready")
        return store
    except Exception as exc:
        logger.warning("Redis unavailable, falling back to local session store: %s", exc)
        return LocalSessionStore(ttl_seconds, keep)
