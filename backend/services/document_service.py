"""
Document service for managing document uploads, ingestion, and deletion.
"""

from typing import List, Optional
from sqlalchemy.orm import Session

from backend.db.models import Document
from backend.ingestion.pipeline import IngestionPipeline
from backend.rag.vector_store import get_vector_store


class DocumentService:
    def __init__(self, db: Session):
        self.db = db
        self.pipeline = IngestionPipeline(db)
        self.vector_store = get_vector_store()

    def ingest_file(
        self,
        twin_id: str,
        filename: str,
        file_path: str,
        content_type: str = "pdf",
        visibility: str = "public",
        source_type: str = "upload",
    ) -> Document:
        doc = Document(
            twin_id=twin_id,
            filename=filename,
            content_type=content_type,
            visibility=visibility,
            source_type=source_type,
            ingestion_status="pending",
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)

        # Execute pipeline
        processed = self.pipeline.process_document(
            document_id=doc.id,
            file_path=file_path,
        )
        return processed

    def ingest_raw_text(
        self,
        twin_id: str,
        filename: str,
        text_content: str,
        visibility: str = "public",
        source_type: str = "manual",
    ) -> Document:
        doc = Document(
            twin_id=twin_id,
            filename=filename,
            content_type="txt",
            visibility=visibility,
            source_type=source_type,
            ingestion_status="pending",
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)

        processed = self.pipeline.process_document(
            document_id=doc.id,
            direct_text=text_content,
        )
        return processed

    def list_documents(self, twin_id: str) -> List[Document]:
        return (
            self.db.query(Document)
            .filter(Document.twin_id == twin_id)
            .order_by(Document.created_at.desc())
            .all()
        )

    def delete_document(self, twin_id: str, document_id: str) -> bool:
        doc = (
            self.db.query(Document)
            .filter(Document.id == document_id, Document.twin_id == twin_id)
            .first()
        )
        if not doc:
            return False

        # Clean from ChromaDB
        self.vector_store.delete_by_document(twin_id, document_id)

        # Delete from DB
        self.db.delete(doc)
        self.db.commit()
        return True

