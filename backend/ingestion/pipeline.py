"""
Ingestion Pipeline orchestrator.
Handles Parse -> Chunk -> DB persist -> Embed -> ChromaDB index.
"""

from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session

from backend.db.models import Document, DocumentChunk
from backend.ingestion.parser import parse_document
from backend.ingestion.chunker import FixedTokenChunker
from backend.rag.embeddings import get_embedding_provider
from backend.rag.vector_store import get_vector_store
from backend.config import settings


class IngestionPipeline:
    def __init__(self, db: Session):
        self.db = db
        self.chunker = FixedTokenChunker(
            target_chunk_size=settings.CHUNK_SIZE,
            overlap=settings.CHUNK_OVERLAP,
        )
        self.embedding_provider = get_embedding_provider()
        self.vector_store = get_vector_store()

    def process_document(
        self,
        document_id: str,
        file_path: Optional[str] = None,
        direct_text: Optional[str] = None,
    ) -> Document:
        """
        Executes end-to-end ingestion for a Document record.
        """
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document {document_id} not found in database.")

        try:
            doc.ingestion_status = "processing"
            self.db.commit()

            # 1. Parse / Extract text
            if direct_text:
                raw_text = direct_text.strip()
            elif file_path:
                raw_text = parse_document(file_path)
            else:
                raise ValueError("Neither file_path nor direct_text provided.")

            doc.raw_text = raw_text

            if not raw_text:
                doc.ingestion_status = "completed"
                doc.chunk_count = 0
                self.db.commit()
                return doc

            # 2. Chunking
            chunks = self.chunker.chunk_text(raw_text)

            # 3. Create DB records
            chunk_records = []
            texts_to_embed = []
            chunk_ids = []

            import uuid
            for c in chunks:
                chunk_id = str(uuid.uuid4())
                chunk_rec = DocumentChunk(
                    id=chunk_id,
                    document_id=doc.id,
                    twin_id=doc.twin_id,
                    chunk_index=c.chunk_index,
                    content=c.content,
                    visibility=doc.visibility,
                    char_start=c.char_start,
                    char_end=c.char_end,
                    heading_path=c.heading_path,
                    chromadb_id=chunk_id,
                )
                self.db.add(chunk_rec)
                chunk_records.append(chunk_rec)

                texts_to_embed.append(c.content)
                chunk_ids.append(chunk_id)

            self.db.flush()  # assign IDs

            # 4. Generate Embeddings
            embeddings = self.embedding_provider.embed_documents(texts_to_embed)

            # 5. Index into ChromaDB
            self.vector_store.add_chunks(
                chunk_ids=chunk_ids,
                twin_id=doc.twin_id,
                texts=texts_to_embed,
                doc_id=doc.id,
                source_type=doc.source_type,
                visibility=doc.visibility,
                chunk_indices=[c.chunk_index for c in chunks],
                embeddings=embeddings,
            )

            # 6. Update document record
            doc.ingestion_status = "completed"
            doc.chunk_count = len(chunks)
            doc.error_message = None
            self.db.commit()
            return doc

        except Exception as e:
            self.db.rollback()
            # Update failed status in fresh transaction
            doc_failed = self.db.query(Document).filter(Document.id == document_id).first()
            if doc_failed:
                doc_failed.ingestion_status = "failed"
                doc_failed.error_message = str(e)
                self.db.commit()
            raise e

