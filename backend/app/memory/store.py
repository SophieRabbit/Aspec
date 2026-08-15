from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import MEMORY_TOKEN_BUDGET, SHORT_TERM_KEEP


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _estimate_tokens(text: str) -> int:
    chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    other_chars = len(text) - chinese_chars
    return chinese_chars + int(other_chars / 3) + 1


class MemoryStore:
    """Stores short-term conversation history and extracted long-term facts."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, conversation_id: str) -> Path:
        safe_id = re.sub(r"[^0-9a-zA-Z_-]", "", conversation_id)
        return self.directory / f"{safe_id}.json"

    def _load(self, conversation_id: str) -> dict[str, Any]:
        path = self._path(conversation_id)
        if not path.exists():
            return {
                "conversation_id": conversation_id,
                "title": "新对话",
                "created_at": _now(),
                "updated_at": _now(),
                "message_count": 0,
                "messages": [],
                "facts": [],
            }
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _save(self, conversation: dict[str, Any]) -> None:
        conversation["updated_at"] = _now()
        with self._path(conversation["conversation_id"]).open("w", encoding="utf-8") as handle:
            json.dump(conversation, handle, ensure_ascii=False, indent=2)

    def exists(self, conversation_id: str) -> bool:
        return self._path(conversation_id).exists()

    def create_conversation(self, title: str = "新对话") -> dict[str, Any]:
        conversation_id = uuid.uuid4().hex[:12]
        conversation = {
            "conversation_id": conversation_id,
            "title": title,
            "created_at": _now(),
            "updated_at": _now(),
            "message_count": 0,
            "messages": [],
            "facts": [],
        }
        self._save(conversation)
        return conversation

    def delete_conversation(self, conversation_id: str) -> bool:
        path = self._path(conversation_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_conversations(self) -> list[dict[str, Any]]:
        conversations: list[dict[str, Any]] = []
        for path in self.directory.glob("*.json"):
            with path.open(encoding="utf-8") as handle:
                conversations.append(json.load(handle))
        conversations.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return conversations

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return self._load(conversation_id).get("messages", [])

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conversation = self._load(conversation_id)
        conversation["message_count"] += 1
        if role == "user" and conversation["title"] == "新对话":
            conversation["title"] = content.strip()[:24]
        message = {
            "role": role,
            "content": content[:2000],
            "created_at": _now(),
        }
        if metadata:
            message.update(metadata)
        conversation["messages"].append(message)
        if role == "user":
            facts = self._extract_facts(content)
            for fact in facts:
                self._upsert_fact(conversation, fact)
        self._save(conversation)

    @staticmethod
    def _extract_facts(text: str) -> list[dict[str, Any]]:
        patterns = [
            r"(项目(?:名称|类型|地点|地区|位置|性质|用途|规模))[:：\s]*([^，。；\n]{1,40})",
            r"(建筑面积|套内面积|建筑高度|总高度|层高|层数|耐火等级|建筑类别|防火分区面积)[:：]?\s*([^，。；\n]{1,40})",
            r"((?:本项目|这个项目|该建筑|住宅|办公楼|医院|学校|厂房|商业建筑)[^，。；\n]{0,34})",
        ]
        facts: list[dict[str, Any]] = []
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                label = match.group(1)
                value = match.group(2) if match.lastindex and match.lastindex >= 2 else label
                fact_text = f"{label}：{value}" if value != label else label
                if len(fact_text) < 6:
                    continue
                facts.append(
                    {
                        "text": fact_text,
                        "category": "项目信息",
                        "importance": 2,
                    }
                )
        return facts

    @staticmethod
    def _upsert_fact(conversation: dict[str, Any], new_fact: dict[str, Any]) -> None:
        normalized = re.sub(r"\s+", "", new_fact["text"])
        for fact in conversation["facts"]:
            if re.sub(r"\s+", "", fact["text"]) == normalized:
                fact["occurrences"] += 1
                fact["importance"] = min(5, fact.get("importance", 2) + 1)
                fact["last_seen_at"] = _now()
                return
        conversation["facts"].append(
            {
                "text": new_fact["text"],
                "category": new_fact["category"],
                "importance": new_fact["importance"],
                "occurrences": 1,
                "created_at": _now(),
                "last_seen_at": _now(),
            }
        )

    def build_context(self, conversation_id: str, max_tokens: int = MEMORY_TOKEN_BUDGET) -> dict[str, Any]:
        conversation = self._load(conversation_id)
        facts = conversation.get("facts", [])
        ranked_facts = sorted(
            facts,
            key=lambda item: item.get("importance", 1) * (1 + min(5, item.get("occurrences", 1))),
            reverse=True,
        )[:8]

        lines: list[str] = []
        if ranked_facts:
            lines.append("长期记忆：")
            lines.extend(f"- {fact['text']}" for fact in ranked_facts)

        recent = conversation.get("messages", [])[-SHORT_TERM_KEEP:]
        if recent:
            lines.append("近期对话：")
            for message in recent:
                role = "用户" if message["role"] == "user" else "助手"
                content = message["content"][:300]
                lines.append(f"{role}：{content}")

        context_text = "\n".join(lines)
        while context_text and _estimate_tokens(context_text) > max_tokens and len(lines) > 1:
            lines.pop()
            context_text = "\n".join(lines)
        return {
            "context": context_text,
            "facts": ranked_facts,
            "recent_messages": len(recent),
            "token_estimate": _estimate_tokens(context_text),
            "budget": max_tokens,
            "strategy": "长期记忆抽取 + 近期对话窗口 + Token 预算裁剪",
        }
