from __future__ import annotations

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.services.rag.config import RAGSettings
from app.services.rag.models import SearchResult
from app.services.rag.vectorstore import BaseVectorStore

if TYPE_CHECKING:
    from app.services.rag.reranker import RerankService

logger = logging.getLogger(__name__)


def _result_key(r: SearchResult) -> str:
    if r.parent_doc_id:
        return f"{r.parent_doc_id}:{r.metadata.get('chunk_num', '')}"
    return hashlib.md5(r.content.encode()).hexdigest()


class BaseRetrievalService(ABC):
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        collection_name: str,
        limit: int = 5,
        min_score: float = 0.0,
        filter: str = "",
        tenant_id: str | None = None,
        role: str | None = None,
        current_user_id: str | None = None,
        status_filter: list[str] | None = None,
        custom_filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        pass

    @abstractmethod
    async def retrieve_by_document(
        self,
        query: str,
        collection_name: str,
        document_id: str,
        limit: int = 3,
        tenant_id: str | None = None,
        role: str | None = None,
        current_user_id: str | None = None,
        status_filter: list[str] | None = None,
        custom_filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        pass


class RetrievalService(BaseRetrievalService):
    def __init__(
        self,
        vector_store: BaseVectorStore,
        settings: RAGSettings,
        rerank_service: RerankService | None = None,
    ):
        self.store = vector_store
        self.settings = settings
        self.rerank_service = rerank_service
        self._reranker_enabled = rerank_service is not None and rerank_service.is_enabled
        self._hybrid_enabled = settings.enable_hybrid_search

    @staticmethod
    def _rrf_fuse(
        vector_results: list[SearchResult],
        bm25_results: list[SearchResult],
        k: int = 60,
    ) -> list[SearchResult]:
        """Reciprocal Rank Fusion of vector and BM25 results."""
        scores: dict[str, float] = {}
        result_map: dict[str, SearchResult] = {}

        for rank, r in enumerate(vector_results):
            key = _result_key(r)
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
            result_map[key] = r

        for rank, r in enumerate(bm25_results):
            key = _result_key(r)
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
            if key not in result_map:
                result_map[key] = r

        sorted_keys = sorted(scores, key=lambda x: scores[x], reverse=True)
        return [
            SearchResult(
                content=result_map[key].content,
                score=scores[key],
                metadata=result_map[key].metadata,
                parent_doc_id=result_map[key].parent_doc_id,
            )
            for key in sorted_keys
        ]

    async def _bm25_search(
        self, query: str, collection_name: str, limit: int
    ) -> list[SearchResult]:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank-bm25 not installed, skipping BM25 search")
            return []

        docs = await self.store.get_documents(collection_name)
        if not docs:
            return []

        all_results = await self.store.search(
            collection_name=collection_name, query=query, limit=min(limit * 10, 100)
        )
        if not all_results:
            return []

        corpus = [r.content.lower().split() for r in all_results]
        bm25 = BM25Okapi(corpus)
        query_tokens = query.lower().split()
        bm25_scores = bm25.get_scores(query_tokens)

        scored = sorted(zip(all_results, bm25_scores), key=lambda x: x[1], reverse=True)
        return [
            SearchResult(
                content=r.content,
                score=float(s),
                metadata=r.metadata,
                parent_doc_id=r.parent_doc_id,
            )
            for r, s in scored[:limit]
            if s > 0
        ]

    def _build_security_filter(
        self,
        tenant_id: str | None,
        role: str | None,
        current_user_id: str | None,
        status_filter: list[str] | None = None,
        custom_filters: dict[str, Any] | None = None,
    ) -> Any:
        import re
        from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

        # Deny by default: if tenant_id is missing, restrict to a non-existent org
        if not tenant_id:
            logger.warning("[RETRIEVAL] tenant_id is missing in query context! Denying access by default.")
            return Filter(
                must=[FieldCondition(key="metadata.tenant_id", match=MatchValue(value="DENY_ALL"))]
            )

        must_conditions = [
            FieldCondition(key="metadata.tenant_id", match=MatchValue(value=str(tenant_id)))
        ]

        # Enforce status filter: normal query returns approved cards only, by default.
        # Admins and Owners can explicitly override the status filter if specified.
        allowed_statuses = ["approved"]
        if (role in ("admin", "owner")) and status_filter:
            allowed_statuses = status_filter
            
        must_conditions.append(
            FieldCondition(key="metadata.status", match=MatchAny(any=allowed_statuses))
        )

        # RBAC permissions filtering
        if role == "viewer":
            must_conditions.append(
                FieldCondition(
                    key="metadata.permissions",
                    match=MatchAny(any=["viewer-only", "viewer", "read", "public"])
                )
            )
        elif role == "member":
            must_conditions.append(
                FieldCondition(
                    key="metadata.permissions",
                    match=MatchAny(any=["viewer-only", "viewer", "read", "public", "member-only", "member"])
                )
            )
        # Admins and Owners bypass permissions checks.

        # Confidentiality filtering: restrict high confidentiality to document owner or organization owner
        if role != "owner":
            user_val = str(current_user_id) if current_user_id else "DENY_ALL"
            must_conditions.append(
                Filter(
                    should=[
                        # Option A: Document confidentiality is NOT high
                        FieldCondition(
                            key="metadata.confidentiality",
                            match=MatchAny(any=["low", "medium", "public"])
                        ),
                        # Option B: Document belongs to the user
                        FieldCondition(
                            key="metadata.owner",
                            match=MatchValue(value=user_val)
                        )
                    ]
                )
            )

        # Apply any additional custom filters from caller (§5.2)
        if custom_filters:
            for k, val in custom_filters.items():
                if val is not None:
                    if k == "tags" and isinstance(val, list):
                        must_conditions.append(
                            FieldCondition(key="metadata.tags", match=MatchAny(any=val))
                        )
                    elif isinstance(val, list):
                        must_conditions.append(
                            FieldCondition(key=f"metadata.{k}", match=MatchAny(any=val))
                        )
                    else:
                        must_conditions.append(
                            FieldCondition(key=f"metadata.{k}", match=MatchValue(value=val))
                        )

        return Filter(must=must_conditions)

    async def retrieve(
        self,
        query: str,
        collection_name: str,
        limit: int = 5,
        min_score: float = 0.0,
        filter: str = "",
        use_reranker: bool = False,
        tenant_id: str | None = None,
        role: str | None = None,
        current_user_id: str | None = None,
        status_filter: list[str] | None = None,
        custom_filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        import re
        should_rerank = use_reranker and self._reranker_enabled

        # Fetch 3x when reranking: gives the reranker room to eliminate weak candidates
        fetch_multiplier = 3 if should_rerank else 2

        logger.info(
            "[RETRIEVAL] Query: '%.50s...', collection: %s, limit: %d, filter: '%s', rerank: %s, tenant: %s, role: %s, status_filter: %s, custom_filters: %s",
            query,
            collection_name,
            limit,
            filter,
            should_rerank,
            tenant_id,
            role,
            status_filter,
            custom_filters,
        )

        start_time = time.time()

        # Build security and access control filters
        qdrant_filter = self._build_security_filter(
            tenant_id, role, current_user_id, status_filter, custom_filters
        )
        if filter and "parent_doc_id" in filter:
            m = re.search(r'parent_doc_id\s*==\s*"([^"]+)"', filter)
            if m:
                from qdrant_client.models import FieldCondition, MatchValue
                qdrant_filter.must.append(
                    FieldCondition(key="parent_doc_id", match=MatchValue(value=m.group(1)))
                )

        from qdrant_client.http.exceptions import UnexpectedResponse
        try:
            pipeline_results = await self.store.search(
                collection_name=collection_name,
                query=query,
                limit=limit * fetch_multiplier,
                query_filter=qdrant_filter,
            )

            search_time = time.time() - start_time
            logger.info(
                "[RETRIEVAL] Vector search completed in %.3fs, found %d results",
                search_time,
                len(pipeline_results),
            )

            if self._hybrid_enabled:
                bm25_results = await self._bm25_search(query, collection_name, limit * fetch_multiplier)
                if bm25_results:
                    pipeline_results = self._rrf_fuse(pipeline_results, bm25_results)
                    logger.info("[RETRIEVAL] Hybrid search: fused %d results", len(pipeline_results))
        except UnexpectedResponse as e:
            if e.status_code == 404:
                logger.warning(
                    "[RETRIEVAL] Collection '%s' does not exist in Qdrant. Returning empty results.",
                    collection_name
                )
                return []
            raise

        for i, r in enumerate(pipeline_results[:3]):
            logger.debug(
                "[RETRIEVAL] Initial result #%d: score=%.4f, content='%.50s...'",
                i + 1,
                r.score,
                r.content,
            )

        if should_rerank and self.rerank_service:
            logger.info("[RETRIEVAL] Applying reranking...")
            rerank_start = time.time()
            pipeline_results = await self.rerank_service.rerank(
                query=query,
                results=pipeline_results,
                top_k=limit * 2,  # Get more from reranker before filtering
            )

            rerank_time = time.time() - rerank_start
            logger.info(
                "[RETRIEVAL] Reranking completed in %.3fs, returned %d results",
                rerank_time,
                len(pipeline_results),
            )
        elif use_reranker and not self._reranker_enabled:
            logger.warning("[RETRIEVAL] Reranking requested but not configured - skipping")

        filtered_results = [res for res in pipeline_results if res.score >= min_score]

        seen_keys: set[str] = set()
        seen_parent_cards: set[str] = set()
        deduped_results: list[SearchResult] = []
        for r in filtered_results:
            key = _result_key(r)
            
            # Collapse sibling chunks: only return the highest scoring chunk from any parent card
            parent_card = r.metadata.get("parent_card_id") or r.metadata.get("card_id")
            if parent_card:
                if parent_card in seen_parent_cards:
                    logger.info(
                        "[RETRIEVAL] Collapsed sibling chunk hit for parent card %s to prioritize diversity.",
                        parent_card,
                    )
                    continue
                seen_parent_cards.add(parent_card)

            if key not in seen_keys:
                seen_keys.add(key)
                deduped_results.append(r)

        if len(deduped_results) < len(filtered_results):
            logger.info(
                "[RETRIEVAL] Deduplicated: %d -> %d results",
                len(filtered_results),
                len(deduped_results),
            )

        for i, r in enumerate(deduped_results[:3]):
            logger.debug(
                "[RETRIEVAL] Final result #%d: score=%.4f, content='%.50s...'",
                i + 1,
                r.score,
                r.content,
            )

        final_results = deduped_results[:limit]

        total_time = time.time() - start_time
        logger.info(
            "[RETRIEVAL] Total retrieval time: %.3fs, returning %d results",
            total_time,
            len(final_results),
        )

        return final_results

    async def retrieve_multi(
        self,
        query: str,
        collection_names: list[str],
        limit: int = 5,
        min_score: float = 0.0,
        use_reranker: bool = False,
        tenant_id: str | None = None,
        role: str | None = None,
        current_user_id: str | None = None,
        status_filter: list[str] | None = None,
        custom_filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        all_results: list[SearchResult] = []
        for name in collection_names:
            try:
                results = await self.retrieve(
                    query=query,
                    collection_name=name,
                    limit=limit,
                    min_score=min_score,
                    use_reranker=use_reranker,
                    tenant_id=tenant_id,
                    role=role,
                    current_user_id=current_user_id,
                    status_filter=status_filter,
                    custom_filters=custom_filters,
                )
                # Tag results with collection name in metadata
                for r in results:
                    r.metadata["collection"] = name
                all_results.extend(results)
            except Exception:
                logger.exception("[RETRIEVAL] Failed to search collection '%s'", name)

        all_results.sort(key=lambda r: r.score, reverse=True)

        seen_keys: set[str] = set()
        deduped: list[SearchResult] = []
        for r in all_results:
            key = _result_key(r)
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(r)

        return deduped[:limit]

    async def retrieve_by_document(
        self,
        query: str,
        collection_name: str,
        document_id: str,
        limit: int = 3,
        use_reranker: bool = False,
        tenant_id: str | None = None,
        role: str | None = None,
        current_user_id: str | None = None,
        status_filter: list[str] | None = None,
        custom_filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Retrieve chunks restricted to a single document."""
        # Sanitize document_id to prevent filter injection
        sanitized_id = document_id.replace('"', "").replace("\\", "")
        filter_expr = f'parent_doc_id == "{sanitized_id}"'
        logger.info(
            "[RETRIEVAL] Retrieve by document: doc_id=%s, query='%.30s...', limit=%d, rerank=%s, tenant=%s, role=%s, status_filter=%s, custom_filters=%s",
            document_id,
            query,
            limit,
            use_reranker,
            tenant_id,
            role,
            status_filter,
            custom_filters,
        )
        return await self.retrieve(
            query=query,
            collection_name=collection_name,
            limit=limit,
            filter=filter_expr,
            use_reranker=use_reranker,
            tenant_id=tenant_id,
            role=role,
            current_user_id=current_user_id,
            status_filter=status_filter,
            custom_filters=custom_filters,
        )
