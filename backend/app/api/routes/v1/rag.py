"""RAG API routes — collection management, search, document upload, sync, status stream.

Routes are HTTP plumbing only. Business logic, file I/O, task dispatch, and Redis
pub/sub all live in their respective services. Domain exceptions raised by services are
mapped to HTTP responses by the global exception handlers in
``app.api.exception_handlers``; routes do not catch and re-wrap them.
"""

import contextlib
from typing import Any

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import (
    ActiveOrg,
    CurrentAdmin,
    CurrentUser,
    DBSession,
    IngestionSvc,
    KnowledgeBaseSvc,
    RAGDocumentSvc,
    RAGSyncSvc,
    RetrievalSvc,
    SyncSourceSvc,
    VectorStoreSvc,
)
from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.schemas.rag import (
    RAGCollectionInfo,
    RAGCollectionList,
    RAGDocumentList,
    RAGIngestResponse,
    RAGMessageResponse,
    RAGQueryCitation,
    RAGQueryRequest,
    RAGQueryResponse,
    RAGRetryResponse,
    RAGSearchRequest,
    RAGSearchResponse,
    RAGSearchResult,
    RAGSyncLogList,
    RAGSyncRequest,
    RAGSyncResponse,
    RAGTrackedDocumentList,
    SupportedFormatsResponse,
    RAGCardIngestRequest,
)
from app.schemas.sync_source import (
    ConnectorList,
    SyncSourceClone,
    SyncSourceCreate,
    SyncSourceList,
    SyncSourceRead,
    SyncSourceUpdate,
)
from app.services.rag.config import get_supported_formats

router = APIRouter()


@router.get("/supported-formats", response_model=SupportedFormatsResponse)
async def get_supported_formats_endpoint() -> Any:
    """Return file formats supported by the current PDF parser configuration."""
    parser_name = getattr(settings, "PDF_PARSER", "pymupdf")
    return {"parser": parser_name, "formats": sorted(get_supported_formats(parser_name))}


@router.get("/collections", response_model=RAGCollectionList)
async def list_collections(
    kb_svc: KnowledgeBaseSvc,
    admin: CurrentAdmin,
    active_org: ActiveOrg,
) -> Any:
    """List collections derived from Knowledge Base records.

    Single source of truth = KnowledgeBase rows, so /rag and /kb stay
    consistent: a freshly-created KB (whose Milvus collection only materializes
    after the first document is ingested) still appears here, and dropping a
    collection here removes the KB too.
    """
    names = await kb_svc.list_accessible_collection_names(
        user_id=admin.id, organization_id=active_org.id
    )
    return RAGCollectionList(items=names)


@router.post(
    "/collections/{name}",
    status_code=status.HTTP_201_CREATED,
    response_model=RAGMessageResponse,
)
async def create_collection(
    name: str,
    vector_store: VectorStoreSvc,
    _: CurrentAdmin,
    kb_svc: KnowledgeBaseSvc,
    admin: CurrentAdmin,
    active_org: ActiveOrg,
) -> Any:
    """Create and initialize a new collection.

    Also creates a matching KnowledgeBase row (idempotent) so the collection
    shows up on /kb as well as /rag.
    """
    await vector_store.create_collection(name)
    await kb_svc.create_for_rag_collection(name, user_id=admin.id, organization_id=active_org.id)
    return RAGMessageResponse(message=f"Collection '{name}' created successfully.")


@router.delete(
    "/collections/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def drop_collection(
    name: str,
    vector_store: VectorStoreSvc,
    rag_doc_svc: RAGDocumentSvc,
    _: CurrentAdmin,
    kb_svc: KnowledgeBaseSvc,
) -> None:
    """Drop a collection — vectors, SQL document records, and the KB row.

    The Milvus collection may not exist yet for a zero-document KB, so the
    vector-store drop is best-effort; the KB + SQL cleanup still runs.
    """
    with contextlib.suppress(Exception):
        await vector_store.delete_collection(name)
    await rag_doc_svc.delete_by_collection(name)
    await kb_svc.delete_by_collection_name(name)


@router.get("/collections/{name}/info", response_model=RAGCollectionInfo)
async def get_collection_info(
    name: str,
    vector_store: VectorStoreSvc,
    _: CurrentAdmin,
) -> Any:
    """Retrieve stats for a specific collection."""
    return await vector_store.get_collection_info(name)


@router.get("/collections/{name}/documents", response_model=RAGDocumentList)
async def list_documents(
    name: str,
    vector_store: VectorStoreSvc,
    _: CurrentAdmin,
) -> Any:
    """List all documents in a specific collection."""
    return await vector_store.get_document_list(name)


@router.post("/search", response_model=RAGSearchResponse)
async def search_documents(
    request: RAGSearchRequest,
    retrieval_service: RetrievalSvc,
    current_user: CurrentUser,
    active_org: ActiveOrg,
    db: DBSession,
    use_reranker: bool = Query(False, description="Whether to use reranking (if configured)"),
) -> Any:
    """Search for relevant document chunks. Supports multi-collection search with tenant and RBAC checks."""
    from app.repositories import member_repo
    membership = await member_repo.get(db, organization_id=active_org.id, user_id=current_user.id)
    role = membership.role if membership else "viewer"

    custom_filters = {
        "type": request.type,
        "area": request.area,
        "project": request.project,
        "tags": request.tags,
        "confidence": request.confidence,
        "owner": request.owner,
        "language": request.language,
    }

    if request.collection_names and len(request.collection_names) > 1:
        results = await retrieval_service.retrieve_multi(
            query=request.query,
            collection_names=request.collection_names,
            limit=request.limit,
            min_score=request.min_score,
            use_reranker=use_reranker,
            tenant_id=str(active_org.id),
            role=role,
            current_user_id=str(current_user.id),
            status_filter=request.status,
            custom_filters=custom_filters,
        )
    else:
        collection = (
            request.collection_names[0] if request.collection_names else request.collection_name
        )
        results = await retrieval_service.retrieve(
            query=request.query,
            collection_name=collection,
            limit=request.limit,
            min_score=request.min_score,
            filter=request.filter or "",
            use_reranker=use_reranker,
            tenant_id=str(active_org.id),
            role=role,
            current_user_id=str(current_user.id),
            status_filter=request.status,
            custom_filters=custom_filters,
        )
    api_results = [RAGSearchResult(**hit.model_dump()) for hit in results]
    return RAGSearchResponse(results=api_results)


@router.post("/query", response_model=RAGQueryResponse)
async def query_knowledge_base(
    request: RAGQueryRequest,
    retrieval_service: RetrievalSvc,
    current_user: CurrentUser,
    active_org: ActiveOrg,
    db: DBSession,
) -> Any:
    """Query the RAG pipeline to retrieve relevant chunks and generate a security-gated answer using the local LLM."""
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.repositories import member_repo

    # Resolve membership role
    membership = await member_repo.get(db, organization_id=active_org.id, user_id=current_user.id)
    role = membership.role if membership else "viewer"

    query_custom_filters = {
        "type": request.type,
        "area": request.area,
        "project": request.project,
        "tags": request.tags,
        "confidence": request.confidence,
        "owner": request.owner,
        "language": request.language,
    }

    # 1. Retrieve security-filtered document chunks
    results = await retrieval_service.retrieve(
        query=request.query,
        collection_name=request.collection_name,
        limit=request.limit,
        min_score=request.min_score,
        use_reranker=request.use_reranker,
        tenant_id=str(active_org.id),
        role=role,
        current_user_id=str(current_user.id),
        status_filter=request.status,
        custom_filters=query_custom_filters,
    )

    # 1.1. Log the access-decision details for auditing
    from app.core.audit import record_audit
    await record_audit(
        db=db,
        actor_user_id=current_user.id,
        action="rag_retrieval_query",
        organization_id=active_org.id,
        target_type="rag_collection",
        target_id=request.collection_name,
        details={
            "query_length": len(request.query),
            "user_role": role,
            "tenant_id": str(active_org.id),
            "allowed_roles": ["viewer", "member", "admin", "owner"],
            "confidentiality_policy": "confidentiality == 'high' strictly restricted to owner or org admin/owner",
            "status_filter": request.status or "approved",
            "decision": "allow",
            "result_count": len(results),
        }
    )

    # 2. Build citations list
    citations = [
        RAGQueryCitation(
            content=hit.content,
            score=hit.score,
            filename=hit.metadata.get("filename", "Unknown"),
            page_num=hit.metadata.get("page_num"),
            parent_doc_id=hit.parent_doc_id,
        )
        for hit in results
    ]

    # 3. Grounded generation
    if not results:
        answer = "I could not find any relevant or permitted documents matching your query in the database."
    else:
        context_str = "\n\n".join([
            f"Document: {hit.metadata.get('filename', 'Unknown')}\n"
            f"Page: {hit.metadata.get('page_num', 'N/A')}\n"
            f"Content: {hit.content}"
            for hit in results
        ])
        
        system_prompt = (
            "You are a helpful AI assistant. Answer the user's question using ONLY the provided document context below.\n"
            "If the answer cannot be found in the context, state that you do not know the answer based on the documents.\n"
            "Always base your answers strictly on the facts provided in the context.\n\n"
            f"--- CONTEXT ---\n{context_str}\n--- END CONTEXT ---"
        )
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=request.query)
        ]
        
        model = ChatOpenAI(
            model=settings.AI_MODEL,
            temperature=0.0,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE or None,
        )
        
        response = await model.ainvoke(messages)
        answer = response.content

    return RAGQueryResponse(answer=answer, citations=citations)


@router.delete(
    "/collections/{name}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_document(
    name: str,
    document_id: str,
    ingestion_service: IngestionSvc,
    _: CurrentAdmin,
) -> None:
    """Delete a specific document by its ID from a collection."""
    success = await ingestion_service.remove_document(name, document_id)
    if not success:
        raise NotFoundError(
            message="Document not found",
            details={"collection": name, "document_id": document_id},
        )


@router.post(
    "/collections/{name}/ingest",
    response_model=RAGIngestResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_file(
    name: str,
    rag_doc_svc: RAGDocumentSvc,
    vector_store: VectorStoreSvc,
    admin: CurrentAdmin,
    active_org: ActiveOrg,
    file: UploadFile = File(...),
    replace: bool = Query(False),
    area: str | None = Query(None, description="Department/Area of the document"),
    language: str | None = Query("en", description="Language of the document"),
    confidentiality: str | None = Query("public", description="Confidentiality level"),
    permissions: str | None = Query("read", description="Access permissions constraint"),
    # Knowledge Card fields
    card_id: str | None = Query(None, description="Canonical card identity"),
    card_type: str | None = Query(None, description="Card type"),
    card_status: str | None = Query("approved", description="Card status"),
    version: int | None = Query(1, description="Card version"),
    project: str | None = Query(None, description="Associated project"),
    tags: list[str] | None = Query(None, description="Free tags"),
    confidence: str | None = Query(None, description="Confidence level"),
    source_pointer: str | None = Query(None, description="Pointer to source document"),
    source_checksum: str | None = Query(None, description="Checksum of original source"),
    source_created_at: str | None = Query(None, description="Original creation date of the source"),
    document_id: str | None = Query(None, description="Lineage identifier"),
    next_review_at: str | None = Query(None, description="Lifecycle reviews"),
    is_chunk: bool | None = Query(False, description="Is it chunked"),
    parent_card_id: str | None = Query(None, description="Parent card identifier"),
    chunk_index: int | None = Query(None, description="Chunk index"),
) -> Any:
    """Upload and queue a file for ingestion into a collection."""
    from uuid import UUID
    from datetime import datetime

    card_uuid = UUID(card_id) if card_id else None
    doc_uuid = UUID(document_id) if document_id else None
    parent_card_uuid = UUID(parent_card_id) if parent_card_id else None
    
    source_created_at_dt = None
    if source_created_at:
        try:
            source_created_at_dt = datetime.fromisoformat(source_created_at)
        except Exception:
            pass
            
    next_review_at_dt = None
    if next_review_at:
        try:
            next_review_at_dt = datetime.fromisoformat(next_review_at)
        except Exception:
            pass

    data = await file.read()
    return await rag_doc_svc.dispatch_upload(
        collection_name=name,
        file_data=data,
        filename=file.filename or "unknown",
        replace=replace,
        vector_store=vector_store,
        organization_id=active_org.id,
        owner_id=admin.id,
        area=area,
        language=language,
        confidentiality=confidentiality,
        permissions=permissions,
        card_id=card_uuid,
        tenant_id=active_org.id,
        card_type=card_type,
        card_status=card_status,
        version=version,
        project=project,
        tags=tags,
        confidence=confidence,
        source_pointer=source_pointer,
        source_checksum=source_checksum,
        source_created_at=source_created_at_dt,
        document_id=doc_uuid,
        next_review_at=next_review_at_dt,
        is_chunk=is_chunk,
        parent_card_id=parent_card_uuid,
        chunk_index=chunk_index,
    )


@router.post(
    "/collections/{name}/ingest/card",
    response_model=RAGIngestResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_card(
    name: str,
    request: RAGCardIngestRequest,
    rag_doc_svc: RAGDocumentSvc,
    vector_store: VectorStoreSvc,
    admin: CurrentAdmin,
    active_org: ActiveOrg,
) -> Any:
    """Ingest a Knowledge Card directly from JSON content (idempotent)."""
    from uuid import UUID
    from datetime import datetime
    from app.services.rag.ingestion import IngestionService
    
    source_created_at_dt = None
    if request.source_created_at:
        try:
            source_created_at_dt = datetime.fromisoformat(request.source_created_at)
        except Exception:
            pass
            
    next_review_at_dt = None
    if request.next_review_at:
        try:
            next_review_at_dt = datetime.fromisoformat(request.next_review_at)
        except Exception:
            pass

    rag_doc = await rag_doc_svc.create_document(
        collection_name=name,
        filename=f"card_{request.card_id}.txt",
        filesize=len(request.content.encode("utf-8")),
        filetype="txt",
        storage_path=request.source_pointer or f"card://{request.card_id}",
        organization_id=active_org.id,
        owner_id=admin.id,
        area=request.area,
        language=request.language,
        confidentiality=request.confidentiality,
        permissions="read",
        # Pass all card details
        card_id=UUID(request.card_id),
        tenant_id=active_org.id,
        card_type=request.type,
        card_status=request.status,
        version=request.version,
        project=request.project,
        tags=request.tags,
        confidence=request.confidence,
        owner=request.owner,
        source_pointer=request.source_pointer,
        source_checksum=request.source_checksum,
        source_created_at=source_created_at_dt,
        document_id=UUID(request.document_id) if request.document_id else None,
        next_review_at=next_review_at_dt,
        is_chunk=False,
        parent_card_id=None,
        chunk_index=None,
    )
    
    ingestion_service = IngestionService.from_settings()
    result = await ingestion_service.ingest_card(
        collection_name=name,
        content=request.content,
        card_id=request.card_id,
        tenant_id=str(active_org.id),
        card_type=request.type,
        card_status=request.status,
        version=request.version,
        area=request.area,
        project=request.project,
        tags=request.tags,
        confidence=request.confidence,
        owner=request.owner,
        language=request.language,
        confidentiality=request.confidentiality,
        permissions="read",
        source_pointer=request.source_pointer,
        source_checksum=request.source_checksum,
        source_created_at=request.source_created_at,
        document_id=request.document_id,
        next_review_at=request.next_review_at,
        is_chunk=False,
        parent_card_id=None,
        chunk_index=None,
    )
    
    if result.status.value == "done":
        await rag_doc_svc.complete_ingestion(
            str(rag_doc.id), vector_document_id=result.document_id
        )
        return RAGIngestResponse(
            id=str(rag_doc.id),
            status="done",
            filename=f"card_{request.card_id}.txt",
            collection=name,
            message="Card successfully ingested.",
        )
    else:
        await rag_doc_svc.fail_ingestion(str(rag_doc.id), error_message=result.error_message)
        raise BadRequestError(message=f"Failed to ingest card: {result.error_message}")


@router.get("/documents", response_model=RAGTrackedDocumentList)
async def list_rag_documents(
    rag_doc_svc: RAGDocumentSvc,
    _: CurrentAdmin,
    collection_name: str | None = Query(None),
) -> Any:
    """List tracked RAG documents."""
    return await rag_doc_svc.list_documents(collection_name)


@router.get("/documents/{doc_id}/download", response_model=None)
async def download_rag_document(
    doc_id: str,
    rag_doc_svc: RAGDocumentSvc,
    _: CurrentAdmin,
) -> Any:
    file_path, filename, mime_type = await rag_doc_svc.get_download_info(doc_id)
    return FileResponse(path=file_path, filename=filename, media_type=mime_type)


@router.delete(
    "/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_rag_document(
    doc_id: str,
    rag_doc_svc: RAGDocumentSvc,
    ingestion_service: IngestionSvc,
    _: CurrentAdmin,
) -> None:
    """Delete a document from SQL, vector store, and file storage."""
    await rag_doc_svc.delete_document(doc_id, ingestion_service)


@router.post("/documents/{doc_id}/retry", response_model=RAGRetryResponse)
async def retry_ingestion(
    doc_id: str,
    rag_doc_svc: RAGDocumentSvc,
    _: CurrentAdmin,
) -> Any:
    """Retry a failed document ingestion."""
    doc = await rag_doc_svc.retry_ingestion(doc_id)
    return RAGRetryResponse(id=str(doc.id), status="processing", message="Retry queued")


@router.get("/sync/logs", response_model=RAGSyncLogList)
async def list_sync_logs(
    rag_sync_svc: RAGSyncSvc,
    _: CurrentAdmin,
    collection_name: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> Any:
    """List sync operation logs."""
    return await rag_sync_svc.list_sync_logs(collection_name=collection_name, limit=limit)


@router.post("/sync/local", response_model=RAGSyncResponse)
async def trigger_local_sync(
    request: RAGSyncRequest,
    rag_sync_svc: RAGSyncSvc,
    _: CurrentAdmin,
) -> Any:
    """Trigger a local directory sync via background task."""
    sync_log = await rag_sync_svc.start_local_sync(
        collection_name=request.collection_name,
        mode=request.mode,
        path=request.path,
    )
    return RAGSyncResponse(
        id=str(sync_log.id),
        status="running",
        message=f"Sync started for '{request.collection_name}' (mode={request.mode})",
    )


@router.delete("/sync/{sync_id}", response_model=RAGMessageResponse)
async def cancel_sync(
    sync_id: str,
    rag_sync_svc: RAGSyncSvc,
    _: CurrentAdmin,
) -> Any:
    """Cancel a running sync operation."""
    await rag_sync_svc.cancel_sync(sync_id)
    return RAGMessageResponse(message="Sync cancelled")


@router.get("/sync/sources", response_model=SyncSourceList)
async def list_sync_sources(
    sync_source_svc: SyncSourceSvc,
    _: CurrentAdmin,
    active_org: ActiveOrg,
    collection_name: str | None = Query(None, description="Filter by KB collection name"),
) -> Any:
    """List sync sources for the active organization.

    Pass ``collection_name`` to see only sources assigned to a specific KB.
    Omit it to list all org-level integrations (assigned and unassigned).
    """
    return await sync_source_svc.list_sources(
        organization_id=active_org.id,
        collection_name=collection_name,
    )


@router.post(
    "/sync/sources",
    response_model=SyncSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_sync_source(
    data: SyncSourceCreate,
    sync_source_svc: SyncSourceSvc,
    _: CurrentAdmin,
    active_org: ActiveOrg,
) -> Any:
    """Create a new sync source configuration.

    Omit ``collection_name`` to create an org-level integration template
    that can later be cloned into one or more knowledge bases.
    """
    return await sync_source_svc.create_source(data, organization_id=active_org.id)


@router.post(
    "/sync/sources/{source_id}/clone",
    response_model=SyncSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def clone_sync_source(
    source_id: str,
    data: SyncSourceClone,
    sync_source_svc: SyncSourceSvc,
    _: CurrentAdmin,
    active_org: ActiveOrg,
) -> Any:
    """Clone an existing integration into a different knowledge base.

    Credentials are decrypted from the source and re-encrypted for the clone.
    The clone is independent — its own schedule and sync history.
    """
    return await sync_source_svc.clone_source(source_id, data, organization_id=active_org.id)


@router.patch("/sync/sources/{source_id}", response_model=SyncSourceRead)
async def update_sync_source(
    source_id: str,
    data: SyncSourceUpdate,
    sync_source_svc: SyncSourceSvc,
    _: CurrentAdmin,
) -> Any:
    """Update an existing sync source configuration."""
    return await sync_source_svc.update_source(source_id, data)


@router.delete(
    "/sync/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_sync_source(
    source_id: str,
    sync_source_svc: SyncSourceSvc,
    _: CurrentAdmin,
) -> None:
    """Delete a sync source configuration."""
    await sync_source_svc.delete_source(source_id)


@router.post("/sync/sources/{source_id}/trigger", response_model=RAGSyncResponse)
async def trigger_sync_source(
    source_id: str,
    sync_source_svc: SyncSourceSvc,
    _: CurrentAdmin,
) -> Any:
    """Trigger a manual sync for a configured source."""
    sync_log = await sync_source_svc.trigger_sync(source_id)
    return RAGSyncResponse(
        id=str(sync_log.id),
        status="running",
        message=f"Sync triggered for source '{source_id}'",
    )


@router.get("/sync/connectors", response_model=ConnectorList)
async def list_connectors(
    sync_source_svc: SyncSourceSvc,
    _: CurrentAdmin,
) -> Any:
    """List available sync connector types with their config schemas."""
    return sync_source_svc.list_connectors()
