from __future__ import annotations

import base64
import csv
import hmac
import io
import re
import shutil
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, File, Form, Header, HTTPException, Response, UploadFile

from .. import schemas
from ..agent.intent_router import (
    INTENT_CHITCHAT,
    INTENT_COLLOQUIAL,
    INTENT_COMPARISON,
    INTENT_FALLBACK,
    INTENT_NAME,
    INTENT_NUMBER,
    INTENT_NUMERIC,
    INTENT_SCENARIO,
    IntentRouter,
)
from ..agent.planner import Planner
from ..config import (
    DATA_DIR,
    FEEDBACK_ADMIN_TOKEN,
    FEEDBACK_DASHBOARD_PASSWORD,
    FEEDBACK_DASHBOARD_USERNAME,
    MEMORY_TOKEN_BUDGET,
    PRIORITY_STANDARD_BOOST,
    RETRIEVAL_TOP_K,
    WEB_SEARCH_ENABLED,
)
from ..knowledge.catalog import Catalog, normalize_code
from ..knowledge.keywords import extract_keywords
from ..knowledge.loader import KnowledgeBase
from ..knowledge.mainland_scope import (
    OUTSIDE_MAINLAND_INTENT,
    detect_outside_mainland_place,
    outside_mainland_result,
)
from ..knowledge.region_hierarchy import detect_requested_region
from ..knowledge.retriever import Retriever, tokenize
from ..memory.store import MemoryStore
from services.synonym_expander import expand_query_details

router = APIRouter(prefix="/api")

knowledge_base = KnowledgeBase()
retriever = Retriever(knowledge_base)
planner = Planner(retriever)
intent_router = IntentRouter(llm_client=planner.llm_client)
memory_store = MemoryStore()
catalog = Catalog()

INTENT_ALIASES = {
    INTENT_NUMBER: "clause_by_id",
    INTENT_NAME: "clause_by_name",
    INTENT_NUMERIC: "numeric_value",
    INTENT_SCENARIO: "scenario_query",
    INTENT_COMPARISON: "compare_query",
    INTENT_COLLOQUIAL: "vague_query",
    INTENT_CHITCHAT: "chitchat",
    INTENT_FALLBACK: "fallback",
}

OUT_OF_SCOPE_REPLY = (
    "抱歉，这个问题与工程建设规范无关，我无法回答。"
    "请提出工程建设规范相关问题。"
)

OUTSIDE_MAINLAND_LABEL = "中国大陆以外"
REGION_CONTEXT_TERMS = (
    "这里",
    "当地",
    "该地区",
    "上述地区",
    "这个项目",
    "本项目",
    "该项目",
    "这个建筑",
    "该建筑",
)

FEEDBACK_REASON_CODES = {
    "answer_inaccurate",
    "source_mismatch",
    "wrong_clause",
    "incomplete",
    "missing_content",
    "misclassified",
    "hard_to_read",
    "other",
}


def _csv_safe(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


def _resolve_user_id(header_user_id: str | None, payload_user_id: str | None = None) -> str:
    raw = header_user_id or payload_user_id or "default"
    cleaned = re.sub(r"[^0-9a-zA-Z_.:-]", "", raw).strip()[:128]
    return cleaned or "default"


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "规宝 API"}


@router.post("/feedback", response_model=schemas.FeedbackRecord)
def submit_feedback(
    payload: schemas.FeedbackRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> schemas.FeedbackRecord:
    user_id = _resolve_user_id(x_user_id)
    assistant = memory_store.get_message(payload.message_id, user_id)
    if (
        not assistant
        or assistant.get("role") != "assistant"
        or assistant.get("conversation_id") != payload.conversation_id
    ):
        raise HTTPException(status_code=404, detail="回答消息不存在")
    if payload.trace_id and assistant.get("trace_id") != payload.trace_id:
        raise HTTPException(status_code=400, detail="反馈关联的对话轨迹不匹配")

    reason_codes = list(dict.fromkeys(payload.reason_codes))
    invalid_reasons = set(reason_codes) - FEEDBACK_REASON_CODES
    if invalid_reasons:
        raise HTTPException(status_code=400, detail="存在无效的反馈原因")
    if payload.rating == "not_helpful" and not reason_codes and not payload.comment.strip():
        raise HTTPException(status_code=400, detail="请选择反馈原因或填写补充说明")

    sources = assistant.get("sources") or []
    if payload.source_doc_id and not any(
        str(source.get("doc_id", "")) == payload.source_doc_id
        for source in sources
    ):
        raise HTTPException(status_code=400, detail="反馈来源不属于该回答")

    messages = memory_store.get_messages(payload.conversation_id, user_id)
    assistant_index = next(
        (
            index
            for index, message in enumerate(messages)
            if str(message.get("id")) == payload.message_id
        ),
        -1,
    )
    question_snapshot = next(
        (
            str(message.get("content", ""))
            for message in reversed(messages[: max(0, assistant_index)])
            if message.get("role") == "user"
        ),
        "",
    )
    feedback = memory_store.save_feedback(
        user_id=user_id,
        conversation_id=payload.conversation_id,
        message_id=payload.message_id,
        trace_id=assistant.get("trace_id", ""),
        rating=payload.rating,
        reason_codes=reason_codes,
        comment=payload.comment,
        source_doc_id=payload.source_doc_id,
        source_article=payload.source_article,
        intent=str(assistant.get("intent", "")),
        intent_source=str(assistant.get("intent_source", "")),
        intent_confidence=float(assistant.get("intent_confidence", 0.0) or 0.0),
        question_snapshot=question_snapshot,
        answer_snapshot=str(assistant.get("content", "")),
        kb_version=f"{knowledge_base.knowledge_base}@{int(knowledge_base.loaded_at)}",
        app_version="0.1.0",
    )
    return schemas.FeedbackRecord(**feedback)


@router.get("/feedback/export")
def export_feedback(
    x_feedback_admin_token: str | None = Header(
        default=None,
        alias="X-Feedback-Admin-Token",
    ),
) -> Response:
    if not FEEDBACK_ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="反馈导出尚未配置")
    if not x_feedback_admin_token or not hmac.compare_digest(
        x_feedback_admin_token,
        FEEDBACK_ADMIN_TOKEN,
    ):
        raise HTTPException(status_code=403, detail="无权导出反馈")

    rows = memory_store.list_feedback()
    columns = (
        "id",
        "user_id",
        "conversation_id",
        "message_id",
        "trace_id",
        "rating",
        "reason_codes",
        "comment",
        "source_doc_id",
        "source_article",
        "intent",
        "intent_source",
        "intent_confidence",
        "question_snapshot",
        "answer_snapshot",
        "kb_version",
        "app_version",
        "status",
        "created_at",
        "updated_at",
    )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        export_row = {
            **row,
            "reason_codes": ",".join(row.get("reason_codes", [])),
        }
        writer.writerow(
            {
                column: _csv_safe(export_row.get(column, ""))
                for column in columns
            }
        )
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="feedback.csv"'},
    )


def _require_feedback_dashboard_auth(authorization: str | None) -> None:
    unauthorized = HTTPException(
        status_code=401,
        detail="用户名或密码错误",
        headers={"WWW-Authenticate": 'Basic realm="Feedback Dashboard", charset="UTF-8"'},
    )
    if not authorization:
        raise unauthorized
    scheme, _, encoded = authorization.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        raise unauthorized
    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise unauthorized from None
    username, separator, password = decoded.partition(":")
    if not separator or not (
        hmac.compare_digest(username, FEEDBACK_DASHBOARD_USERNAME)
        and hmac.compare_digest(password, FEEDBACK_DASHBOARD_PASSWORD)
    ):
        raise unauthorized


def _feedback_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _feedback_dashboard_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    shanghai = ZoneInfo("Asia/Shanghai")
    now = datetime.now(shanghai)
    helpful = sum(1 for row in rows if row.get("rating") == "helpful")
    not_helpful = sum(1 for row in rows if row.get("rating") == "not_helpful")
    total = helpful + not_helpful
    reason_counts = Counter(
        str(code)
        for row in rows
        for code in row.get("reason_codes", [])
        if str(code).strip()
    )
    intent_counts = Counter(
        str(row.get("intent") or "未记录")
        for row in rows
    )

    trend: dict[str, dict[str, Any]] = {}
    for offset in range(13, -1, -1):
        day = (now - timedelta(days=offset)).date()
        trend[day.isoformat()] = {
            "date": day.strftime("%m-%d"),
            "total": 0,
            "helpful": 0,
            "not_helpful": 0,
        }
    for row in rows:
        created = _feedback_datetime(row.get("created_at"))
        if created is None:
            continue
        day_key = created.astimezone(shanghai).date().isoformat()
        if day_key not in trend:
            continue
        point = trend[day_key]
        point["total"] += 1
        rating = row.get("rating")
        if rating in ("helpful", "not_helpful"):
            point[rating] += 1

    recent = []
    for row in rows[:30]:
        recent.append(
            {
                "id": str(row.get("id", "")),
                "user_id": str(row.get("user_id", "")),
                "rating": row.get("rating"),
                "reason_codes": list(row.get("reason_codes", [])),
                "comment": str(row.get("comment", "")),
                "question": str(row.get("question_snapshot", "")),
                "answer": str(row.get("answer_snapshot", "")),
                "intent": str(row.get("intent", "")),
                "intent_source": str(row.get("intent_source", "")),
                "trace_id": str(row.get("trace_id", "")),
                "kb_version": str(row.get("kb_version", "")),
                "created_at": str(row.get("created_at", "")),
                "updated_at": str(row.get("updated_at", "")),
            }
        )
    return {
        "generated_at": now.isoformat(),
        "summary": {
            "total": total,
            "helpful": helpful,
            "not_helpful": not_helpful,
            "helpful_rate": round(helpful / total * 100, 1) if total else 0.0,
            "users": len({str(row.get("user_id", "")).strip() for row in rows if row.get("user_id")}),
        },
        "trend": list(trend.values()),
        "reasons": [
            {"name": name, "count": count}
            for name, count in reason_counts.most_common()
        ],
        "intents": [
            {"name": name, "count": count}
            for name, count in intent_counts.most_common(10)
        ],
        "recent": recent,
    }


@router.get(
    "/admin/feedback/dashboard",
    response_model=schemas.FeedbackDashboardResponse,
)
def feedback_dashboard(
    response: Response,
    authorization: str | None = Header(default=None),
) -> schemas.FeedbackDashboardResponse:
    _require_feedback_dashboard_auth(authorization)
    response.headers["Cache-Control"] = "no-store"
    return schemas.FeedbackDashboardResponse(
        **_feedback_dashboard_payload(memory_store.list_feedback())
    )


@router.get("/knowledge/status", response_model=schemas.KnowledgeStatus)
def knowledge_status() -> schemas.KnowledgeStatus:
    return schemas.KnowledgeStatus(**knowledge_base.stats())


@router.get("/knowledge/priority")
def priority_coverage() -> dict:
    stats = retriever.priority_stats()
    stats["boost"] = PRIORITY_STANDARD_BOOST
    return stats


@router.post("/knowledge/reload", response_model=schemas.KnowledgeStatus)
def reload_knowledge() -> schemas.KnowledgeStatus:
    knowledge_base.reload()
    retriever.reload()
    return schemas.KnowledgeStatus(**knowledge_base.stats())


@router.get("/standards/recommend", response_model=schemas.RecommendationResponse)
def recommend_standards(query: str = "") -> schemas.RecommendationResponse:
    categories = catalog.recommend(query)
    total = sum(len(group["items"]) for group in categories)
    return schemas.RecommendationResponse(query=query, total=total, categories=categories)


@router.get("/knowledge/documents/{doc_id}/context", response_model=schemas.DocumentContext)
def document_context(doc_id: str, query: str = "") -> schemas.DocumentContext:
    document = next((doc for doc in knowledge_base.documents if doc.get("id") == doc_id), None)
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    query_terms: list[str] = []
    seen: set[str] = set()
    if query:
        for term in tokenize(query):
            if len(term) >= 2 and term not in seen:
                seen.add(term)
                query_terms.append(term)
            if len(query_terms) >= 12:
                break

    matches: list[schemas.DocumentMatch] = []
    for snippet in document.get("snippets", []):
        text = snippet.get("text", "")
        if not text:
            continue
        if query_terms:
            text_tokens = set(tokenize(text))
            score = sum(1 for term in query_terms if term in text_tokens)
            if score == 0:
                continue
        else:
            score = 0
        matches.append(
            schemas.DocumentMatch(
                chapter=snippet.get("chapter", ""),
                article=snippet.get("article", ""),
                page=snippet.get("page"),
                book_page=snippet.get("book_page"),
                text=text,
                score=score,
            )
        )

    matches.sort(key=lambda match: (-match.score, match.page or 0))
    return schemas.DocumentContext(
        doc_id=document.get("id", doc_id),
        standard=document.get("standard", ""),
        title=document.get("title", ""),
        document_type=document.get("document_type", "规范"),
        region=document.get("region", "全国"),
        query=query,
        query_terms=query_terms[:12],
        total_snippets=len(document.get("snippets", [])),
        matches=matches[:30],
    )


@router.get("/search", response_model=schemas.SearchResponse)
def search_standards(q: str = "") -> schemas.SearchResponse:
    if not q.strip():
        return schemas.SearchResponse(query=q, items=[])
    if detect_outside_mainland_place(q):
        return schemas.SearchResponse(query=q, items=[])
    intent_result = intent_router.classify(q, use_llm=False)
    if intent_result.intent in {INTENT_CHITCHAT, INTENT_FALLBACK}:
        return schemas.SearchResponse(query=q, items=[])
    return schemas.SearchResponse(**planner.format_search_list(q))


@router.get("/spec/{doc_id}/detail", response_model=schemas.SpecDetailResponse)
def spec_detail(
    doc_id: str,
    q: str = "",
    article: str = "",
    page: int | None = None,
) -> schemas.SpecDetailResponse:
    result = planner.format_spec_detail(
        doc_id,
        q,
        article=article,
        page=page,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="规范详情不存在")
    return schemas.SpecDetailResponse(**result)


@router.post("/knowledge/upload", status_code=201)
async def upload_pdf(
    file: UploadFile = File(...),
    title: str = Form(...),
    standard: str = Form(...),
) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")
    temp_path = DATA_DIR / f"upload-{uuid.uuid4().hex}.pdf"
    with temp_path.open("wb") as target:
        shutil.copyfileobj(file.file, target)
    try:
        document = knowledge_base.ingest_pdf(temp_path, title=title, standard=standard)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    finally:
        if temp_path.exists():
            temp_path.unlink()
    retriever.reload()
    return document


@router.get("/conversations", response_model=list[schemas.ConversationSummary])
def list_conversations(
    user_id: str = "default",
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> list[schemas.ConversationSummary]:
    resolved_user_id = _resolve_user_id(x_user_id, user_id)
    return [
        schemas.ConversationSummary(
            conversation_id=item["conversation_id"],
            title=item["title"],
            created_at=item["created_at"],
            updated_at=item["updated_at"],
            message_count=item["message_count"],
            user_id=item["user_id"],
        )
        for item in memory_store.list_conversations(resolved_user_id)
    ]


@router.post("/conversations", response_model=schemas.ConversationSummary)
def create_conversation(
    user_id: str = "default",
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> schemas.ConversationSummary:
    item = memory_store.create_conversation(user_id=_resolve_user_id(x_user_id, user_id))
    return schemas.ConversationSummary(
        conversation_id=item["conversation_id"],
        title=item["title"],
        created_at=item["created_at"],
        updated_at=item["updated_at"],
        message_count=item["message_count"],
        user_id=item["user_id"],
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    user_id: str = "default",
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, bool]:
    return {"deleted": memory_store.delete_conversation(conversation_id, _resolve_user_id(x_user_id, user_id))}


@router.get("/conversations/{conversation_id}/messages", response_model=list[schemas.MessageRecord])
def conversation_messages(
    conversation_id: str,
    user_id: str = "default",
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> list[schemas.MessageRecord]:
    resolved_user_id = _resolve_user_id(x_user_id, user_id)
    if not memory_store.exists(conversation_id, resolved_user_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    records = memory_store.get_messages(conversation_id, resolved_user_id)
    last_user_query = ""
    refreshed: list[schemas.MessageRecord] = []
    for item in records:
        item["id"] = str(item.get("id", ""))
        if item.get("role") == "user":
            last_user_query = str(item.get("content", ""))
        elif item.get("role") == "assistant" and last_user_query:
            requested_region = detect_requested_region(
                last_user_query,
                knowledge_base.documents,
            )
            item["keywords"] = extract_keywords(
                last_user_query,
                requested_region,
            )
            concept_terms = expand_query_details(last_user_query).terms
            if concept_terms:
                item["sources"] = [
                    source
                    for source in item.get("sources", [])
                    if any(
                        term in str(source.get("snippet", ""))
                        for term in concept_terms
                    )
                ]
        refreshed.append(schemas.MessageRecord(**item))
    return refreshed


@router.get("/memory", response_model=list[schemas.MemoryFact])
def list_memory(
    user_id: str = "default",
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> list[schemas.MemoryFact]:
    return memory_store.list_facts(_resolve_user_id(x_user_id, user_id))


@router.delete("/memory/{item_id}")
def forget_memory(
    item_id: str,
    user_id: str = "default",
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, bool]:
    return {"deleted": memory_store.forget_fact(item_id, _resolve_user_id(x_user_id, user_id))}


@router.get("/memory/jobs")
def list_memory_jobs(
    user_id: str = "default",
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> list[dict]:
    return memory_store.list_distill_jobs(_resolve_user_id(x_user_id, user_id))


def _intent_result(
    reply: str,
    step_title: str,
    step_detail: str,
    effective_query: str,
) -> dict[str, Any]:
    return {
        "reply": reply,
        "sources": [],
        "steps": [
            {
                "tool": "intent_router",
                "title": step_title,
                "detail": step_detail,
                "duration_ms": 0,
            }
        ],
        "follow_ups": [],
        "calculation": None,
        "comparison": None,
        "region_path": [],
        "requested_region": None,
        "web_results": [],
        "web_note": "",
        "effective_query": effective_query,
        "memory_used": False,
    }


def _chitchat_reply(user_input: str) -> str:
    if re.search(r"(?:谢谢|多谢|感谢)", user_input):
        return "不客气！需要查询工程建设规范时，直接告诉我建筑类型、部位或指标就可以。"
    if re.search(r"(?:你是谁|你叫什么|你是什么)", user_input):
        return "我是规宝，专门帮你查询工程建设规范。直接描述你想了解的建筑类型、部位或指标即可。"
    return "你好！我是规宝，可以帮你查询工程建设规范。直接描述你想了解的建筑类型、部位或指标即可。"


def _attach_intent(result: dict[str, Any], intent_result: Any) -> dict[str, Any]:
    result["intent"] = intent_result.intent
    result["intent_label"] = intent_result.label
    result["intent_source"] = intent_result.source
    result["intent_confidence"] = intent_result.confidence
    result["intent_alias"] = INTENT_ALIASES.get(intent_result.intent, "default")
    return result


def search_by_id(
    user_input: str,
    *,
    previous_query: str | None = None,
    memory_facts: list[dict[str, Any]] | None = None,
    enable_web_search: bool = False,
) -> dict[str, Any]:
    # TODO: 用正则提取规范编号，并精确匹配数据库中的条文。
    # 占位期间沿用原 Planner，避免影响现有问答；实现后替换为精确检索。
    return planner.run(
        user_input,
        previous_query=previous_query,
        memory_facts=memory_facts,
        enable_web_search=enable_web_search,
    )


def search_by_name(
    user_input: str,
    *,
    previous_query: str | None = None,
    memory_facts: list[dict[str, Any]] | None = None,
    enable_web_search: bool = False,
) -> dict[str, Any]:
    # TODO: 使用 ES 模糊匹配规范名称，并返回候选规范列表。
    return planner.run(
        user_input,
        previous_query=previous_query,
        memory_facts=memory_facts,
        enable_web_search=enable_web_search,
        enable_function_calling=False,
    )


def search_numeric(
    user_input: str,
    *,
    previous_query: str | None = None,
    memory_facts: list[dict[str, Any]] | None = None,
    enable_web_search: bool = False,
) -> dict[str, Any]:
    # TODO: 先走 RAG 检索指标条文，再用 LLM 提取数值并标注出处。
    return planner.run(
        user_input,
        previous_query=previous_query,
        memory_facts=memory_facts,
        enable_web_search=enable_web_search,
    )


def search_scenario(
    user_input: str,
    *,
    previous_query: str | None = None,
    memory_facts: list[dict[str, Any]] | None = None,
    enable_web_search: bool = False,
) -> dict[str, Any]:
    # TODO: 走 RAG 多文档融合，汇总场景要求并生成答案。
    return planner.run(
        user_input,
        previous_query=previous_query,
        memory_facts=memory_facts,
        enable_web_search=enable_web_search,
    )


def search_comparison(
    user_input: str,
    *,
    previous_query: str | None = None,
    memory_facts: list[dict[str, Any]] | None = None,
    enable_web_search: bool = False,
) -> dict[str, Any]:
    # TODO: 并行检索多个城市/规范，生成对比结果。
    return planner.run(
        user_input,
        previous_query=previous_query,
        memory_facts=memory_facts,
        enable_web_search=enable_web_search,
    )


def search_colloquial(
    user_input: str,
    *,
    previous_query: str | None = None,
    memory_facts: list[dict[str, Any]] | None = None,
    enable_web_search: bool = False,
) -> dict[str, Any]:
    # TODO: 先调用 rewrite_vague_query() 改写，再走 RAG 检索。
    return planner.run(
        user_input,
        previous_query=previous_query,
        memory_facts=memory_facts,
        enable_web_search=enable_web_search,
    )


def _is_standard_list_query(user_input: str) -> bool:
    if "规范" not in user_input and "标准" not in user_input:
        return False
    return any(
        token in user_input
        for token in (
            "有啥",
            "有哪些",
            "哪些规范",
            "相关规范",
            "规范清单",
            "推荐规范",
            "哪几本",
        )
    )


def _detect_query_outside_mainland(
    user_input: str,
    previous_query: str | None,
    memory_facts: list[dict[str, Any]] | None,
) -> str | None:
    direct_match = detect_outside_mainland_place(user_input)
    if direct_match:
        return direct_match

    uses_context = any(term in user_input for term in REGION_CONTEXT_TERMS)
    if not uses_context:
        return None
    if previous_query:
        previous_match = detect_outside_mainland_place(previous_query)
        if previous_match:
            return previous_match
    for fact in memory_facts or []:
        memory_match = detect_outside_mainland_place(str(fact.get("text", "")))
        if memory_match:
            return memory_match
    return None


def _attach_mainland_scope_intent(result: dict[str, Any]) -> dict[str, Any]:
    result["intent"] = OUTSIDE_MAINLAND_INTENT
    result["intent_label"] = OUTSIDE_MAINLAND_LABEL
    result["intent_source"] = "rules"
    result["intent_confidence"] = 0.99
    result["intent_alias"] = OUTSIDE_MAINLAND_INTENT
    return result


def handle_query(
    user_input: str,
    user_id: str,
    *,
    previous_query: str | None = None,
    memory_facts: list[dict[str, Any]] | None = None,
    enable_web_search: bool = False,
) -> dict[str, Any]:
    outside_place = _detect_query_outside_mainland(
        user_input,
        previous_query,
        memory_facts,
    )
    if outside_place:
        return _attach_mainland_scope_intent(
            outside_mainland_result(user_input, outside_place)
        )

    intent_result = None
    try:
        intent_result = intent_router.route(user_input, use_llm=False)
        if _is_standard_list_query(user_input):
            return _attach_intent(
                search_by_name(
                    user_input,
                    previous_query=previous_query,
                    memory_facts=memory_facts,
                    enable_web_search=enable_web_search,
                ),
                intent_result,
            )
        alias = INTENT_ALIASES.get(intent_result.intent, "default")
        if alias == "clause_by_id":
            return _attach_intent(
                search_by_id(
                    user_input,
                    previous_query=previous_query,
                    memory_facts=memory_facts,
                    enable_web_search=enable_web_search,
                ),
                intent_result,
            )
        if alias == "clause_by_name":
            return _attach_intent(
                search_by_name(
                    user_input,
                    previous_query=previous_query,
                    memory_facts=memory_facts,
                    enable_web_search=enable_web_search,
                ),
                intent_result,
            )
        if alias == "numeric_value":
            return _attach_intent(
                search_numeric(
                    user_input,
                    previous_query=previous_query,
                    memory_facts=memory_facts,
                    enable_web_search=enable_web_search,
                ),
                intent_result,
            )
        if alias == "scenario_query":
            return _attach_intent(
                search_scenario(
                    user_input,
                    previous_query=previous_query,
                    memory_facts=memory_facts,
                    enable_web_search=enable_web_search,
                ),
                intent_result,
            )
        if alias == "compare_query":
            return _attach_intent(
                search_comparison(
                    user_input,
                    previous_query=previous_query,
                    memory_facts=memory_facts,
                    enable_web_search=enable_web_search,
                ),
                intent_result,
            )
        if alias == "vague_query":
            return _attach_intent(
                search_colloquial(
                    user_input,
                    previous_query=previous_query,
                    memory_facts=memory_facts,
                    enable_web_search=enable_web_search,
                ),
                intent_result,
            )
        if alias == "chitchat":
            return _attach_intent(
                _intent_result(
                    _chitchat_reply(user_input),
                    "闲聊问候",
                    "识别为问候或致谢，无需检索规范",
                    user_input,
                ),
                intent_result,
            )
        if alias == "fallback":
            return _attach_intent(
                _intent_result(
                    OUT_OF_SCOPE_REPLY,
                    "拒绝无关问题",
                    "问题与工程建设规范无关，不触发规范检索或内容生成",
                    user_input,
                ),
                intent_result,
            )
    except Exception:
        # 占位实现异常时回退到原有 Planner 流程。
        pass
    result = planner.run(
        user_input,
        previous_query=previous_query,
        memory_facts=memory_facts,
        enable_web_search=enable_web_search,
    )
    return _attach_intent(result, intent_result) if intent_result else result


@router.post("/chat", response_model=schemas.ChatResponse)
def chat(
    payload: schemas.ChatRequest,
    background_tasks: BackgroundTasks,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> schemas.ChatResponse:
    trace_id = payload.trace_id or uuid.uuid4().hex[:12]
    user_id = _resolve_user_id(x_user_id, payload.user_id)
    conversation_id = payload.conversation_id
    if conversation_id and not memory_store.exists(conversation_id, user_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    if not conversation_id:
        conversation_id = memory_store.create_conversation(user_id=user_id)["conversation_id"]

    previous_messages = memory_store.get_messages(conversation_id, user_id)
    previous_query = next(
        (item["content"] for item in reversed(previous_messages) if item["role"] == "user"),
        None,
    )
    user_message = memory_store.add_message(
        conversation_id,
        "user",
        payload.message,
        user_id=user_id,
        trace_id=trace_id,
    )
    memory = memory_store.build_context(conversation_id, user_id=user_id, max_tokens=MEMORY_TOKEN_BUDGET)
    result = handle_query(
        payload.message,
        user_id,
        previous_query=previous_query,
        memory_facts=memory["facts"],
        enable_web_search=WEB_SEARCH_ENABLED and not payload.disable_web_search,
    )
    non_retrieval = result.get("intent") in {
        INTENT_CHITCHAT,
        INTENT_FALLBACK,
        OUTSIDE_MAINLAND_INTENT,
    }
    if non_retrieval:
        keywords = []
        recommendations = []
    else:
        exclude_codes = {
            normalize_code(doc.get("standard", ""))
            for doc in knowledge_base.documents
        }
        keywords = extract_keywords(
            result.get("effective_query") or payload.message,
            result.get("requested_region"),
        )
        recommendations = catalog.recommend(
            f"{payload.message} {' '.join(source['standard'] for source in result['sources'])}",
            exclude_codes=exclude_codes,
        )

    metadata = {
        "sources": result["sources"],
        "reasoning": result["steps"],
        "follow_ups": result["follow_ups"],
        "recommendations": recommendations,
        "region_path": result["region_path"],
        "keywords": keywords,
        "web_results": result["web_results"],
        "web_note": result["web_note"],
        "intent": result.get("intent", ""),
        "intent_label": result.get("intent_label", ""),
        "intent_source": result.get("intent_source", ""),
        "intent_confidence": result.get("intent_confidence", 0.0),
        "intent_alias": result.get("intent_alias", ""),
        "trace_id": trace_id,
    }
    assistant_message = memory_store.add_message(
        conversation_id,
        "assistant",
        result["reply"],
        user_id=user_id,
        metadata=metadata,
        trace_id=trace_id,
    )
    if not non_retrieval:
        background_tasks.add_task(
            memory_store.distill,
            conversation_id=conversation_id,
            user_id=user_id,
            user_message_id=user_message["id"],
            user_content=payload.message,
            assistant_content=result["reply"],
        )

    response = schemas.ChatResponse(
        trace_id=trace_id,
        conversation_id=conversation_id,
        message_id=assistant_message["id"],
        reply=result["reply"],
        sources=result["sources"],
        reasoning=result["steps"],
        follow_ups=result["follow_ups"],
        recommendations=recommendations,
        region_path=result["region_path"],
        keywords=keywords,
        web_results=result["web_results"],
        web_note=result["web_note"],
        intent=result.get("intent", ""),
        intent_label=result.get("intent_label", ""),
        intent_source=result.get("intent_source", ""),
        intent_confidence=result.get("intent_confidence", 0.0),
        intent_alias=result.get("intent_alias", ""),
        memory=schemas.MemoryInfo(
            facts=memory["facts"],
            recent_messages=memory["recent_messages"],
            token_estimate=memory["token_estimate"],
            budget=memory["budget"],
            strategy=memory["strategy"],
        ),
        usage={
            "input_tokens": memory["token_estimate"],
            "top_k": RETRIEVAL_TOP_K,
        },
    )
    return response
