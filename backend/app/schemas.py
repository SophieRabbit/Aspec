from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)
    trace_id: str | None = None
    disable_web_search: bool = False


class FeedbackRequest(BaseModel):
    trace_id: str = ""
    question: str = Field(min_length=1, max_length=2000)
    actual_reply: str = ""
    user_note: str = ""


class Source(BaseModel):
    doc_id: str
    title: str
    standard: str
    document_type: str
    region: str
    chapter: str
    article: str
    page: int | None = None
    snippet: str
    score: float


class ReasoningStep(BaseModel):
    tool: str
    title: str
    detail: str
    duration_ms: int


class MemoryFact(BaseModel):
    text: str
    category: str
    importance: int
    created_at: datetime
    last_seen_at: datetime
    occurrences: int


class MemoryInfo(BaseModel):
    facts: list[MemoryFact] = []
    recent_messages: int
    token_estimate: int
    budget: int
    strategy: str


class ChatResponse(BaseModel):
    trace_id: str = ""
    conversation_id: str
    reply: str
    sources: list[Source] = []
    reasoning: list[ReasoningStep] = []
    follow_ups: list[str] = []
    memory: MemoryInfo | None = None
    recommendations: list[RecommendationCategory] = []
    region_path: list[RegionPathItem] = []
    keywords: list[KeywordItem] = []
    web_results: list[WebResult] = []
    web_note: str = ""
    usage: dict = {}


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class MessageRecord(BaseModel):
    trace_id: str = ""
    role: str
    content: str
    created_at: datetime
    sources: list[Source] = []
    reasoning: list[ReasoningStep] = []
    follow_ups: list[str] = []
    recommendations: list[RecommendationCategory] = []
    region_path: list[RegionPathItem] = []
    keywords: list[KeywordItem] = []
    web_results: list[WebResult] = []
    web_note: str = ""


class KnowledgeStatus(BaseModel):
    document_count: int
    snippet_count: int
    standards: list[str]
    knowledge_base: str


class DocumentMatch(BaseModel):
    chapter: str
    article: str
    page: int | None = None
    text: str
    score: float = 0.0


class DocumentContext(BaseModel):
    doc_id: str
    standard: str
    title: str
    document_type: str
    region: str
    query: str
    query_terms: list[str] = []
    total_snippets: int
    matches: list[DocumentMatch] = []


class RecommendationItem(BaseModel):
    code: str
    title: str
    category: str
    path: str


class RecommendationCategory(BaseModel):
    category: str
    items: list[RecommendationItem] = []


class RecommendationResponse(BaseModel):
    query: str
    total: int
    categories: list[RecommendationCategory] = []


class RegionPathItem(BaseModel):
    level: str
    count: int
    available: bool


class KeywordItem(BaseModel):
    text: str
    kind: str


class WebResult(BaseModel):
    title: str
    url: str
