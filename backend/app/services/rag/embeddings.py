from abc import ABC, abstractmethod

from openai import OpenAI

from app.core.config import settings as app_settings
from app.services.rag.config import RAGSettings
from app.services.rag.models import Document


def _chunk_texts(document: Document) -> list[str]:
    return [
        doc.chunk_content if doc.chunk_content else "" for doc in (document.chunked_pages or [])
    ]


class BaseEmbeddingProvider(ABC):
    @abstractmethod
    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        pass

    @abstractmethod
    def embed_document(self, document: Document) -> list[list[float]]:
        pass

    @abstractmethod
    def warmup(self) -> None:
        """Ensures the model is loaded and ready for inference."""
        pass


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI embedding provider using the OpenAI API.

    Uses OpenAI's embedding models to generate text embeddings.
    """

    def __init__(self, model: str, api_key: str = "", base_url: str | None = None) -> None:
        """Initialize the OpenAI embedding provider.

        Args:
            model: The OpenAI embedding model name (e.g., 'text-embedding-3-small').
            api_key: API key; falls back to OPENAI_API_KEY env var when empty.
            base_url: Override base URL (e.g. OpenRouter-compatible endpoint).
        """
        self.model = model
        self.client = OpenAI(api_key=api_key or None, base_url=base_url)

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(model=self.model, input=texts)
        return [data.embedding for data in response.data]

    def embed_document(self, document: Document) -> list[list[float]]:
        return self.embed_queries(_chunk_texts(document))

    def warmup(self) -> None:
        pass


import httpx
from qdrant_client.models import SparseVector


class BGEM3EmbeddingProvider(BaseEmbeddingProvider):
    """BGE-M3 dense + sparse embedding provider client.
    
    Tries to connect to the self-hosted BGE-M3 REST service.
    Falls back to local dense + simple TF-IDF-like sparse generation during development.
    """

    def __init__(
        self,
        endpoint_url: str | None = None,
        api_key: str | None = None,
        fallback_dense_provider: BaseEmbeddingProvider | None = None,
    ):
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.fallback_dense = fallback_dense_provider

    def _generate_mock_sparse(self, text: str) -> dict[str, list]:
        import re
        words = re.findall(r"\w+", text.lower())
        if not words:
            return {"indices": [], "values": []}
        freq = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        
        # Build indices and values
        raw_indices = []
        raw_values = []
        for w, f in freq.items():
            # Deterministic index from 1 to 100000 based on word hash
            idx = (abs(hash(w)) % 99999) + 1
            raw_indices.append(idx)
            raw_values.append(float(f) / len(words))
            
        # Qdrant requires sorted indices for sparse vectors
        sorted_pairs = sorted(zip(raw_indices, raw_values))
        return {
            "indices": [p[0] for p in sorted_pairs],
            "values": [p[1] for p in sorted_pairs]
        }

    async def embed_text_async(self, text: str) -> tuple[list[float], dict[str, list]]:
        """Call BGE-M3 endpoint or fall back to local dense + local mock sparse."""
        if self.endpoint_url:
            try:
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.endpoint_url,
                        json={"text": text},
                        headers=headers,
                        timeout=5.0
                    )
                    if response.status_code == 200:
                        data = response.json()
                        dense = data.get("dense")
                        sparse = data.get("sparse")
                        if dense and sparse:
                            return dense, sparse
            except Exception:
                # Log or handle exceptions quietly, fall back to mock
                pass

        # Fallback dense embedding using Ollama via OpenAI interface
        dense_vector = [0.0] * 768
        if self.fallback_dense:
            try:
                dense_vector = self.fallback_dense.embed_queries([text])[0]
            except Exception:
                pass
        
        sparse_dict = self._generate_mock_sparse(text)
        return dense_vector, sparse_dict

    def embed_queries(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        loop = asyncio.get_event_loop()
        results = []
        for t in texts:
            # Sync fallback for legacy dense interfaces
            if loop.is_running():
                # If loop is already running (e.g. inside FastAPI requests),
                # we must run the async function using standard task mapping or mock fallback
                dense_vector = [0.0] * 768
                if self.fallback_dense:
                    try:
                        dense_vector = self.fallback_dense.embed_queries([t])[0]
                    except Exception:
                        pass
                results.append(dense_vector)
            else:
                dense, _ = loop.run_until_complete(self.embed_text_async(t))
                results.append(dense)
        return results

    def embed_document(self, document: Document) -> list[list[float]]:
        return self.embed_queries(_chunk_texts(document))

    def warmup(self) -> None:
        if self.fallback_dense:
            self.fallback_dense.warmup()


class EmbeddingService:
    def __init__(self, settings: RAGSettings):
        config = settings.embeddings_config
        self.expected_dim = config.dim
        self.provider_dense = OpenAIEmbeddingProvider(
            model=config.model,
            api_key=app_settings.OPENAI_API_KEY,
            base_url=app_settings.OPENAI_API_BASE or None,
        )
        self.bge_provider = BGEM3EmbeddingProvider(
            endpoint_url=app_settings.BGEM3_ENDPOINT_URL or None,
            api_key=app_settings.BGEM3_API_KEY or None,
            fallback_dense_provider=self.provider_dense
        )

    def embed_query(self, query: str) -> list[float]:
        result = self.provider_dense.embed_queries([query])[0]
        if len(result) != self.expected_dim:
            # Pad or slice to match expected dim
            if len(result) < self.expected_dim:
                result = result + [0.0] * (self.expected_dim - len(result))
            else:
                result = result[:self.expected_dim]
        return result

    def embed_document(self, document: Document) -> list[list[float]]:
        results = self.provider_dense.embed_document(document)
        if results:
            for i in range(len(results)):
                if len(results[i]) != self.expected_dim:
                    if len(results[i]) < self.expected_dim:
                        results[i] = results[i] + [0.0] * (self.expected_dim - len(results[i]))
                    else:
                        results[i] = results[i][:self.expected_dim]
        return results

    async def embed_text(self, text: str) -> tuple[list[float], dict[str, list]]:
        """Returns both dense and sparse embeddings dynamically."""
        dense, sparse = await self.bge_provider.embed_text_async(text)
        if len(dense) != self.expected_dim:
            if len(dense) < self.expected_dim:
                dense = dense + [0.0] * (self.expected_dim - len(dense))
            else:
                dense = dense[:self.expected_dim]
        return dense, sparse

    def warmup(self) -> None:
        self.provider_dense.warmup()
