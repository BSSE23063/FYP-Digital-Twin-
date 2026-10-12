"""
Documents API endpoints for uploading and managing knowledge sources.
"""

from pathlib import Path
from typing import List, Optional
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.services.document_service import DocumentService
from backend.config import settings

router = APIRouter(prefix="/twins/{twin_id}/documents", tags=["documents"])


class TextIngestRequest(BaseModel):
    filename: str
    text_content: str
    visibility: Optional[str] = "public"


class DocumentResponse(BaseModel):
    id: str
    twin_id: str
    filename: str
    content_type: str
    source_type: str
    visibility: str
    ingestion_status: str
    chunk_count: int
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    twin_id: str,
    file: UploadFile = File(...),
    visibility: str = Form("public"),
    db: Session = Depends(get_db),
):
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest_path = upload_dir / f"{twin_id}_{file.filename}"
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    ext = Path(file.filename).suffix.lower().replace(".", "")
    service = DocumentService(db)

    try:
        doc = service.ingest_file(
            twin_id=twin_id,
            filename=file.filename,
            file_path=str(dest_path),
            content_type=ext or "bin",
            visibility=visibility,
            source_type="upload",
        )
        return doc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/text", response_model=DocumentResponse)
def ingest_text(
    twin_id: str,
    payload: TextIngestRequest,
    db: Session = Depends(get_db),
):
    service = DocumentService(db)
    try:
        doc = service.ingest_raw_text(
            twin_id=twin_id,
            filename=payload.filename,
            text_content=payload.text_content,
            visibility=payload.visibility or "public",
            source_type="manual",
        )
        return doc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.get("", response_model=List[DocumentResponse])
def list_documents(twin_id: str, db: Session = Depends(get_db)):
    service = DocumentService(db)
    return service.list_documents(twin_id)


@router.delete("/{document_id}")
def delete_document(twin_id: str, document_id: str, db: Session = Depends(get_db)):
    service = DocumentService(db)
    success = service.delete_document(twin_id, document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document deleted and removed from knowledge base"}

