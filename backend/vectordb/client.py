"""
Qdrant client initialization (lazy singleton).

Lazy so importing this module never crashes before Settings/the filesystem are
ready, and so a test can swap settings.QDRANT_PATH before the first call.
"""
from functools import lru_cache

from qdrant_client import QdrantClient

from backend.config import settings


@lru_cache(maxsize=1)
def get_client() -> QdrantClient:
    return QdrantClient(path=settings.QDRANT_PATH)
