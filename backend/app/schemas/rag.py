"""RAG API schemas."""

from typing import Any

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


class RAGSearchRequest(BaseSchema):
    """Parameters for a vector search query."""

    collection_name: str = Field("documents", description="Target collection for search")
    collection_names: list[str] | None = Field(
        None, description="Search across multiple collections (overrides collection_name)"
    )
    query: str = Field(..., description="Natural language search query")
    limit: int = Field(default=4, ge=1, le=20)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    filter: str | None = Field(
        None, description="Scalar filter expression (e.g. 'filetype == \"pdf\"')"
    )


class RAGSearchResult(BaseSchema):
    """A single retrieved chunk with its associated metadata."""

    content: str
    score: float
    metadata: dict[str, Any]
    parent_doc_id: str


class RAGSearchResponse(BaseSchema):
    """List of results found in the vector store."""

    results: list[RAGSearchResult]


class RAGCollectionInfo(BaseSchema):
    """Statistical information about a specific collection."""

    name: str
    total_vectors: int
    dim: int
    indexing_status: str = "complete"


class RAGCollectionList(BaseSchema):
    """List of all available collection names."""

    items: list[str]


class RAGDocumentItem(BaseSchema):
    """Information about a single document in a collection."""

    document_id: str = Field(..., description="Unique identifier of the document")
    filename: str | None = Field(None, description="Original filename of the document")
    filesize: int | None = Field(None, description="Size of the file in bytes")
    filetype: str | None = Field(None, description="MIME type of the file")
    chunk_count: int = Field(default=0, description="Number of chunks/vectors in the collection")
    additional_info: dict[str, Any] | None = Field(None, description="Additional metadata")


class RAGDocumentList(BaseSchema):
    """List of all documents in a collection."""

    items: list[RAGDocumentItem]
    total: int = Field(..., description="Total number of unique documents")


class RAGMessageResponse(BaseSchema):
    """Simple message response."""

    message: str


class RAGTrackedDocumentItem(BaseSchema):
    """A document tracked in the SQL database."""

    id: str
    collection_name: str
    filename: str
    filesize: int
    filetype: str
    status: str
    error_message: str | None = None
    vector_document_id: str | None = None
    chunk_count: int = 0
    has_file: bool = False
    created_at: str | None = None
    completed_at: str | None = None

    # Knowledge Card fields
    card_id: str | None = None
    tenant_id: str | None = None
    card_type: str | None = None
    card_status: str | None = None
    version: int | None = None
    project: str | None = None
    tags: list[str] | None = None
    confidence: str | None = None
    owner: str | None = None
    source_pointer: str | None = None
    source_checksum: str | None = None
    source_created_at: str | None = None
    document_id: str | None = None
    next_review_at: str | None = None
    is_chunk: bool | None = None
    parent_card_id: str | None = None
    chunk_index: int | None = None


class RAGTrackedDocumentList(BaseSchema):
    """List of tracked RAG documents."""

    items: list[RAGTrackedDocumentItem]
    total: int


class RAGIngestResponse(BaseSchema):
    """Response for document ingestion (async or sync)."""

    id: str
    status: str
    filename: str
    collection: str
    message: str
    document_id: str | None = None


class RAGRetryResponse(BaseSchema):
    """Response for document retry."""

    id: str
    status: str
    message: str


class RAGSyncRequest(BaseSchema):
    """Request to trigger a sync operation."""

    collection_name: str = Field("documents", description="Target collection")
    mode: str = Field("full", description="Sync mode: full, new_only, update_only")
    path: str = Field("", description="Source path")


class RAGSyncLogItem(BaseSchema):
    """A sync operation log entry."""

    id: str
    source: str
    collection_name: str
    status: str
    mode: str
    total_files: int = 0
    ingested: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    error_message: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    @field_validator("started_at", "completed_at", mode="before")
    @classmethod
    def serialize_datetime(cls, v: Any) -> str | None:
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)


class RAGSyncLogList(BaseSchema):
    """List of sync log entries."""

    items: list[RAGSyncLogItem]
    total: int


class RAGSyncResponse(BaseSchema):
    """Response for sync trigger."""

    id: str
    status: str
    message: str


class SupportedFormatsResponse(BaseSchema):
    parser: str
    formats: list[str]


class RAGQueryRequest(BaseSchema):
    """Parameters for a RAG retrieval and generation query."""

    collection_name: str = Field("documents", description="Target collection for search")
    query: str = Field(..., description="Natural language question to ask")
    limit: int = Field(default=4, ge=1, le=20, description="Max context chunks to retrieve")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    use_reranker: bool = Field(default=False, description="Whether to use reranking")


class RAGQueryCitation(BaseSchema):
    """Citation of a retrieved document chunk supporting the answer."""

    content: str = Field(..., description="The chunk text context")
    score: float = Field(..., description="Confidence/relevance score")
    filename: str = Field(..., description="Source document filename")
    page_num: int | None = Field(None, description="Page number of source document")
    parent_doc_id: str = Field(..., description="Parent document identifier")

    # Knowledge Card fields
    card_id: str | None = Field(None, description="Canonical card identity")
    tenant_id: str | None = Field(None, description="Tenant identifier")
    card_type: str | None = Field(None, description="Card type")
    card_status: str | None = Field(None, description="Card status")
    version: int | None = Field(None, description="Card version")
    project: str | None = Field(None, description="Associated project")
    source_pointer: str | None = Field(None, description="Pointer to source document")


class RAGQueryResponse(BaseSchema):
    """RAG generated answer with supporting context citations."""

    answer: str = Field(..., description="The generated answer from LLM")
    citations: list[RAGQueryCitation] = Field(..., description="List of source chunks used for answer")


class RAGCardIngestRequest(BaseSchema):
    """Payload to ingest a Knowledge Card directly from JSON."""

    card_id: str = Field(..., description="Canonical card identity issued by Postgres registry")
    content: str = Field(..., description="Raw text content of the Knowledge Card")
    type: str = Field(..., description="Card type")
    status: str = Field(default="approved", description="draft / proposed / approved / superseded / obsolete / archived")
    version: int = Field(default=1, description="Version number")
    area: str | None = Field(None, description="Business area")
    project: str | None = Field(None, description="Associated project")
    tags: list[str] | None = Field(None, description="Free tags")
    confidence: str | None = Field(None, description="Confidence level")
    confidentiality: str = Field(default="public", description="Confidentiality level")
    owner: str | None = Field(None, description="Knowledge Owner")
    language: str = Field(default="en", description="Content language")
    source_pointer: str | None = Field(None, description="Pointer/URI to raw archive source")
    source_checksum: str | None = Field(None, description="Checksum of original source")
    source_created_at: str | None = Field(None, description="Original creation date of the source")
    document_id: str | None = Field(None, description="Lineage identifier")
    next_review_at: str | None = Field(None, description="Timestamps")
