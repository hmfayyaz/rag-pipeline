import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.rag.retrieval import RetrievalService
from app.services.rag.vectorstore import BaseVectorStore
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny


@pytest.fixture
def mock_vector_store():
    store = MagicMock(spec=BaseVectorStore)
    store.search = AsyncMock(return_value=[])
    return store


@pytest.fixture
def mock_rag_settings():
    settings = MagicMock()
    settings.enable_hybrid_search = False
    return settings


def test_build_security_filter_viewer(mock_vector_store, mock_rag_settings):
    """Verify that a viewer is restricted to viewer-level document permissions."""
    svc = RetrievalService(mock_vector_store, mock_rag_settings)
    
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    
    q_filter = svc._build_security_filter(
        tenant_id=tenant_id,
        role="viewer",
        current_user_id=user_id
    )
    
    assert isinstance(q_filter, Filter)
    # Check must conditions
    conditions = q_filter.must
    assert len(conditions) == 3  # Tenant, Permissions, Confidentiality (since role != owner)
    
    # 1. Tenant match
    assert conditions[0].key == "metadata.tenant_id"
    assert conditions[0].match.value == tenant_id
    
    # 2. Permissions match
    assert conditions[1].key == "metadata.permissions"
    assert isinstance(conditions[1].match, MatchAny)
    assert "viewer" in conditions[1].match.any
    assert "admin-only" not in conditions[1].match.any


def test_build_security_filter_member(mock_vector_store, mock_rag_settings):
    """Verify that a member can see member-level permissions but not admin-only."""
    svc = RetrievalService(mock_vector_store, mock_rag_settings)
    
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    
    q_filter = svc._build_security_filter(
        tenant_id=tenant_id,
        role="member",
        current_user_id=user_id
    )
    
    conditions = q_filter.must
    assert len(conditions) == 3
    
    # Permissions match
    assert conditions[1].key == "metadata.permissions"
    assert isinstance(conditions[1].match, MatchAny)
    assert "member-only" in conditions[1].match.any
    assert "admin-only" not in conditions[1].match.any


def test_build_security_filter_admin_bypass(mock_vector_store, mock_rag_settings):
    """Verify that an admin/owner bypasses permissions filter."""
    svc = RetrievalService(mock_vector_store, mock_rag_settings)
    
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    
    q_filter = svc._build_security_filter(
        tenant_id=tenant_id,
        role="admin",
        current_user_id=user_id
    )
    
    conditions = q_filter.must
    assert len(conditions) == 2  # Tenant, Confidentiality (role != owner gets confidentiality checks)
    
    assert conditions[0].key == "metadata.tenant_id"
    assert conditions[0].match.value == tenant_id


def test_build_security_filter_owner_bypass_all(mock_vector_store, mock_rag_settings):
    """Verify that the organization owner bypasses both permissions and confidentiality filters."""
    svc = RetrievalService(mock_vector_store, mock_rag_settings)
    
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    
    q_filter = svc._build_security_filter(
        tenant_id=tenant_id,
        role="owner",
        current_user_id=user_id
    )
    
    conditions = q_filter.must
    assert len(conditions) == 1  # Only tenant_id condition remains!
    assert conditions[0].key == "metadata.tenant_id"
    assert conditions[0].match.value == tenant_id


def test_build_security_filter_confidentiality_restriction(mock_vector_store, mock_rag_settings):
    """Verify that high confidentiality documents are hidden from non-owners unless they uploaded it."""
    svc = RetrievalService(mock_vector_store, mock_rag_settings)
    
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    
    q_filter = svc._build_security_filter(
        tenant_id=tenant_id,
        role="admin",  # Admin gets confidentiality check, bypasses permissions
        current_user_id=user_id
    )
    
    conditions = q_filter.must
    assert len(conditions) == 2
    
    confidentiality_filter = conditions[1]
    assert isinstance(confidentiality_filter, Filter)
    
    # Should contain OR conditions for low/med confidentiality OR user ownership
    should_conds = confidentiality_filter.should
    assert len(should_conds) == 2
    
    # Option A: low/medium/public
    assert should_conds[0].key == "metadata.confidentiality"
    assert isinstance(should_conds[0].match, MatchAny)
    assert "public" in should_conds[0].match.any
    assert "high" not in should_conds[0].match.any
    
    # Option B: matches user_id
    assert should_conds[1].key == "metadata.owner"
    assert should_conds[1].match.value == user_id


@pytest.mark.anyio
async def test_retrieve_passes_qdrant_filter(mock_vector_store, mock_rag_settings):
    """Verify retrieve constructs and passes Filter object to vector store search."""
    svc = RetrievalService(mock_vector_store, mock_rag_settings)
    
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    
    await svc.retrieve(
        query="test query",
        collection_name="test_collection",
        tenant_id=tenant_id,
        role="viewer",
        current_user_id=user_id
    )
    
    mock_vector_store.search.assert_called_once()
    called_kwargs = mock_vector_store.search.call_args[1]
    
    qdrant_filter = called_kwargs["query_filter"]
    assert isinstance(qdrant_filter, Filter)
    
    # Check that tenant condition is in the must list
    assert qdrant_filter.must[0].key == "metadata.tenant_id"
    assert qdrant_filter.must[0].match.value == tenant_id
