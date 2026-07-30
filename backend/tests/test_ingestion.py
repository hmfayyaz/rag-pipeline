import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.rag.documents import DocumentProcessor
from app.services.rag.embeddings import EmbeddingService
from app.services.rag.ingestion import IngestionService
from app.services.rag.models import Document, DocumentMetadata, DocumentPage
from app.services.rag.vectorstore import QdrantVectorStore


@pytest.fixture
def mock_embeddings():
    embedder = MagicMock(spec=EmbeddingService)
    # Simulate embedding vectors matching expected dimensions
    embedder.embed_document = MagicMock(return_value=[[0.1] * 768])
    embedder.embed_query = MagicMock(return_value=[0.1] * 768)
    embedder.embed_text = AsyncMock(return_value=([0.1] * 768, {"indices": [1, 2], "values": [0.5, 0.5]}))
    return embedder


@pytest.fixture
def mock_rag_settings():
    settings = MagicMock()
    settings.collection_name = "test_collection"
    settings.chunk_size = 512
    settings.chunk_overlap = 50
    settings.chunking_strategy = "recursive"
    settings.embeddings_config.dim = 768
    settings.embeddings_config.model = "nomic-embed-text"
    return settings


@pytest.mark.anyio
async def test_document_processor_creates_token_chunks(mock_rag_settings):
    """Verify DocumentProcessor splits file into correct chunks using RecursiveCharacterTextSplitter."""
    processor = DocumentProcessor(mock_rag_settings)
    
    # Write a temporary text file to parse
    test_file = Path("test_sample.txt")
    test_file.write_text("Hello world. This is a sentence. " * 50, encoding="utf-8")
    
    try:
        doc = await processor.process_file(test_file)
        assert len(doc.pages) == 1
        assert doc.metadata.filename == "test_sample.txt"
        assert doc.chunked_pages is not None
        assert len(doc.chunked_pages) > 0
        for chunk in doc.chunked_pages:
            assert chunk.chunk_content != ""
            assert chunk.parent_doc_id == doc.id
    finally:
        test_file.unlink(missing_ok=True)


@pytest.mark.anyio
async def test_ingest_file_assigns_metadata(mock_embeddings, mock_rag_settings):
    """Verify IngestionService maps metadata values onto Document models."""
    processor = MagicMock(spec=DocumentProcessor)
    
    # Create fake parsed document
    fake_doc = Document(
        pages=[DocumentPage(page_num=1, content="mock content")],
        metadata=DocumentMetadata(
            filename="mock.pdf",
            filesize=100,
            filetype="pdf",
            source_path="mock.pdf",
            content_hash="hash123",
        )
    )
    processor.process_file = AsyncMock(return_value=fake_doc)
    
    # Mock Vector Store to intercept insert
    vector_store = MagicMock(spec=QdrantVectorStore)
    vector_store.insert_document = AsyncMock()
    vector_store.get_documents = AsyncMock(return_value=[])
    
    svc = IngestionService(processor, vector_store)
    
    tenant_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    
    result = await svc.ingest_file(
        filepath=Path("mock.pdf"),
        collection_name="test_collection",
        replace=True,
        source_path="mock.pdf",
        tenant_id=tenant_id,
        area="finance",
        owner=owner_id,
        language="en",
        confidentiality="high",
        permissions="admin-only",
    )
    
    assert result.status.value == "done"
    
    # Check that metadata was correctly mapped to the Document before insertion
    vector_store.insert_document.assert_called_once()
    called_doc = vector_store.insert_document.call_args[1]["document"]
    
    assert called_doc.metadata.tenant_id == tenant_id
    assert called_doc.metadata.owner == owner_id
    assert called_doc.metadata.area == "finance"
    assert called_doc.metadata.language == "en"
    assert called_doc.metadata.confidentiality == "high"
    assert called_doc.metadata.permissions == "admin-only"


@pytest.mark.anyio
async def test_qdrant_store_inserts_payload_with_metadata(mock_embeddings, mock_rag_settings):
    """Verify QdrantVectorStore inserts payloads formatting metadata inside Qdrant PointStruct."""
    with patch("app.services.rag.vectorstore.AsyncQdrantClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
        mock_client_cls.return_value = mock_client
        
        store = QdrantVectorStore(mock_rag_settings, mock_embeddings)
        
        tenant_id = str(uuid.uuid4())
        owner_id = str(uuid.uuid4())
        
        fake_doc = Document(
            pages=[DocumentPage(page_num=1, content="chunk content")],
            metadata=DocumentMetadata(
                filename="test.pdf",
                filesize=123,
                filetype="pdf",
                source_path="test.pdf",
                content_hash="hash456",
                tenant_id=tenant_id,
                owner=owner_id,
                area="hr",
                language="ur",
                confidentiality="medium",
                permissions="read",
            )
        )
        # Manually attach chunked page
        from app.services.rag.models import DocumentPageChunk
        fake_doc.chunked_pages = [
            DocumentPageChunk(
                page_num=1,
                content="chunk content",
                chunk_content="chunk content",
                chunk_num=0,
                parent_doc_id=fake_doc.id,
            )
        ]
        
        await store.insert_document("test_collection", fake_doc)
        
        # Verify upsert call
        mock_client.upsert.assert_called_once()
        points = mock_client.upsert.call_args[1]["points"]
        assert len(points) == 1
        
        inserted_payload = points[0].payload
        assert inserted_payload["content"] == "chunk content"
        assert inserted_payload["parent_doc_id"] == fake_doc.id
        
        meta = inserted_payload["metadata"]
        assert meta["tenant_id"] == tenant_id
        assert meta["owner"] == owner_id
        assert meta["area"] == "hr"
        assert meta["language"] == "ur"
        assert meta["confidentiality"] == "medium"
        assert meta["permissions"] == "read"
