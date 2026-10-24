"""
Point-level operations against a twin's own Qdrant collection.

Every point still carries point_kind ('knowledge' | 'memory') so one twin's
collection can serve both the twin's documents and per-visitor memory — the
silo model only changes WHICH collection a point lands in, not this tagging.
"""
import uuid
from typing import Any, Dict, List

from qdrant_client.http import models

from backend.vectordb.client import get_client
from backend.vectordb.collections import ensure_twin_collection


def upsert_knowledge_chunks(
    twin_id: str,
    source_id: str,
    visibility: str,
    vectors: List[List[float]],
    documents: List[str],
    metadatas: List[Dict[str, Any]],
) -> List[str]:
    """Upserts document chunks tagged point_kind='knowledge' into this twin's
    own collection (created on demand), retrievable by anyone whose tier
    covers `visibility`."""
    collection_name = ensure_twin_collection(twin_id)

    points, point_ids = [], []
    for vector, doc, meta in zip(vectors, documents, metadatas):
        point_id = str(uuid.uuid4())
        payload = {
            "document": doc,
            "point_kind": "knowledge",
            "source_id": source_id,
            "visibility": visibility,
            **meta,
        }
        points.append(models.PointStruct(id=point_id, vector=vector, payload=payload))
        point_ids.append(point_id)

    get_client().upsert(collection_name=collection_name, points=points)
    return point_ids


def upsert_memory_chunks(
    twin_id: str,
    visitor_id: str,
    memory_chunk_id: str,
    vectors: List[List[float]],
    documents: List[str],
) -> List[str]:
    """Upserts summarized memory text tagged point_kind='memory' into this
    twin's own collection, scoped to one visitor via the visitor_id payload
    field. memory_chunk_id links back to the Postgres memory_chunks registry
    row that owns the deletion lifecycle for these points."""
    collection_name = ensure_twin_collection(twin_id)

    points, point_ids = [], []
    for vector, doc in zip(vectors, documents):
        point_id = str(uuid.uuid4())
        payload = {
            "document": doc,
            "point_kind": "memory",
            "visitor_id": visitor_id,
            "memory_chunk_id": memory_chunk_id,
        }
        points.append(models.PointStruct(id=point_id, vector=vector, payload=payload))
        point_ids.append(point_id)

    get_client().upsert(collection_name=collection_name, points=points)
    return point_ids


def delete_source_chunks(twin_id: str, source_id: str) -> None:
    """Deletes all knowledge points belonging to a specific source registry entry."""
    collection_name = ensure_twin_collection(twin_id)
    get_client().delete(
        collection_name=collection_name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[models.FieldCondition(key="source_id", match=models.MatchValue(value=source_id))]
            )
        ),
    )
    print(f"[Qdrant] deleted knowledge points for source_id: {source_id}")


def delete_visitor_memory(twin_id: str, visitor_id: str) -> None:
    """Deletes every memory point for one visitor within this twin's collection
    — backs a visitor's 'forget what you know about me' request."""
    collection_name = ensure_twin_collection(twin_id)
    get_client().delete(
        collection_name=collection_name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[models.FieldCondition(key="visitor_id", match=models.MatchValue(value=visitor_id))]
            )
        ),
    )
    print(f"[Qdrant] deleted memory points for twin_id={twin_id}, visitor_id={visitor_id}")
