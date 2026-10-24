"""
Ingestion pipeline smoke test.

Covers: text ingestion, file ingestion (.txt and .md, exercising the format
dispatcher in backend/ingestion/parser.py), that ingested content is actually
retrievable from Qdrant afterward, the idempotent-reprocess guarantee (no
duplicate points on a retry), a parse failure, and an oversized-document
rejection.

Not a pytest suite (no test runner, just asserts + prints) — see CLAUDE.md
Phase 5 for converting this into real pytest tests.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from backend.config import settings
from backend.db.session import SessionLocal
from backend.db.models import Source, Twin, User
from backend.ingestion.pipeline import IngestionError, IngestionPipeline
from backend.rag.embeddings import embed_texts
from backend.rag.retriever import search_twin_knowledge
from backend.vectordb.client import get_client
from backend.vectordb.collections import twin_collection_name


def run_test():
    db = SessionLocal()
    try:
        # ── setup: a throwaway owner + twin for this run ──────────
        owner = User(email=f"ingest-test-{uuid.uuid4().hex[:6]}@t2rag.local", display_name="Ingestion Test Owner")
        db.add(owner)
        db.commit()
        db.refresh(owner)

        twin = Twin(
            owner_id=owner.id,
            slug=f"ingest-test-{uuid.uuid4().hex[:6]}",
            name="Ingestion Test Twin",
            domain="Software ingestion testing",
        )
        db.add(twin)
        db.commit()
        db.refresh(twin)
        print(f"[OK] test twin created: {twin.slug}")

        pipeline = IngestionPipeline(db)

        # ── 1. text ingestion ──────────────────────────────────────
        text = (
            "Umair is a final-year student building T2-RAG, a personal digital twin "
            "platform. The twin answers questions about his background, projects, "
            "and schedule, grounded only in what he has actually provided."
        )
        source_text = pipeline.ingest_text(
            twin_id=twin.id, name="bio.txt", text=text, source_type="manual", visibility="public",
        )
        assert source_text.status == "completed"
        assert source_text.chunk_count > 0
        print(f"[OK] text ingestion: {source_text.chunk_count} chunk(s), status={source_text.status}")

        # ── 2. file ingestion: .txt and .md, through parse_document ─
        with tempfile.TemporaryDirectory() as tmp:
            txt_path = Path(tmp) / "notes.txt"
            txt_path.write_text(
                "Umair's preferred working hours are weekday afternoons. "
                "He is most productive after 2pm and avoids early meetings.",
                encoding="utf-8",
            )
            source_txt = pipeline.ingest_file(
                twin_id=twin.id, name="notes.txt", file_path=str(txt_path),
                source_type="upload", visibility="public",
            )
            assert source_txt.status == "completed" and source_txt.chunk_count > 0
            print(f"[OK] .txt file ingestion: {source_txt.chunk_count} chunk(s)")

            md_path = Path(tmp) / "projects.md"
            md_path.write_text(
                "# Projects\n\n## T2-RAG\nA multi-tenant digital twin RAG platform "
                "using FastAPI, PostgreSQL, Qdrant, and Groq.\n",
                encoding="utf-8",
            )
            source_md = pipeline.ingest_file(
                twin_id=twin.id, name="projects.md", file_path=str(md_path),
                source_type="upload", visibility="public",
            )
            assert source_md.status == "completed" and source_md.chunk_count > 0
            print(f"[OK] .md file ingestion: {source_md.chunk_count} chunk(s)")

        # ── 3. ingested content is actually retrievable ─────────────
        query_vector = embed_texts(["What time of day does Umair work best?"])[0]
        results = search_twin_knowledge(
            twin_id=twin.id, query_vector=query_vector, allowed_visibilities=["public"], top_k=3,
        )
        assert any(source_txt.id == r["source_id"] for r in results), "expected the working-hours chunk to be retrievable"
        print(f"[OK] retrieval: {len(results)} knowledge chunk(s) found, including the just-ingested one")

        # ── 4. idempotent reprocessing: no duplicate points on a retry ─
        collection = twin_collection_name(twin.id)
        before = get_client().count(collection_name=collection, exact=True).count
        pipeline._process(source_text, text)  # simulates retrying the same source
        after = get_client().count(collection_name=collection, exact=True).count
        assert before == after, f"reprocessing duplicated points: {before} -> {after}"
        print(f"[OK] idempotent reprocess: point count unchanged ({after})")

        # ── 5. parse failure: nonexistent file ───────────────────────
        try:
            pipeline.ingest_file(
                twin_id=twin.id, name="missing.txt", file_path="/no/such/file.txt", source_type="upload",
            )
            assert False, "expected IngestionError for a missing file"
        except IngestionError:
            failed_sources = db.query(Source).filter(Source.twin_id == twin.id, Source.status == "failed").all()
            assert len(failed_sources) == 1
            print(f"[OK] parse failure handled: Source marked failed, error='{failed_sources[0].error_message[:60]}...'")

        # ── 6. oversized document is rejected before any processing ──
        huge_text = "word " * (settings.MAX_INGEST_CHARS // 4)
        try:
            pipeline.ingest_text(twin_id=twin.id, name="huge.txt", text=huge_text, source_type="manual")
            assert False, "expected IngestionError for an oversized document"
        except IngestionError as e:
            assert "too large" in str(e)
            print(f"[OK] oversized document rejected before chunking: {e}")

        print("\nAll ingestion pipeline checks passed.")

    finally:
        db.close()


if __name__ == "__main__":
    run_test()
