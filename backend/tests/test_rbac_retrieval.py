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
    """Verify that a viewer is restricted to viewer-level document permissions and approved status."""
    svc = RetrievalService(mock_vector_store, mock_rag_settings)
    
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    
    q_filter = svc._build_security_filter(
        tenant_id=tenant_id,
        role="viewer",
        current_user_id=user_id
    )
    
    assert isinstance(q_filter, Filter)
    conditions = q_filter.must
    assert len(conditions) == 4  # Tenant, Status, Permissions, Confidentiality (since role != owner)
    
    # 1. Tenant match
    assert conditions[0].key == "metadata.tenant_id"
    assert conditions[0].match.value == tenant_id
    
    # 2. Status match (defaults to approved)
    assert conditions[1].key == "metadata.status"
    assert "approved" in conditions[1].match.any

    # 3. Permissions match
    assert conditions[2].key == "metadata.permissions"
    assert isinstance(conditions[2].match, MatchAny)
    assert "viewer" in conditions[2].match.any
    assert "admin-only" not in conditions[2].match.any


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
    assert len(conditions) == 4  # Tenant, Status, Permissions, Confidentiality
    
    # Permissions match
    assert conditions[2].key == "metadata.permissions"
    assert isinstance(conditions[2].match, MatchAny)
    assert "member-only" in conditions[2].match.any
    assert "admin-only" not in conditions[2].match.any


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
    assert len(conditions) == 3  # Tenant, Status, Confidentiality (role != owner gets confidentiality checks)
    
    assert conditions[0].key == "metadata.tenant_id"
    assert conditions[0].match.value == tenant_id
    assert conditions[1].key == "metadata.status"


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
    assert len(conditions) == 2  # Tenant, Status only!
    assert conditions[0].key == "metadata.tenant_id"
    assert conditions[0].match.value == tenant_id
    assert conditions[1].key == "metadata.status"


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
    assert len(conditions) == 3  # Tenant, Status, Confidentiality
    
    confidentiality_filter = conditions[2]
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


def test_build_security_filter_status_override(mock_vector_store, mock_rag_settings):
    """Verify status filter overrides are permitted for admins/owners but ignored for viewers."""
    svc = RetrievalService(mock_vector_store, mock_rag_settings)
    
    tenant_id = str(uuid.uuid4())
    
    # Admin tries to query proposed and approved status
    q_filter_admin = svc._build_security_filter(
        tenant_id=tenant_id,
        role="admin",
        current_user_id=str(uuid.uuid4()),
        status_filter=["proposed", "approved"]
    )
    assert "proposed" in q_filter_admin.must[1].match.any
    assert "approved" in q_filter_admin.must[1].match.any

    # Viewer tries to override status filter
    q_filter_viewer = svc._build_security_filter(
        tenant_id=tenant_id,
        role="viewer",
        current_user_id=str(uuid.uuid4()),
        status_filter=["draft", "proposed"]
    )
    # Ignored: viewer should still only get "approved"
    assert q_filter_viewer.must[1].match.any == ["approved"]


def test_build_security_filter_custom_metadata(mock_vector_store, mock_rag_settings):
    """Verify custom metadata filters (type, tags, project) are correctly mapped to Qdrant."""
    svc = RetrievalService(mock_vector_store, mock_rag_settings)
    
    q_filter = svc._build_security_filter(
        tenant_id=str(uuid.uuid4()),
        role="owner",
        current_user_id=str(uuid.uuid4()),
        custom_filters={
            "type": "Decision",
            "project": "F2",
            "tags": ["critical", "release"]
        }
    )
    
    # Owner must conditions: Tenant, Status, Type, Project, Tags
    conditions = q_filter.must
    assert len(conditions) == 5
    
    assert conditions[2].key == "metadata.type"
    assert conditions[2].match.value == "Decision"
    
    assert conditions[3].key == "metadata.project"
    assert conditions[3].match.value == "F2"
    
    assert conditions[4].key == "metadata.tags"
    assert isinstance(conditions[4].match, MatchAny)
    assert "critical" in conditions[4].match.any


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
