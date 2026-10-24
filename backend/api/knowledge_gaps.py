"""
Knowledge gaps API: the owner's inbox of questions the twin couldn't answer,
and the endpoint that closes one by turning the answer into real knowledge.
Owner-only.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user, require_owner
from backend.db.models import User
from backend.db.session import get_db
from backend.services.knowledge_gap_service import KnowledgeGapService

router = APIRouter(prefix="/twins/{twin_id}/knowledge-gaps", tags=["knowledge-gaps"])


class AnswerGapRequest(BaseModel):
    answer_text: str
    visibility: str = "public"


class GapResponse(BaseModel):
    id: str
    twin_id: str
    conversation_id: str
    question_text: str
    status: str
    answer_text: Optional[str] = None
    resulting_source_id: Optional[str] = None

    class Config:
        from_attributes = True


class GapClusterResponse(BaseModel):
    theme: str
    gap_ids: List[str]
    suggested_prompt: str


class CurateRequest(BaseModel):
    gap_ids: List[str]
    raw_answer: str


class CuratedDraftResponse(BaseModel):
    text: str
    suggested_visibility: str
    reasoning: str


class ConfirmClusterRequest(BaseModel):
    gap_ids: List[str]
    text: str
    visibility: str = "public"


@router.get("", response_model=List[GapResponse])
def list_gaps(
    twin_id: str,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    return KnowledgeGapService(db).list_gaps(twin_id, status)


@router.get("/analyze", response_model=List[GapClusterResponse])
def analyze_gaps_endpoint(
    twin_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Gap Analyst agent: clusters pending gaps so the owner can answer
    related questions once instead of one at a time."""
    require_owner(twin_id, current_user, db)
    return KnowledgeGapService(db).analyze_pending(twin_id)


@router.post("/curate", response_model=CuratedDraftResponse)
def curate_answer_endpoint(
    twin_id: str,
    payload: CurateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Curator agent: drafts a cleaned-up version of the owner's raw answer
    plus a suggested visibility tier. Returns a draft only — nothing is
    saved until /confirm is called with the owner-approved text."""
    require_owner(twin_id, current_user, db)
    service = KnowledgeGapService(db)
    gaps = [g for g in service.list_gaps(twin_id) if g.id in payload.gap_ids]
    if not gaps:
        raise HTTPException(status_code=404, detail="No matching knowledge gaps found")
    question_context = "; ".join(g.question_text for g in gaps)
    draft = service.curate_draft(question_context, payload.raw_answer)
    return CuratedDraftResponse(
        text=draft.text, suggested_visibility=draft.suggested_visibility, reasoning=draft.reasoning
    )


@router.post("/confirm", response_model=List[GapResponse])
def confirm_cluster_endpoint(
    twin_id: str,
    payload: ConfirmClusterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Saves the owner-approved text: ingests it as one source and marks
    every gap in the cluster answered."""
    require_owner(twin_id, current_user, db)
    try:
        KnowledgeGapService(db).confirm_cluster_answer(
            twin_id, payload.gap_ids, payload.text, payload.visibility
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return [g for g in KnowledgeGapService(db).list_gaps(twin_id) if g.id in payload.gap_ids]


@router.post("/{gap_id}/answer", response_model=GapResponse)
def answer_gap(
    twin_id: str,
    gap_id: str,
    payload: AnswerGapRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    try:
        return KnowledgeGapService(db).answer_gap(twin_id, gap_id, payload.answer_text, payload.visibility)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{gap_id}/dismiss")
def dismiss_gap(
    twin_id: str,
    gap_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owner(twin_id, current_user, db)
    if not KnowledgeGapService(db).dismiss_gap(twin_id, gap_id):
        raise HTTPException(status_code=404, detail="Knowledge gap not found")
    return {"message": "Dismissed"}
