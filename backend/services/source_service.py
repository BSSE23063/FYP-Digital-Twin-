"""
Source service: a thin wrapper around IngestionPipeline for the API layer —
handles saving an uploaded file to disk before handing it to the pipeline,
and listing/deleting sources. Ingestion correctness itself lives entirely in
backend/ingestion/ (see FLOW.md); this module doesn't duplicate any of it.
"""
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, List, Optional

from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.models import Source
from backend.ingestion.fetchers import FetchError, fetch_github_profile
from backend.ingestion.pipeline import IngestionError, IngestionPipeline
from backend.vectordb.operations import delete_source_chunks
from backend.voice.asr import transcribe_file


class SourceService:
    def __init__(self, db: Session):
        self.db = db
        self.pipeline = IngestionPipeline(db)

    def ingest_upload(
        self, twin_id: str, filename: str, file_obj: IO[bytes], visibility: str = "public"
    ) -> Source:
        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / f"{twin_id}_{filename}"
        with open(dest, "wb") as f:
            shutil.copyfileobj(file_obj, f)

        return self.pipeline.ingest_file(
            twin_id=twin_id,
            name=filename,
            file_path=str(dest),
            source_type="upload",
            visibility=visibility,
        )

    def ingest_text(
        self, twin_id: str, name: str, text: str, visibility: str = "public"
    ) -> Source:
        return self.pipeline.ingest_text(
            twin_id=twin_id,
            name=name,
            text=text,
            source_type="manual",
            visibility=visibility,
        )

    def ingest_voice_note(
        self, twin_id: str, filename: str, file_obj: IO[bytes], visibility: str = "public"
    ) -> tuple[Source, str]:
        """Speak-to-add-knowledge: transcribes a recorded utterance and
        ingests the transcript exactly like a typed note (session 14) — the
        raw audio itself is discarded once transcribed, not kept as a
        MediaAsset (that table is for voice *cloning* reference clips, a
        different downstream consumer — see models.py's MediaAsset
        docstring). Returns (source, transcript) so the caller can show the
        user what was actually captured."""
        suffix = Path(filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            shutil.copyfileobj(file_obj, tmp)
            tmp_path = tmp.name
        try:
            transcript = transcribe_file(tmp_path).strip()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if not transcript:
            raise IngestionError("Couldn't make out any speech in that recording")

        name = f"Voice note — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        source = self.pipeline.ingest_text(
            twin_id=twin_id,
            name=name,
            text=transcript,
            source_type="voice_transcript",
            visibility=visibility,
        )
        return source, transcript

    def ingest_github(self, twin_id: str, username: str, visibility: str = "public") -> Source:
        """Imports a public GitHub profile + repo list as a source — the
        first of the "attach your profile" import paths (session 15); see
        backend/ingestion/fetchers.py for why LinkedIn isn't alongside it."""
        try:
            text = fetch_github_profile(username)
        except FetchError as e:
            raise IngestionError(str(e)) from e

        return self.pipeline.ingest_text(
            twin_id=twin_id,
            name=f"GitHub — @{username.strip().lstrip('@')}",
            text=text,
            source_type="github",
            visibility=visibility,
        )

    def list_sources(self, twin_id: str) -> List[Source]:
        return (
            self.db.query(Source)
            .filter(Source.twin_id == twin_id)
            .order_by(Source.created_at.desc())
            .all()
        )

    def delete_source(self, twin_id: str, source_id: str) -> bool:
        source = (
            self.db.query(Source)
            .filter(Source.id == source_id, Source.twin_id == twin_id)
            .first()
        )
        if not source:
            return False
        delete_source_chunks(twin_id, source_id)
        self.db.delete(source)
        self.db.commit()
        return True
