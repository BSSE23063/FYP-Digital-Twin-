"""
Embedding providers interface and implementation.
Uses ChromaDB ONNX-accelerated MiniLM embeddings (or sentence-transformers when available).
"""

from abc import ABC, abstractmethod
from typing import List
from backend.config import settings


class BaseEmbeddingProvider(ABC):
    """Abstract interface for embedding models."""

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents/chunks."""
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Embed a single search query."""
        pass


class ONNXMiniLMEmbeddingProvider(BaseEmbeddingProvider):
    """
    High-performance ONNX embedding provider using all-MiniLM-L6-v2.
    Runs fast on CPU without requiring heavy PyTorch binaries.
    """

    def __init__(self):
        from chromadb.utils import embedding_functions
        self._fn = embedding_functions.DefaultEmbeddingFunction()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        embeddings = self._fn(texts)
        return [[float(x) for x in e] for e in embeddings]

    def embed_query(self, text: str) -> List[float]:
        embeddings = self._fn([text])
        return [float(x) for x in embeddings[0]]


def get_embedding_provider() -> BaseEmbeddingProvider:
    """Factory function returning active embedding provider."""
    return ONNXMiniLMEmbeddingProvider()
