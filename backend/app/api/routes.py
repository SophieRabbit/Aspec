from __future__ import annotations

import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .. import schemas
from ..agent.planner import Planner
from ..config import DATA_DIR, MEMORY_DIR, MEMORY_TOKEN_BUDGET, RETRIEVAL_TOP_K
from ..knowledge.catalog import Catalog, normalize_code
from ..knowledge.keywords import extract_keywords
from ..knowledge.loader import KnowledgeBase
from ..knowledge.retriever import Retriever, tokenize
from ..eval.store import EvalStore
from ..memory.store import MemoryStore

router = APIRouter(prefix="/api")

knowledge_base = KnowledgeBase()
retriever = Retriever(knowledge_base)
planner = Planner(retriever)
memory_store = MemoryStore(MEMORY_DIR)
catalog = Catalog()
eval_store = EvalStore()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "规宝 API"}


@router.get("/knowledge/status", response_model=schemas.KnowledgeStatus)
def knowledge_status() -> schemas.KnowledgeStatus:
    return schemas.KnowledgeStatus(**knowledge_base.stats())


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
def list_conversations() -> list[schemas.ConversationSummary]:
    return [
        schemas.ConversationSummary(
            conversation_id=item["conversation_id"],
            title=item["title"],
            created_at=item["created_at"],
            updated_at=item["updated_at"],
            message_count=item["message_count"],
        )
        for item in memory_store.list_conversations()
    ]


@router.post("/conversations", response_model=schemas.ConversationSummary)
def create_conversation() -> schemas.ConversationSummary:
    item = memory_store.create_conversation()
    return schemas.ConversationSummary(
        conversation_id=item["conversation_id"],
        title=item["title"],
        created_at=item["created_at"],
        updated_at=item["updated_at"],
        message_count=item["message_count"],
    )


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, bool]:
    return {"deleted": memory_store.delete_conversation(conversation_id)}


@router.get("/conversations/{conversation_id}/messages", response_model=list[schemas.MessageRecord])
def conversation_messages(conversation_id: str) -> list[schemas.MessageRecord]:
    if not memory_store.exists(conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return [schemas.MessageRecord(**item) for item in memory_store.get_messages(conversation_id)]


@router.post("/chat", response_model=schemas.ChatResponse)
def chat(payload: schemas.ChatRequest) -> schemas.ChatResponse:
    started = time.perf_counter()
    trace_id = payload.trace_id or uuid.uuid4().hex[:12]
    conversation_id = payload.conversation_id
    if conversation_id and not memory_store.exists(conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    if not conversation_id:
        conversation_id = memory_store.create_conversation()["conversation_id"]

    previous_messages = memory_store.get_messages(conversation_id)
    previous_query = next(
        (item["content"] for item in reversed(previous_messages) if item["role"] == "user"),
        None,
    )
    memory_store.add_message(conversation_id, "user", payload.message)
    memory = memory_store.build_context(conversation_id, MEMORY_TOKEN_BUDGET)
    result = planner.run(
        payload.message,
        previous_query=previous_query,
        enable_web_search=not payload.disable_web_search,
    )
    exclude_codes = {normalize_code(doc.get("standard", "")) for doc in knowledge_base.documents}
    keywords = extract_keywords(result.get("effective_query") or payload.message, result.get("requested_region"))
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
        "trace_id": trace_id,
    }
    memory_store.add_message(conversation_id, "assistant", result["reply"], metadata=metadata)

    response = schemas.ChatResponse(
        trace_id=trace_id,
        conversation_id=conversation_id,
        reply=result["reply"],
        sources=result["sources"],
        reasoning=result["steps"],
        follow_ups=result["follow_ups"],
        recommendations=recommendations,
        region_path=result["region_path"],
        keywords=keywords,
        web_results=result["web_results"],
        web_note=result["web_note"],
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
    latency_ms = (time.perf_counter() - started) * 1000
    eval_store.save_trace(
        trace_id,
        {"message": payload.message, "conversation_id": conversation_id},
        response.model_dump(),
        latency_ms,
    )
    return response


@router.post("/feedback/bad-case")
def feedback_bad_case(payload: schemas.FeedbackRequest) -> dict[str, str]:
    bad_case_id = eval_store.add_bad_case(
        question=payload.question,
        actual_reply=payload.actual_reply,
        failed_dimensions=["user_feedback"],
        source="user_feedback",
        trace_id=payload.trace_id,
        user_note=payload.user_note,
    )
    return {"bad_case_id": bad_case_id}
