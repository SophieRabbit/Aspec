from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)
    trace_id: str | None = None
    disable_web_search: bool = True
    user_id: str | None = None


class Source(BaseModel):
    doc_id: str
    title: str
    standard: str
    document_type: str
    region: str
    chapter: str
    article: str
    page: int | None = None
    book_page: int | None = None
    snippet: str
    score: float
    priority: int = 0
    tier: str = ""


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
    message_id: str = ""
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
    intent: str = ""
    intent_label: str = ""
    intent_source: str = ""
    intent_confidence: float = 0.0
    intent_alias: str = ""
    usage: dict = {}


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    user_id: str = "default"


class FeedbackRecord(BaseModel):
    id: str
    message_id: str
    trace_id: str = ""
    rating: Literal["helpful", "not_helpful"]
    reason_codes: list[str] = []
    comment: str = ""
    source_doc_id: str = ""
    source_article: str = ""
    status: str = "new"
    created_at: datetime
    updated_at: datetime


class FeedbackRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    message_id: str = Field(min_length=1, max_length=64)
    trace_id: str = Field(default="", max_length=64)
    rating: Literal["helpful", "not_helpful"]
    reason_codes: list[str] = Field(default_factory=list, max_length=8)
    comment: str = Field(default="", max_length=1000)
    source_doc_id: str = Field(default="", max_length=128)
    source_article: str = Field(default="", max_length=64)


class AnalyticsEventRequest(BaseModel):
    name: Literal[
        "page_view",
        "new_conversation",
        "conversation_open",
        "question_submit",
        "answer_complete",
        "answer_error",
        "source_open",
        "follow_up_click",
        "feedback_submit",
    ]
    path: str = Field(default="/", max_length=255)
    conversation_id: str = Field(default="", max_length=64)
    message_id: str = Field(default="", max_length=64)
    trace_id: str = Field(default="", max_length=64)
    properties: dict = Field(default_factory=dict)


class AnalyticsBatchRequest(BaseModel):
    events: list[AnalyticsEventRequest] = Field(min_length=1, max_length=20)


class AnalyticsBatchResponse(BaseModel):
    accepted: int


class FeedbackDashboardSummary(BaseModel):
    total: int
    helpful: int
    not_helpful: int
    helpful_rate: float
    users: int


class FeedbackDashboardTrendPoint(BaseModel):
    date: str
    total: int
    helpful: int
    not_helpful: int


class FeedbackDashboardCount(BaseModel):
    name: str
    count: int


class FeedbackDashboardItem(BaseModel):
    id: str
    user_id: str
    rating: Literal["helpful", "not_helpful"]
    reason_codes: list[str] = []
    comment: str = ""
    question: str = ""
    answer: str = ""
    intent: str = ""
    intent_source: str = ""
    trace_id: str = ""
    kb_version: str = ""
    created_at: str = ""
    updated_at: str = ""


class AnalyticsDashboardSummary(BaseModel):
    pv: int
    uv: int
    sessions: int
    questions: int
    answers: int
    answer_errors: int
    source_opens: int
    feedback_submits: int
    answer_rate: float
    feedback_rate: float


class AnalyticsDashboardTrendPoint(BaseModel):
    date: str
    pv: int
    uv: int
    questions: int
    answers: int


class AnalyticsRecentQuestion(BaseModel):
    question: str
    intent: str = ""
    source_count: int = 0
    latency_ms: int = 0
    status: str = "submitted"
    created_at: str = ""


class AnalyticsDashboard(BaseModel):
    generated_at: str
    summary: AnalyticsDashboardSummary
    trend: list[AnalyticsDashboardTrendPoint] = []
    intents: list[FeedbackDashboardCount] = []
    recent_questions: list[AnalyticsRecentQuestion] = []


class FeedbackDashboardResponse(BaseModel):
    generated_at: str
    summary: FeedbackDashboardSummary
    trend: list[FeedbackDashboardTrendPoint] = []
    reasons: list[FeedbackDashboardCount] = []
    intents: list[FeedbackDashboardCount] = []
    recent: list[FeedbackDashboardItem] = []
    analytics: AnalyticsDashboard


class MessageRecord(BaseModel):
    id: str = ""
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
    intent: str = ""
    intent_label: str = ""
    intent_source: str = ""
    intent_confidence: float = 0.0
    intent_alias: str = ""
    feedback: FeedbackRecord | None = None


class KnowledgeStatus(BaseModel):
    document_count: int
    snippet_count: int
    standards: list[str]
    knowledge_base: str


class DocumentMatch(BaseModel):
    chapter: str
    article: str
    page: int | None = None
    book_page: int | None = None
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


class SearchItem(BaseModel):
    doc_id: str
    standard: str
    title: str
    status: str
    effective_date: str = ""
    region: str = ""
    level: str = ""
    priority: int = 0
    tier: str = ""
    full_text_match: bool = False


class SearchResponse(BaseModel):
    query: str
    items: list[SearchItem] = []


class SpecSnippet(BaseModel):
    chapter: str = ""
    article: str = ""
    page: int | None = None
    book_page: int | None = None
    text: str = ""


class SpecDetailResponse(BaseModel):
    doc_id: str
    standard: str
    title: str
    document_type: str
    region: str
    status: str
    effective_date: str = ""
    priority: int = 0
    tier: str = ""
    matched: bool = True
    full_text: bool = False
    total_snippets: int = 0
    has_more: bool = False
    snippets: list[SpecSnippet] = []


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
