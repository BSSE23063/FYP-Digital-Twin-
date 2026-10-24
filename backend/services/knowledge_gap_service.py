"""
Knowledge gap service: the owner's side of "the twin asks when it doesn't
know something" (CLAUDE.md §9.1's feedback loop). ConversationService
creates the KnowledgeGap row when the agent escalates (session 8); this is
where it actually gets closed — the owner's answer becomes a new Source,
chunked and embedded through the exact same IngestionPipeline every other
source goes through, so it's answerable next time.
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.agent.curator import CuratedDraft, curate_answer
from backend.agent.gap_analyst import GapCluster, analyze_gaps
from backend.db.models import KnowledgeGap, Source
from backend.ingestion.pipeline import IngestionPipeline


class KnowledgeGapService:
    def __init__(self, db: Session):
        self.db = db
        self.pipeline = IngestionPipeline(db)

    def list_gaps(self, twin_id: str, status: Optional[str] = None) -> List[KnowledgeGap]:
        query = self.db.query(KnowledgeGap).filter(KnowledgeGap.twin_id == twin_id)
        if status:
            query = query.filter(KnowledgeGap.status == status)
        return query.order_by(KnowledgeGap.created_at.desc()).all()

    def answer_gap(
        self, twin_id: str, gap_id: str, answer_text: str, visibility: str = "public"
    ) -> KnowledgeGap:
        gap = (
            self.db.query(KnowledgeGap)
            .filter(KnowledgeGap.id == gap_id, KnowledgeGap.twin_id == twin_id)
            .first()
        )
        if not gap:
            raise ValueError("Knowledge gap not found")
        if gap.status == "answered":
            raise ValueError("This question has already been answered")

        source: Source = self.pipeline.ingest_text(
            twin_id=twin_id,
            name=f"Answer: {gap.question_text[:60]}",
            text=answer_text,
            source_type="escalation_answer",
            visibility=visibility,
        )

        gap.status = "answered"
        gap.answer_text = answer_text
        gap.answered_at = datetime.now(timezone.utc)
        gap.resulting_source_id = source.id
        self.db.commit()
        self.db.refresh(gap)
        return gap

    def analyze_pending(self, twin_id: str) -> List[GapCluster]:
        """Gap Analyst agent: clusters this twin's pending gaps so the owner
        can answer "what's your work background?" once instead of three
        near-duplicate phrasings of it separately."""
        pending = self.list_gaps(twin_id, status="pending")
        return analyze_gaps(pending)

    def curate_draft(self, question_context: str, raw_answer: str) -> CuratedDraft:
        """Curator agent: cleans up the owner's raw answer and suggests a
        visibility tier. Draft only — nothing is written to the database
        here; see confirm_cluster_answer for the actual save."""
        return curate_answer(question_context, raw_answer)

    def confirm_cluster_answer(
        self, twin_id: str, gap_ids: List[str], text: str, visibility: str = "public"
    ) -> Source:
        """The owner-approved save: ingests `text` once (covers every gap in
        the cluster — they were grouped because one answer resolves all of
        them) and marks each listed gap answered, pointing at the same
        resulting source."""
        gaps = (
            self.db.query(KnowledgeGap)
            .filter(KnowledgeGap.id.in_(gap_ids), KnowledgeGap.twin_id == twin_id)
            .all()
        )
        if not gaps:
            raise ValueError("No matching knowledge gaps found")
        already_answered = [g.id for g in gaps if g.status == "answered"]
        if already_answered:
            raise ValueError(f"Already answered: {', '.join(already_answered)}")

        name = f"Answer: {gaps[0].question_text[:60]}" + (f" (+{len(gaps) - 1} more)" if len(gaps) > 1 else "")
        source: Source = self.pipeline.ingest_text(
            twin_id=twin_id,
            name=name,
            text=text,
            source_type="escalation_answer",
            visibility=visibility,
        )

        now = datetime.now(timezone.utc)
        for gap in gaps:
            gap.status = "answered"
            gap.answer_text = text
            gap.answered_at = now
            gap.resulting_source_id = source.id
        self.db.commit()
        return source

    def dismiss_gap(self, twin_id: str, gap_id: str) -> bool:
        gap = (
            self.db.query(KnowledgeGap)
            .filter(KnowledgeGap.id == gap_id, KnowledgeGap.twin_id == twin_id)
            .first()
        )
        if not gap:
            return False
        gap.status = "dismissed"
        self.db.commit()
        return True
