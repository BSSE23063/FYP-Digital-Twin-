"""
Sources API: upload a file, ingest raw text, list, delete.

All owner-only now — managing a twin's knowledge is an owner action, not
something any caller should be able to do just by knowing a twin_id.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, require_owner
from backend.db.models import User
from backend.db.session import get_db
from backend.ingestion.pipeline import IngestionError
from backend.services.source_service import SourceService

router = APIRouter(prefix="/twins/{twin_id}/sources", tags=["sources"])


class TextIngestRequest(BaseModel):
    name: str
    text: str
    visibility: str = "public"


class GithubIngestRequest(BaseModel):
    username: str
    visibility: str = "public"


class SourceResponse(BaseModel):
    id: str
    twin_id: str
    source_type: str
    name: str
    visibility: str
    status: str
    chunk_count: int
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class VoiceNoteResponse(BaseModel):
    source: SourceResponse
    transcript: str


@router.post("/upload", response_model=SourceResponse)
def upload_source(
    twin_id: str,
    file: UploadFile = File(...),
    visibility: str = Form("public"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    # Plain (non-async) def: ingestion is CPU-bound (parsing + embedding, no
    # GPU anywhere in this project — see CLAUDE.md §9.2), so FastAPI runs this
    # in its threadpool instead of blocking the single event loop.
    try:
        return SourceService(db).ingest_upload(twin_id, file.filename, file.file, visibility)
    except IngestionError as e:
        raise HTTPException(status_code=422, detail=f"Ingestion failed: {e}")


@router.post("/text", response_model=SourceResponse)
def ingest_text(
    twin_id: str,
    payload: TextIngestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    try:
        return SourceService(db).ingest_text(twin_id, payload.name, payload.text, payload.visibility)
    except IngestionError as e:
        raise HTTPException(status_code=422, detail=f"Ingestion failed: {e}")


@router.post("/github", response_model=SourceResponse)
def ingest_github(
    twin_id: str,
    payload: GithubIngestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import a public GitHub profile + repo list as a source."""
    require_owner(twin_id, current_user, db)
    try:
        return SourceService(db).ingest_github(twin_id, payload.username, payload.visibility)
    except IngestionError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/voice-note", response_model=VoiceNoteResponse)
def ingest_voice_note(
    twin_id: str,
    audio: UploadFile = File(...),
    visibility: str = Form("public"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Speak-to-add-knowledge: record, transcribe, ingest as a source — the
    voice-input alternative to typing a note (session 14)."""
    require_owner(twin_id, current_user, db)
    try:
        source, transcript = SourceService(db).ingest_voice_note(
            twin_id, audio.filename or "note.webm", audio.file, visibility
        )
        return VoiceNoteResponse(source=source, transcript=transcript)
    except IngestionError as e:
        raise HTTPException(status_code=422, detail=f"Ingestion failed: {e}")


@router.get("", response_model=List[SourceResponse])
def list_sources(
    twin_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    return SourceService(db).list_sources(twin_id)


@router.delete("/{source_id}")
def delete_source(
    twin_id: str,
    source_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    if not SourceService(db).delete_source(twin_id, source_id):
        raise HTTPException(status_code=404, detail="Source not found")
    return {"message": "Source deleted"}
