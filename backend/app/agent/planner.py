from __future__ import annotations

import re
import time
from typing import Any

from ..config import RETRIEVAL_TOP_K
from ..knowledge.keywords import extract_keywords
from ..knowledge.retriever import REQUIRED_DOMAIN_TERMS, Retriever
from ..knowledge.region_hierarchy import build_region_notice, build_region_path, detect_requested_region
from ..knowledge.web_search import web_note, web_search
from .tools import calculate_tool, compare_tool, retrieve_tool

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

STRICTER_TERMS = ("更严格", "严格", "地方标准", "省级", "省内")


class Planner:
    """Plans tool calls, executes them, and composes a traceable answer."""

    def __init__(self, retriever: Retriever) -> None:
        self.retriever = retriever

    def plan(self, query: str) -> list[tuple[str, str, str]]:
        if any(word in query for word in ("比较", "对比", "区别", "差异", "有何不同")):
            return [
                ("compare", "横向对比", "识别问题涉及的多本规范并进行条文对比"),
                ("retrieve", "条文检索", "检索对比涉及的具体规范条文"),
            ]
        if any(word in query for word in ("计算", "算一下", "面积", "宽度", "高度", "距离", "多少")) or re.search(
            r"[0-9]+[+\-*/()%]", query
        ):
            return [
                ("retrieve", "条文检索", "先定位问题对应的规范条文"),
                ("calculate", "数值计算", "对条文中的数值关系进行计算校验"),
            ]
        return [("retrieve", "条文检索", "从预构建知识库中检索最相关的规范条文")]

    def run(
        self,
        query: str,
        previous_query: str | None = None,
        enable_web_search: bool = True,
    ) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        calculation: dict[str, Any] | None = None
        comparison: dict[str, Any] | None = None
        requested_region = detect_requested_region(query, self.retriever.knowledge_base.documents)
        inherited_region = requested_region is None and bool(previous_query)
        if requested_region is None and previous_query:
            requested_region = detect_requested_region(previous_query, self.retriever.knowledge_base.documents)
        effective_query = query
        if previous_query and (inherited_region or any(term in query for term in REFERENCE_TERMS)):
            effective_query = f"{previous_query} {query}"
        stricter_followup = bool(previous_query) and any(term in query for term in STRICTER_TERMS) and (
            any(term in query for term in REFERENCE_TERMS)
            or "地方标准" in query
            or "省级" in query
            or "省内" in query
        )
        region_notice = build_region_notice(requested_region, self.retriever.knowledge_base.documents)
        region_path = build_region_path(requested_region, self.retriever.knowledge_base.documents)
        web_results: list[dict[str, Any]] = []

        if stricter_followup:
            all_sources = retrieve_tool(
                effective_query,
                self.retriever,
                top_k=RETRIEVAL_TOP_K,
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
                "sources": sources,
                "steps": [],
                "follow_ups": follow_ups,
                "calculation": None,
                "comparison": None,
                "region_path": region_path,
                "requested_region": requested_region,
                "web_results": web_results,
                "web_note": web_note(web_results),
                "effective_query": effective_query,
            }

        for tool, title, detail in self.plan(effective_query):
            started = time.perf_counter()
            if tool == "retrieve":
                sources = retrieve_tool(
                    effective_query,
                    self.retriever,
                    top_k=RETRIEVAL_TOP_K,
                    requested_region=requested_region,
                )
                sources.sort(
                    key=lambda source: (source.get("region_priority", 0), source.get("score", 0)),
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
                    effective_query,
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
        )
        follow_ups = self._suggest_follow_ups(effective_query, sources)
        return {
            "reply": reply,
            "sources": sources,
            "steps": steps,
            "follow_ups": follow_ups,
            "calculation": calculation,
            "comparison": comparison,
            "region_path": region_path,
            "requested_region": requested_region,
            "web_results": web_results,
            "web_note": web_note(web_results),
            "effective_query": effective_query,
        }

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

    @staticmethod
    def _compose_answer(
        query: str,
        sources: list[dict[str, Any]],
        calculation: dict[str, Any] | None,
        comparison: dict[str, Any] | None,
        region_notice: str = "",
        web_results: list[dict[str, Any]] | None = None,
    ) -> str:
        parts: list[str] = []

        if region_notice:
            parts.append(region_notice)

        if comparison and comparison.get("summary") and "未检索到" not in comparison["summary"]:
            parts.append("【规范对比】\n" + comparison["summary"])

        if calculation and calculation.get("result") is not None:
            parts.append("【计算校验】\n" + calculation["note"])

        if not sources:
            if web_results:
                parts.append("【网络检索】\n以下内容来源于网络搜索，请核实后引用：\n")
                for index, result in enumerate(web_results[:5], start=1):
                    parts.append(f"{index}. {result.get('title', '')}\n   {result.get('url', '')}")
                return "\n\n".join(parts)
            parts.append("当前知识库暂未检索到足够相关的规范条文。建议换一种问法，或先上传对应的规范 PDF。")
            return "\n\n".join(parts)

        parts.append("根据检索到的规范条文，答复如下：\n")
        for index, source in enumerate(sources[:3], start=1):
            location = f"{source['standard']}《{source['title']}》{source['chapter']} {source['article']}".strip()
            if source.get("page"):
                location += f"，第{source['page']}页"
            snippet = source["snippet"]
            if len(snippet) > 220:
                snippet = snippet[:220] + "……"
            parts.append(
                f"{index}. 出处：{location}\n"
                f"   条文：{snippet}"
            )
        if web_results:
            parts.append("【网络检索参考】\n以下为联网检索结果，仅供参考：\n")
            for index, result in enumerate(web_results[:5], start=1):
                parts.append(f"{index}. {result.get('title', '')}\n   {result.get('url', '')}")
        return "\n\n".join(parts)

    @staticmethod
    def _compose_stricter_answer(
        query: str,
        requested_region: dict[str, Any] | None,
        local_sources: list[dict[str, Any]],
        web_results: list[dict[str, Any]],
    ) -> str:
        place = requested_region.get("place", "该地区") if requested_region else "该地区"
        parts: list[str] = []
        if local_sources:
            parts.append(f"已检索到【{place}】相关地方标准条文，可作为更严格或更细化的参考：\n")
            for index, source in enumerate(local_sources[:5], start=1):
                location = (
                    f"{source['standard']}《{source['title']}》"
                    f"{source.get('chapter', '')} {source.get('article', '')}".strip()
                )
                if source.get("page"):
                    location += f"，第{source['page']}页"
                snippet = source["snippet"]
                if len(snippet) > 180:
                    snippet = snippet[:180] + "……"
                parts.append(f"{index}. {location}\n   条文：{snippet}")
            parts.append("具体是否比国家规范更严格，请对照数值并核实现行有效版本。")
        else:
            parts.append(f"未找到【{place}】含省内城市关于该主题的地方标准条文。")
            if web_results:
                parts.append("以下为联网检索结果，仅供参考，请核实：\n")
                for index, result in enumerate(web_results[:5], start=1):
                    parts.append(f"{index}. {result.get('title', '')}\n   {result.get('url', '')}")
            else:
                parts.append("联网检索暂不可用，建议查阅当地住建部门或地方标准发布平台。")
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
