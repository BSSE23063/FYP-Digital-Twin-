"""
One Qdrant collection PER TWIN (the "silo" tenant-isolation model).

Chosen over a shared pool: isolation is physical (a separate collection per
twin), not a payload filter you have to remember to apply on every query. A
new twin's collection is created on first use; it is NEVER shared with any
other twin's data. Within one twin's own collection, points still carry a
point_kind payload field ('knowledge' | 'memory') so a single collection can
serve both the twin's documents and per-visitor memory.
"""
from qdrant_client.http import models

from backend.config import settings
from backend.vectordb.client import get_client


def twin_collection_name(twin_id: str) -> str:
    return f"{settings.QDRANT_COLLECTION_PREFIX}{twin_id}"


def ensure_twin_collection(twin_id: str) -> str:
    """Creates this twin's collection + its payload indexes if missing.
    Idempotent — safe to call before every upsert."""
    client = get_client()
    name = twin_collection_name(twin_id)

    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=settings.EMBEDDING_DIM,
                distance=models.Distance.COSINE,
            ),
        )
        # No twin_id index needed here — every point in THIS collection already
        # belongs to this twin, so it'd be an index on a constant. point_kind
        # and visitor_id are what actually vary within one twin's collection.
        for field in ("point_kind", "visitor_id"):
            client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        print(f"[Qdrant] created collection '{name}' with payload indexes")

    return name


def delete_twin_collection(twin_id: str) -> None:
    """Drops the entire collection when a twin is deleted — the whole point of
    physical isolation is that this is a single clean operation, not a filtered
    bulk-delete."""
    client = get_client()
    name = twin_collection_name(twin_id)
    if client.collection_exists(name):
        client.delete_collection(collection_name=name)
        print(f"[Qdrant] deleted collection '{name}'")
