"""
Ingestion orchestrator: parse -> chunk+embed -> upsert to Qdrant -> update Source.

This is the one place that keeps a Source row (Postgres) and its knowledge
points (Qdrant) in sync — nothing else in the codebase is allowed to write
knowledge chunks directly. Postgres and Qdrant are two separate systems with
no shared transaction, so correctness here comes from careful ordering, not
a two-phase commit:

  1. Create the Source row as 'processing' (cheap, Postgres-only, commits
     immediately so the row exists even if everything after this fails).
  2. Do the expensive work (parse, chunk, embed) with nothing yet written to
     Qdrant.
  3. Delete any pre-existing points for this source_id, THEN upsert the new
     ones. This makes ingestion idempotent: retrying a failed attempt (or
     re-processing the same source_id for any reason) can never leave
     duplicate or stale chunks behind, because old ones are always cleared
     first.
  4. Only mark the Source 'completed' after the Qdrant write succeeds.

If anything fails between steps 2 and 4, the except handler best-effort
deletes any points this attempt may have already written (so a failed
ingestion never leaves half-indexed chunks silently poisoning retrieval),
then marks the Source 'failed' with the error recorded on the row.
"""
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.models import Source
from backend.ingestion.parser import parse_document
from backend.rag.embeddings import process_document
from backend.vectordb.operations import delete_source_chunks, upsert_knowledge_chunks


class IngestionError(Exception):
    """Raised after the Source row has already been marked 'failed' with the
    same message — callers can catch this instead of re-deriving the error
    from the Source row's state."""


class IngestionPipeline:
    def __init__(self, db: Session):
        self.db = db

    def ingest_file(
        self,
        twin_id: str,
        name: str,
        file_path: str,
        source_type: str = "upload",
        visibility: str = "public",
        media_asset_id: Optional[str] = None,
    ) -> Source:
        """Parses a file on disk, then runs the shared chunk/embed/upsert path."""
        source = self._create_source(
            twin_id, name, source_type, visibility, media_asset_id,
            storage_path=str(file_path),
        )
        try:
            raw_text = parse_document(file_path)
        except Exception as e:
            self._fail(source, f"parse error: {e}")
            raise IngestionError(str(e)) from e
        return self._process(source, raw_text)

    def ingest_text(
        self,
        twin_id: str,
        name: str,
        text: str,
        source_type: str = "manual",
        visibility: str = "public",
        media_asset_id: Optional[str] = None,
    ) -> Source:
        """Ingests raw text directly — manual notes, escalation answers, or
        (once built) ASR transcripts and fetched profile text all funnel
        through here, since by the time it's text, the origin doesn't matter."""
        source = self._create_source(
            twin_id, name, source_type, visibility, media_asset_id,
            storage_path=None,
        )
        return self._process(source, text)

    # ── internals ──────────────────────────────────────────────

    def _create_source(
        self,
        twin_id: str,
        name: str,
        source_type: str,
        visibility: str,
        media_asset_id: Optional[str],
        storage_path: Optional[str],
    ) -> Source:
        source = Source(
            twin_id=twin_id,
            media_asset_id=media_asset_id,
            source_type=source_type,
            name=name,
            visibility=visibility,
            status="processing",
            storage_path=storage_path,
        )
        self.db.add(source)
        self.db.commit()
        self.db.refresh(source)
        return source

    def _process(self, source: Source, raw_text: str) -> Source:
        raw_text = (raw_text or "").strip()

        if not raw_text:
            source.status = "completed"
            source.chunk_count = 0
            source.error_message = None
            self.db.commit()
            return source

        if len(raw_text) > settings.MAX_INGEST_CHARS:
            message = f"document too large: {len(raw_text)} chars > {settings.MAX_INGEST_CHARS} limit"
            self._fail(source, message)
            raise IngestionError(message)

        try:
            processed = process_document(raw_text)
            chunks = processed["chunks"]
            offsets = processed["offsets"]
            embeddings = processed["embeddings"]

            # Idempotent: always clear this source's existing points before
            # writing new ones (see module docstring).
            delete_source_chunks(source.twin_id, source.id)

            metadatas = [
                {"chunk_index": i, "char_start": start, "char_end": end}
                for i, (start, end) in enumerate(offsets)
            ]
            upsert_knowledge_chunks(
                twin_id=source.twin_id,
                source_id=source.id,
                visibility=source.visibility,
                vectors=embeddings,
                documents=chunks,
                metadatas=metadatas,
            )

            source.status = "completed"
            source.chunk_count = len(chunks)
            source.error_message = None
            self.db.commit()
            return source

        except Exception as e:
            try:
                delete_source_chunks(source.twin_id, source.id)
            except Exception:
                pass  # best-effort cleanup; the Source row still gets marked failed below
            self._fail(source, str(e))
            raise IngestionError(str(e)) from e

    def _fail(self, source: Source, message: str) -> None:
        self.db.rollback()
        failed = self.db.get(Source, source.id)
        if failed is not None:
            failed.status = "failed"
            failed.error_message = message
            self.db.commit()
