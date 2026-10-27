from __future__ import annotations

import html
import json
import logging
import re
import time
from typing import Any

from ..config import (
    AGENT_FUNCTION_CALLING_ENABLED,
    AGENT_MAX_TOOL_TURNS,
    AGENT_TOOL_RESULT_CHARS,
    RETRIEVAL_TOP_K,
    STANDARD_STATUS_PATH,
)
from ..knowledge.keywords import extract_keywords
from ..knowledge.mainland_scope import (
    detect_outside_mainland_place,
    outside_mainland_result,
)
from ..knowledge.retriever import (
    REQUIRED_DOMAIN_TERMS,
    Retriever,
    _has_nearby_terms,
    tokenize,
)
from ..knowledge.region_hierarchy import (
    COMPARISON_TERMS,
    KNOWN_HIERARCHY,
    REGION_ALIASES,
    build_region_notice,
    build_region_path,
    detect_requested_region,
    extract_regions,
)
from ..knowledge.text_cleaner import normalize_ocr_paragraphs
from ..knowledge.web_search import web_note, web_search
from .intent_router import (
    INTENT_COMPARISON,
    INTENT_FALLBACK,
    INTENT_NUMERIC,
    IntentRouter,
)
from .llm import FunctionCallingClient
from .tool_specs import TOOL_DEFINITIONS, TOOL_LABELS
from .tools import (
    calculate_tool,
    compare_regional_tool,
    compare_tool,
    normalize_comparison_query,
    retrieve_tool,
)
from services.compound_intent import detect_compound_intent
from services.local_dependency import detect_local_dependency
from services.synonym_expander import expand_query_details

REFERENCE_TERMS = (
    "这条",
    "该规定",
    "上述",
    "这个",
    "这项",
    "这里",
    "上面",
    "之前",
    "前述",
    "此条",
    "它",
)

PROJECT_CONTEXT_TERMS = (
    "本项目",
    "这个项目",
    "该项目",
    "当前项目",
    "项目背景",
    "项目信息",
    "我们项目",
    "我们的项目",
    "这个建筑",
    "该建筑",
    "本建筑",
)

STRICTER_TERMS = ("更严格", "严格", "地方标准", "省级", "省内")

_CLAUSE_NUMBER_RE = re.compile(
    r"(?<![0-9.])(?<![\u4e00-\u9fff])(?<!表\s)(?<!第\s)(?<!图\s)"
    r"(\d{1,2}(?:\.\d{1,2}){1,2})"
    r"(?!\s*[（(])"
    r"(?=\s*[\u4e00-\u9fff])"
)

_ENTRY_START_RE = re.compile(
    r"(?<![0-9.])(?<![\u4e00-\u9fff])"
    r"(?:\d{1,2}(?:\.\d{1,2}){1,2}"
    r"|\d+\s*[)）]|[(（]\s*\d+\s*[)）])"
    r"(?=\s*[\u4e00-\u9fff（(])"
)

_CLAUSE_REFERENCE_START_RE = re.compile(
    r"(?<=[。；;])[ \t]*"
    r"(\d{1,2}(?:\.\d{1,2}){1,3})"
    r"(?=[、,，])"
)

logger = logging.getLogger(__name__)
CHAT_SOURCE_LIMIT = min(6, RETRIEVAL_TOP_K)

NOISE_LINE_MARKERS = (
    "文档来源于网络",
    "全咨之家",
    "标准分享网",
    "免费下载",
)


class Planner:
    """Plans tool calls, executes them, and composes a traceable answer."""

    def __init__(
        self,
        retriever: Retriever,
        llm_client: FunctionCallingClient | None = None,
    ) -> None:
        self.retriever = retriever
        self.llm_client = llm_client or FunctionCallingClient()
        self.retriever.llm_client = self.llm_client
        self.intent_router = IntentRouter(llm_client=self.llm_client)
        self.standard_status = self._load_standard_status()

    def plan(self, query: str) -> list[tuple[str, str, str]]:
        intent = self.intent_router.classify(query, use_llm=False)
        if intent.intent == INTENT_COMPARISON:
            return [
                ("compare", "横向对比", "识别问题涉及的多本规范并进行条文对比"),
                ("retrieve", "条文检索", "检索对比涉及的具体规范条文"),
            ]
        if intent.intent == INTENT_NUMERIC or any(
            word in query for word in ("计算", "算一下")
        ) or re.search(r"[0-9]+[+\-*/()%]", query):
            return [
                ("retrieve", "条文检索", "先定位问题对应的规范条文"),
                ("calculate", "数值计算", "对条文中的数值关系进行计算校验"),
            ]
        if intent.intent == INTENT_FALLBACK:
            return []
        return [("retrieve", "条文检索", "从预构建知识库中检索最相关的规范条文")]

    def run(
        self,
        query: str,
        previous_query: str | None = None,
        memory_facts: list[dict[str, Any]] | None = None,
        enable_web_search: bool = False,
        enable_function_calling: bool = AGENT_FUNCTION_CALLING_ENABLED,
    ) -> dict[str, Any]:
        outside_place = detect_outside_mainland_place(query)
        if outside_place:
            return outside_mainland_result(query, outside_place)
        if enable_function_calling and self.llm_client.enabled:
            try:
                result = self._run_function_calling(
                    query,
                    previous_query=previous_query,
                    memory_facts=memory_facts,
                    enable_web_search=enable_web_search,
                )
            except Exception as exc:
                logger.warning("function calling failed, falling back to rule planner: %s", exc)
            else:
                return self._with_local_dependency_notice(result, query)
        result = self._run_rule_based(
            query,
            previous_query=previous_query,
            memory_facts=memory_facts,
            enable_web_search=enable_web_search,
        )
        return self._with_local_dependency_notice(result, query)

    def _with_local_dependency_notice(
        self,
        result: dict[str, Any],
        query: str,
    ) -> dict[str, Any]:
        dependency = detect_local_dependency(query)
        if dependency is None:
            return result

        reply = str(result.get("reply", "")).strip()
        if self._has_local_dependency_notice(reply):
            return result

        requested_region = result.get("requested_region")
        if requested_region:
            if self._has_regional_source(requested_region):
                return result
            place = (
                requested_region.get("place")
                or requested_region.get("city")
                or requested_region.get("province")
                or "项目所在地"
            )
            notice_text = (
                f"💡 {place}地方规范暂未收录，"
                f"建议查阅{place}住建局官网确认当地审图要求。"
                "上述国标内容仅供参考。"
            )
            notice = f"**__{notice_text}__**"
        else:
            notice_text = (
                "💡 该问题需结合地方规范："
                f"{dependency.get('prompt') or '各地规定差异较大，建议查阅项目所在地住建局或规划部门官网。'}"
            )
            notice = f"**__{notice_text}__**"

        result["reply"] = f"{reply}\n\n{notice}" if reply else notice
        result["local_dependency"] = dependency
        return result

    def _has_regional_source(self, requested_region: dict[str, Any]) -> bool:
        preferred = {
            str(requested_region.get(key, "")).strip()
            for key in ("place", "city", "district")
            if str(requested_region.get(key, "")).strip()
        }
        wanted = preferred or {
            str(requested_region.get(key, "")).strip()
            for key in ("province", "region")
            if str(requested_region.get(key, "")).strip()
        }
        if not wanted:
            return False
        return any(
            str(document.get("region", "")).strip() in wanted
            for document in self.retriever.knowledge_base.documents
        )

    @staticmethod
    def _has_local_dependency_notice(reply: str) -> bool:
        if "该问题需结合地方规范" in reply:
            return True
        if "上述国标内容仅供参考" in reply:
            return True
        return (
            "地方" in reply
            and "未收录" in reply
            and "建议查阅" in reply
        )

    def _run_rule_based(
        self,
        query: str,
        previous_query: str | None = None,
        memory_facts: list[dict[str, Any]] | None = None,
        enable_web_search: bool = False,
    ) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        calculation: dict[str, Any] | None = None
        comparison: dict[str, Any] | None = None
        requested_region = detect_requested_region(query, self.retriever.knowledge_base.documents)
        memory_hint = self._memory_hint(memory_facts)
        uses_memory = self._uses_memory(query, memory_hint)
        if not uses_memory:
            memory_hint = ""
        inherited_region = (
            requested_region is None
            and bool(previous_query)
            and any(term in query for term in REFERENCE_TERMS)
        )
        if inherited_region and previous_query:
            requested_region = detect_requested_region(
                previous_query,
                self.retriever.knowledge_base.documents,
            )
        effective_query = query
        if previous_query and (inherited_region or any(term in query for term in REFERENCE_TERMS)):
            effective_query = f"{previous_query} {query}"
        if uses_memory:
            effective_query = f"{effective_query}，项目背景：{memory_hint}"
        constraint_query = self._constraint_query(query, previous_query)
        comparison_query = normalize_comparison_query(effective_query)

        regions = extract_regions(effective_query, self.retriever.knowledge_base.documents)
        if len(regions) >= 2 and any(term in effective_query for term in COMPARISON_TERMS):
            return self._run_regional_comparison(
                effective_query,
                regions,
                enable_web_search=enable_web_search,
            )

        stricter_followup = bool(previous_query) and any(term in query for term in STRICTER_TERMS) and (
            any(term in query for term in REFERENCE_TERMS)
            or "地方标准" in query
            or "省级" in query
            or "省内" in query
        )
        region_notice = build_region_notice(requested_region, self.retriever.knowledge_base.documents)
        region_path = [
            item
            for item in build_region_path(
                requested_region,
                self.retriever.knowledge_base.documents,
            )
            if item.get("available")
        ]
        web_results: list[dict[str, Any]] = []

        if stricter_followup:
            all_sources = retrieve_tool(
                effective_query,
                self.retriever,
                top_k=500,
                requested_region=requested_region,
            )
            local_sources = [source for source in all_sources if source.get("region") != "全国"]
            sources = local_sources
            if not local_sources and enable_web_search:
                web_results = web_search(self._build_web_query(effective_query, requested_region))
            reply = self._compose_stricter_answer(
                effective_query,
                requested_region,
                local_sources,
                web_results,
            )
            follow_ups = []
            return {
                "reply": reply,
                "sources": self._limit_sources(sources),
                "steps": [],
                "follow_ups": follow_ups,
                "calculation": None,
                "comparison": None,
                "region_path": region_path,
                "requested_region": requested_region,
                "web_results": web_results,
                "web_note": web_note(web_results),
                "effective_query": effective_query,
                "memory_used": uses_memory,
            }

        for tool, title, detail in self.plan(comparison_query):
            started = time.perf_counter()
            if tool == "retrieve":
                sources = retrieve_tool(
                    comparison_query,
                    self.retriever,
                    top_k=500,
                    requested_region=requested_region,
                )
                sources.sort(
                    key=lambda source: (
                        -source.get("retrieval_rank", 0),
                        source.get("region_priority", 0),
                        source.get("score", 0),
                        source.get("priority", 0),
                    ),
                    reverse=True,
                )
                detail = f"召回 {len(sources)} 条相关条文，按相关度排序"
                if requested_region:
                    detail = f"按区域范围【{requested_region['place']}】{detail}"
            elif tool == "calculate":
                calculation = calculate_tool(effective_query)
                detail = (
                    calculation.get("note", "")
                    if calculation.get("expression")
                    else "未检测到数值表达式，跳过计算"
                )
            elif tool == "compare":
                comparison = compare_tool(
                    comparison_query,
                    self.retriever,
                    requested_region=requested_region,
                )
                detail = f"对比 {len(comparison.get('standards', []))} 本规范：{'、'.join(comparison.get('standards', []))}"
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            steps.append(
                {
                    "tool": tool,
                    "title": title,
                    "detail": detail,
                    "duration_ms": elapsed_ms,
                }
            )

        if comparison and comparison.get("standards"):
            compared_standards = {
                str(standard).replace(" ", "")
                for standard in comparison["standards"]
                if str(standard).strip()
            }
            selected_sources = [
                source
                for source in sources
                if str(source.get("standard", "")).replace(" ", "")
                in compared_standards
            ]
            if selected_sources:
                sources = selected_sources

        if not sources and enable_web_search:
            web_results = web_search(self._build_web_query(effective_query, requested_region))
        elif (
            enable_web_search
            and requested_region
            and any(term in effective_query for term in REQUIRED_DOMAIN_TERMS)
        ):
            web_results = web_search(self._build_web_query(effective_query, requested_region))
        reply = self._compose_answer(
            effective_query,
            sources,
            calculation,
            comparison,
            region_notice,
            web_results,
            requested_region=requested_region,
        )
        reply = self._with_compound_intent_header(
            constraint_query,
            reply,
            requested_region=requested_region,
            llm_client=None,
        )
        follow_ups = self._suggest_follow_ups(effective_query, sources)
        return {
            "reply": reply,
            "sources": self._limit_sources(sources),
            "steps": steps,
            "follow_ups": follow_ups,
            "calculation": calculation,
            "comparison": comparison,
            "region_path": region_path,
            "requested_region": requested_region,
            "web_results": web_results,
            "web_note": web_note(web_results),
            "effective_query": effective_query,
            "memory_used": uses_memory,
        }

    def _run_function_calling(
        self,
        query: str,
        *,
        previous_query: str | None,
        memory_facts: list[dict[str, Any]] | None,
        enable_web_search: bool,
    ) -> dict[str, Any]:
        documents = self.retriever.knowledge_base.documents
        requested_region = detect_requested_region(query, documents)
        memory_hint = self._memory_hint(memory_facts)
        uses_memory = self._uses_memory(query, memory_hint)
        if not uses_memory:
            memory_hint = ""
        inherited_region = (
            requested_region is None
            and bool(previous_query)
            and any(term in query for term in REFERENCE_TERMS)
        )
        if inherited_region and previous_query:
            requested_region = detect_requested_region(
                previous_query,
                documents,
            )
        effective_query = query
        if previous_query and (inherited_region or any(term in query for term in REFERENCE_TERMS)):
            effective_query = f"{previous_query} {query}"
        if uses_memory:
            effective_query = f"{effective_query}，项目背景：{memory_hint}"
        constraint_query = self._constraint_query(query, previous_query)
        region_notice = build_region_notice(requested_region, documents)
        context_region_notice = self._visible_region_summary(requested_region, documents)
        context = self._build_agent_context(
            previous_query,
            memory_hint,
            requested_region,
            context_region_notice,
        )
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": f"{self._agent_system_prompt(enable_web_search)}\n\n{context}",
            },
            {"role": "user", "content": query},
        ]
        tools = [
            tool
            for tool in TOOL_DEFINITIONS
            if enable_web_search
            or tool.get("function", {}).get("name") != "web_search"
        ]
        steps: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        calculation: dict[str, Any] | None = None
        comparison: dict[str, Any] | None = None
        web_results: list[dict[str, Any]] = []
        final_reply = ""

        max_turns = max(1, AGENT_MAX_TOOL_TURNS)
        for iteration in range(max_turns):
            is_final_turn = iteration == max_turns - 1
            if is_final_turn:
                messages.append(
                    {
                        "role": "user",
                        "content": "请基于以上工具结果直接给出最终答案，不要再调用工具。",
                    }
                )
                final_message = self.llm_client.chat(
                    messages,
                    None,
                    tool_choice="none",
                )
                final_reply = final_message.get("content") or ""
                break

            message = self.llm_client.chat(messages, tools)
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                final_reply = message.get("content") or ""
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls,
                }
            )
            for tool_call in tool_calls:
                function = tool_call.get("function", {}) or {}
                name = str(function.get("name", ""))
                arguments = self._parse_tool_arguments(function.get("arguments", "{}"))
                started = time.perf_counter()
                result, step, state_update = self._execute_tool_call(
                    name,
                    arguments,
                    requested_region=requested_region,
                    enable_web_search=enable_web_search,
                )
                step["duration_ms"] = int((time.perf_counter() - started) * 1000)
                steps.append(step)
                if "sources" in state_update:
                    sources.extend(state_update["sources"])
                if "calculation" in state_update:
                    calculation = state_update["calculation"]
                if "comparison" in state_update:
                    comparison = state_update["comparison"]
                if "web_results" in state_update:
                    web_results.extend(state_update["web_results"])
                if state_update.get("requested_region"):
                    requested_region = state_update["requested_region"]
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(tool_call.get("id", "")),
                        "content": self._serialize_tool_result(result),
                    }
                )

        if not final_reply.strip():
            region_notice = build_region_notice(requested_region, documents)
            final_reply = self._compose_answer(
                effective_query,
                sources,
                calculation,
                comparison,
                region_notice,
                web_results,
                requested_region=requested_region,
            )
        final_reply = self._with_compound_intent_header(
            constraint_query,
            final_reply,
            requested_region=requested_region,
            llm_client=None,
        )
        follow_ups = self._suggest_follow_ups(effective_query, sources)
        return {
            "reply": final_reply,
            "sources": self._limit_sources(sources),
            "steps": steps,
            "follow_ups": follow_ups,
            "calculation": calculation,
            "comparison": comparison,
            "region_path": [
                item
                for item in build_region_path(requested_region, documents)
                if item.get("available")
            ],
            "requested_region": requested_region,
            "web_results": web_results,
            "web_note": web_note(web_results),
            "effective_query": effective_query,
            "memory_used": uses_memory,
        }

    def _run_regional_comparison(
        self,
        query: str,
        regions: list[str],
        *,
        enable_web_search: bool,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        result = compare_regional_tool(
            query,
            regions,
            self.retriever,
            top_k_per_region=4,
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        sources = result.get("sources", [])
        available = result.get("available_region_count", 0)
        web_results: list[dict[str, Any]] = []
        if available == 0 and enable_web_search:
            web_results = web_search(query)
        reply = self._compose_regional_comparison_answer(
            query,
            result,
            web_results,
        )
        return {
            "reply": reply,
            "sources": self._limit_sources(sources, limit=CHAT_SOURCE_LIMIT * 2),
            "steps": [
                {
                    "tool": "compare",
                    "title": "跨地区对比",
                    "detail": f"对比 {len(regions)} 个地区：{'、'.join(regions)}，{available} 个地区有本地规范",
                    "duration_ms": elapsed_ms,
                }
            ],
            "follow_ups": self._suggest_follow_ups(query, sources),
            "calculation": None,
            "comparison": result,
            "region_path": [],
            "requested_region": None,
            "web_results": web_results,
            "web_note": web_note(web_results),
            "effective_query": query,
            "memory_used": False,
        }

    def _compose_regional_comparison_answer(
        self,
        query: str,
        result: dict[str, Any],
        web_results: list[dict[str, Any]],
    ) -> str:
        groups = result.get("groups", [])
        if not groups:
            return "未识别到需要对比的地区，请明确写出地区或城市名称。"

        parts: list[str] = []
        available_regions: list[str] = []
        for group in groups:
            region = group.get("region", "")
            if not group.get("available"):
                continue
            available_regions.append(region)
            parts.append(f"【{region}】")
            for standard in group.get("standards", []):
                for source in standard.get("sources", [])[:3]:
                    location = (
                        f"{source.get('standard', '')}《{source.get('title', '')}》"
                        f"{source.get('chapter', '')} {source.get('article', '')}".strip()
                    )
                    if source.get("page"):
                        location += f"，第{source['page']}页"
                    snippet = str(source.get("snippet", ""))
                    status = self._source_status(source)
                    parts.append(f"{location} —— {status}")
                    parts.append(f"  {snippet}")

        if not available_regions:
            parts.append("当前知识库暂未收录相关规范，可尝试换关键词查询")

        if web_results:
            parts.append("【联网检索参考】以下为网络搜索结果，仅供参考：")
            for index, item in enumerate(web_results[:5], start=1):
                parts.append(f"{index}. {item.get('title', '')}\n   {item.get('url', '')}")
        return "\n\n".join(parts)

    def _execute_tool_call(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        requested_region: dict[str, Any] | None,
        enable_web_search: bool,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        title, default_detail = TOOL_LABELS.get(name, (name, "执行本地工具"))
        documents = self.retriever.knowledge_base.documents

        if name == "retrieve_standards":
            tool_query = str(arguments.get("query") or "").strip()
            top_k = self._clamp_int(arguments.get("top_k"), 1, 30)
            region = detect_requested_region(
                str(arguments.get("region") or tool_query),
                documents,
            )
            sources = retrieve_tool(
                tool_query,
                self.retriever,
                top_k=top_k,
                requested_region=region,
            )
            sources.sort(
                key=lambda source: (
                    -source.get("retrieval_rank", 0),
                    source.get("region_priority", 0),
                    source.get("score", 0),
                    source.get("priority", 0),
                ),
                reverse=True,
            )
            result = {
                "sources": [
                    self._tool_source(source)
                    for source in self._limit_sources(
                        sources,
                        limit=3,
                        per_standard=1,
                    )
                ],
                "total": len(sources),
            }
            detail = f"召回 {len(sources)} 条相关条文"
            if region:
                detail += f"，地区【{region['place']}】"
            return (
                result,
                {"tool": "retrieve", "title": title, "detail": detail},
                {"sources": sources, "requested_region": region},
            )

        if name == "calculate_expression":
            expression_query = str(arguments.get("query") or arguments.get("expression") or "")
            result = calculate_tool(expression_query)
            detail = result.get("note", default_detail)
            return (
                result,
                {"tool": "calculate", "title": title, "detail": detail},
                {"calculation": result},
            )

        if name == "compare_standards":
            tool_query = str(arguments.get("query") or "").strip()
            region = detect_requested_region(
                str(arguments.get("region") or tool_query),
                documents,
            )
            result = compare_tool(
                tool_query,
                self.retriever,
                requested_region=region,
            )
            standards = result.get("standards", [])
            detail = f"对比 {len(standards)} 本规范：{'、'.join(standards)}" if standards else default_detail
            return (
                result,
                {"tool": "compare", "title": title, "detail": detail},
                {"comparison": result, "requested_region": region},
            )

        if name == "compare_regional_standards":
            tool_query = str(arguments.get("query") or "").strip()
            raw_regions = arguments.get("regions") or []
            if not isinstance(raw_regions, list):
                raw_regions = [raw_regions]
            regions = [str(item).strip() for item in raw_regions if str(item).strip()]
            if not regions:
                regions = extract_regions(tool_query, documents)
            top_k = self._clamp_int(arguments.get("top_k_per_region"), 1, 10)
            result = compare_regional_tool(
                tool_query,
                regions,
                self.retriever,
                top_k_per_region=top_k,
            )
            result_for_llm = {
                key: value
                for key, value in result.items()
                if key != "sources"
            }
            detail = (
                f"对比 {len(regions)} 个地区：{'、'.join(regions)}，"
                f"{result.get('available_region_count', 0)} 个地区有本地规范"
            )
            return (
                result_for_llm,
                {"tool": "compare", "title": title, "detail": detail},
                {
                    "sources": result.get("sources", []),
                    "comparison": result,
                    "requested_region": None,
                },
            )

        if name == "web_search":
            tool_query = str(arguments.get("query") or "").strip()
            region = detect_requested_region(
                str(arguments.get("region") or tool_query),
                documents,
            )
            if not enable_web_search:
                result = {"results": [], "note": "联网检索已禁用"}
                detail = "联网检索已禁用，跳过"
                return (
                    result,
                    {"tool": "web_search", "title": title, "detail": detail},
                    {"web_results": [], "requested_region": region},
                )
            search_query = self._build_web_query(tool_query, region)
            results = web_search(search_query)
            result = {"results": results, "query": search_query}
            detail = f"联网检索到 {len(results)} 条结果"
            return (
                result,
                {"tool": "web_search", "title": title, "detail": detail},
                {"web_results": results, "requested_region": region},
            )

        result = {"error": f"未知工具：{name}"}
        return (
            result,
            {"tool": name, "title": title, "detail": "工具不存在，已跳过"},
            {},
        )

    @staticmethod
    def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, str) or not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _clamp_int(value: Any, low: int, high: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return low
        return max(low, min(high, parsed))

    @staticmethod
    def _serialize_tool_result(result: dict[str, Any]) -> str:
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) > AGENT_TOOL_RESULT_CHARS:
            return f"{text[:AGENT_TOOL_RESULT_CHARS]}\n...（工具结果已截断）"
        return text

    @staticmethod
    def _with_compound_intent_header(
        query: str,
        reply: str,
        requested_region: dict[str, Any] | None = None,
        llm_client: Any | None = None,
    ) -> str:
        intent = detect_compound_intent(query, llm_client)
        if not intent.is_compound:
            return reply
        header_lines = ["识别到的约束："]
        region_name = (requested_region or {}).get("place") or intent.region
        if region_name:
            header_lines.append(f"  地域：{region_name}")
        if intent.building_type:
            header_lines.append(f"  建筑类型：{intent.building_type}")
        for concept in intent.concepts:
            header_lines.append(
                f"  相关概念：{concept.canonical}"
                f"（同义词：{'、'.join(concept.synonyms)}）"
            )
        target = (
            f"{intent.component}{intent.attribute}"
            if intent.component
            else intent.attribute
        )
        if target:
            header_lines.append(f"  检索目标：{target}")
        header = "\n".join(header_lines)
        if reply.startswith(header):
            return reply
        return f"{header}\n\n{reply}".strip()

    def _limit_sources(
        self,
        sources: list[dict[str, Any]],
        limit: int = CHAT_SOURCE_LIMIT,
        per_standard: int = 2,
    ) -> list[dict[str, Any]]:
        limited: list[dict[str, Any]] = []
        seen: set[tuple[str, str, Any, str]] = set()
        standard_counts: dict[str, int] = {}
        for allowance in range(1, per_standard + 1):
            for source in sources:
                if self._is_obsolete_source(source):
                    continue
                key = (
                    str(source.get("doc_id", "")),
                    str(source.get("article", "")),
                    source.get("page"),
                    str(source.get("snippet", ""))[:120],
                )
                if key in seen:
                    continue
                standard = str(
                    source.get("standard")
                    or source.get("doc_id")
                    or source.get("title")
                    or ""
                )
                if standard_counts.get(standard, 0) >= allowance:
                    continue
                seen.add(key)
                standard_counts[standard] = standard_counts.get(standard, 0) + 1
                limited.append(source)
                if len(limited) >= limit:
                    return limited
        return limited

    @staticmethod
    def _tool_source(source: dict[str, Any]) -> dict[str, Any]:
        return {
            "doc_id": source.get("doc_id", ""),
            "standard": source.get("standard", ""),
            "title": source.get("title", ""),
            "document_type": source.get("document_type", "规范"),
            "region": source.get("region", "全国"),
            "chapter": source.get("chapter", ""),
            "article": source.get("article", ""),
            "page": source.get("page"),
            "snippet": str(source.get("snippet", "")),
            "score": source.get("score", 0.0),
            "priority": source.get("priority", 0),
            "tier": source.get("tier", ""),
        }

    @staticmethod
    def _build_agent_context(
        previous_query: str | None,
        memory_hint: str,
        requested_region: dict[str, Any] | None,
        region_notice: str,
    ) -> str:
        lines: list[str] = []
        if previous_query:
            lines.append(f"上一轮用户问题：{previous_query}")
        if memory_hint:
            lines.append(f"长期记忆/项目背景：{memory_hint}")
        if requested_region:
            lines.append(f"当前地区：{requested_region['place']}")
        if region_notice:
            lines.append(f"地区提示：{region_notice}")
        if not lines:
            return "当前无额外背景。"
        return "\n".join(lines)

    @staticmethod
    def _agent_system_prompt(enable_web_search: bool = False) -> str:
        web_policy = (
            "只有用户明确允许联网且本地知识库依据不足时，才可以调用一次 web_search；"
            "能用本地知识库回答时必须使用本地结果。"
            if enable_web_search
            else "当前禁止联网搜索，不得调用 web_search；仅使用本地知识库和本地工具。"
        )
        return (
            "你是工程规范智能问答助手。优先使用本地工具获取规范条文、完成数值计算和规范对比。"
            "服务范围仅限工程建设规范及其直接相关的设计、施工、验收和技术问题。"
            "遇到生肖、星座、命理、娱乐、生活常识等与工程建设规范无关的问题，"
            "必须直接、简短地拒绝回答，不得介绍或解释无关内容，也不得调用任何工具。"
            f"{web_policy}"
            "当用户问题指代“这条、上述、这个项目”等时，应结合会话背景补全后再调用检索工具。"
            "回答必须基于工具返回的结果，引用标准编号、章节、条文和页码，不得编造条文。"
            "如果工具结果为空，如实说明并建议补充资料。请使用中文给出简洁专业的最终答案。"
        )

    @staticmethod
    def _memory_hint(memory_facts: list[dict[str, Any]] | None) -> str:
        if not memory_facts:
            return ""
        lines: list[str] = []
        for fact in memory_facts[:6]:
            text = str(fact.get("text", "")).strip()
            if text and len(text) <= 80:
                lines.append(text)
        return "；".join(lines)

    @staticmethod
    def _uses_memory(query: str, memory_hint: str) -> bool:
        if not memory_hint:
            return False
        return any(
            term in query
            for term in (*REFERENCE_TERMS, *PROJECT_CONTEXT_TERMS)
        )

    @staticmethod
    def _constraint_query(query: str, previous_query: str | None) -> str:
        if previous_query and any(term in query for term in REFERENCE_TERMS):
            return f"{previous_query} {query}"
        return query

    @staticmethod
    def _build_web_query(query: str, requested_region: dict[str, Any] | None) -> str:
        domain_terms: list[str] = []
        for keyword in extract_keywords(query, requested_region):
            if keyword["kind"] == "domain" and keyword["text"] not in domain_terms:
                domain_terms.append(keyword["text"])

        domain = ""
        for term in domain_terms:
            if term not in ("民用建筑", "公共建筑", "商业建筑", "住宅"):
                domain = term
                break
        if not domain and domain_terms:
            domain = domain_terms[0]

        if domain:
            phrase = f"{domain}标准" if domain.startswith("建筑") else f"建筑{domain}标准"
        else:
            phrase = query
        prefix = requested_region.get("place", "") if requested_region else ""
        extra = " 更严格 地方标准" if ("更严格" in query or "严格" in query) else ""
        return f"{prefix} {phrase} 规范{extra}".strip()

    def _load_standard_status(self) -> dict[str, dict[str, str]]:
        if not STANDARD_STATUS_PATH.exists():
            return {}
        try:
            payload = json.loads(STANDARD_STATUS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        result: dict[str, dict[str, str]] = {}
        for code, value in payload.items():
            if not str(code).strip():
                continue
            if isinstance(value, dict):
                result[re.sub(r"\s+", "", str(code))] = {
                    str(key): str(item)
                    for key, item in value.items()
                    if str(item).strip()
                }
            elif str(value).strip():
                result[re.sub(r"\s+", "", str(code))] = {"status": str(value)}
        return result

    def _standard_info(self, standard: str) -> dict[str, str]:
        return self.standard_status.get(re.sub(r"\s+", "", standard), {})

    def _source_status(self, source: dict[str, Any]) -> str:
        mapped_status = self._standard_info(source.get("standard", "")).get("status", "")
        document = next(
            (
                doc
                for doc in self.retriever.knowledge_base.documents
                if doc.get("id") == source.get("doc_id")
            ),
            {},
        )
        status = str(
            mapped_status
            or document.get("status")
            or source.get("status")
            or ""
        )
        if status in ("现行", "有效", "现行有效"):
            return "现行有效"
        if status in ("废止", "已废止"):
            return "已废止"
        return ""

    def _is_obsolete_source(self, source: dict[str, Any]) -> bool:
        return self._source_status(source) == "已废止"

    def _dedup_sources_by_standard(
        self,
        sources: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for source in sources:
            standard = re.sub(r"\s+", "", source.get("standard", ""))
            if standard:
                key = standard
            else:
                key = f"{source.get('region', '')}:{source.get('title', '')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(source)
        return deduped

    def _visible_region_summary(
        self,
        requested_region: dict[str, Any] | None,
        documents: list[dict[str, Any]],
    ) -> str:
        path = [
            item
            for item in build_region_path(requested_region, documents)
            if item.get("available")
        ]
        return "、".join(f"{item['level']} {item['count']}部" for item in path)

    def _source_level(
        self,
        source: dict[str, Any],
        requested_region: dict[str, Any] | None,
    ) -> str:
        region = source.get("region", "") or "全国"
        if region == "全国":
            return "national"

        hierarchy = KNOWN_HIERARCHY.get(region)
        if hierarchy:
            if hierarchy[2]:
                return "district"
            if hierarchy[1]:
                return "city"
            if hierarchy[0]:
                return "province"
        if region in REGION_ALIASES:
            return "region"

        if requested_region:
            if (
                requested_region.get("region")
                and region
                in REGION_ALIASES.get(
                    requested_region["region"],
                    (requested_region["region"],),
                )
            ):
                return "region"
            if requested_region.get("district") and region == requested_region["district"]:
                return "district"
            if requested_region.get("city") and region == requested_region["city"]:
                return "city"
            if requested_region.get("province") and region == requested_region["province"]:
                return "province"
        return "province"

    def _group_sources_by_level(
        self,
        sources: list[dict[str, Any]],
        requested_region: dict[str, Any] | None,
    ) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {
            "district": [],
            "city": [],
            "province": [],
            "region": [],
            "national": [],
        }
        for source in sources:
            level = self._source_level(source, requested_region)
            grouped.setdefault(level, []).append(source)
        return grouped

    def _level_display_name(
        self,
        level: str,
        requested_region: dict[str, Any] | None,
        sources: list[dict[str, Any]],
    ) -> str:
        if level == "national":
            return "国家标准"
        if level == "region":
            if requested_region and requested_region.get("region"):
                return requested_region["region"]
            return sources[0].get("region", "区域") if sources else "区域"
        if level in ("city", "district"):
            if requested_region:
                return (
                    requested_region.get("district")
                    or requested_region.get("city")
                    or requested_region.get("place")
                    or "市级"
                )
            return sources[0].get("region", "市级") if sources else "市级"
        if requested_region:
            return requested_region.get("province") or requested_region.get("place") or "省级"
        return sources[0].get("region", "省级") if sources else "省级"

    @staticmethod
    def _topic_from_query(query: str, place: str = "") -> str:
        text = query
        for candidate in {place, place.replace("市", "")}:
            text = text.replace(candidate, "")
        for stopword in (
            "的",
            "了",
            "吗",
            "呢",
            "我",
            "想",
            "了解",
            "什么",
            "怎么",
            "如何",
            "有啥",
            "啥",
            "相关",
            "规范",
            "标准",
            "请问",
            "一下",
            "要求",
        ):
            text = text.replace(stopword, "")
        text = re.sub(r"[？?。！!\s，,、；;：:（）()]", "", text)
        return text or "相关规范"

    @staticmethod
    def _highlight_terms(query: str) -> list[str]:
        stopwords = (
            "的",
            "了",
            "吗",
            "呢",
            "我",
            "想",
            "了解",
            "什么",
            "怎么",
            "如何",
            "有啥",
            "请问",
            "一下",
            "规范",
            "标准",
        )
        cleaned = query
        for stopword in sorted(stopwords, key=len, reverse=True):
            cleaned = cleaned.replace(stopword, "")
        cleaned = re.sub(r"[？?。！!\s，,、；;：:（）()]", "", cleaned)
        terms: list[str] = []
        for synonym in expand_query_details(query).terms:
            if synonym not in terms:
                terms.append(synonym)
        for keyword in extract_keywords(query):
            text = str(keyword.get("text", "")).strip()
            if len(text) >= 2 and text not in terms:
                terms.append(text)
        if cleaned and len(cleaned) <= 8 and cleaned not in terms:
            terms.append(cleaned)
        terms.sort(key=len, reverse=True)
        return terms[:32]

    @staticmethod
    def _highlight_html(text: str, terms: list[str]) -> str:
        escaped = html.escape(text)
        for term in terms:
            escaped = escaped.replace(html.escape(term), f"<mark>{html.escape(term)}</mark>")
        return escaped

    def _highlight_clause_html(self, text: str, terms: list[str]) -> str:
        if not terms:
            return html.escape(text)
        return "\n".join(
            (
                self._highlight_html(line, terms)
                if line.lstrip().startswith("|")
                else self._highlight_clause_line(line, terms)
            )
            for line in text.split("\n")
        )

    def _highlight_clause_line(self, line: str, terms: list[str]) -> str:
        matches = list(_ENTRY_START_RE.finditer(line))
        if not matches:
            highlighted = self._highlight_html(line, terms)
            if any(term in line for term in terms):
                return f'<u class="clause-hit">{highlighted}</u>'
            return highlighted
        parts: list[str] = []
        cursor = 0
        for index, match in enumerate(matches):
            if match.start() > cursor:
                parts.append(
                    self._highlight_entry_segment(
                        line[cursor : match.start()],
                        terms,
                    )
                )
            end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(line)
            )
            parts.append(
                self._highlight_entry_segment(line[match.start() : end], terms)
            )
            cursor = end
        if cursor < len(line):
            parts.append(
                self._highlight_entry_segment(line[cursor:], terms)
            )
        return "".join(parts)

    def _highlight_entry_segment(
        self,
        segment: str,
        terms: list[str],
    ) -> str:
        highlighted = self._highlight_html(segment, terms)
        if any(term in segment for term in terms):
            return f'<u class="clause-hit">{highlighted}</u>'
        return highlighted

    def _standard_effective_date(self, standard: str) -> str:
        return self._standard_info(standard).get("effective_date", "")

    def _topic_term(self, query: str) -> str:
        for term in REQUIRED_DOMAIN_TERMS:
            if term in query:
                return term
        return ""

    def _standard_list_key(
        self,
        topic: str,
        source: dict[str, Any],
        standard_ranks: dict[str, int],
        concept_terms: tuple[str, ...] = (),
    ) -> tuple[Any, ...]:
        title = source.get("title", "")
        title_hit = int(bool(topic) and topic in title)
        snippet = str(source.get("snippet", ""))
        concept_hit = sum(1 for term in concept_terms if term in snippet)
        standard_raw = source.get("standard", "")
        standard = re.sub(r"\s+", "", standard_raw)
        normalized_standard = re.sub(r"[\s/\-－—]", "", standard_raw).lower()
        standard_rank = standard_ranks.get(
            normalized_standard,
            len(standard_ranks),
        )
        gb55 = int(bool(title_hit) and standard.upper().startswith("GB55"))
        local_recency = int(source.get("year", 0) or 0) if not standard else 0
        return (
            concept_hit,
            title_hit,
            gb55,
            -standard_rank,
            source.get("region_priority", 0),
            source.get("score", 0),
            source.get("priority", 0),
            local_recency,
        )

    @staticmethod
    def _term_outside_parentheses(text: str, term: str) -> bool:
        depth = 0
        index = 0
        while index < len(text):
            char = text[index]
            if char in "（(":
                depth += 1
            elif char in "）)":
                depth = max(0, depth - 1)
            elif depth == 0 and text.startswith(term, index):
                return True
            index += 1
        return False

    def format_search_list(self, query: str) -> dict[str, Any]:
        requested_region = detect_requested_region(
            query,
            self.retriever.knowledge_base.documents,
        )
        sources = retrieve_tool(
            query,
            self.retriever,
            top_k=500,
            requested_region=requested_region,
        )
        compound_intent = detect_compound_intent(
            query,
            getattr(self, "llm_client", None),
        )
        topic = compound_intent.component or self._topic_term(query)
        concept_terms = tuple(
            term
            for concept in compound_intent.concepts
            for term in concept.synonyms
        )
        topic_terms = tuple(
            dict.fromkeys(
                term
                for term in (
                    topic,
                    *compound_intent.attribute_keywords,
                    *concept_terms,
                )
                if term
            )
        )
        standard_ranks = {
            re.sub(r"[\s/\-－—]", "", code).lower(): index
            for index, code in enumerate(compound_intent.primary_standards)
        }
        sources = [
            source
            for source in sources
            if not self._is_obsolete_source(source)
        ]
        if concept_terms:
            sources = [
                source
                for source in sources
                if any(
                    term in str(source.get("snippet", ""))
                    for term in concept_terms
                )
            ]
        sources.sort(
            key=lambda source: self._standard_list_key(
                topic,
                source,
                standard_ranks,
                concept_terms,
            ),
            reverse=True,
        )
        groups: dict[str, list[dict[str, Any]]] = {}
        for source in sources:
            standard = re.sub(r"\s+", "", source.get("standard", ""))
            if standard:
                key = standard
            else:
                key = f"{source.get('region', '')}:{source.get('title', '')}"
            groups.setdefault(key, []).append(source)
        items: list[dict[str, Any]] = []
        for group_sources in groups.values():
            source = group_sources[0]
            if topic_terms and not any(
                term in source.get("title", "")
                for term in topic_terms
            ):
                if (
                    not compound_intent.component
                    and compound_intent.attribute_keywords
                ):
                    has_strong_hit = any(
                        any(
                            term in item.get("snippet", "")
                            and (
                                not compound_intent.building_aliases
                                or _has_nearby_terms(
                                    item.get("snippet", ""),
                                    compound_intent.building_aliases,
                                    (term,),
                                    window=80,
                                )
                            )
                            for term in topic_terms
                        )
                        for item in group_sources
                    )
                else:
                    has_strong_hit = any(
                        self._term_outside_parentheses(
                            item.get("snippet", ""),
                            topic,
                        )
                        for item in group_sources
                    )
                if not has_strong_hit:
                    continue
            level = self._source_level(source, requested_region)
            label = self._level_display_name(level, requested_region, [source])
            items.append(
                {
                    "doc_id": source.get("doc_id", ""),
                    "standard": source.get("standard", ""),
                    "title": source.get("title", ""),
                    "status": self._source_status(source),
                    "effective_date": self._standard_effective_date(
                        source.get("standard", "")
                    ),
                    "region": source.get("region", ""),
                    "level": label,
                    "priority": source.get("priority", 0),
                    "tier": source.get("tier", ""),
                }
            )
        return {"query": query, "items": items}

    @staticmethod
    def _split_snippet_clause_fragments(
        text: str,
    ) -> list[tuple[bool, str]]:
        spans: list[tuple[int, int]] = []
        for match in _CLAUSE_NUMBER_RE.finditer(text):
            start = match.start()
            line_start = text.rfind("\n", 0, start) + 1
            if text[line_start:start].lstrip().startswith("|"):
                start = line_start
            spans.append((start, match.end()))
        spans.extend(
            (
                match.start(1),
                match.end(1),
            )
            for match in _CLAUSE_REFERENCE_START_RE.finditer(text)
        )
        spans = sorted(set(spans))
        if not spans:
            return [(False, text)]
        fragments: list[tuple[bool, str]] = []
        cursor = 0
        for index, (start, _) in enumerate(spans):
            if start > cursor:
                fragments.append((False, text[cursor:start]))
            end = spans[index + 1][0] if index + 1 < len(spans) else len(text)
            fragments.append((True, text[start:end]))
            cursor = end
        return fragments

    @staticmethod
    def _normalize_ocr_layout(text: str) -> str:
        """Join OCR physical lines into paragraphs while keeping table rows."""
        lines = [
            line
            for line in text.splitlines()
            if not any(marker in line for marker in NOISE_LINE_MARKERS)
        ]
        return normalize_ocr_paragraphs("\n".join(lines))

    @staticmethod
    def _build_clause_units(
        snippets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        units: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        def close() -> None:
            nonlocal current
            if current:
                units.append(current)
            current = None

        previous_page: Any = None
        ordered_snippets = sorted(
            enumerate(snippets),
            key=lambda item: (int(item[1].get("page") or 0), item[0]),
        )
        for _, snippet in ordered_snippets:
            if str(snippet.get("chapter", "")) == "表格":
                continue
            page = snippet.get("page")
            book_page = snippet.get("book_page")
            for starts_clause, fragment in Planner._split_snippet_clause_fragments(
                snippet.get("text", "")
            ):
                if not fragment.strip():
                    continue
                if starts_clause:
                    close()
                    current = {
                        "parts": [(page, book_page, fragment)],
                        "start_page": page,
                        "start_book_page": book_page,
                    }
                elif current is not None:
                    current_text = "".join(part[2] for part in current["parts"]).rstrip()
                    if (
                        page != previous_page
                        and current_text
                        and current_text[-1] in "。；;"
                    ):
                        close()
                        continue
                    if page != previous_page and fragment.strip().startswith(
                        (
                            "附录",
                            "本规范用词说明",
                            "引用标准名录",
                            "起草说明",
                            "条文说明",
                        )
                    ):
                        close()
                        continue
                    current["parts"].append((page, book_page, fragment))
            previous_page = page
        close()
        return units

    def format_spec_detail(
        self,
        doc_id: str,
        query: str = "",
        article: str = "",
        page: int | None = None,
    ) -> dict[str, Any] | None:
        document = next(
            (
                doc
                for doc in self.retriever.knowledge_base.documents
                if doc.get("id") == doc_id
            ),
            None,
        )
        if document is None:
            return None

        def build_detail(
            snippets: list[dict[str, Any]],
            *,
            matched: bool,
        ) -> dict[str, Any]:
            standard = document.get("standard", "")
            return {
                "doc_id": doc_id,
                "standard": standard,
                "title": document.get("title", ""),
                "document_type": document.get("document_type", "瑙勮寖"),
                "region": document.get("region", "鍏ㄥ浗"),
                "status": self._source_status(
                    {
                        "standard": standard,
                        "doc_id": doc_id,
                    }
                ),
                "effective_date": self._standard_effective_date(standard),
                "priority": document.get("priority", 0),
                "tier": document.get("tier", ""),
                "matched": matched,
                "snippets": snippets,
            }

        terms = self._highlight_terms(query)
        normalized_article = re.sub(r"\s+", "", article or "")
        if normalized_article:
            exact_snippets = [
                snippet
                for snippet in document.get("snippets", [])
                if re.sub(
                    r"\s+",
                    "",
                    str(snippet.get("article", "")),
                )
                == normalized_article
            ]
            if exact_snippets:
                exact_snippets.sort(
                    key=lambda snippet: (
                        page is not None
                        and snippet.get("page") != page,
                        int(snippet.get("page") or 0),
                    )
                )
                return build_detail(
                    [
                        {
                            "chapter": snippet.get("chapter", ""),
                            "article": snippet.get("article", ""),
                            "page": snippet.get("page"),
                            "book_page": snippet.get("book_page"),
                            "text": self._highlight_clause_html(
                                self._normalize_ocr_layout(
                                    str(snippet.get("text", "")).rstrip()
                                ),
                                terms,
                            ),
                            "score": 10000.0,
                        }
                        for snippet in exact_snippets[:30]
                    ],
                    matched=True,
                )

        if query.strip():
            ranked_sources = [
                source
                for source in retrieve_tool(
                    query,
                    self.retriever,
                    top_k=200,
                )
                if source.get("doc_id") == doc_id
            ]
            if page is not None:
                ranked_sources.sort(
                    key=lambda source: (
                        source.get("page") != page,
                        -float(source.get("score", 0.0)),
                    )
                )
            if ranked_sources:
                seen: set[tuple[Any, Any, str]] = set()
                ranked_snippets: list[dict[str, Any]] = []
                for source in ranked_sources:
                    text = self._normalize_ocr_layout(
                        str(source.get("snippet", "")).rstrip()
                    )
                    key = (
                        source.get("article", ""),
                        source.get("page"),
                        text[:120],
                    )
                    if not text or key in seen:
                        continue
                    seen.add(key)
                    ranked_snippets.append(
                        {
                            "chapter": source.get("chapter", ""),
                            "article": source.get("article", ""),
                            "page": source.get("page"),
                            "book_page": source.get("book_page"),
                            "text": self._highlight_clause_html(text, terms),
                            "score": source.get("score", 0),
                        }
                    )
                    if len(ranked_snippets) >= 30:
                        break
                if ranked_snippets:
                    return build_detail(ranked_snippets, matched=True)

        concept_terms = expand_query_details(query).terms
        if concept_terms:
            concept_snippets: list[dict[str, Any]] = []
            for snippet in document.get("snippets", []):
                text = self._normalize_ocr_layout(
                    str(snippet.get("text", "")).rstrip()
                )
                if not text or not any(
                    term in text for term in concept_terms
                ):
                    continue
                positions = [
                    text.find(term)
                    for term in concept_terms
                    if text.find(term) >= 0
                ]
                focus = min(positions) if positions else 0
                start = max(0, focus - 120)
                end = min(len(text), focus + 520)
                excerpt = text[start:end].strip()
                if start > 0:
                    excerpt = f"...{excerpt}"
                if end < len(text):
                    excerpt = f"{excerpt}..."
                article_match = re.match(
                    r"\s*(\d{1,2}(?:\.\d{1,2}){1,2})",
                    text,
                )
                concept_snippets.append(
                    {
                        "chapter": "",
                        "article": (
                            article_match.group(1)
                            if article_match
                            else ""
                        ),
                        "page": snippet.get("page"),
                        "book_page": snippet.get("book_page"),
                        "text": self._highlight_clause_html(excerpt, terms),
                        "score": sum(
                            text.count(term) for term in concept_terms
                        ),
                    }
                )
            concept_snippets.sort(
                key=lambda item: (
                    -int(item.get("score", 0)),
                    int(item.get("page") or 0),
                )
            )
            return {
                "doc_id": doc_id,
                "standard": document.get("standard", ""),
                "title": document.get("title", ""),
                "document_type": document.get("document_type", "规范"),
                "region": document.get("region", "全国"),
                "status": self._source_status(
                    {
                        "standard": document.get("standard", ""),
                        "doc_id": doc_id,
                    }
                ),
                "effective_date": self._standard_effective_date(
                    document.get("standard", "")
                ),
                "priority": document.get("priority", 0),
                "tier": document.get("tier", ""),
                "matched": bool(concept_snippets),
                "snippets": concept_snippets[:30],
            }
        if query.strip():
            return build_detail([], matched=False)
        units = self._build_clause_units(document.get("snippets", []))
        snippets: list[dict[str, Any]] = []
        for unit in units:
            parts = unit.get("parts", [])
            assembled = "\n".join(str(part[2]).rstrip() for part in parts)
            text = self._normalize_ocr_layout(assembled)
            if not text.strip():
                continue
            if self._looks_like_standard_index(text):
                continue
            if terms and not any(term in text for term in terms):
                continue
            if terms and not any(
                self._term_outside_parentheses(text, term) for term in terms
            ):
                continue
            article_match = re.match(r"\s*(\d{1,2}(?:\.\d{1,2}){1,2})", text)
            article = article_match.group(1) if article_match else ""
            display_part = parts[0]
            if terms:
                for part in parts:
                    if any(term in part[2] for term in terms):
                        display_part = part
                        break
            score = sum(text.count(term) for term in terms)
            snippets.append(
                {
                    "chapter": "",
                    "article": article,
                    "page": display_part[0],
                    "book_page": display_part[1],
                    "text": self._highlight_clause_html(text, terms),
                    "score": score,
                }
            )
        matched = bool(snippets)
        if not matched:
            noise = (
                "UDC",
                "中华人民共和国",
                "前言",
                "目录",
                "目次",
                "公告",
                "发布",
                "实施",
                "书号",
                "定价",
                "印刷",
                "www.",
            )
            for unit in units:
                parts = unit.get("parts", [])
                text = "".join(part[2] for part in parts)
                if len(text) < 30:
                    continue
                if self._looks_like_standard_index(text):
                    continue
                if any(token in text[:60] for token in noise):
                    continue
                snippets.append(
                    {
                        "chapter": "",
                        "article": "",
                        "page": parts[0][0],
                        "book_page": parts[0][1],
                        "text": self._highlight_html(text, []),
                        "score": 0,
                    }
                )
                if len(snippets) >= 12:
                    break
        snippets.sort(
            key=lambda item: (-item["score"], item.get("page") or 0)
        )
        standard = document.get("standard", "")
        return {
            "doc_id": doc_id,
            "standard": standard,
            "title": document.get("title", ""),
            "document_type": document.get("document_type", "规范"),
            "region": document.get("region", "全国"),
            "status": self._source_status({"standard": standard, "doc_id": doc_id}),
            "effective_date": self._standard_effective_date(standard),
            "priority": document.get("priority", 0),
            "tier": document.get("tier", ""),
            "matched": matched,
            "snippets": snippets[:30],
        }

    @staticmethod
    def _looks_like_standard_index(text: str) -> bool:
        if ("规范名称" in text) and (("序号" in text) or ("编号" in text)):
            return True
        if ("目次" in text) or ("目录" in text):
            return True
        if len(re.findall(r"·{3,}|⋯{3,}|…{3,}", text)) >= 2:
            return True
        codes = re.findall(
            r"(?i)\b(?:GB|GB/T|JGJ|CJJ|DB|CJ|JG|JTG|DL|TD|T/CECS)"
            r"\s*/?\s*\d{1,6}",
            text,
        )
        return len(set(codes)) >= 4

    def _compose_answer(
        self,
        query: str,
        sources: list[dict[str, Any]],
        calculation: dict[str, Any] | None,
        comparison: dict[str, Any] | None,
        region_notice: str = "",
        web_results: list[dict[str, Any]] | None = None,
        requested_region: dict[str, Any] | None = None,
    ) -> str:
        parts: list[str] = []

        if comparison and comparison.get("summary") and "未检索到" not in comparison["summary"]:
            parts.append("【规范对比】\n" + comparison["summary"])

        if calculation and calculation.get("result") is not None:
            parts.append("【计算校验】\n" + calculation["note"])

        place = requested_region.get("place", "") if requested_region else ""
        compound_intent = detect_compound_intent(
            query,
            getattr(self, "llm_client", None),
        )
        topic = (
            compound_intent.topic
            or self._topic_term(query)
            or self._topic_from_query(query, place)
            or "相关规范"
        )

        if not sources:
            if region_notice:
                parts.append(region_notice)
            if web_results:
                parts.append("【网络检索参考】以下为联网检索结果，仅供参考：")
                for index, result in enumerate(web_results[:5], start=1):
                    parts.append(f"{index}. {result.get('title', '')}\n   {result.get('url', '')}")
            parts.append("当前知识库暂未收录相关规范，可尝试换关键词查询")
            return "\n\n".join(parts)

        current_standards = {
            re.sub(r"\s+", "", source.get("standard", ""))
            for source in sources
        }
        if len(current_standards) < 3:
            extra_sources = retrieve_tool(
                query,
                self.retriever,
                top_k=120,
                requested_region=requested_region,
            )
            if extra_sources:
                extra_sources.sort(
                    key=lambda source: (
                        -source.get("retrieval_rank", 0),
                        source.get("region_priority", 0),
                        source.get("score", 0),
                        source.get("priority", 0),
                    ),
                    reverse=True,
                )
                sources = list(sources)
                for source in extra_sources:
                    key = re.sub(r"\s+", "", source.get("standard", ""))
                    if key not in current_standards:
                        sources.append(source)
                        current_standards.add(key)
        grouped = self._group_sources_by_level(sources, requested_region)
        local_levels = ("district", "city", "province", "region")
        city_or_district_hits = False
        has_local_topic = False
        for level in local_levels:
            level_sources = self._dedup_sources_by_standard(grouped.get(level, []))
            if not level_sources:
                continue
            has_local_topic = True
            if level in ("district", "city"):
                city_or_district_hits = True

        scope = (requested_region or {}).get("scope", "")
        if requested_region and scope in ("city", "district"):
            if not city_or_district_hits:
                parts.append(
                    f"💡 {place}地方{topic}规范暂未收录，"
                    f"建议查阅{place}住建局官网确认当地审图要求。"
                )
        elif requested_region and scope == "province" and not has_local_topic:
            parts.append(
                f"当前知识库未收录【{place}】的{topic}地方规范，"
                "本次仅展示可参考的国家级规范。"
            )
        elif requested_region and scope == "region" and not has_local_topic:
            parts.append(
                f"当前知识库未收录{place}地区{topic}地方规范，"
                "本次仅展示可参考的国家级规范。"
            )
        elif region_notice:
            parts.append(region_notice)

        if web_results:
            parts.append("【网络检索参考】以下为联网检索结果，仅供参考：")
            for index, result in enumerate(web_results[:5], start=1):
                parts.append(f"{index}. {result.get('title', '')}\n   {result.get('url', '')}")
        if not parts:
            parts.append("已检索到相关规范条文，请查看来源。")
        return "\n\n".join(parts)

    def _compose_stricter_answer(
        self,
        query: str,
        requested_region: dict[str, Any] | None,
        local_sources: list[dict[str, Any]],
        web_results: list[dict[str, Any]],
    ) -> str:
        place = requested_region.get("place", "该地区") if requested_region else "该地区"
        parts: list[str] = []
        if local_sources:
            parts.append(f"已检索到【{place}】相关地方标准条文，可作为更严格或更细化的参考：\n")
            parts.append("具体是否比国家规范更严格，请对照数值并核实现行有效版本。")
        else:
            if web_results:
                parts.append("以下为联网检索结果，仅供参考，请核实：\n")
                for index, result in enumerate(web_results[:5], start=1):
                    parts.append(f"{index}. {result.get('title', '')}\n   {result.get('url', '')}")
            else:
                parts.append("当前知识库暂未收录该地区相关规范，可尝试换关键词查询")
        return "\n\n".join(parts)

    @staticmethod
    def _suggest_follow_ups(query: str, sources: list[dict[str, Any]]) -> list[str]:
        keyword = re.sub(r"[？?。！!\s]", "", query)[:14]
        follow_ups: list[str] = []
        if sources:
            standard = sources[0]["standard"]
            title = sources[0]["title"]
            follow_ups.append(f"《{title}》中关于{keyword}还有哪些补充规定？")
            follow_ups.append(f"上述条文是否适用于不同耐火等级的建筑？")
        if len(sources) >= 2 and sources[0]["standard"] != sources[1]["standard"]:
            follow_ups.append(f"对比《{sources[0]['title']}》和《{sources[1]['title']}》的相关规定")
        follow_ups.append("这条规定在地方标准中有没有更严格的要求？")
        return follow_ups[:3]
