from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import (
    AGENT_LLM_TIMEOUT_SECONDS,
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_MODEL,
)

logger = logging.getLogger(__name__)


class FunctionCallingClient:
    """OpenAI-compatible chat client that can receive tool_calls."""

    def __init__(
        self,
        *,
        api_base: str = LLM_API_BASE,
        api_key: str = LLM_API_KEY,
        model: str = LLM_MODEL,
        timeout_seconds: float = AGENT_LLM_TIMEOUT_SECONDS,
    ) -> None:
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self.api_base and self.api_key)

    @property
    def _chat_url(self) -> str:
        base = self.api_base.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("LLM_API_BASE and LLM_API_KEY are required for function calling")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "tool_choice": tool_choice,
        }
        if tools:
            payload["tools"] = tools

        response = httpx.post(
            self._chat_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        return {
            "content": message.get("content"),
            "tool_calls": message.get("tool_calls") or [],
        }
