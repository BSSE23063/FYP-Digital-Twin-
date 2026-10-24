"""
Retrieval against a twin's own Qdrant collection.

Tenant isolation is physical here (a separate collection per twin — see
backend/vectordb/collections.py), so unlike a shared-pool design there's no
twin_id filter to remember. A brand-new twin with nothing ingested yet has no
collection at all: both search functions check collection_exists() first and
return [] rather than letting the client raise, instead of trusting every
caller to call ensure_twin_collection() before searching.
"""
from typing import Any, Dict, List

from qdrant_client.http import models

from backend.vectordb.client import get_client
from backend.vectordb.collections import twin_collection_name


def search_twin_knowledge(
    twin_id: str,
    query_vector: List[float],
    allowed_visibilities: List[str],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Searches a twin's knowledge chunks, enforcing the caller's access-tier
    visibility filter."""
    client = get_client()
    collection_name = twin_collection_name(twin_id)
    if not client.collection_exists(collection_name):
        return []

    query_filter = models.Filter(
        must=[
            models.FieldCondition(key="point_kind", match=models.MatchValue(value="knowledge")),
            models.FieldCondition(key="visibility", match=models.MatchAny(any=allowed_visibilities)),
        ]
    )
    response = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
    )
    return [
        {
            "content": p.payload.get("document", ""),
            "source_id": p.payload.get("source_id"),
            "score": p.score,
            "metadata": p.payload,
        }
        for p in response.points
    ]


def search_visitor_memory(
    twin_id: str,
    visitor_id: str,
    query_vector: List[float],
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Searches what this twin remembers about this specific visitor. Run as a
    separate call from search_twin_knowledge so each result set stays
    independently debuggable."""
    client = get_client()
    collection_name = twin_collection_name(twin_id)
    if not client.collection_exists(collection_name):
        return []

    query_filter = models.Filter(
        must=[
            models.FieldCondition(key="point_kind", match=models.MatchValue(value="memory")),
            models.FieldCondition(key="visitor_id", match=models.MatchValue(value=visitor_id)),
        ]
    )
    response = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
    )
    return [
        {
            "content": p.payload.get("document", ""),
            "score": p.score,
            "metadata": p.payload,
        }
        for p in response.points
    ]
