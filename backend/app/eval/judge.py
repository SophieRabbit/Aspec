from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL


def completeness_score(question: str, reply: str, expected_keywords: list[str]) -> float:
    if LLM_API_BASE and LLM_API_KEY:
        llm_score = _llm_judge(question, reply)
        if llm_score is not None:
            return llm_score
    return _heuristic_judge(reply, expected_keywords)


def _llm_judge(question: str, reply: str) -> float | None:
    prompt = (
        "你是建筑规范问答评测员。请判断回答是否完整回答了问题。"
        "只输出 JSON：{\"score\": 1-5, \"reason\": \"简短原因\"}。\n"
        f"问题：{question}\n回答：{reply}"
    )
    try:
        response = httpx.post(
            f"{LLM_API_BASE.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
            timeout=20,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        start = content.find("{")
        end = content.rfind("}") + 1
        parsed = json.loads(content[start:end])
        return max(1.0, min(5.0, float(parsed.get("score", 3.0))))
    except Exception:
        return None


def _heuristic_judge(reply: str, expected_keywords: list[str]) -> float:
    score = 2.0
    if len(reply or "") >= 50:
        score += 1.0
    if expected_keywords:
        coverage = sum(1 for keyword in expected_keywords if keyword in reply) / len(expected_keywords)
        if coverage >= 0.8:
            score += 1.0
        elif coverage >= 0.5:
            score += 0.5
    if "未找到" in reply or "暂未检索到" in reply:
        score = max(score, 3.0)
    return max(1.0, min(5.0, score))
