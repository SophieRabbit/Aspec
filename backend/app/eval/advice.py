from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL

DIMENSION_LABELS = {
    "retrieval": "检索未命中",
    "keyword": "关键词覆盖不足",
    "source": "出处错误",
    "completeness": "回答不完整",
    "user_feedback": "用户反馈",
}

HEURISTIC_ADVICE: dict[str, dict[str, list[str]]] = {
    "retrieval": {
        "root_causes": [
            "分块策略可能截断了跨页条文，导致关键词无法同时命中",
            "规范编号和建筑专业术语缺少同义词/别名扩展",
            "地域层级回退不足，市级/省级数据未命中时没有正确退回大区或国家",
        ],
        "suggestions": [
            "将 chunk_size 从 500 调整到 300，并在分块时保留条文编号与页码",
            "增加同义词表：日照=采光、踏步=楼梯、耐火等级=防火等级等",
            "检查地域过滤：国家→大区→省→地级市→区县逐级回退",
        ],
    },
    "keyword": {
        "root_causes": [
            "答案模板可能只引用部分条文，未覆盖期望关键词",
            "召回数量不足或来源排序靠后的条文没有进入回答",
            "清洗/停用词策略可能误删了专业术语",
        ],
        "suggestions": [
            "回答生成时强制引用检索到的条文原文片段",
            "提高 RETRIEVAL_TOP_K 或对来源按地域+相关度加权",
            "复查 STOP_TOKENS，避免误删“民用”“日照”等核心词",
        ],
    },
    "source": {
        "root_causes": [
            "PDF 提取的页码/章节元数据缺失或不一致",
            "分块时未保留条文编号和页码信息",
            "扫描件/低质量 PDF 的文本与版面错位",
        ],
        "suggestions": [
            "导入时校验并补齐 chapter/article/page 字段",
            "对质检报告标记的低质量文档执行 PyMuPDF 重提取或 OCR",
            "在展示时增加页码校验，防止引用错位",
        ],
    },
    "completeness": {
        "root_causes": [
            "检索结果数量或相关度不足，回答缺失关键维度",
            "多轮追问没有继承上一轮的主题词和地域",
            "未命中时没有明确说明并补充联网参考",
        ],
        "suggestions": [
            "提高 top_k，并按“地域优先级+相关度”排序",
            "多轮对话合并上一问主题、地域和关键词后再检索",
            "无本地结果时明确提示，并展示国家/大区规范或联网参考",
        ],
    },
    "user_feedback": {
        "root_causes": [
            "用户认为答案不准确、不完整或答非所问",
            "用户备注中可能包含具体遗漏内容",
        ],
        "suggestions": [
            "人工复核用户备注，并把问题自动纳入下一轮评测集",
            "对同类反馈聚类，优先修复出现频率最高的维度",
        ],
    },
}


def generate_advice(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bad_cases = [result for result in results if result.get("is_bad_case")]
    if not bad_cases:
        return []

    groups: dict[str, list[dict[str, Any]]] = {}
    for result in bad_cases:
        for dimension in result.get("failed_dimensions", []) or ["completeness"]:
            groups.setdefault(dimension, []).append(result)

    if LLM_API_BASE and LLM_API_KEY:
        llm_advice = _llm_advice(groups)
        if llm_advice:
            return llm_advice

    return [
        {
            "dimension": dimension,
            "label": DIMENSION_LABELS.get(dimension, dimension),
            "count": len(cases),
            "examples": [case.get("question", "") for case in cases[:3]],
            **HEURISTIC_ADVICE.get(dimension, HEURISTIC_ADVICE["completeness"]),
        }
        for dimension, cases in groups.items()
    ]


def _llm_advice(groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]] | None:
    prompt_lines = ["请对以下建筑规范问答评测的 Bad Case 做根因分析，并给出具体可执行的优化建议。"]
    prompt_lines.append("只输出 JSON：{\"advice\":[{\"dimension\":\"...\",\"label\":\"...\",\"root_causes\":[],\"suggestions\":[]}]}")
    for dimension, cases in groups.items():
        prompt_lines.append(
            f"- {DIMENSION_LABELS.get(dimension, dimension)} ({len(cases)} 条)："
            + "；".join(case.get("question", "") for case in cases[:5])
        )
    try:
        response = httpx.post(
            f"{LLM_API_BASE.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": "\n".join(prompt_lines)}],
                "temperature": 0,
            },
            timeout=30,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        start = content.find("{")
        end = content.rfind("}") + 1
        parsed = json.loads(content[start:end])
        return parsed.get("advice", [])
    except Exception:
        return None
