"""RAGDocument model — tracks documents ingested into RAG collections."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, Boolean
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class RAGDocument(TimestampMixin, Base):
    """Tracks ingested documents with processing status."""

    __tablename__ = "rag_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    filesize: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filetype: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    vector_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    area: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True, default="en")
    confidentiality: Mapped[str | None] = mapped_column(String(50), nullable=True, default="public", index=True)
    permissions: Mapped[str | None] = mapped_column(String(50), nullable=True, default="read")

    # Knowledge Card specification fields
    card_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, unique=True, index=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    card_type: Mapped[str | None] = mapped_column("type", String(50), nullable=True, index=True)
    card_status: Mapped[str | None] = mapped_column(String(50), nullable=True, default="approved", index=True)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True, default=1)
    project: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_pointer: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_chunk: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    parent_card_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True, index=True)
    chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
