"""
Qdrant inspection API — lets the owner actually see what's indexed for their
own twins (collection point counts, payloads, text chunks) without needing
any external tooling.

Why this exists instead of pointing a real Qdrant server/dashboard at
qdrant_storage/ (tried first, session 16): QdrantClient(path=...) — the
embedded mode this whole project runs on — is qdrant-client's own pure-Python
`QdrantLocal` implementation (backend/vectordb/client.py), NOT the same
on-disk format the Rust qdrant-server/Docker image writes. Confirmed directly:
mounting qdrant_storage/ into a real `qdrant/qdrant` container made it
initialize a second, empty, differently-named `collections/` directory
alongside the real `collection/` one instead of reading it — not a version
mismatch (client 1.19.1 vs server 1.19.2, functionally the same), a genuinely
different storage engine. No Docker image will ever read this data. These
routes exist because the only thing that CAN read it is this exact
QdrantClient instance already running inside this process — so inspection has
to go through it, not around it.

Owner-scoped throughout: every route either lists only the caller's own
twins or requires ownership of the specific twin_id in the path — this reads
the full, un-redacted content of a twin's knowledge base (including private-
visibility chunks), so it is not something to leave open to an arbitrary
caller just because they know a twin_id.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from qdrant_client.http import models
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, require_owner
from backend.db.models import User
from backend.db.session import get_db
from backend.services.twin_service import TwinService
from backend.vectordb.client import get_client
from backend.vectordb.collections import twin_collection_name

router = APIRouter(prefix="/debug/qdrant", tags=["debug"])


class CollectionSummary(BaseModel):
    twin_id: str
    twin_name: str
    collection_name: str
    exists: bool
    vector_size: Optional[int] = None
    knowledge_points: int = 0
    memory_points: int = 0
    total_points: int = 0


class PointOut(BaseModel):
    id: str
    payload: dict


class PointsPage(BaseModel):
    points: List[PointOut]
    next_offset: Optional[str] = None


@router.get("/twins", response_model=List[CollectionSummary])
def list_my_qdrant_collections(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """One row per twin the caller owns — only their own, never every twin on
    the server, since this exposes full chunk content including private
    material."""
    client = get_client()
    out = []
    for twin in TwinService(db).list_twins(current_user.id):
        name = twin_collection_name(twin.id)
        exists = client.collection_exists(name)
        summary = CollectionSummary(
            twin_id=twin.id, twin_name=twin.name, collection_name=name, exists=exists
        )
        if exists:
            info = client.get_collection(name)
            summary.vector_size = info.config.params.vectors.size
            summary.knowledge_points = client.count(
                name,
                count_filter=models.Filter(
                    must=[models.FieldCondition(key="point_kind", match=models.MatchValue(value="knowledge"))]
                ),
            ).count
            summary.memory_points = client.count(
                name,
                count_filter=models.Filter(
                    must=[models.FieldCondition(key="point_kind", match=models.MatchValue(value="memory"))]
                ),
            ).count
            summary.total_points = summary.knowledge_points + summary.memory_points
        out.append(summary)
    return out


@router.get("/twins/{twin_id}/points", response_model=PointsPage)
def list_twin_points(
    twin_id: str,
    point_kind: Optional[str] = None,
    limit: int = 50,
    offset: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated raw points (payload only, no vectors — the 384 floats aren't
    visually useful; the payload text/metadata is the actually inspectable
    part) for one twin's collection. `offset` is Qdrant's own opaque scroll
    cursor (a point id), not a page number."""
    require_owner(twin_id, current_user, db)
    client = get_client()
    name = twin_collection_name(twin_id)
    if not client.collection_exists(name):
        return PointsPage(points=[], next_offset=None)

    scroll_filter = None
    if point_kind:
        scroll_filter = models.Filter(
            must=[models.FieldCondition(key="point_kind", match=models.MatchValue(value=point_kind))]
        )

    records, next_page = client.scroll(
        collection_name=name,
        scroll_filter=scroll_filter,
        limit=min(limit, 200),
        offset=offset,
        with_payload=True,
        with_vectors=False,
    )
    return PointsPage(
        points=[PointOut(id=str(r.id), payload=r.payload or {}) for r in records],
        next_offset=str(next_page) if next_page is not None else None,
    )
