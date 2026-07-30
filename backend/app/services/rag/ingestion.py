from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.core.config import settings
from app.services.rag.documents import DocumentProcessor
from app.services.rag.embeddings import EmbeddingService
from app.services.rag.models import Document, IngestionResult, IngestionStatus
from app.services.rag.vectorstore import BaseVectorStore
from app.services.rag.vectorstore import QdrantVectorStore as VectorStore

logger = logging.getLogger(__name__)


class IngestionService:
    """File → Parse/Chunk → Deduplicate → Embed/Store → Query-Ready."""

    def __init__(
        self,
        processor: DocumentProcessor,
        vector_store: BaseVectorStore,
        on_event: Callable[..., Awaitable[None]] | None = None,
    ):
        self.processor = processor
        self.store = vector_store
        self._on_event = on_event

    @classmethod
    def from_settings(
        cls,
        on_event: Callable[..., Awaitable[None]] | None = None,
    ) -> IngestionService:
        rag_settings = settings.rag
        embed_service = EmbeddingService(settings=rag_settings)
        vector_store = VectorStore(settings=rag_settings, embedding_service=embed_service)
        processor = DocumentProcessor(settings=rag_settings)
        return cls(processor=processor, vector_store=vector_store, on_event=on_event)

    async def _emit(self, event: str, data: dict[str, object]) -> None:
        if self._on_event:
            try:
                await self._on_event(event, data)
            except Exception as e:
                logger.warning("Webhook event dispatch failed: %s", e)

    async def _find_existing_by_source(self, collection_name: str, source_path: str) -> str | None:
        try:
            docs = await self.store.get_documents(collection_name)
            for doc in docs:
                meta = doc.additional_info or {}
                if meta.get("source_path") == source_path:
                    return doc.document_id
                # Also check top-level metadata fields
                # (source_path is stored in metadata dict per chunk)
            for doc in docs:
                if doc.filename and doc.filename == Path(source_path).name:
                    return doc.document_id
        except Exception as exc:
            logger.warning("Could not check for existing document: %s", exc, exc_info=True)
        return None

    async def _find_existing_by_hash(self, collection_name: str, content_hash: str) -> str | None:
        """Find an existing document by content hash (exact duplicate check)."""
        try:
            docs = await self.store.get_documents(collection_name)
            for doc in docs:
                meta = doc.additional_info or {}
                if meta.get("content_hash") == content_hash:
                    return doc.document_id
        except Exception as exc:
            logger.warning("Could not check for existing document: %s", exc, exc_info=True)
        return None

    async def ingest_file(
        self,
        filepath: Path,
        collection_name: str,
        replace: bool = True,
        source_path: str = "",
        tenant_id: str | None = None,
        area: str | None = None,
        owner: str | None = None,
        language: str | None = "en",
        confidentiality: str | None = "public",
        permissions: str | None = "read",
        # New card fields
        card_id: str | None = None,
        card_type: str | None = None,
        card_status: str | None = "approved",
        version: int | None = 1,
        project: str | None = None,
        tags: list[str] | None = None,
        confidence: str | None = None,
        source_pointer: str | None = None,
        source_checksum: str | None = None,
        source_created_at: str | None = None,
        document_id: str | None = None,
        next_review_at: str | None = None,
        is_chunk: bool | None = False,
        parent_card_id: str | None = None,
        chunk_index: int | None = None,
    ) -> IngestionResult:
        """`source_path` accepts URI schemes like gdrive://id or s3://bucket/key."""
        try:
            document: Document = await self.processor.process_file(filepath)

            if source_path:
                document.metadata.source_path = source_path
                document.metadata.filename = Path(source_path).name

            # Map multi-tenant and access control metadata parameters
            document.metadata.tenant_id = tenant_id
            document.metadata.area = area
            document.metadata.owner = owner
            document.metadata.language = language
            document.metadata.confidentiality = confidentiality
            document.metadata.permissions = permissions
            
            # Map new card fields
            document.metadata.card_id = card_id
            document.metadata.card_type = card_type
            document.metadata.card_status = card_status
            document.metadata.version = version
            document.metadata.project = project
            document.metadata.tags = tags
            document.metadata.confidence = confidence
            document.metadata.source_pointer = source_pointer
            document.metadata.source_checksum = source_checksum
            document.metadata.source_created_at = source_created_at
            document.metadata.document_id = document_id
            document.metadata.next_review_at = next_review_at
            document.metadata.is_chunk = is_chunk
            document.metadata.parent_card_id = parent_card_id
            document.metadata.chunk_index = chunk_index

            existing_id = None
            if replace:
                if card_id:
                    # Idempotency check: purge Qdrant points matching card_id
                    await self.store.delete_card(collection_name, card_id)
                else:
                    if document.metadata.source_path:
                        existing_id = await self._find_existing_by_source(
                            collection_name, document.metadata.source_path
                        )
                    # Check by content hash when path lookup missed
                    if not existing_id and document.metadata.content_hash:
                        existing_id = await self._find_existing_by_hash(
                            collection_name, document.metadata.content_hash
                        )

            if existing_id:
                await self.store.delete_document(collection_name, existing_id)
                logger.info("Replaced existing document %s for '%s'", existing_id, filepath.name)

            await self.store.insert_document(
                collection_name=collection_name,
                document=document,
            )

            action = "replaced" if (existing_id or card_id) else "ingested"

            await self._emit(
                "rag.document.ingested",
                {
                    "document_id": document.id,
                    "filename": filepath.name,
                    "collection": collection_name,
                    "action": action,
                    "chunks": len(document.chunked_pages or []),
                    "source_path": document.metadata.source_path,
                },
            )
            return IngestionResult(
                status=IngestionStatus.DONE,
                document_id=document.id,
                message=f"Successfully {action} '{filepath.name}'",
            )
        except Exception as e:
            logger.error("Ingestion error for %s: %s", filepath.name, e)
            return IngestionResult(
                status=IngestionStatus.ERROR,
                error_message=str(e),
                message=f"Failed to process {filepath.name}",
            )

    async def ingest_card(
        self,
        collection_name: str,
        content: str,
        card_id: str,
        tenant_id: str,
        card_type: str,
        card_status: str = "approved",
        version: int = 1,
        area: str | None = None,
        project: str | None = None,
        tags: list[str] | None = None,
        confidence: str | None = None,
        owner: str | None = None,
        language: str | None = "en",
        confidentiality: str | None = "public",
        permissions: str | None = "read",
        source_pointer: str | None = None,
        source_checksum: str | None = None,
        source_created_at: str | None = None,
        document_id: str | None = None,
        next_review_at: str | None = None,
        is_chunk: bool = False,
        parent_card_id: str | None = None,
        chunk_index: int | None = None,
    ) -> IngestionResult:
        """Ingest a Knowledge Card directly from raw text content.
        
        If the card is oversized (>8000 characters), it will be split into sibling points
        referencing the parent card.
        """
        try:
            from app.services.rag.models import DocumentPage, DocumentPageChunk, DocumentMetadata
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            import hashlib
            import uuid

            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            # Idempotency: delete any existing points in Qdrant matching this card_id!
            await self.store.delete_card(collection_name, card_id)

            MAX_CARD_LENGTH = 8000
            if len(content) <= MAX_CARD_LENGTH:
                metadata = DocumentMetadata(
                    filename=f"card_{card_id}.txt",
                    filesize=len(content.encode("utf-8")),
                    filetype="txt",
                    source_path=source_pointer or f"card://{card_id}",
                    content_hash=content_hash,
                    tenant_id=tenant_id,
                    area=area,
                    owner=owner,
                    language=language,
                    confidentiality=confidentiality,
                    permissions=permissions,
                    card_id=card_id,
                    card_type=card_type,
                    card_status=card_status,
                    version=version,
                    project=project,
                    tags=tags,
                    confidence=confidence,
                    source_pointer=source_pointer,
                    source_checksum=source_checksum,
                    source_created_at=source_created_at,
                    document_id=document_id,
                    next_review_at=next_review_at,
                    is_chunk=False,
                    parent_card_id=None,
                    chunk_index=None,
                )

                page = DocumentPage(page_num=1, content=content)
                chunk = DocumentPageChunk(
                    chunk_id=card_id,
                    page_num=1,
                    content=content,
                    chunk_content=content,
                    chunk_num=0,
                    parent_doc_id=card_id,
                )

                document = Document(
                    id=card_id,
                    pages=[page],
                    chunked_pages=[chunk],
                    metadata=metadata
                )

                await self.store.insert_document(
                    collection_name=collection_name,
                    document=document,
                )
            else:
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=6000,
                    chunk_overlap=1000,
                    length_function=len,
                )
                chunks = splitter.split_text(content)
                logger.info(
                    "Card %s content length (%d) exceeds limit (%d). Split into %d chunks.",
                    card_id,
                    len(content),
                    MAX_CARD_LENGTH,
                    len(chunks),
                )

                for idx, chunk_text in enumerate(chunks):
                    # Deterministic point UUID based on card_id and chunk index
                    chunk_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{card_id}_chunk_{idx}"))

                    metadata = DocumentMetadata(
                        filename=f"card_{card_id}_chunk_{idx}.txt",
                        filesize=len(chunk_text.encode("utf-8")),
                        filetype="txt",
                        source_path=source_pointer or f"card://{card_id}",
                        content_hash=content_hash,
                        tenant_id=tenant_id,
                        area=area,
                        owner=owner,
                        language=language,
                        confidentiality=confidentiality,
                        permissions=permissions,
                        card_id=card_id,
                        card_type=card_type,
                        card_status=card_status,
                        version=version,
                        project=project,
                        tags=tags,
                        confidence=confidence,
                        source_pointer=source_pointer,
                        source_checksum=source_checksum,
                        source_created_at=source_created_at,
                        document_id=document_id,
                        next_review_at=next_review_at,
                        is_chunk=True,
                        parent_card_id=card_id,
                        chunk_index=idx,
                    )

                    page = DocumentPage(page_num=1, content=chunk_text)
                    chunk = DocumentPageChunk(
                        chunk_id=chunk_uuid,
                        page_num=1,
                        content=chunk_text,
                        chunk_content=chunk_text,
                        chunk_num=0,
                        parent_doc_id=chunk_uuid,
                    )

                    document = Document(
                        id=chunk_uuid,
                        pages=[page],
                        chunked_pages=[chunk],
                        metadata=metadata
                    )

                    await self.store.insert_document(
                        collection_name=collection_name,
                        document=document,
                    )

            return IngestionResult(
                status=IngestionStatus.DONE,
                document_id=card_id,
                message=f"Successfully ingested Knowledge Card '{card_id}'",
            )
        except Exception as e:
            logger.error("Card ingestion error for %s: %s", card_id, e)
            return IngestionResult(
                status=IngestionStatus.ERROR,
                error_message=str(e),
                message=f"Failed to process card {card_id}",
            )

    async def find_existing(self, collection_name: str, source_path: str) -> str | None:
        return await self._find_existing_by_source(collection_name, source_path)

    async def get_existing_hash(self, collection_name: str, source_path: str) -> str | None:
        try:
            docs = await self.store.get_documents(collection_name)
            doc_id: str | None = None
            content_hash: str | None = None
            for doc in docs:
                meta = doc.additional_info or {}
                if doc_id is None:
                    if meta.get("source_path") == source_path:
                        doc_id = doc.document_id
                        content_hash = meta.get("content_hash")
                        break
                    if doc.filename and doc.filename == Path(source_path).name:
                        doc_id = doc.document_id
                        content_hash = meta.get("content_hash")
            return content_hash
        except Exception as exc:
            logger.warning("Could not retrieve existing hash: %s", exc, exc_info=True)
        return None

    async def remove_document(self, collection_name: str, document_id: str) -> bool:
        """Wipes all traces of a document from the vector store."""
        try:
            await self.store.delete_document(
                collection_name=collection_name,
                document_id=document_id,
            )
            await self._emit(
                "rag.document.deleted",
                {
                    "document_id": document_id,
                    "collection": collection_name,
                },
            )
            return True
        except Exception as e:
            logger.error("Failed to delete document %s: %s", document_id, e)
            return False
