from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="Domanda dell'utente")
    top_k: int | None = Field(default=None, ge=1, le=20, description="Numero di documenti da recuperare")


class CitationResponse(BaseModel):
    title: str
    source: str
    relevance_score: float
    excerpt: str
    content_overlap: float | None = None


class RetrievedDocResponse(BaseModel):
    content: str
    source: str
    title: str
    score: float
    chunk_index: int = 0
    category: str = ""


class QueryResponse(BaseModel):
    response: str
    citations: list[CitationResponse]
    category: str
    trace_id: str
    fallback_triggered: bool = False
    retrieved_docs: list[RetrievedDocResponse] = Field(default_factory=list)
    context_docs: list[RetrievedDocResponse] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str
    code: str


class HealthResponse(BaseModel):
    status: str
    version: str
    documents_indexed: int
    llm_connected: bool


class IngestResponse(BaseModel):
    status: str
    documents_crawled: int
    documents_total: int = 0
    chunks_indexed: int
    message: str
